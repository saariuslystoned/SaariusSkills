import { test, expect, shopperPage } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { note, record } from "../support/proof.mjs";
import { openStoreAdmin } from "../support/signin.mjs";
import { openShopperPage } from "../support/shopper.mjs";
import { journey, step } from "../support/steps.mjs";
import { describePlugins } from "../support/store-plugins.mjs";
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

const SIGN_IN_ONCE = "Run once with DINKUS_E2E_ADMIN_SIGNIN=wait and sign in by hand.";

/** Opens a page of the store admin, signing in to its Access app with a one-time PIN when it asks. */
async function openAdmin(page, url) {
  if (!await openStoreAdmin(page, url, { waitForPerson: config.adminSignIn === "wait" })) {
    throw new Error(`The store admin needs a sign-in the test can't make: its Access app offers no one-time PIN and the saved profile has no sign-in. ${SIGN_IN_ONCE}`);
  }
  // A store whose admin isn't signed in through Access asks for EmDash's own sign-in (passkey or email link).
  if (!new URL(page.url()).pathname.startsWith("/_emdash/admin/login")) return;
  if (config.adminSignIn !== "wait" || config.headless) throw new Error(`The store admin asks for an EmDash sign-in (passkey or email link) that the saved profile doesn't have. ${SIGN_IN_ONCE}`);
  console.log(`\n>>> Sign in to the store admin in this test's browser window (once per profile).\n`);
  await page.waitForURL(next => !next.pathname.startsWith("/_emdash/admin/login"), { timeout: 10 * 60 * 1000 });
  await page.goto(url);
}

/** Notes which plugin versions the store runs, so the proof says what it covers. */
async function notePlugins(page) {
  const response = await page.context().request.get(`${config.store}/_emdash/api/admin/plugins`, { headers: { "X-EmDash-Request": "1" } }).catch(error => error);
  if (response instanceof Error) note("plugins", `couldn't read the plugin list (${firstLine(response)})`);
  else note("plugins", response.ok() ? describePlugins(await response.json()) : `couldn't read the plugin list (HTTP ${response.status()})`);
}

/** Waits for Commerce to confirm an action ("Product saved"); a refusal fails with the reason Commerce shows. */
async function confirmed(page, message) {
  const done = page.getByText(message, { exact: true }).first();
  const refused = page.locator('main [role="alert"]').first();
  await done.or(refused).waitFor({ timeout: 30_000 }).catch(() => {});
  if (await done.isVisible()) return;
  const reason = await text(refused);
  throw new Error(reason ? `Commerce refused it: "${reason}"` : `Commerce never said "${message}".`);
}

/** Answers the question the admin asks before an action with one of its buttons. */
async function answer(page, question, choice) {
  // Commerce's question carries no name of its own, so it's found by what it asks.
  const dialog = page.getByRole("dialog").or(page.getByRole("alertdialog")).filter({ hasText: question }).first();
  if (!await dialog.waitFor({ timeout: 15_000 }).then(() => true, () => false)) throw new Error(`The admin never asked "${question}"`);
  await dialog.getByRole("button", { name: choice, exact: true }).click();
}

/** Opens a product in Commerce Products, paging through the list until it finds it. */
async function openProduct(page, name) {
  await openAdmin(page, config.productsAdmin);
  for (;;) {
    await page.getByRole("button", { name: "Add product", exact: true }).waitFor({ timeout: 30_000 });
    const open = page.getByRole("button", { name: `Open ${name}`, exact: true });
    if (await open.count()) {
      await open.click();
      await page.getByRole("heading", { name, level: 2 }).waitFor({ timeout: 30_000 });
      return;
    }
    const next = page.getByRole("button", { name: "Next", exact: true });
    if (!await next.count()) throw new Error(`Commerce Products doesn't list "${name}".`);
    const first = await page.getByRole("button", { name: /^Open / }).first().textContent();
    await next.click();
    await expect.poll(() => page.getByRole("button", { name: /^Open / }).first().textContent(), { timeout: 30_000 }).not.toBe(first);
  }
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
  const painter = await page.context().newPage();
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

/** Saves a new EmDash entry and returns its editor's address. */
async function saveNew(page) {
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.waitForURL(url => !url.pathname.endsWith("/new"), { timeout: 30_000 });
  return page.url();
}

/** Publishes the open EmDash entry; a refusal fails with the reason the admin gives. */
async function publish(page, collection) {
  const published = page.waitForResponse(r => r.request().method() === "POST" && new RegExp(`/_emdash/api/content/${collection}/[^/]+/publish`).test(r.url()), { timeout: 30_000 });
  await page.getByRole("button", { name: "Publish now" }).click();
  await answer(page, "Publish now?", "Publish now");
  const response = await published;
  if (response.ok()) return;
  const body = await response.json().catch(() => null);
  throw new Error(body?.error?.message ?? `HTTP ${response.status()}`);
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
const categoryCards = page => page.locator("main").locator("[data-commerce-product], [data-merch-item]");

/** What's wrong with how one product card shows this run's product. */
async function cardProblems(card, where, { name, cents, path }) {
  if (!card) return [`${where} doesn't list it`];
  const shown = await readCard(card);
  const problems = [];
  if (shown.name !== name) problems.push(`${where} names it "${shown.name || "nothing"}" instead of "${name}"`);
  if (money(shown.price) !== cents) problems.push(`${where} shows ${shown.price ? `"${shown.price}"` : "no price"} instead of ${dollars(cents)}`);
  if (shown.image !== "photo") problems.push(`${where} ${photoProblem[shown.image]}`);
  if (path && shown.href !== path) problems.push(`${where} links to ${shown.href ?? "no product page"} instead of ${path}`);
  return problems;
}

/** What's wrong with how the product page shows this run's product. */
async function productPageProblems(shopper, response, { name, cents, categoryPath }) {
  if (response.status() !== 200) return [`the product page answered HTTP ${response.status()}`];
  const product = shopper.locator("[data-product-page]");
  if (!await product.count()) return ["the product page shows no product"];
  const problems = [];
  const heading = await text(product.locator("h1"));
  if (heading !== name) problems.push(`the product page's heading says "${heading || "nothing"}" instead of "${name}"`);
  const price = await text(product.locator("[data-product-price]"));
  if (money(price) !== cents) problems.push(`the product page shows ${price ? `"${price}"` : "no price"} instead of ${dollars(cents)}`);
  const image = await photo(product.locator(".product-detail__visual"));
  if (image !== "photo") problems.push(`the product page ${photoProblem[image]}`);
  // Ready means wired to the cart and pressable; the journey never presses it.
  const add = shopper.locator('[data-add-to-cart][data-guest-cart-ready="1"]').first();
  if (!await add.waitFor({ timeout: 15_000 }).then(() => true, () => false)) problems.push("the product page has no working Add to cart button");
  else if (!await add.isEnabled()) problems.push("the product page's Add to cart button can't be pressed");
  if (categoryPath && !await shopper.locator(`.browse-breadcrumb a[href="${categoryPath}"]`).count()) problems.push(`the product page doesn't link to its category ${categoryPath}`);
  return problems;
}

/** Where the store shows the product, for a passing step's summary. */
const places = state => ["the Shop list", ...state.productPath ? [state.productPath, state.categoryPath] : []].join(", ");

/**
 * Everything wrong with how the store shows this run's product now (the Shop list, and its page and
 * category page once published), with the longest the store took to catch up.
 */
async function storeShows(shopper, state) {
  const { id, name, cents, productPath, categoryPath } = state;
  const checks = [await catchUp(shopper, "/", async () => {
    const card = await findCard(shopCards(shopper), { id, name });
    // A product shown without its own ID still tells the journey which ID the Shop list gave it.
    if (card && !state.id) state.id = await card.getAttribute("data-commerce-product") ?? "";
    return cardProblems(card, "the Shop list", { name, cents, path: productPath });
  })];
  if (productPath) {
    checks.push(await catchUp(shopper, productPath, response => productPageProblems(shopper, response, state)));
    checks.push(await catchUp(shopper, categoryPath, async response => response.status() !== 200 ? [`${categoryPath} answered HTTP ${response.status()}`]
      : cardProblems(await findCard(categoryCards(shopper), { id, path: productPath }), `the category page ${categoryPath}`, { name, cents, path: productPath })));
  }
  return { problems: checks.flatMap(check => check.problems), seconds: Math.max(...checks.map(check => check.seconds)) };
}

/**
 * Everything that still offers this run's product to shoppers once the owner archived it or took its
 * page down. An archived product's page must say it's no longer available.
 */
async function storeHides(shopper, { id, name, productPath, categoryPath }, { archived = false } = {}) {
  const checks = [await catchUp(shopper, "/", async () => await findCard(shopCards(shopper), { id, name }) ? ["the Shop list still lists it"] : [])];
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
    checks.push(await catchUp(shopper, categoryPath, async response => response.status() === 200
      && await findCard(categoryCards(shopper), { id, path: productPath }) ? [`the category page ${categoryPath} still lists it`] : []));
  }
  return { problems: checks.flatMap(check => check.problems), seconds: Math.max(...checks.map(check => check.seconds)) };
}

const after = seconds => seconds ? ` after ${seconds} s` : "";

// An owner's catalog work: add a product, give it a page in a new category, change its price and
// name, archive and restore it, with the store following each change. It tidies up after itself.
test("Manage products", { tag: "@next" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const run = runNames();
  // Commerce keeps the product open in the saved profile's page; Media and Content work in a second tab.
  const content = await page.context().newPage();
  const shopper = await shopperPage();
  // Playwright Test lets a click wait forever; a button the store doesn't show fails its step within a minute instead.
  for (const context of [page.context(), shopper.context()]) context.setDefaultTimeout(60_000);
  // What the store should show, and what this run made, so the last step can take it all off the store.
  const state = { id: "", idShown: false, name: run.product, adminName: run.product, cents: 1200, productPath: "", categoryPath: "", archived: false };
  const made = { product: false, page: "", category: "" };
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
      if (!await existing.count()) return "Commerce Products opened; no products yet, so the new one shows whether Commerce can rename and archive";
      await existing.first().click();
      await page.getByText("Commerce / Products", { exact: true }).waitFor({ timeout: 30_000 });
      const canRename = await page.getByRole("button", { name: "Rename", exact: true }).count();
      const canArchive = await page.getByRole("button", { name: /^(Archive|Restore) product$/ }).count();
      if (!canRename || !canArchive) {
        throw new Error(`Commerce on this store can't ${[...canRename ? [] : ["rename"], ...canArchive ? [] : ["archive"]].join(" or ")} a product yet, so the journey stops before adding one it couldn't take off the store again. It needs a Commerce release with rename and archive.`);
      }
      await openAdmin(page, config.productsAdmin);
      await page.getByRole("button", { name: "Add product", exact: true }).waitFor({ timeout: 30_000 });
      return "Commerce Products opened, and its product pages offer Rename and Archive product";
    });

    // Nothing after this can run without the product, so this step stops the journey too.
    await step(page, "The owner adds a product with a price, a weight and a photo", async () => {
      await uploadPhoto(content, run.photo, run.product);
      await page.getByRole("textbox", { name: "Name", exact: true }).fill(run.product);
      await page.getByRole("textbox", { name: "SKU", exact: true }).fill(run.sku);
      await page.getByRole("radio", { name: "Physical", exact: true }).check();
      await page.getByRole("button", { name: "Add product", exact: true }).click();
      await confirmed(page, "Product added");
      made.product = true;
      // The product page shows the ID a product page's "Commerce product" field takes.
      const id = await text(page.locator("main pre, main code"));
      state.idShown = /^[\w-]{8,}$/.test(id);
      if (state.idShown) state.id = id;
      await setPrice(page, "12.00");
      await page.getByRole("textbox", { name: "Weight (oz)", exact: true }).fill("8");
      await page.getByRole("button", { name: "Save weight", exact: true }).click();
      await expect(page.getByRole("textbox", { name: "Weight (oz)", exact: true }), "Commerce didn't keep the weight").toHaveValue("8", { timeout: 15_000 });
      await page.getByRole("button", { name: "Choose image", exact: true }).click();
      await page.getByRole("button", { name: `Use ${run.photo}`, exact: true }).click({ timeout: 30_000 });
      await confirmed(page, "Image saved");
      return `"${run.product}" (SKU ${run.sku}) at $12.00, 8 oz, with its photo${state.idShown ? `; Product ID ${state.id}` : ""}`;
    });

    await step(shopper, "The Shop list shows the new product with its name, price and photo", async () => {
      // A store that keeps every page behind Cloudflare Access gets a one-time PIN sign-in first.
      await openShopperPage(shopper, "/");
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `"${state.name}" at ${dollars(state.cents)} with its photo${after(seconds)}`;
    }, soft);

    const pageStep = "The owner gives the product its own page in a new category";
    await step(content, pageStep, async () => {
      if (!state.id) throw new Error("The test couldn't learn the product's ID: Commerce's product page doesn't show it and the Shop list doesn't list the product.");
      await openAdmin(content, `${config.store}/_emdash/admin/content/categories/new`);
      await (await field(content, "Category title", "The new category editor")).fill(run.category);
      const categorySlug = await slugOf(content);
      made.category = await saveNew(content);
      await publish(content, "categories").catch(error => { throw new Error(`Publishing the category failed: ${firstLine(error)}`); });

      await openAdmin(content, `${config.store}/_emdash/admin/content/products/new`);
      const editor = "The new product page editor";
      await (await field(content, "Product title", editor)).fill(run.product);
      await (await field(content, "Illustration style (TEE, HOODIE, CAP, or BEANIE)", editor)).fill("CAP");
      await (await field(content, "Commerce product (optional)", editor)).fill(state.id);
      const slug = await slugOf(content);
      made.page = await saveNew(content);
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
      Object.assign(state, { productPath: `/products/${slug}`, categoryPath: `/categories/${categorySlug}` });
      // Linking the page needs the ID, which an owner can only copy from Commerce's product page.
      if (!state.idShown) throw new Error(`Published ${state.productPath} in ${state.categoryPath}, but Commerce's product page shows no Product ID, so the test copied it from the Shop list's markup.`);
      return `published ${state.productPath} in the new category ${state.categoryPath}, linked by the Product ID Commerce shows`;
    }, soft);

    const showsStep = "The product page and its category page show the product";
    if (!state.productPath) record(showsStep, "SKIP", "the product page wasn't published, so there's no page to check");
    else await step(shopper, showsStep, async () => {
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `the Shop card links to ${state.productPath}, which shows "${state.name}" at ${dollars(state.cents)} with its photo and Add to cart; ${state.categoryPath} lists it${after(seconds)}`;
    }, soft);

    await step(shopper, "A new price shows on the store", async () => {
      await onProduct(page, state.adminName);
      await setPrice(page, "13.50");
      state.cents = 1350;
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `$13.50 on ${places(state)}${after(seconds)}`;
    }, soft);

    await step(shopper, "A new name shows on the store", async () => {
      await onProduct(page, state.adminName);
      const rename = page.getByRole("button", { name: "Rename", exact: true });
      if (!await rename.count()) throw new Error("Commerce's product page has no Rename.");
      await page.getByRole("textbox", { name: "Name", exact: true }).fill(run.renamed);
      await rename.click();
      await confirmed(page, "Product renamed");
      Object.assign(state, { name: run.renamed, adminName: run.renamed });
      const { problems, seconds } = await storeShows(shopper, state);
      if (problems.length) throw new Error(`${problems.join("; ")}${after(seconds)}.`);
      return `"${state.name}" on ${places(state)}${after(seconds)}`;
    }, soft);

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
      return `back on ${places(state)} as "${state.name}" at ${dollars(state.cents)}${after(seconds)}`;
    }, soft);
  } finally {
    // Whatever this run added comes off the store again, even when a step above stopped the journey.
    if (made.product || made.page || made.category) await step(shopper, "The test takes its product, page and category off the store", async () => {
      const problems = [];
      if (made.product && !state.archived) {
        await archive(page, state.adminName).then(() => { state.archived = true; }, error => problems.push(`archiving "${state.adminName}" in Commerce failed: ${firstLine(error)}`));
      }
      // Each finding names what's left, so the owner can take it off the store by hand.
      for (const [what, url] of [[`product page "${run.product}"`, made.page], [`category "${run.category}"`, made.category]]) {
        if (url) await trash(content, url).catch(error => problems.push(`moving the ${what} to the Trash failed: ${firstLine(error)}`));
      }
      const left = await storeHides(shopper, state);
      problems.push(...left.problems);
      for (const path of [state.productPath, state.categoryPath].filter(Boolean)) {
        const response = await shopper.goto(new URL(path, config.store).href).catch(error => error);
        if (!(response instanceof Error) && response.status() === 200) problems.push(`${path} still answers HTTP 200`);
      }
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return `archived "${state.adminName}" in Commerce${made.page || made.category ? " and moved its page and category to EmDash's Trash" : ""}; the store shows none of them`;
    }, soft);
    await shopper.context().browser().close();
    await content.close();
  }
}));
