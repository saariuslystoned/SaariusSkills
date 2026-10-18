import { createHash } from "node:crypto";
import { get, newPage, test, expect, shopperPage, closeShopper } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { record } from "../support/proof.mjs";
import { openShopperPage } from "../support/shopper.mjs";
import { confirmed, notePlugins, openAdmin } from "../support/store-admin.mjs";
import { journey, step } from "../support/steps.mjs";
import { photo, photoProblem, quick, readCard, text } from "../support/storefront-page.mjs";
import { dollars, money } from "../support/storefront-text.mjs";

const firstLine = error => String(error?.message ?? error).split("\n")[0];
// How long the store gets to show a change the owner just made.
const CATCH_UP_MS = 60_000;

/** This run's names, unique to the second and plainly the live test's. */
function runNames() {
  const stamp = new Date().toISOString().replace(/^\d{4}-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d).*$/, "$1$2-$3$4$5");
  return {
    product: `Live test product ${stamp}`,
    renamed: `Live test product ${stamp} renamed`,
    sku: `LIVE-TEST-${stamp}`,
    category: `Live test category ${stamp}`,
    photo: `live-test-${stamp}.png`,
  };
}

/** Answers the question the admin asks before an action with one of its buttons. */
async function answer(page, question, choice) {
  // Commerce's question carries no name of its own, so it's found by what it asks.
  const dialog = page.getByRole("dialog").or(page.getByRole("alertdialog")).filter({ hasText: question }).first();
  if (!await dialog.waitFor({ timeout: 15_000 }).then(() => true, () => false)) throw new Error(`The admin never asked "${question}"`);
  await dialog.getByRole("button", { name: choice, exact: true }).click();
}

/**
 * Opens a product in Commerce Products, paging through the list until it finds it. False only when
 * every page was read and none lists it; a page that won't open or turn fails instead.
 */
async function findProduct(page, name) {
  await openAdmin(page, config.productsAdmin);
  for (;;) {
    await page.getByRole("button", { name: "Add product", exact: true }).waitFor({ timeout: 30_000 });
    const open = page.getByRole("button", { name: `Open ${name}`, exact: true });
    if (await open.count()) {
      await open.click();
      await page.getByRole("heading", { name, level: 2 }).waitFor({ timeout: 30_000 });
      return true;
    }
    const next = page.getByRole("button", { name: "Next", exact: true });
    if (!await next.count()) return false;
    const before = await listedRows(page);
    await next.click();
    await expect.poll(() => listedRows(page), { timeout: 30_000 }).not.toEqual(before);
  }
}

/**
 * The rows the shown page of Commerce Products lists, each read with the text beside its Open button
 * ("name — SKU"). SKUs are unique, so the rows tell one page from the next even when products share a name.
 */
function listedRows(page) {
  return page.getByRole("button", { name: /^Open / }).evaluateAll(buttons => buttons.map(button => {
    let row = button;
    while (row.parentElement && row.textContent === button.textContent) row = row.parentElement;
    return row.textContent;
  }));
}

/** Opens a product in Commerce Products; a product the list doesn't have fails. */
async function openProduct(page, name) {
  if (!await findProduct(page, name)) throw new Error(`Commerce Products doesn't list "${name}".`);
}

/** What the open Commerce product page lacks of the controls the journey needs to take its product off the store again. */
async function missingControls(page) {
  await page.getByText("Commerce / Products", { exact: true }).waitFor({ timeout: 30_000 });
  return [...await page.getByRole("button", { name: "Rename", exact: true }).count() ? [] : ["rename"],
    ...await page.getByRole("button", { name: /^(Archive|Restore) product$/ }).count() ? [] : ["archive"]];
}

const CANT_REMOVE = "It needs a Commerce release with rename and archive.";

/**
 * Opens this run's product under whichever of its names it has now. Null only when Commerce Products
 * was read through and lists none of them; a lookup that fails throws.
 */
async function openRunProduct(page, names) {
  for (const name of new Set(names)) if (await findProduct(page, name)) return name;
  return null;
}

/** Makes sure the saved profile's page shows this product in Commerce, opening it again when a step left it elsewhere. */
async function onProduct(page, name) {
  if (await page.getByRole("heading", { name, level: 2 }).isVisible() && await page.getByText("Commerce / Products", { exact: true }).isVisible()) return;
  await openProduct(page, name);
}

/** Saves the open Commerce product's regular price. */
async function setPrice(page, regular) {
  await page.getByRole("textbox", { name: "Regular", exact: true }).fill(regular);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await confirmed(page, "Product saved");
}

/** Archives the open Commerce product, answering the question Commerce asks first. */
async function archive(page, name) {
  await onProduct(page, name);
  const button = page.getByRole("button", { name: "Archive product", exact: true });
  if (!await button.count()) throw new Error("Commerce's product page has no Archive product.");
  await button.click();
  await answer(page, `Archive ${name}?`, "Archive");
  await confirmed(page, "Product archived");
}

/** Uploads a plain square photo to the Media library, as an owner does before choosing it for a product. */
async function uploadPhoto(page, fileName, label) {
  // The browser draws the photo, so the test carries no image file. Its label makes each run's photo
  // its own: the Media library keeps one copy of identical files, under the first one's name.
  const painter = await newPage(page.context());
  await painter.setContent(`<div style="width:480px;height:480px;display:grid;place-items:center;background:linear-gradient(135deg,#2a6,#246);color:#fff;font:600 28px sans-serif">${label}</div>`);
  const png = await painter.locator("div").screenshot();
  await painter.close();
  await openAdmin(page, `${config.store}/_emdash/admin/media`);
  await page.getByRole("button", { name: "Upload Files" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Upload to Library" });
  const [chooser] = await Promise.all([page.waitForEvent("filechooser"), dialog.getByRole("button", { name: "Browse files", exact: true }).click()]);
  await chooser.setFiles({ name: fileName, mimeType: "image/png", buffer: png });
  const upload = dialog.getByRole("listitem").filter({ hasText: fileName });
  if (!await expect(upload).toContainText("Complete", { timeout: 60_000 }).then(() => true, () => false)) {
    throw new Error(`The Media library didn't take the photo: "${await text(upload) || "no upload listed"}".`);
  }
  await dialog.getByRole("button", { name: "Done" }).click();
}

/**
 * A fingerprint of the image file at `src`, fetched with `page`'s sign-ins, or "" when it can't be
 * fetched. Commerce's admin and the store address the same Media library file differently, so the
 * test compares the files themselves.
 */
async function imageHash(page, src) {
  if (!src) return "";
  const response = await get(page, new URL(src, config.store).href).catch(() => null);
  return response?.ok() ? createHash("sha256").update(await response.body()).digest("hex") : "";
}

/**
 * Why the open Commerce product page doesn't show the photo with fingerprint `hash` as the product's
 * image, or "" when it does. Once a product has an image, Commerce shows it under Images with Change
 * image beside it.
 */
async function adminPhotoProblem(page, hash) {
  const images = page.getByRole("heading", { name: "Images", level: 2 });
  if (!await images.waitFor({ timeout: 30_000 }).then(() => true, () => false)) return "the product's Commerce page has no Images section";
  // Commerce says so in the image's place when the product has none, or when the Media library has lost it.
  const said = await text(page.getByText(/^(No image|Image .+ is unavailable\.)$/));
  if (said) return `the product's Commerce page says "${said}" under Images`;
  if (!await page.getByRole("button", { name: "Change image", exact: true }).count()) return "the product's Commerce page has no Change image, which it shows only for a product with an image";
  const img = images.locator("xpath=following::img[1]");
  if (!await img.count()) return "the product's Commerce page shows no image under Images";
  const loaded = await expect.poll(() => img.evaluate(el => el.complete && el.naturalWidth > 0), { timeout: 15_000 }).toBe(true).then(() => true, () => false);
  if (!loaded) return "the image on the product's Commerce page didn't load";
  return await imageHash(page, await img.getAttribute("src")) === hash ? "" : "the product's Commerce page shows another image than the photo the owner chose";
}

/** An EmDash editor's field by its label; an editor without it fails with that plain reason. */
async function field(page, label, editor) {
  const box = page.getByRole("textbox", { name: label, exact: true });
  if (!await box.waitFor({ timeout: 30_000 }).then(() => true, () => false)) throw new Error(`${editor} has no "${label}" field.`);
  return box;
}

/** The slug EmDash makes from the title, once it has made one. */
async function slugOf(page) {
  const slug = page.getByRole("textbox", { name: "Slug", exact: true });
  await expect.poll(() => slug.inputValue(), quick).not.toBe("");
  return slug.inputValue();
}

/**
 * Saves a new EmDash entry and returns its editor's address. When the editor doesn't move there, the
 * address comes from EmDash's answer to the save; null when neither says, though the entry may exist.
 */
async function saveNew(page, collection) {
  const saved = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname === `/_emdash/api/content/${collection}`, { timeout: 30_000 });
  saved.catch(() => {});
  await page.getByRole("button", { name: "Save", exact: true }).click();
  if (await page.waitForURL(url => !url.pathname.endsWith("/new"), { timeout: 30_000 }).then(() => true, () => false)) return page.url();
  const id = await saved.then(response => response.json()).then(body => body?.data?.item?.id, () => null);
  return typeof id === "string" && id ? `${config.store}/_emdash/admin/content/${collection}/${id}` : null;
}

/** Publishes the open EmDash entry; a refusal fails with the reason the admin gives. */
async function publish(page, collection) {
  const published = page.waitForResponse(r => r.request().method() === "POST" && new RegExp(`/_emdash/api/content/${collection}/[^/]+/publish`).test(r.url()), { timeout: 30_000 });
  // When the click or the question fails first, this wait's own failure mustn't go unhandled; awaiting it below still fails the step.
  published.catch(() => {});
  await page.getByRole("button", { name: "Publish now" }).click();
  await answer(page, "Publish now?", "Publish now");
  const response = await published;
  if (response.ok()) return;
  const body = await response.json().catch(() => null);
  throw new Error(body?.error?.message ?? `HTTP ${response.status()}`);
}

/**
 * The full address the "View published" link in EmDash's list of product pages goes to for this title,
 * once the list shows the page as Published; null when it doesn't.
 */
async function publishedLink(page, title) {
  await openAdmin(page, `${config.store}/_emdash/admin/content/products`);
  await page.getByRole("searchbox", { name: "Search products" }).fill(title);
  const view = page.getByRole("link", { name: `View published ${title}`, exact: true });
  if (!await view.waitFor({ timeout: 15_000 }).then(() => true, () => false)) return null;
  const row = page.getByRole("row").filter({ has: view });
  if (!await row.getByRole("cell", { name: "Published", exact: true }).count()) return null;
  const href = await view.getAttribute("href");
  return href === null ? null : new URL(href, config.store).href;
}

/** Moves an EmDash entry to the Trash, so the store stops showing it. */
async function trash(page, url) {
  await openAdmin(page, url);
  await page.getByRole("button", { name: "Move to Trash" }).click();
  await answer(page, "Move to Trash?", "Move to Trash");
  await page.waitForURL(next => !next.href.startsWith(url.split("?")[0]), { timeout: 30_000 });
}

/**
 * Reloads a store page until `check` finds nothing wrong, giving the store a minute to show a change
 * the owner just made. Returns the last problems found (none once the page caught up) and the wait.
 */
async function catchUp(shopper, path, check) {
  const started = Date.now();
  for (;;) {
    const response = await shopper.goto(new URL(path, config.store).href).catch(error => error);
    const problems = response instanceof Error ? [`${path} didn't answer (${firstLine(response)})`]
      : new URL(shopper.url()).origin !== config.store ? [`${path} sent the shopper away from the store`]
        : await check(response);
    const seconds = Math.round((Date.now() - started) / 1000);
    if (!problems.length || Date.now() - started > CATCH_UP_MS) return { problems, seconds };
    await shopper.waitForTimeout(3_000);
  }
}

/** This run's product among a page's product cards: by its Commerce ID, the page it links to, or its name. */
async function findCard(cards, { id, path, name }) {
  for (const card of await cards.all()) {
    if (id && (await card.getAttribute("data-commerce-product") === id || await card.locator(`img[data-commerce-image="${id}"]`).count())) return card;
    if (path && (await card.getAttribute("href") === path || await card.locator(`a[href="${path}"]`).count())) return card;
    if (!id && name && await text(card.locator("h2, h3, h4")) === name) return card;
  }
  return null;
}

const shopCards = page => page.locator("[data-commerce-catalog] [data-commerce-product]");

/**
 * Why the homepage's Shop list can't be read, or "" when it lists products or says it has none. A card
 * missing from a Shop list that couldn't have shown it proves nothing.
 */
async function unreadableShop(shopper) {
  const catalog = shopper.locator("[data-commerce-catalog]");
  if (!await catalog.count()) return "the homepage has no Shop list";
  if (await catalog.locator("[data-commerce-product], [data-commerce-empty]").count()) return "";
  const said = await text(catalog.locator('[role="alert"]'));
  return said ? `the Shop list says "${said}"` : "the Shop list shows neither products nor that it has none";
}
const categoryCards = page => page.locator("main").locator("[data-commerce-product], [data-merch-item]");

/**
 * What's wrong with the photo a product card or page shows, given what `photo` made of it: it must be
 * the photo the owner chose, the file with fingerprint `hash`.
 */
async function photoProblems(media, where, image, hash) {
  if (image !== "photo") return [`${where} ${photoProblem[image]}`];
  const src = await media.locator("img[data-commerce-image]").first().getAttribute("src");
  return await imageHash(media.page(), src) === hash ? [] : [`${where} shows another photo (${new URL(src ?? "", config.store).pathname}) than the one the owner chose`];
}

/** What's wrong with how one product card shows this run's product. */
async function cardProblems(card, where, { name, cents, hasPhoto, photoHash, path }) {
  if (!card) return [`${where} doesn't list it`];
  const shown = await readCard(card, { withPhoto: hasPhoto });
  const problems = [];
  if (shown.name !== name) problems.push(`${where} names it "${shown.name || "nothing"}" instead of "${name}"`);
  if (money(shown.price) !== cents) problems.push(`${where} shows ${shown.price ? `"${shown.price}"` : "no price"} instead of ${dollars(cents)}`);
  if (hasPhoto) problems.push(...await photoProblems(card, where, shown.image, photoHash));
  if (path && shown.href !== path) problems.push(`${where} links to ${shown.href ?? "no product page"} instead of ${path}`);
  return problems;
}

/** What's wrong with how the product page shows this run's product. */
async function productPageProblems(shopper, response, { name, cents, hasPhoto, photoHash, categoryPath }) {
  if (response.status() !== 200) return [`the product page answered HTTP ${response.status()}`];
  const product = shopper.locator("[data-product-page]");
  if (!await product.count()) return ["the product page shows no product"];
  const problems = [];
  const heading = await text(product.locator("h1"));
  if (heading !== name) problems.push(`the product page's heading says "${heading || "nothing"}" instead of "${name}"`);
  const price = await text(product.locator("[data-product-price]"));
  if (money(price) !== cents) problems.push(`the product page shows ${price ? `"${price}"` : "no price"} instead of ${dollars(cents)}`);
  if (hasPhoto) {
    const visual = product.locator(".product-detail__visual");
    problems.push(...await photoProblems(visual, "the product page", await photo(visual), photoHash));
  }
  // Ready means wired to the cart and pressable; the journey never presses it.
  const add = shopper.locator('[data-add-to-cart][data-guest-cart-ready="1"]').first();
  if (!await add.waitFor({ timeout: 15_000 }).then(() => true, () => false)) problems.push("the product page has no working Add to cart button");
  else if (!await add.isEnabled()) problems.push("the product page's Add to cart button can't be pressed");
  if (categoryPath && !await shopper.locator(`.browse-breadcrumb a[href="${categoryPath}"]`).count()) problems.push(`the product page doesn't link to its category ${categoryPath}`);
  return problems;
}

/**
 * What goes wrong when a shopper presses this run's product on a list page (its Shop card, or View
 * details on a category page) to open its page.
 */
async function linkProblems(shopper, where, path, cards, { id, name, productPath }) {
  const response = await shopper.goto(new URL(path, config.store).href).catch(error => error);
  if (response instanceof Error) return [`${where} didn't answer (${firstLine(response)})`];
  const card = await findCard(cards(shopper), { id, path: productPath });
  if (!card) return [`${where} doesn't list it`];
  // A Shop card is the link itself; a category card links from View details.
  const link = await card.getAttribute("href") === productPath ? card : card.locator(`a[href="${productPath}"]`).first();
  if (!await link.count()) return [`${where} lists it without a link to ${productPath}`];
  const opened = await Promise.all([
    shopper.waitForResponse(r => r.request().isNavigationRequest() && new URL(r.url()).pathname === productPath, { timeout: 30_000 }),
    link.click(),
  ]).then(([navigation]) => navigation, () => null);
  if (!opened) return [`pressing it on ${where} didn't open ${productPath}`];
  if (opened.status() !== 200) return [`pressing it on ${where} opened ${productPath}, which answered HTTP ${opened.status()}`];
  await shopper.waitForLoadState("load");
  const heading = await text(shopper.locator("[data-product-page] h1"));
  return heading === name ? [] : [`pressing it on ${where} opened a page headed "${heading || "nothing"}" instead of "${name}"`];
}

/** Where the store shows the product, for a passing step's summary. */
const places = state => ["the Shop list", ...state.productPath ? [state.productPath, state.categoryPath] : []].join(", ");

/**
 * Everything wrong with how the store shows this run's product now (the Shop list, and its page and
 * category page once published), with the longest the store took to catch up.
 */
async function storeShows(shopper, state) {
  const { id, name, cents, hasPhoto, photoHash, productPath, categoryPath } = state;
  const checks = [await catchUp(shopper, "/", async response => {
    if (response.status() !== 200) return [`the homepage answered HTTP ${response.status()}`];
    const card = await findCard(shopCards(shopper), { id, name });
    const unreadable = card ? "" : await unreadableShop(shopper);
    if (unreadable) return [unreadable];
    // A product shown without its own ID still tells the journey which ID the Shop list gave it.
    if (card && !state.id) state.id = await card.getAttribute("data-commerce-product") ?? "";
    return cardProblems(card, "the Shop list", { name, cents, hasPhoto, photoHash, path: productPath });
  })];
  if (productPath) {
    checks.push(await catchUp(shopper, productPath, response => productPageProblems(shopper, response, state)));
    checks.push(await catchUp(shopper, categoryPath, async response => response.status() !== 200 ? [`${categoryPath} answered HTTP ${response.status()}`]
      : cardProblems(await findCard(categoryCards(shopper), { id, path: productPath }), `the category page ${categoryPath}`, { name, cents, hasPhoto, photoHash, path: productPath })));
  }
  return { problems: checks.flatMap(check => check.problems), seconds: Math.max(...checks.map(check => check.seconds)) };
}

/**
 * Everything that still offers this run's product to shoppers once the owner archived it or took its
 * page down. An archived product's page must say it's no longer available, and its category, still
 * published then, must answer for the missing card to count.
 */
async function storeHides(shopper, { id, name, productPath, categoryPath }, { archived = false } = {}) {
  // A homepage that doesn't answer, or whose Shop list can't be read, shows no cards either, which proves nothing.
  const checks = [await catchUp(shopper, "/", async response => {
    if (response.status() !== 200) return [`the homepage answered HTTP ${response.status()}`];
    if (await findCard(shopCards(shopper), { id, name })) return ["the Shop list still lists it"];
    const unreadable = await unreadableShop(shopper);
    return unreadable ? [unreadable] : [];
  })];
  if (productPath) {
    checks.push(await catchUp(shopper, productPath, async response => {
      const product = shopper.locator("[data-product-page]");
      const price = await text(product.locator("[data-product-price]"));
      const offers = [...money(price) !== null ? [`shows ${price}`] : [], ...await product.locator("[data-add-to-cart]").count() ? ["offers Add to cart"] : []];
      if (offers.length) return [`${productPath} still ${offers.join(" and ")}`];
      // A shopper following an old link to an archived product learns it's gone, from a page that answers 404.
      if (!archived) return [];
      const says = /no longer available/i.test(await text(shopper.locator("main")));
      return response.status() === 404 && says ? [] : [`${productPath} answers HTTP ${response.status()}${says ? " instead of 404" : " without saying the product is no longer available"}`];
    }));
    // Once the clean-up has moved the category to the Trash, its page may stop answering.
    checks.push(await catchUp(shopper, categoryPath, async response => response.status() !== 200
      ? archived ? [`the category page ${categoryPath} answered HTTP ${response.status()}`] : []
      : await findCard(categoryCards(shopper), { id, path: productPath }) ? [`the category page ${categoryPath} still lists it`] : []));
  }
  return { problems: checks.flatMap(check => check.problems), seconds: Math.max(...checks.map(check => check.seconds)) };
}

const after = seconds => seconds ? ` after ${seconds} s` : "";
/**
 * A passing step's word on the photo: the store showed it, or the step didn't look for it, since none
 * was chosen or an earlier step found the store showing the product wrong.
 */
const withPhoto = state => state.hasPhoto ? " with its photo"
  : state.photoHash ? " (its photo not looked for, since an earlier store check failed)" : " (no photo to look for, since none was chosen)";

// An owner's catalog work: add a product, give it a photo that stays after a reload and a page in a
// new category that the store links to, change its price and name, archive and restore it, with the
// store following each change. It tidies up after itself.
test("Manage products", { tag: "@next" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const run = runNames();
  // Commerce keeps the product open in the saved profile's page; Media and Content work in a second tab.
  const content = await newPage(page.context());
  const shopper = await shopperPage();
  // Playwright Test lets a click wait forever; a button the store doesn't show fails its step within a minute instead.
  for (const context of [page.context(), shopper.context()]) context.setDefaultTimeout(60_000);
  // What the store should show, and what this run made, so the last step can take it all off the store.
  const state = { id: "", idShown: false, name: run.product, adminName: run.product, cents: 1200, productPath: "", categoryPath: "", archived: false,
    checkNewProduct: false, cantArchive: false, hasPhoto: false, photoHash: "" };
  // `product` is "asked" from the moment Add product is pressed, and true once Commerce confirms it; the
  // page and category keep their store addresses from just before each is saved and their editor's once
  // it opens. `lost` names an entry saved without the test learning where its editor is.
  const made = { product: false, page: "", category: "", pagePath: "", categoryPath: "", lost: [] };
  const soft = { soft: true };
  try {
    // Commerce that can't archive would leave this run's product in the shop, so that's checked before anything is added.
    await step(page, "The owner can open Commerce Products", async () => {
      await openAdmin(page, config.productsAdmin);
      await notePlugins(page);
      if (!await page.getByRole("button", { name: "Add product", exact: true }).waitFor({ timeout: 30_000 }).then(() => true, () => false)) {
        throw new Error(`${config.productsAdmin} shows no Add product form.`);
      }
      const existing = page.getByRole("button", { name: /^Open / });
      if (!await existing.count()) {
        // The new product's own page gets the check instead, before it has a price; unpriced, the store doesn't list it.
        state.checkNewProduct = true;
        return "Commerce Products opened; no products yet, so the new product's page shows whether Commerce can rename and archive before it gets a price";
      }
      await existing.first().click();
      const missing = await missingControls(page);
      if (missing.length) {
        throw new Error(`Commerce on this store can't ${missing.join(" or ")} a product yet, so the journey stops before adding one it couldn't take off the store again. ${CANT_REMOVE}`);
      }
      await openAdmin(page, config.productsAdmin);
      await page.getByRole("button", { name: "Add product", exact: true }).waitFor({ timeout: 30_000 });
      return "Commerce Products opened, and its product pages offer Rename and Archive product";
    });

    // Nothing after this can run without the product, so this step stops the journey too.
    await step(page, "The owner adds a product with a price and a weight", async () => {
      await page.getByRole("textbox", { name: "Name", exact: true }).fill(run.product);
      await page.getByRole("textbox", { name: "SKU", exact: true }).fill(run.sku);
      await page.getByRole("radio", { name: "Physical", exact: true }).check();
      // A product Commerce adds without confirming it still gets cleaned up.
      made.product = "asked";
      await page.getByRole("button", { name: "Add product", exact: true }).click();
      await confirmed(page, "Product added");
      made.product = true;
      if (state.checkNewProduct) {
        const missing = await missingControls(page);
        state.cantArchive = missing.includes("archive");
        if (missing.length) throw new Error(`Commerce on this store can't ${missing.join(" or ")} a product yet, so the journey stops before pricing "${run.product}"; without a price the store doesn't list it. ${CANT_REMOVE}`);
      }
      // The product page shows the ID a product page's "Commerce product" field takes.
      const id = await text(page.locator("main pre, main code"));
      state.idShown = /^[\w-]{8,}$/.test(id);
      if (state.idShown) state.id = id;
      await setPrice(page, "12.00");
      await page.getByRole("textbox", { name: "Weight (oz)", exact: true }).fill("8");
      await page.getByRole("button", { name: "Save weight", exact: true }).click();
      await confirmed(page, "Weight saved");
      // Commerce draws the product again from what it stored, so the field now shows the saved weight.
      await expect(page.getByRole("textbox", { name: "Weight (oz)", exact: true }), "Commerce didn't keep the weight").toHaveValue("8", { timeout: 15_000 });
      return `"${run.product}" (SKU ${run.sku}) at $12.00, 8 oz${state.idShown ? `; Product ID ${state.id}` : ""}`;
    });

    await step(page, "The owner uploads a photo and makes it the product's image", async () => {
      await uploadPhoto(content, run.photo, run.product);
      await onProduct(page, state.adminName);
      await page.getByRole("button", { name: "Choose image", exact: true }).click();
      const use = page.getByRole("button", { name: `Use ${run.photo}`, exact: true });
      await use.waitFor({ timeout: 30_000 });
      // The library shows each photo just above its Use button, so that picture is the file chosen.
      const hash = await imageHash(page, await use.locator("xpath=preceding::img[1]").getAttribute("src", quick).catch(() => null));
      if (!hash) throw new Error(`Commerce's image picker shows no picture the test could fetch above "Use ${run.photo}".`);
      await use.click();
      await confirmed(page, "Image saved");
      Object.assign(state, { hasPhoto: true, photoHash: hash });
      return `uploaded ${run.photo} to the Media library and chose it on the product's Commerce page, which said "Image saved"`;
    }, soft);

    const keptStep = "The photo is still the product's image after a reload";
    if (!state.hasPhoto) record(keptStep, "SKIP", "the photo wasn't chosen, so there's no choice to check");
    else await step(page, keptStep, async () => {
      // Opening Commerce Products afresh, as a reload does, draws the product's page from what Commerce stored.
      await openProduct(page, state.adminName);
      const problem = await adminPhotoProblem(page, state.photoHash);
      if (problem) throw new Error(`After a reload, ${problem}.`);
      return "after a reload, the product's Commerce page shows the chosen photo under Images, loaded, with Change image beside it";
    }, soft);

    const shopRight = await step(shopper, "The Shop list shows the new product with its name, price and photo", async () => {
      // A store that keeps every page behind Cloudflare Access gets a one-time PIN sign-in first.
      await openShopperPage(shopper, "/");
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `"${state.name}" at ${dollars(state.cents)}${withPhoto(state)}${after(seconds)}`;
    }, soft);

    const pageStep = "The owner gives the product its own page in a new category";
    await step(content, pageStep, async () => {
      if (!state.id) throw new Error("The test couldn't learn the product's ID: Commerce's product page doesn't show it and the Shop list doesn't list the product.");
      await openAdmin(content, `${config.store}/_emdash/admin/content/categories/new`);
      await (await field(content, "Category title", "The new category editor")).fill(run.category);
      made.categoryPath = `/categories/${await slugOf(content)}`;
      made.category = await saveNew(content, "categories") ?? "";
      if (!made.category) {
        made.lost.push(`category "${run.category}"`);
        throw new Error(`Saving the category "${run.category}" never opened its editor, and EmDash's answer didn't say where it is.`);
      }
      await publish(content, "categories").catch(error => { throw new Error(`Publishing the category failed: ${firstLine(error)}`); });

      await openAdmin(content, `${config.store}/_emdash/admin/content/products/new`);
      const editor = "The new product page editor";
      await (await field(content, "Product title", editor)).fill(run.product);
      await (await field(content, "Illustration style (TEE, HOODIE, CAP, or BEANIE)", editor)).fill("CAP");
      await (await field(content, "Commerce product (optional)", editor)).fill(state.id);
      made.pagePath = `/products/${await slugOf(content)}`;
      made.page = await saveNew(content, "products") ?? "";
      if (!made.page) {
        made.lost.push(`product page "${run.product}"`);
        throw new Error(`Saving the product page "${run.product}" never opened its editor, and EmDash's answer didn't say where it is.`);
      }
      await content.getByRole("button", { name: "Add reference" }).click();
      const picker = content.getByRole("dialog", { name: "Add references" });
      await picker.getByPlaceholder("Search content...").fill(run.category);
      await picker.locator("label").filter({ hasText: run.category }).first().click({ timeout: 15_000 });
      await picker.getByRole("button", { name: "Add selected" }).click();
      await content.getByRole("button", { name: `Remove ${run.category}` }).waitFor({ timeout: 15_000 });
      const save = content.getByRole("button", { name: "Save", exact: true });
      if (await save.isEnabled()) {
        await save.click();
        await expect(save).toBeDisabled({ timeout: 15_000 }).catch(() => {});
      }
      await publish(content, "products").catch(error => { throw new Error(`Publishing the product page failed: ${firstLine(error)}`); });
      Object.assign(state, { productPath: made.pagePath, categoryPath: made.categoryPath });
      // The owner's list of product pages says it's published and links to its address.
      const listed = await publishedLink(content, run.product);
      if (listed !== new URL(state.productPath, config.store).href) {
        throw new Error(listed === null ? `Published ${state.productPath}, but EmDash's list of product pages doesn't show it as Published with a View published link.`
          : `EmDash's list of product pages links "${run.product}" to ${listed} instead of ${state.productPath}.`);
      }
      // Linking the page needs the ID, which an owner can only copy from Commerce's product page.
      if (!state.idShown) throw new Error(`Published ${state.productPath} in ${state.categoryPath}, but Commerce's product page shows no Product ID, so the test copied it from the Shop list's markup.`);
      return `published ${state.productPath} in the new category ${state.categoryPath}, linked by the Product ID Commerce shows; EmDash lists it as Published, with View published linking to it`;
    }, soft);

    const showsStep = "The product page and its category page show the product";
    let storeRight = shopRight;
    if (!state.productPath) record(showsStep, "SKIP", "the product page wasn't published, so there's no page to check");
    else storeRight = await step(shopper, showsStep, async () => {
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `the Shop card links to ${state.productPath}, which shows "${state.name}" at ${dollars(state.cents)}${withPhoto(state)} and Add to cart; ${state.categoryPath} lists it${after(seconds)}`;
    }, soft);
    // The changes below look for the photo too, until a step finds the store showing the product wrong,
    // so a photo the store lost fails the step that first misses it, not every change after that too.
    if (!storeRight) state.hasPhoto = false;

    const linkStep = "The product's links open its page";
    if (!state.productPath) record(linkStep, "SKIP", "the product page wasn't published, so there's no link to follow");
    else await step(shopper, linkStep, async () => {
      const problems = [
        ...await linkProblems(shopper, "the Shop list", "/", shopCards, state),
        ...await linkProblems(shopper, `the category page ${state.categoryPath}`, state.categoryPath, categoryCards, state),
      ];
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return `pressing the product's Shop card, and View details on ${state.categoryPath}, opens ${state.productPath}, headed "${state.name}"`;
    }, soft);

    const priceRight = await step(shopper, "A new price shows on the store", async () => {
      await onProduct(page, state.adminName);
      await setPrice(page, "13.50");
      state.cents = 1350;
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `$13.50${withPhoto(state)} on ${places(state)}${after(seconds)}`;
    }, soft);
    if (!priceRight) state.hasPhoto = false;

    const nameRight = await step(shopper, "A new name shows on the store", async () => {
      await onProduct(page, state.adminName);
      const rename = page.getByRole("button", { name: "Rename", exact: true });
      if (!await rename.count()) throw new Error("Commerce's product page has no Rename.");
      await page.getByRole("textbox", { name: "Name", exact: true }).fill(run.renamed);
      await rename.click();
      await confirmed(page, "Product renamed");
      Object.assign(state, { name: run.renamed, adminName: run.renamed });
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `"${state.name}"${withPhoto(state)} on ${places(state)}${after(seconds)}`;
    }, soft);
    if (!nameRight) state.hasPhoto = false;

    await step(shopper, "Archiving the product takes it off the store", async () => {
      await archive(page, state.adminName);
      state.archived = true;
      const { problems, seconds } = await storeHides(shopper, state, { archived: true });
      if (problems.length) throw new Error(`Archived in Commerce, but ${problems.join("; ")}${after(seconds)}.`);
      const where = state.productPath ? places(state).replace(state.productPath, `${state.productPath} (now "no longer available", HTTP 404)`) : places(state);
      return `gone from ${where}${after(seconds)}`;
    }, soft);

    const restoreStep = "Restoring the product puts it back on the store";
    if (!state.archived) record(restoreStep, "SKIP", "the product wasn't archived, so there's nothing to restore");
    else await step(shopper, restoreStep, async () => {
      await onProduct(page, state.adminName);
      await page.getByRole("button", { name: "Restore product", exact: true }).click();
      await confirmed(page, "Product restored");
      state.archived = false;
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`Restored in Commerce, but ${problems.join("; ")}${after(seconds)}.`);
      return `back on ${places(state)} as "${state.name}" at ${dollars(state.cents)}${withPhoto(state)}${after(seconds)}`;
    }, soft);
  } finally {
    // Whatever this run added comes off the store again, even when a step above stopped the journey.
    if (made.product || made.page || made.category || made.lost.length) await step(shopper, "The test takes its product, page and category off the store", async () => {
      const problems = [];
      if (state.cantArchive) problems.push(`"${run.product}" stays in Commerce Products without a price, since this Commerce can't archive it; the store doesn't list it`);
      else if (made.product) {
        // A confirmation the journey missed can leave its notes stale, so the product's own page says what it is now.
        // A lookup that fails proves nothing either way, so it's a finding (and `name` stays undefined).
        const name = await openRunProduct(page, [state.adminName, run.renamed, run.product])
          .catch(error => { problems.push(`looking for "${run.product}" in Commerce Products failed, so it may still be on the store: ${firstLine(error)}`); });
        if (name === null) {
          // A product Commerce never confirmed adding may not exist at all.
          if (made.product === true) problems.push(`Commerce Products lists neither "${run.product}" nor "${run.renamed}", so the test couldn't archive it`);
        } else if (name) {
          state.adminName = name;
          if (await page.getByRole("button", { name: "Archive product", exact: true }).count()) {
            await archive(page, name).then(() => { state.archived = true; }, error => problems.push(`archiving "${name}" in Commerce failed: ${firstLine(error)}`));
          } else if (await page.getByRole("button", { name: "Restore product", exact: true }).count()) state.archived = true;
          else problems.push(`"${name}" offers neither Archive product nor Restore product`);
        }
      }
      // Each finding names what's left, so the owner can take it off the store by hand.
      for (const [what, url] of [[`product page "${run.product}"`, made.page], [`category "${run.category}"`, made.category]]) {
        if (url) await trash(content, url).catch(error => problems.push(`moving the ${what} to the Trash failed: ${firstLine(error)}`));
      }
      for (const what of made.lost) problems.push(`the ${what} may have been saved without the test learning where, so look for it under Content in the store admin`);
      // A step that stopped the journey early can leave the shopper's browser not yet signed in to a store
      // that keeps every page behind Cloudflare Access, so it opens the store first.
      if (await openShopperPage(shopper, "/").then(() => true, error => { problems.push(`the test couldn't open the store as a shopper to check it: ${firstLine(error)}`); return false; })) {
        problems.push(...(await storeHides(shopper, state)).problems);
        // Every address the run saved stops answering within a minute, published or not.
        for (const path of [made.pagePath, made.categoryPath].filter(Boolean)) {
          problems.push(...(await catchUp(shopper, path, response => response.status() === 200 ? [`${path} still answers HTTP 200`] : [])).problems);
        }
      }
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return `${state.archived ? `archived "${state.adminName}" in Commerce` : "Commerce never added the product"}${made.page || made.category ? " and moved its page and category to EmDash's Trash" : ""}; the store shows none of them`;
    }, soft);
    await closeShopper(shopper);
    await content.close();
  }
}));
