import { test, expect, shopperPage } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { note, record } from "../support/proof.mjs";
import { STORE_OPENS, elsewhere, openShopperPage as open, storeOpens } from "../support/shopper.mjs";
import { journey, step } from "../support/steps.mjs";
import { cantBuyClaims } from "../support/storefront-text.mjs";

const quick = { timeout: 5_000 };

/** The visible error boxes a shopper would see: a missing home page, unknown content blocks, alerts. */
async function developerNotices(page) {
  return page.locator('[data-content-missing], [data-emdash-missing-block], .store-error, [role="alert"]').evaluateAll(boxes => [
    ...new Set(boxes.filter(box => box.getClientRects().length && getComputedStyle(box).visibility !== "hidden")
      .map(box => box.innerText.split(/\n+/).map(line => line.trim()).filter(Boolean).join(" / ")).filter(Boolean)),
  ]);
}

/**
 * "photo", "placeholder" (the store's stand-in image), "illustration" (a picture that isn't the
 * product's own), "none", "broken" or "hidden" for a product's image area. The store marks a product's own
 * photo from Commerce with data-commerce-image.
 */
async function photo(media) {
  const img = media.locator("img[data-commerce-image]").first();
  if (!await img.count()) return await media.locator("img").count() ? "illustration" : "none";
  // Product photos load lazily, so bring each into view first.
  await img.scrollIntoViewIfNeeded(quick).catch(() => {});
  const loaded = await expect.poll(() => img.evaluate(el => el.complete && el.naturalWidth > 0), { timeout: 15_000 }).toBe(true).then(() => true, () => false);
  if (!loaded) return "broken";
  // A photo the page's styles hide is no photo to a shopper.
  if (!await img.isVisible()) return "hidden";
  return await img.getAttribute("data-placeholder") === "true" ? "placeholder" : "photo";
}

const photoProblem = {
  placeholder: "has no photo of its own (the store shows its placeholder)",
  illustration: "shows a stand-in drawing instead of its photo",
  none: 'has no photo ("No image")',
  broken: "has a photo that didn't load",
  hidden: "has a photo shoppers can't see (the page hides it)",
};

/** A page's developer notices as one finding, so they're listed with the page's other findings. */
const shows = notices => notices.length ? [`shows ${notices.map(notice => `"${notice}"`).join(", ")}`] : [];

// Passing summaries name the first few products; a failure names every finding.
const short = (items, count = 5) => items.length > count ? [...items.slice(0, count), `${items.length - count} more`] : items;
const products = count => `${count} product${count === 1 ? "" : "s"}`;
const unlinked = count => `${products(count)} link${count === 1 ? "s" : ""} to no product page`;
// innerText also reads an element the page hides, so only the first one a shopper can see counts.
const text = async (locator) => (await locator.filter({ visible: true }).first().innerText(quick).catch(() => "")).replace(/\s+/g, " ").trim();
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

/** The product pages among `links` that don't answer HTTP 200 on the store. */
async function brokenLinks(page, links) {
  const broken = [];
  for (const href of new Set(links)) {
    // A link that gets no answer at all is a finding too, and the rest are still checked.
    const response = await page.request.get(new URL(href, config.store).href).catch(error => error);
    if (response instanceof Error) broken.push(`${href} didn't answer (${response.message.split("\n")[0]})`);
    else if (new URL(response.url()).origin !== config.store) broken.push(`${href} sent the shopper to ${elsewhere(response.url())}`);
    else if (response.status() !== 200) broken.push(`${href} answered HTTP ${response.status()}`);
  }
  return broken;
}

// A new shopper's first look: the homepage, the product list, a product page and its category.
test("Storefront", { tag: "@next" }, journey(async () => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const page = await shopperPage();
  // Each page's visible text, for the last step's check of what it says about buying.
  const seen = [];
  // The Shop list's products and the product pages they link to.
  let shop = { listed: [], links: [] };
  let category = null;
  // After the first step every step is soft: the checks don't depend on each other, so one finding never hides the next.
  const soft = { soft: true };
  try {
    // A store nobody can open has nothing else to check, so this step alone stops the journey.
    await step(page, STORE_OPENS, () => storeOpens(page));

    await step(page, "The homepage shows no developer notices", async () => {
      seen.push({ where: "the homepage", text: await page.locator("body").innerText() });
      category = await firstHref(page.locator('a[href^="/categories/"]'));
      const notices = await developerNotices(page);
      if (notices.length) throw new Error(`The homepage shows: ${notices.map(notice => `"${notice}"`).join("; ")}.`);
      return "no developer notices";
    }, soft);

    await step(page, "The product list shows each product's name, price and photo", async () => {
      const catalog = page.locator("[data-commerce-catalog]");
      if (!await catalog.count()) throw new Error("The homepage has no Shop product list.");
      const cards = catalog.locator("[data-commerce-product]");
      if (!await cards.count()) throw new Error(`The Shop list shows no products: "${await text(catalog)}".`);
      const found = await readCards(cards);
      shop = found;
      note("products listed", found.listed.length);
      if (found.problems.length) throw new Error(`${found.problems.join("; ")}.`);
      return `${products(found.listed.length)}: ${short(found.listed).join(", ")}`;
    }, soft);

    await step(page, "Every product in the list opens its own page", async () => {
      if (!shop.listed.length) throw new Error("The Shop list showed no products to open.");
      const problems = [];
      if (shop.links.length < shop.listed.length) problems.push(unlinked(shop.listed.length - shop.links.length));
      problems.push(...await brokenLinks(page, shop.links));
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return `${shop.links.length} product page${shop.links.length === 1 ? "" : "s"} answered HTTP 200`;
    }, soft);

    await step(page, "The product page shows the name, price and photo and offers Add to cart", async () => {
      const path = config.productPath || shop.links[0];
      if (!path) throw new Error("No product page to open; set DINKUS_E2E_PRODUCT_PATH.");
      await open(page, path);
      seen.push({ where: path, text: await page.locator("body").innerText() });
      // The product's own category comes first for the category step.
      category = await firstHref(page.locator('.browse-breadcrumb a[href^="/categories/"]')) ?? category;
      const problems = shows(await developerNotices(page));
      const product = page.locator("[data-product-page]");
      if (!await product.count()) throw new Error(`${path}: ${[...problems, "shows no product"].join("; ")}.`);
      const name = await text(product.locator("h1"));
      const price = await text(product.locator("[data-product-price]"));
      const image = await photo(product.locator(".product-detail__visual"));
      if (!name) problems.push("no name");
      if (!/\$\s?\d/.test(price)) problems.push("no price");
      if (image !== "photo") problems.push(`the product ${photoProblem[image]}`);
      // Ready means wired to the cart and pressable; the journey never presses it.
      const add = page.locator('[data-add-to-cart][data-guest-cart-ready="1"]').first();
      if (!await add.waitFor({ timeout: 15_000 }).then(() => true, () => false)) problems.push("no working Add to cart button");
      else if (!await expect(add).toBeEnabled(quick).then(() => true, () => false)) problems.push("an Add to cart button shoppers can't press");
      if (problems.length) throw new Error(`${path}: ${problems.join("; ")}.`);
      return `"${name}" ${price} with its photo and Add to cart`;
    }, soft);

    const categoryStep = "A category page lists its products with name, price and photo";
    if (!category) {
      record(categoryStep, "SKIP", "neither the product page nor the homepage links a category page");
    } else await step(page, categoryStep, async () => {
      await open(page, category);
      seen.push({ where: category, text: await page.locator("body").innerText() });
      const problems = shows(await developerNotices(page));
      const cards = page.locator("main").locator("[data-commerce-product], [data-merch-item]");
      if (!await cards.count()) throw new Error(`${category}: ${[...problems, `lists no products: "${await text(page.locator("main"))}"`].join("; ")}.`);
      const found = await readCards(cards);
      problems.push(...found.problems);
      if (found.links.length < found.listed.length) problems.push(unlinked(found.listed.length - found.links.length));
      problems.push(...await brokenLinks(page, found.links));
      if (problems.length) throw new Error(`${category}: ${problems.join("; ")}.`);
      return `${category} lists ${products(found.listed.length)}: ${short(found.listed).join(", ")}`;
    }, soft);

    // The cart page carries the store's checkout admission; only on a store that takes checkouts is
    // "checkout is unavailable" wrong, whether a page before it or the empty cart itself says it.
    const wording = "No page says checkout is unavailable on a store that takes checkouts";
    let admitted = null;
    let cartError = "";
    try {
      await open(page, "/cart");
      admitted = await page.locator("[data-guest-cart]").first().getAttribute("data-guest-checkout-admitted", quick).catch(() => null);
      seen.push({ where: "the empty cart", text: await page.locator("body").innerText() });
    } catch (error) {
      cartError = error.message.split("\n")[0];
    }
    // Only a cart page that says the store takes no checkouts skips the check; one that won't open or doesn't say fails it.
    if (admitted === "false") {
      record(wording, "SKIP", "the store takes no checkouts (its cart page says so), so saying so is true");
    } else await step(page, wording, async () => {
      if (cartError) throw new Error(`The cart page didn't open, so the test couldn't tell whether the store takes checkouts: ${cartError}`);
      if (admitted !== "true") throw new Error("The cart page doesn't say whether the store takes checkouts, so the wording couldn't be checked.");
      // Grouped by page, so every sentence is listed and a banner repeated on each page reads as such.
      const claims = seen.map(({ where, text: words }) => ({ where, said: cantBuyClaims(words) })).filter(({ said }) => said.length);
      if (claims.length) throw new Error(`The store takes checkouts, but ${claims.map(({ where, said }) => `${where} says ${said.map(line => `"${line}"`).join(", ")}`).join("; ")}.`);
      return `checked ${seen.map(({ where }) => where).join(", ")}`;
    }, soft);
  } finally {
    await page.context().browser().close();
  }
}, { profile: false }));
