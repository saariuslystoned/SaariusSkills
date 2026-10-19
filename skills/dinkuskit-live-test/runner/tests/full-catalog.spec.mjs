import { newPage, test, expect, shopperPage, closeShopper } from "../support/browser.mjs";
import { catalogPlan } from "../support/catalog.mjs";
import { config } from "../support/env.mjs";
import {
  addCategory, addProductPage, choosePhoto, finishProductPage, listedProducts, openProduct, productPageEntry, publish, publishedLink, setPrice, setWeight,
  shownProductId, uploadPhotos,
} from "../support/products-admin.mjs";
import { PAGE_ROOM, PHOTO_ROOM, STORE_BUDGET, paceStore } from "../support/pace.mjs";
import { note } from "../support/proof.mjs";
import { openShopperPage } from "../support/shopper.mjs";
import { confirmed, notePlugins, openAdmin } from "../support/store-admin.mjs";
import { pluginVersion, versionAtLeast } from "../support/store-plugins.mjs";
import { journey, step } from "../support/steps.mjs";
import { photo, photoProblem, quick, readCard, text } from "../support/storefront-page.mjs";
import { dollars, money } from "../support/storefront-text.mjs";

// An error's first line without its full stop, since findings are joined into one sentence.
const firstLine = error => String(error?.message ?? error).split("\n")[0].replace(/\.$/, "");
// Before this release Commerce read every product to draw each product screen, so with more than a
// handful of products the owner couldn't save one; adding the catalog there would break the store admin.
const COMMERCE_FOR_CATALOGS = "0.3.0-beta.4";
const tooOld = (commerce, lacks) => new Error(`The catalog lacks ${lacks}, but this store runs Commerce ${commerce ?? "of a version the test couldn't read"}, which reads every product to draw each product screen, so with the catalog in place the owner couldn't save a product. It needs Commerce ${COMMERCE_FOR_CATALOGS} or later; nothing was added.`);
// Commerce's image picker lists twelve photos a page, so uploading that many at a time keeps each new photo on its first page.
const UPLOAD_BATCH = 12;
// The most store requests the owner's work sends, measured on a local store: the Media library shows
// its photos while a batch uploads, so a batch waits for the store's whole allowance; one product's
// Commerce screens, image picker photos and page editor send about 40.
const UPLOADS_ROOM = STORE_BUDGET;
const PRODUCT_ROOM = 50;

const plural = (count, one, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;
// Passing summaries name the first few products; a failure names every finding.
const short = (items, count = 5) => items.length > count ? [...items.slice(0, count), `${items.length - count} more`] : items;
const total = names => [...names.values()].reduce((sum, count) => sum + count, 0);

/**
 * The cards of a list page that name one of the catalog's products, read as a shopper sees them: name,
 * price, photo, the page each links to, and its photo's address. Several cards can name one product.
 */
async function catalogCards(cards, names) {
  const found = new Map();
  for (const card of await cards.all()) {
    const shown = await readCard(card, { withPhoto: false });
    if (!names.has(shown.name)) continue;
    // Only the catalog's cards get their photos read, sparing the wait on other products' photos.
    await paceStore(PHOTO_ROOM);
    shown.image = await photo(card);
    shown.src = shown.image === "photo" ? await card.locator("img[data-commerce-image]").first().getAttribute("src", quick).catch(() => null) : null;
    found.set(shown.name, [...found.get(shown.name) ?? [], shown]);
  }
  return found;
}

/**
 * The homepage's Shop list: how many products it lists, and its cards for the catalog's products. A list
 * with no products counts as read only when it says the store lists none yet, and only with `mayBeEmpty`.
 */
async function readShop(shopper, names, { mayBeEmpty = false } = {}) {
  await openShopperPage(shopper, "/");
  const catalog = shopper.locator("[data-commerce-catalog]");
  if (!await catalog.count()) throw new Error("The homepage has no Shop list.");
  const cards = catalog.locator("[data-commerce-product]");
  const count = await cards.count();
  if (!count) {
    const said = await text(catalog.locator('[role="alert"]'));
    if (said) throw new Error(`The Shop list says "${said}".`);
    const empty = await text(catalog.locator("[data-commerce-empty]"));
    if (!empty) throw new Error("The Shop list shows neither products nor that it has none.");
    if (!mayBeEmpty) throw new Error(`The Shop list says "${empty}".`);
  }
  return { count, found: await catalogCards(cards, names) };
}

/** A category page's cards for the catalog's products. */
async function readCategory(shopper, path, names) {
  await openShopperPage(shopper, path);
  return catalogCards(shopper.locator("main").locator("[data-commerce-product], [data-merch-item]"), names);
}

/**
 * Where a link takes a shopper: a store page by its path and query, any other site by its whole address.
 * A #part only scrolls the page, so it's left out.
 */
function destination(href) {
  const url = new URL(href, config.store);
  url.hash = "";
  return url.origin === config.store ? `${url.pathname}${url.search}` : url.href;
}

/**
 * What's wrong with how a list page shows `products`: one it doesn't list or lists twice, one at
 * another price, without a photo of its own or a link to its page, or two showing the same photo.
 * `pages` holds the page each product's Shop card links to, which its other cards must link to too.
 */
function listProblems(found, products, where, pages = new Map()) {
  const problems = [];
  const bySrc = new Map();
  for (const product of products) {
    const cards = found.get(product.name) ?? [];
    if (!cards.length) {
      problems.push(`${where} doesn't list "${product.name}"`);
      continue;
    }
    if (cards.length > 1) problems.push(`${where} lists "${product.name}" ${cards.length} times`);
    const [card] = cards;
    if (money(card.price) !== product.cents) problems.push(`${where} shows "${product.name}" at ${card.price ? `"${card.price}"` : "no price"} instead of ${dollars(product.cents)}`);
    if (card.image !== "photo") problems.push(`"${product.name}" on ${where} ${photoProblem[card.image]}`);
    if (!card.href) problems.push(`"${product.name}" on ${where} links to no product page`);
    else if (pages.has(product.name) && destination(card.href) !== pages.get(product.name)) problems.push(`"${product.name}" on ${where} links to ${destination(card.href)} instead of ${pages.get(product.name)}`);
    if (card.src) bySrc.set(card.src, [...bySrc.get(card.src) ?? [], product.name]);
  }
  // Every product has a photo of its own, so two products showing one photo means one shows the wrong photo.
  for (const shared of bySrc.values()) if (shared.length > 1) problems.push(`${where} shows one photo for ${shared.map(name => `"${name}"`).join(" and ")}`);
  return problems;
}

/** What's wrong with how the open product page shows `product`: its name, its price and a working Add to cart button. */
async function productPageProblems(shopper, product) {
  const shown = shopper.locator("[data-product-page]");
  if (!await shown.count()) return ["shows no product"];
  const problems = [];
  const heading = await text(shown.locator("h1"));
  if (heading !== product.name) problems.push(`is headed "${heading || "nothing"}" instead of "${product.name}"`);
  const price = await text(shown.locator("[data-product-price]"));
  if (money(price) !== product.cents) problems.push(`shows ${price ? `"${price}"` : "no price"} instead of ${dollars(product.cents)}`);
  // Ready means wired to the cart and pressable; the journey never presses it.
  const add = shown.locator('[data-add-to-cart][data-guest-cart-ready="1"]').first();
  if (!await add.waitFor({ timeout: 15_000 }).then(() => true, () => false)) problems.push("has no working Add to cart button");
  else if (!await add.isEnabled()) problems.push("has an Add to cart button shoppers can't press");
  return problems;
}

/**
 * Gives one catalog product what the store lacks for it, as an owner would: adds it to Commerce when
 * it isn't there (or restores it when archived), saves its price and weight where they differ, chooses
 * its photo when Commerce shows none (uploading it first unless its batch did), and gives it a published
 * page in its category when it has none. Returns what it did, which is nothing when Commerce had it all.
 */
async function completeProduct(page, content, product, { inCommerce, card, shelved }) {
  const did = [];
  if (inCommerce) {
    await openProduct(page, product.name);
    const restore = page.getByRole("button", { name: "Restore product", exact: true });
    if (await restore.count()) {
      await restore.click();
      await confirmed(page, "Product restored");
      did.push("restored");
    }
  } else {
    await openAdmin(page, config.productsAdmin);
    await page.getByRole("textbox", { name: "Name", exact: true }).fill(product.name);
    await page.getByRole("textbox", { name: "SKU", exact: true }).fill(product.sku);
    await page.getByRole("radio", { name: "Physical", exact: true }).check();
    await page.getByRole("button", { name: "Add product", exact: true }).click();
    await confirmed(page, "Product added");
    did.push("added");
  }
  const id = await shownProductId(page);
  // Commerce shows the price and weight it stored, so only one that differs is saved, and reported.
  const price = (product.cents / 100).toFixed(2);
  if (await page.getByRole("textbox", { name: "Regular", exact: true }).inputValue() !== price) {
    await setPrice(page, price);
    did.push("price");
  }
  if (await page.getByRole("textbox", { name: "Weight (oz)", exact: true }).inputValue() !== String(product.ounces)) {
    await setWeight(page, product.ounces);
    did.push("weight");
  }
  // Every drawing of the product screen has the Images section's button, so it's read once that's there.
  if (!await page.getByRole("button", { name: /^(Choose|Change) image$/ }).waitFor({ timeout: 30_000 }).then(() => true, () => false)) {
    throw new Error("Commerce's product page has no Images section");
  }
  // Commerce says so in the image's place when the product has none, or when the Media library has lost
  // it. A photo Commerce already shows stays, since choosing it again can't change what the store shows.
  if (!inCommerce || await page.getByText(/^(No image|Image .+ is unavailable\.)$/).count()) {
    // A new product's photo came with its batch; one Commerce already had gets its photo only now.
    if (inCommerce) await uploadPhotos(content, [{ fileName: product.photo, label: product.name }]);
    await choosePhoto(page, product.photo);
    did.push("photo");
  }
  if (!card?.href || !shelved) {
    // A page an earlier run saved and never published is finished, not added again. A published page
    // the store doesn't show belongs to the owner to fix, so the test reports it and leaves it alone,
    // unless the product was archived, which kept the store from showing it; the later steps check it.
    const entry = await productPageEntry(content, product.name);
    if (entry?.published) {
      if (did.includes("restored")) return did;
      throw new Error(`its published page ${card?.href ? "isn't on its category page" : "isn't linked from the Shop list"}; check that page's Commerce product and category`);
    }
    if (!id) throw new Error("Commerce's product page shows no Product ID to link its page to");
    const details = { style: product.style, productId: id, category: product.category };
    if (entry) await finishProductPage(content, entry.editor, details);
    else await addProductPage(content, { title: product.name, ...details }, { lost: [] });
    did.push(entry ? "page published" : "page");
  }
  return did;
}

// A store with as many products as a real shop: the catalog's categories, each holding several products
// with their own price, weight, photo and page. The test adds what the store lacks and leaves it there for
// later runs, then checks that the Shop list, every category page and every product page show the whole
// catalog, and that the owner can still save a product with all of it in place.
test("Full catalog", { tag: "@next" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const plan = catalogPlan(config.catalog);
  const products = plan.flatMap(category => category.products);
  const names = new Set(products.map(product => product.name));
  note("catalog", `${plural(plan.length, "category", "categories")} of ${plural(plan[0].products.length, "product")} (${products.length} in all)`);
  // Checking takes a few seconds a product at the shopper's pace, so a big catalog gets that time on top of the usual limit.
  test.info().setTimeout(test.info().timeout + products.length * 10_000);
  // Media and Content work in a second tab, so Commerce keeps its product open in the first.
  const content = await newPage(page.context());
  const shopper = await shopperPage();
  // Commerce Products as the first step read it, where each category's View published link goes, and the Shop list's catalog cards.
  let listed = { names: new Map(), pages: 0 };
  // The store's Commerce, and whether it's late enough for the test to add to the catalog.
  let commerce = null;
  let canAdd = false;
  const categoryPaths = new Map();
  let shopFound = new Map();
  const soft = { soft: true };
  try {
    // Nothing after this can run without Commerce Products, so this step stops the journey.
    await step(page, "Commerce Products opens and lists every product", async () => {
      // A run just before this one may have left little of the store's allowance.
      await paceStore(PRODUCT_ROOM);
      listed = await listedProducts(page);
      // Commerce Products' address carries Commerce's id: /_emdash/admin/plugins/<id>/products.
      commerce = pluginVersion(await notePlugins(page), new URL(config.productsAdmin).pathname.match(/\/plugins\/([^/]+)/)?.[1]);
      canAdd = versionAtLeast(commerce, COMMERCE_FOR_CATALOGS);
      note("products in Commerce", total(listed.names));
      const have = products.filter(product => listed.names.has(product.name)).length;
      return `${plural(total(listed.names), "product")} on ${plural(listed.pages, "page")}; ${have} of the catalog's ${products.length} among them`;
    });

    // Product pages need their category, so a category the store can't publish stops the journey too.
    await step(content, "The catalog's categories are published", async () => {
      const added = [];
      for (const { title } of plan) {
        await paceStore(PAGE_ROOM);
        let view = await publishedLink(content, title, "categories");
        if (!view) {
          if (!canAdd) throw tooOld(commerce, `the category "${title}"`);
          // A category an earlier run saved but never published is published, not added again.
          const edit = content.getByRole("link", { name: `Edit ${title}`, exact: true });
          const saved = await edit.count();
          if (saved > 1) throw new Error(`EmDash lists ${saved} categories titled "${title}" and none of them is published, so the test can't tell which to publish; remove the extra one.`);
          if (saved) {
            await openAdmin(content, new URL(await edit.getAttribute("href"), config.store).href);
            await publish(content, "categories");
          } else await addCategory(content, title, { lost: [] });
          added.push(title);
          view = await publishedLink(content, title, "categories");
          if (!view) throw new Error(`After publishing "${title}", EmDash's list of categories doesn't show it as Published with a View published link.`);
        }
        categoryPaths.set(title, destination(view));
      }
      return plan.map(({ title }) => `${title} at ${categoryPaths.get(title)}${added.includes(title) ? " (added)" : ""}`).join(", ");
    });

    await step(page, "The owner adds what the catalog lacks", async () => {
      // A product is whole once Commerce has it, the Shop list shows it at its price with its photo and
      // a link to its page, and its category page lists it. Only what the store shows decides what to
      // add, so a list that won't open stops the step before anything is added.
      let shop;
      const shelves = new Map();
      try {
        shop = await readShop(shopper, names, { mayBeEmpty: true });
        for (const [title, path] of categoryPaths) shelves.set(title, await readCategory(shopper, path, names));
      } catch (error) {
        throw new Error(`Nothing was added, because the test couldn't read what the store shows: ${firstLine(error)}.`);
      }
      const shelved = product => shelves.get(product.category).has(product.name);
      const lacking = products.filter(product => {
        const card = shop.found.get(product.name)?.[0];
        return !listed.names.has(product.name) || !card || money(card.price) !== product.cents || card.image !== "photo" || !card.href || !shelved(product);
      });
      if (!lacking.length) return `nothing: Commerce and the store already show all ${products.length} catalog products`;
      if (!canAdd) throw tooOld(commerce, plural(lacking.length, "product"));
      // Commerce Products lists archived products too, so a name it lists twice may be an archived copy;
      // the test can't tell which is the catalog's and leaves both alone.
      const twins = lacking.filter(product => listed.names.get(product.name) > 1);
      const problems = twins.map(product => `"${product.name}": Commerce Products lists ${listed.names.get(product.name)} products by that name, so the test can't tell which to complete; rename the extra one`);
      const todo = lacking.filter(product => !twins.includes(product));
      // Adding takes about a minute a product, so a big catalog's first run gets that time on top of the usual limit.
      test.info().setTimeout(test.info().timeout + todo.length * 2 * 60_000);
      const added = [];
      const completed = [];
      // Products Commerce already had whole, which the store shows wrong anyway.
      const whole = [];
      for (let start = 0; start < todo.length; start += UPLOAD_BATCH) {
        const batch = todo.slice(start, start + UPLOAD_BATCH);
        // New products' photos go up together; a product Commerce has gets one only if its screen shows none.
        const photos = batch.filter(product => !listed.names.has(product.name));
        if (photos.length) await uploadPhotos(content, photos.map(product => ({ fileName: product.photo, label: product.name })), UPLOADS_ROOM);
        for (const product of batch) {
          await paceStore(PRODUCT_ROOM);
          // One product's trouble is recorded and the rest still get added.
          const state = { inCommerce: listed.names.has(product.name), card: shop.found.get(product.name)?.[0], shelved: shelved(product) };
          const did = await completeProduct(page, content, product, state)
            .catch(error => { problems.push(`"${product.name}": ${firstLine(error)}`); });
          if (did?.includes("added")) added.push(product.name);
          else if (did?.length) completed.push(`${product.name} (${did.join(", ")})`);
          else if (did) whole.push(product.name);
        }
      }
      const done = [
        ...added.length ? [`added ${added.length} (${short(added).join(", ")}), each with its price, weight, photo and a published page in its category`] : [],
        ...completed.length ? [`completed ${short(completed).join(", ")}`] : [],
        ...whole.length ? [`found nothing to add in Commerce for ${short(whole).join(", ")}, so the next steps report what the store shows wrong`] : [],
      ];
      if (problems.length) throw new Error(`${[...done, ...problems].join("; ")}.`);
      return done.join("; ");
    }, soft);

    await step(shopper, "The Shop list shows every catalog product with its own price and photo", async () => {
      const { count, found } = await readShop(shopper, names);
      shopFound = found;
      note("products in the Shop list", count);
      const problems = listProblems(found, products, "the Shop list");
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return `all ${products.length} catalog products, each at its own price with its own photo and a link to its page, among the ${count} the Shop list shows`;
    }, soft);

    await step(shopper, "Each category page lists its products with their own price and photo", async () => {
      const problems = [];
      const shown = [];
      // Each product's card links to the page its Shop card does, which the next step opens.
      const pages = new Map([...shopFound].filter(([, [card]]) => card.href).map(([name, [card]]) => [name, destination(card.href)]));
      for (const category of plan) {
        const path = categoryPaths.get(category.title);
        const found = await readCategory(shopper, path, names).catch(error => { problems.push(firstLine(error)); });
        if (!found) continue;
        problems.push(...listProblems(found, category.products, path, pages));
        // The other categories' products don't belong here.
        const strays = [...found.keys()].filter(name => !category.products.some(product => product.name === name));
        if (strays.length) problems.push(`${path} also lists ${strays.map(name => `"${name}"`).join(", ")}`);
        shown.push(`${path} lists its ${category.products.length}`);
      }
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return shown.join(", ");
    }, soft);

    await step(shopper, "Every catalog product's page opens with its name, price and Add to cart", async () => {
      // The Shop list's links are the pages to open, so without them there's one reason, not one per product.
      if (!shopFound.size) throw new Error("The Shop list couldn't be read or showed none of the catalog's products (see its step), so there was no product page to open.");
      const problems = [];
      for (const product of products) {
        const href = shopFound.get(product.name)?.[0]?.href;
        if (!href) {
          problems.push(`the Shop list links "${product.name}" to no page`);
          continue;
        }
        // A link to another site is followed there, where the request filter or the store check stops it.
        const target = destination(href);
        const failed = await openShopperPage(shopper, target).then(() => "", error => {
          const line = firstLine(error);
          return line.startsWith(target) ? line : `${target} didn't open (${line})`;
        });
        if (failed) problems.push(failed);
        else problems.push(...(await productPageProblems(shopper, product)).map(problem => `${target} ${problem}`));
      }
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return `all ${products.length} pages show the product's name and price and a working Add to cart button`;
    }, soft);

    const [first] = products;
    await step(page, "The owner saves a product's weight with the whole catalog in place", async () => {
      // A weight save once failed on a store with more than a handful of products, since each product
      // screen read the whole catalog; this is that save, with every page of Commerce Products read first.
      await paceStore(PRODUCT_ROOM);
      const now = await listedProducts(page);
      const missing = products.filter(product => !now.names.has(product.name)).map(product => `"${product.name}"`);
      if (missing.length) throw new Error(`Commerce Products doesn't list ${short(missing).join(", ")}.`);
      await openProduct(page, first.name);
      await setWeight(page, first.ounces);
      return `Commerce Products lists ${plural(total(now.names), "product")} on ${plural(now.pages, "page")}; "${first.name}" saved at ${first.ounces} oz`;
    }, soft);
  } finally {
    await closeShopper(shopper);
    await content.close();
  }
}));
