import { test, expect, shopperPage } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { note, record } from "../support/proof.mjs";
import { journey, step } from "../support/steps.mjs";
import { cantBuyClaims } from "../support/storefront-text.mjs";

const quick = { timeout: 5_000 };

/** Opens a store page; anything but HTTP 200 fails the step that opened it. */
async function open(page, path) {
  const response = await page.goto(new URL(path, config.store).href);
  if (response?.status() !== 200) throw new Error(`${path} answered HTTP ${response?.status() ?? "nothing"}.`);
}

/** The visible error boxes a shopper would see: a missing home page, unknown content blocks, alerts. */
async function developerNotices(page) {
  return page.locator('[data-content-missing], [data-emdash-missing-block], .store-error, [role="alert"]').evaluateAll(boxes => [
    ...new Set(boxes.filter(box => box.getClientRects().length && getComputedStyle(box).visibility !== "hidden")
      .map(box => box.innerText.split(/\n+/).map(line => line.trim()).filter(Boolean).join(" / ")).filter(Boolean)),
  ]);
}

/** "photo", "placeholder" (the store's stand-in image), "none" or "broken" for a product's image area. */
async function photo(media) {
  const img = media.locator("img").first();
  if (!await img.count()) return "none";
  // Product photos load lazily, so bring each into view first.
  await img.scrollIntoViewIfNeeded(quick).catch(() => {});
  const loaded = await expect.poll(() => img.evaluate(el => el.complete && el.naturalWidth > 0), { timeout: 15_000 }).toBe(true).then(() => true, () => false);
  if (!loaded) return "broken";
  return await img.getAttribute("data-placeholder") === "true" ? "placeholder" : "photo";
}

const photoProblem = {
  placeholder: "has no photo of its own (the store shows its placeholder)",
  none: 'has no photo ("No image")',
  broken: "has a photo that didn't load",
};

const short = (items, count = 5) => items.length > count ? [...items.slice(0, count), `${items.length - count} more`] : items;

// A new shopper's first look: the homepage, the product list and a product page.
test("Storefront", { tag: "@next" }, journey(async () => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const page = await shopperPage();
  // Each page's visible text, for the last step's check of what it says about buying.
  const seen = [];
  const links = [];
  let category = null;
  // Every step is soft: the checks don't depend on each other, so one finding never hides the next.
  const soft = { soft: true };
  try {
    await step(page, "The homepage loads with no developer notices", async () => {
      await open(page, "/");
      seen.push({ where: "the homepage", text: await page.locator("body").innerText() });
      const notices = await developerNotices(page);
      if (notices.length) throw new Error(`The homepage shows: ${notices.map(text => `"${text}"`).join("; ")}.`);
      return `"${await page.title()}" with no developer notices`;
    }, soft);

    await step(page, "The product list shows each product's name, price and photo", async () => {
      const catalog = page.locator("[data-commerce-catalog]");
      if (!await catalog.count()) throw new Error("The homepage has no Shop product list.");
      const cards = catalog.locator("[data-commerce-product]");
      if (!await cards.count()) throw new Error(`The Shop list shows no products: "${(await catalog.innerText(quick)).replace(/\s+/g, " ").trim()}".`);
      const products = [];
      const problems = [];
      for (const card of await cards.all()) {
        const name = (await card.locator("h3").first().innerText(quick).catch(() => "")).trim();
        const price = (await card.locator(".price").first().innerText(quick).catch(() => "")).replace(/\s+/g, " ").trim();
        const image = await photo(card.locator(".commerce-product-media"));
        const label = name || `product ${products.length + 1}`;
        if (!name) problems.push(`${label} has no name`);
        if (!/\$\s?\d/.test(price)) problems.push(`"${label}" shows no price`);
        if (image !== "photo") problems.push(`"${label}" ${photoProblem[image]}`);
        products.push(`${label} ${price}`);
        const href = await card.getAttribute("href");
        if (href) links.push(href);
      }
      note("products listed", products.length);
      if (problems.length) throw new Error(`${short(problems).join("; ")}.`);
      return `${products.length} products: ${short(products).join(", ")}`;
    }, soft);

    await step(page, "Every product in the list opens its own page", async () => {
      if (!links.length) throw new Error("No product in the Shop list links to a product page.");
      const broken = [];
      for (const href of links) {
        const response = await page.request.get(new URL(href, config.store).href);
        if (response.status() !== 200) broken.push(`${href} answered HTTP ${response.status()}`);
      }
      if (broken.length) throw new Error(`${short(broken).join("; ")}.`);
      return `${links.length} product pages answered HTTP 200`;
    }, soft);

    await step(page, "The product page shows the name, price and photo and offers Add to cart", async () => {
      const path = config.productPath || links[0];
      if (!path) throw new Error("No product page to open; set DINKUS_E2E_PRODUCT_PATH.");
      await open(page, path);
      seen.push({ where: path, text: await page.locator("body").innerText() });
      const notices = await developerNotices(page);
      if (notices.length) throw new Error(`${path} shows: ${notices.map(text => `"${text}"`).join("; ")}.`);
      const product = page.locator("[data-product-page]");
      if (!await product.count()) throw new Error(`${path} shows no product.`);
      const name = (await product.locator("h1").first().innerText(quick).catch(() => "")).trim();
      const price = (await product.locator("[data-product-price]").first().innerText(quick).catch(() => "")).replace(/\s+/g, " ").trim();
      const image = await photo(product.locator(".product-detail__visual"));
      const problems = [];
      if (!name) problems.push("no name");
      if (!/\$\s?\d/.test(price)) problems.push("no price");
      if (image !== "photo") problems.push(`the product ${photoProblem[image]}`);
      const add = page.locator('[data-add-to-cart][data-guest-cart-ready="1"]').first();
      if (!await add.waitFor({ timeout: 15_000 }).then(() => true, () => false)) problems.push("no working Add to cart button");
      category = await page.locator('.browse-breadcrumb a[href^="/categories/"]').first().getAttribute("href", quick).catch(() => null);
      if (problems.length) throw new Error(`${path} has ${problems.join(", ")}.`);
      return `"${name}" ${price} with its photo and Add to cart`;
    }, soft);

    // The cart says whether this store takes checkouts; only then is "checkout is unavailable" wrong.
    const cart = "No page says checkout is unavailable while the cart offers it";
    await open(page, "/cart").catch(() => {});
    const admitted = await page.locator("[data-guest-cart]").first().getAttribute("data-guest-checkout-admitted", quick).catch(() => null);
    if (admitted !== "true") {
      record(cart, "SKIP", admitted === "false" ? "the cart offers no checkout on this store, so saying so is true" : "the cart page didn't say whether checkout is open");
    } else await step(page, cart, async () => {
      // The product's category page carries the same banner as the others.
      if (category) await open(page, category).then(async () => seen.push({ where: category, text: await page.locator("body").innerText() }), () => {});
      const claims = seen.flatMap(({ where, text }) => cantBuyClaims(text).map(claim => `${where} says "${claim}"`));
      if (claims.length) throw new Error(`The cart offers checkout, but ${short(claims, 8).join("; ")}.`);
      return `checked ${seen.map(({ where }) => where).join(", ")}`;
    }, soft);
  } finally {
    await page.context().browser().close();
  }
}, { profile: false }));
