import { get, newPage, test, expect, shopperPage, closeShopper } from "../support/browser.mjs";
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

const firstLine = error => String(error?.message ?? error).split("\n")[0];
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
 * The homepage's Shop list: how many products it lists, and its cards for the catalog's products. An
 * empty list proves nothing about the catalog when it says why it's empty, unless `mayBeEmpty` and it
 * only says the store lists no products yet.
 */
async function readShop(shopper, names, { mayBeEmpty = false } = {}) {
  await openShopperPage(shopper, "/");
  const catalog = shopper.locator("[data-commerce-catalog]");
  if (!await catalog.count()) throw new Error("The homepage has no Shop list.");
  const cards = catalog.locator("[data-commerce-product]");
  const count = await cards.count();
  const said = count ? "" : await text(catalog.locator(mayBeEmpty ? '[role="alert"]' : '[role="alert"], [data-commerce-empty]'));
  if (said) throw new Error(`The Shop list says "${said}".`);
  return { count, found: await catalogCards(cards, names) };
}

/** A category page's cards for the catalog's products. */
async function readCategory(shopper, path, names) {
  await openShopperPage(shopper, path);
  return catalogCards(shopper.locator("main").locator("[data-commerce-product], [data-merch-item]"), names);
}

/**
 * What's wrong with how a list page shows `products`: one it doesn't list or lists twice, one at
 * another price, without a photo of its own or a link to its page, or two showing the same photo.
 */
function listProblems(found, products, where) {
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
    if (card.src) bySrc.set(card.src, [...bySrc.get(card.src) ?? [], product.name]);
  }
  // Every product has a photo of its own, so two products showing one photo means one shows the wrong photo.
  for (const shared of bySrc.values()) if (shared.length > 1) problems.push(`${where} shows one photo for ${shared.map(name => `"${name}"`).join(" and ")}`);
  return problems;
}

/**
 * Gives one catalog product what the store lacks for it, as an owner would: adds it to Commerce when
 * it isn't there (or restores it when archived), saves its price and weight, chooses its photo when it
 * has none of its own, and gives it a published page in its category when it has none. Returns what it did.
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
  await setPrice(page, (product.cents / 100).toFixed(2));
  await setWeight(page, product.ounces);
  if (!inCommerce || card?.image !== "photo" || await page.getByText("No image", { exact: true }).count()) {
    await choosePhoto(page, product.photo);
    did.push("photo");
  }
  if (!card?.href || !shelved) {
    // A page an earlier run saved and never published is finished, not added again. A published page
    // the store doesn't show belongs to the owner to fix, so the test reports it and leaves it alone.
    const entry = await productPageEntry(content, product.name);
    if (entry?.published) {
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
  // Media and Content work in a second tab, so Commerce keeps its product open in the first.
  const content = await newPage(page.context());
  const shopper = await shopperPage();
  // Commerce Products as the first step read it, the store addresses of the categories, and the Shop list's catalog cards.
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
      listed = await listedProducts(page);
      commerce = pluginVersion(await notePlugins(page), new URL(config.productsAdmin).pathname.split("/")[4]);
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
          if (await edit.count()) {
            await openAdmin(content, new URL(await edit.getAttribute("href"), config.store).href);
            await publish(content, "categories");
          } else await addCategory(content, title, { lost: [] });
          added.push(title);
          view = await publishedLink(content, title, "categories");
          if (!view) throw new Error(`After publishing "${title}", EmDash's list of categories doesn't show it as Published with a View published link.`);
        }
        categoryPaths.set(title, new URL(view).pathname);
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
        throw new Error(`Nothing was added, because the test couldn't read what the store shows: ${firstLine(error)}`);
      }
      const shelved = product => shelves.get(product.category).has(product.name);
      const lacking = products.filter(product => {
        const card = shop.found.get(product.name)?.[0];
        return !listed.names.has(product.name) || !card || money(card.price) !== product.cents || card.image !== "photo" || !card.href || !shelved(product);
      });
      if (!lacking.length) return `nothing: Commerce and the store already show all ${products.length} catalog products`;
      if (!canAdd) throw tooOld(commerce, plural(lacking.length, "product"));
      // Adding takes about a minute a product, so a big catalog's first run gets that time on top of the usual limit.
      test.info().setTimeout(test.info().timeout + lacking.length * 2 * 60_000);
      const added = [];
      const completed = [];
      const problems = [];
      for (let start = 0; start < lacking.length; start += UPLOAD_BATCH) {
        const batch = lacking.slice(start, start + UPLOAD_BATCH);
        await paceStore(UPLOADS_ROOM);
        await uploadPhotos(content, batch.map(product => ({ fileName: product.photo, label: product.name })));
        for (const product of batch) {
          await paceStore(PRODUCT_ROOM);
          // One product's trouble is recorded and the rest still get added.
          const state = { inCommerce: listed.names.has(product.name), card: shop.found.get(product.name)?.[0], shelved: shelved(product) };
          const did = await completeProduct(page, content, product, state)
            .catch(error => { problems.push(`"${product.name}": ${firstLine(error)}`); });
          if (did?.includes("added")) added.push(product.name);
          else if (did) completed.push(`${product.name} (${did.join(", ") || "price and weight"})`);
        }
      }
      const done = [
        ...added.length ? [`added ${added.length} (${short(added).join(", ")}), each with its price, weight, photo and a published page in its category`] : [],
        ...completed.length ? [`completed ${short(completed).join(", ")}`] : [],
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
      for (const category of plan) {
        const path = categoryPaths.get(category.title);
        const found = await readCategory(shopper, path, names).catch(error => { problems.push(firstLine(error)); });
        if (!found) continue;
        problems.push(...listProblems(found, category.products, path));
        // The other categories' products don't belong here.
        const strays = [...found.keys()].filter(name => !category.products.some(product => product.name === name));
        if (strays.length) problems.push(`${path} also lists ${strays.map(name => `"${name}"`).join(", ")}`);
        shown.push(`${path} lists its ${category.products.length}`);
      }
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return shown.join(", ");
    }, soft);

    await step(shopper, "Every catalog product's page opens with its name, price and Add to cart", async () => {
      const problems = [];
      for (const product of products) {
        const href = shopFound.get(product.name)?.[0]?.href;
        if (!href) {
          problems.push(`the Shop list links "${product.name}" to no page`);
          continue;
        }
        await paceStore();
        const response = await get(shopper, new URL(href, config.store).href).catch(error => error);
        if (response instanceof Error) problems.push(`${href} didn't answer (${firstLine(response)})`);
        else if (response.status() !== 200) problems.push(`${href} answered HTTP ${response.status()}`);
        else {
          const html = await response.text();
          const lacks = [...html.includes(product.name) ? [] : ["its name"], ...html.includes(dollars(product.cents)) ? [] : [`its price ${dollars(product.cents)}`],
            ...html.includes("data-add-to-cart") ? [] : ["an Add to cart button"]];
          if (lacks.length) problems.push(`${href} shows no ${lacks.join(", ")}`);
        }
      }
      if (problems.length) throw new Error(`${problems.join("; ")}.`);
      return `all ${products.length} pages answered HTTP 200 with the product's name, its price and an Add to cart button`;
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
