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

/**
 * "photo", "placeholder" (the store's stand-in image), "illustration" (a picture that isn't the
 * product's own), "none" or "broken" for a product's image area. The store marks a product's own
 * photo from Commerce with data-commerce-image.
 */
async function photo(media) {
  const img = media.locator("img[data-commerce-image]").first();
  if (!await img.count()) return await media.locator("img").count() ? "illustration" : "none";
  // Product photos load lazily, so bring each into view first.
  await img.scrollIntoViewIfNeeded(quick).catch(() => {});
  const loaded = await expect.poll(() => img.evaluate(el => el.complete && el.naturalWidth > 0), { timeout: 15_000 }).toBe(true).then(() => true, () => false);
  if (!loaded) return "broken";
  return await img.getAttribute("data-placeholder") === "true" ? "placeholder" : "photo";
}

const photoProblem = {
  placeholder: "has no photo of its own (the store shows its placeholder)",
  illustration: "shows a stand-in drawing instead of its photo",
  none: 'has no photo ("No image")',
  broken: "has a photo that didn't load",
};

const short = (items, count = 5) => items.length > count ? [...items.slice(0, count), `${items.length - count} more`] : items;
const products = count => `${count} product${count === 1 ? "" : "s"}`;
const text = async (locator) => (await locator.first().innerText(quick).catch(() => "")).replace(/\s+/g, " ").trim();
// Pages are fully loaded when read, so a missing link is absent now rather than worth waiting for.
const firstHref = async (locator) => await locator.count() ? locator.first().getAttribute("href") : null;

/** Each product card's name, price and photo, and the product page it links to. */
async function readCards(cards) {
  const listed = [];
  const problems = [];
  const links = [];
  for (const card of await cards.all()) {
    const name = await text(card.locator("h2, h3, h4"));
    const price = await text(card.locator(".price, [data-product-price]"));
    const image = await photo(card);
    const label = name || `product ${listed.length + 1}`;
    if (!name) problems.push(`${label} has no name`);
    if (!/\$\s?\d/.test(price)) problems.push(`"${label}" shows no price`);
    if (image !== "photo") problems.push(`"${label}" ${photoProblem[image]}`);
    listed.push(`${label} ${price}`.trim());
    const href = await card.getAttribute("href") ?? await firstHref(card.locator('a[href^="/products/"]'));
    if (href) links.push(href);
  }
  return { listed, problems, links };
}

/** The product pages among `links` that don't answer HTTP 200. */
async function brokenLinks(page, links) {
  const broken = [];
  for (const href of new Set(links)) {
    const response = await page.request.get(new URL(href, config.store).href);
    if (response.status() !== 200) broken.push(`${href} answered HTTP ${response.status()}`);
  }
  return broken;
}

// A new shopper's first look: the homepage, the product list, a product page and its category.
test("Storefront", { tag: "@next" }, journey(async () => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const page = await shopperPage();
  // Each page's visible text, for the last step's check of what it says about buying.
  const seen = [];
  let links = [];
  let category = null;
  // Every step is soft: the checks don't depend on each other, so one finding never hides the next.
  const soft = { soft: true };
  try {
    await step(page, "The homepage loads with no developer notices", async () => {
      await open(page, "/");
      seen.push({ where: "the homepage", text: await page.locator("body").innerText() });
      category = await firstHref(page.locator('a[href^="/categories/"]'));
      const notices = await developerNotices(page);
      if (notices.length) throw new Error(`The homepage shows: ${notices.map(notice => `"${notice}"`).join("; ")}.`);
      return `"${await page.title()}" with no developer notices`;
    }, soft);

    await step(page, "The product list shows each product's name, price and photo", async () => {
      const catalog = page.locator("[data-commerce-catalog]");
      if (!await catalog.count()) throw new Error("The homepage has no Shop product list.");
      const cards = catalog.locator("[data-commerce-product]");
      if (!await cards.count()) throw new Error(`The Shop list shows no products: "${await text(catalog)}".`);
      const found = await readCards(cards);
      links = found.links;
      note("products listed", found.listed.length);
      if (found.problems.length) throw new Error(`${short(found.problems).join("; ")}.`);
      return `${products(found.listed.length)}: ${short(found.listed).join(", ")}`;
    }, soft);

    await step(page, "Every product in the list opens its own page", async () => {
      if (!links.length) throw new Error("No product in the Shop list links to a product page.");
      const broken = await brokenLinks(page, links);
      if (broken.length) throw new Error(`${short(broken).join("; ")}.`);
      return `${links.length} product page${links.length === 1 ? "" : "s"} answered HTTP 200`;
    }, soft);

    await step(page, "The product page shows the name, price and photo and offers Add to cart", async () => {
      const path = config.productPath || links[0];
      if (!path) throw new Error("No product page to open; set DINKUS_E2E_PRODUCT_PATH.");
      await open(page, path);
      seen.push({ where: path, text: await page.locator("body").innerText() });
      // The product's own category comes first for the category step.
      category = await firstHref(page.locator('.browse-breadcrumb a[href^="/categories/"]')) ?? category;
      const notices = await developerNotices(page);
      if (notices.length) throw new Error(`${path} shows: ${notices.map(notice => `"${notice}"`).join("; ")}.`);
      const product = page.locator("[data-product-page]");
      if (!await product.count()) throw new Error(`${path} shows no product.`);
      const name = await text(product.locator("h1"));
      const price = await text(product.locator("[data-product-price]"));
      const image = await photo(product.locator(".product-detail__visual"));
      const problems = [];
      if (!name) problems.push("no name");
      if (!/\$\s?\d/.test(price)) problems.push("no price");
      if (image !== "photo") problems.push(`the product ${photoProblem[image]}`);
      const add = page.locator('[data-add-to-cart][data-guest-cart-ready="1"]').first();
      if (!await add.waitFor({ timeout: 15_000 }).then(() => true, () => false)) problems.push("no working Add to cart button");
      if (problems.length) throw new Error(`${path} has ${problems.join(", ")}.`);
      return `"${name}" ${price} with its photo and Add to cart`;
    }, soft);

    const categoryStep = "A category page lists its products with name, price and photo";
    if (!category) {
      record(categoryStep, "SKIP", "neither the product page nor the homepage links a category page");
    } else await step(page, categoryStep, async () => {
      await open(page, category);
      seen.push({ where: category, text: await page.locator("body").innerText() });
      const notices = await developerNotices(page);
      if (notices.length) throw new Error(`${category} shows: ${notices.map(notice => `"${notice}"`).join("; ")}.`);
      const cards = page.locator("main").locator("[data-commerce-product], [data-merch-item]");
      if (!await cards.count()) throw new Error(`${category} lists no products: "${await text(page.locator("main"))}".`);
      const found = await readCards(cards);
      const problems = [...found.problems];
      if (found.links.length < found.listed.length) problems.push(`${products(found.listed.length - found.links.length)} link to no product page`);
      problems.push(...await brokenLinks(page, found.links));
      if (problems.length) throw new Error(`${category}: ${short(problems).join("; ")}.`);
      return `${category} lists ${products(found.listed.length)}: ${short(found.listed).join(", ")}`;
    }, soft);

    // The cart says whether this store takes checkouts; only then is "checkout is unavailable" wrong.
    const cart = "No page says checkout is unavailable while the cart offers it";
    await open(page, "/cart").catch(() => {});
    const admitted = await page.locator("[data-guest-cart]").first().getAttribute("data-guest-checkout-admitted", quick).catch(() => null);
    if (admitted !== "true") {
      record(cart, "SKIP", admitted === "false" ? "the cart offers no checkout on this store, so saying so is true" : "the cart page didn't say whether checkout is open");
    } else await step(page, cart, async () => {
      const claims = seen.flatMap(({ where, text: words }) => cantBuyClaims(words).map(claim => `${where} says "${claim}"`));
      if (claims.length) throw new Error(`The cart offers checkout, but ${short(claims, 8).join("; ")}.`);
      return `checked ${seen.map(({ where }) => where).join(", ")}`;
    }, soft);
  } finally {
    await page.context().browser().close();
  }
}, { profile: false }));
