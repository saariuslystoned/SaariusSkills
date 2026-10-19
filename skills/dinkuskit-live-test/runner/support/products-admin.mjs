import { newPage, expect } from "./browser.mjs";
import { config } from "./env.mjs";
import { MEDIA_ROOM, PICKER_PAGE_ROOM, paceStore } from "./pace.mjs";
import { confirmed, openAdmin } from "./store-admin.mjs";
import { quick, text } from "./storefront-page.mjs";

// What an owner does with products in the store admin: Commerce Products, the Media library, and
// EmDash's product pages and categories. Manage products and Full catalog share these.

const firstLine = error => String(error?.message ?? error).split("\n")[0];

/** Answers the question the admin asks before an action with one of its buttons. */
export async function answer(page, question, choice) {
  // Commerce's question carries no name of its own, so it's found by what it asks.
  const dialog = page.getByRole("dialog").or(page.getByRole("alertdialog")).filter({ hasText: question }).first();
  if (!await dialog.waitFor({ timeout: 15_000 }).then(() => true, () => false)) throw new Error(`The admin never asked "${question}"`);
  await dialog.getByRole("button", { name: choice, exact: true }).click();
}

/**
 * Opens a product in Commerce Products, paging through the list until it finds it. False only when
 * every page was read and none lists it; a page that won't open or turn fails instead.
 */
export async function findProduct(page, name) {
  await openAdmin(page, config.productsAdmin);
  for (;;) {
    await page.getByRole("button", { name: "Add product", exact: true }).waitFor({ timeout: 30_000 });
    const open = page.getByRole("button", { name: `Open ${name}`, exact: true });
    if (await open.count()) {
      await open.click();
      await page.getByRole("heading", { name, level: 2 }).waitFor({ timeout: 30_000 });
      return true;
    }
    if (!await nextPage(page)) return false;
  }
}

/**
 * Every product Commerce Products lists, read page by page: how many rows carry each name, and how
 * many pages the list took.
 */
export async function listedProducts(page) {
  await openAdmin(page, config.productsAdmin);
  const names = new Map();
  for (let pages = 1; ; pages++) {
    await page.getByRole("button", { name: "Add product", exact: true }).waitFor({ timeout: 30_000 });
    const opens = await page.getByRole("button", { name: /^Open / })
      .evaluateAll(buttons => buttons.map(button => (button.getAttribute("aria-label") || button.textContent).trim()));
    for (const name of opens.map(open => open.replace(/^Open /, ""))) names.set(name, (names.get(name) ?? 0) + 1);
    if (!await nextPage(page)) return { names, pages };
  }
}

/** Turns Commerce Products to its next page; false when the shown page is the last. */
async function nextPage(page) {
  const next = page.getByRole("button", { name: "Next", exact: true });
  if (!await next.count()) return false;
  const before = await listedRows(page);
  await next.click();
  await expect.poll(() => listedRows(page), { timeout: 30_000 }).not.toEqual(before);
  return true;
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
export async function openProduct(page, name) {
  if (!await findProduct(page, name)) throw new Error(`Commerce Products doesn't list "${name}".`);
}

/** Makes sure the saved profile's page shows this product in Commerce, opening it again when a step left it elsewhere. */
export async function onProduct(page, name) {
  if (await page.getByRole("heading", { name, level: 2 }).isVisible() && await page.getByText("Commerce / Products", { exact: true }).isVisible()) return;
  await openProduct(page, name);
}

/** The Product ID the open Commerce product page shows, which a product page's "Commerce product" field takes; "" when it shows none. */
export async function shownProductId(page) {
  const id = await text(page.locator("main pre, main code"));
  return /^[\w-]{8,}$/.test(id) ? id : "";
}

/** Saves the open Commerce product's regular price. */
export async function setPrice(page, regular) {
  await page.getByRole("textbox", { name: "Regular", exact: true }).fill(regular);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await confirmed(page, "Product saved");
}

/** Saves the open Commerce product's weight in ounces, and checks Commerce kept it. */
export async function setWeight(page, ounces) {
  const weight = page.getByRole("textbox", { name: "Weight (oz)", exact: true });
  await weight.fill(String(ounces));
  await page.getByRole("button", { name: "Save weight", exact: true }).click();
  await confirmed(page, "Weight saved");
  // Commerce draws the product again from what it stored, so the field now shows the saved weight.
  await expect(weight, "Commerce didn't keep the weight").toHaveValue(String(ounces), { timeout: 15_000 });
}

/** Archives the open Commerce product, answering the question Commerce asks first. */
export async function archive(page, name) {
  await onProduct(page, name);
  const button = page.getByRole("button", { name: "Archive product", exact: true });
  if (!await button.count()) throw new Error("Commerce's product page has no Archive product.");
  await button.click();
  await answer(page, `Archive ${name}?`, "Archive");
  await confirmed(page, "Product archived");
}

/** Uploads a plain square photo to the Media library, as an owner does before choosing it for a product. */
export async function uploadPhoto(page, fileName, label) {
  await uploadPhotos(page, [{ fileName, label }]);
}

/**
 * Uploads several plain square photos to the Media library in one go, each with its own label drawn on
 * it. The browser draws them, so the test carries no image files. A label makes its photo its own: the
 * Media library keeps one copy of identical files, under the first one's name. It first waits until
 * `room` more store requests fit, which for a single photo is MEDIA_ROOM.
 */
export async function uploadPhotos(page, photos, room = MEDIA_ROOM) {
  const painter = await newPage(page.context());
  const files = [];
  for (const { fileName, label } of photos) {
    await painter.setContent(`<div style="width:480px;height:480px;display:grid;place-items:center;background:linear-gradient(135deg,#2a6,#246);color:#fff;font:600 28px sans-serif">${label}</div>`);
    files.push({ name: fileName, mimeType: "image/png", buffer: await painter.locator("div").screenshot() });
  }
  await painter.close();
  await paceStore(room);
  await openAdmin(page, `${config.store}/_emdash/admin/media`);
  await page.getByRole("button", { name: "Upload Files" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Upload to Library" });
  const [chooser] = await Promise.all([page.waitForEvent("filechooser"), dialog.getByRole("button", { name: "Browse files", exact: true }).click()]);
  await chooser.setFiles(files);
  for (const { name } of files) {
    const upload = dialog.getByRole("listitem").filter({ hasText: name });
    if (!await expect(upload).toContainText("Complete", { timeout: 60_000 }).then(() => true, () => false)) {
      throw new Error(`The Media library didn't take the photo${files.length > 1 ? ` ${name}` : ""}: "${await text(upload) || "no upload listed"}".`);
    }
  }
  await dialog.getByRole("button", { name: "Done" }).click();
}

/**
 * Chooses the Media library photo `fileName` as the open Commerce product's image. Commerce's picker
 * lists the library twelve photos at a time, so it turns the picker's pages until it finds the photo.
 */
export async function choosePhoto(page, fileName) {
  await page.getByRole("button", { name: /^(Choose|Change) image$/ }).click();
  const use = page.getByRole("button", { name: `Use ${fileName}`, exact: true });
  const shown = () => page.getByRole("button", { name: /^Use / }).evaluateAll(buttons => buttons.map(button => button.textContent));
  for (;;) {
    if (!await page.getByRole("button", { name: /^Use / }).first().waitFor({ timeout: 30_000 }).then(() => true, () => false)) {
      throw new Error("Commerce's image picker shows no photos to use.");
    }
    if (await use.count()) break;
    const next = page.getByRole("button", { name: "Next", exact: true });
    if (!await next.count()) throw new Error(`Commerce's image picker doesn't offer ${fileName}.`);
    const before = await shown();
    await paceStore(PICKER_PAGE_ROOM);
    await next.click();
    await expect.poll(shown, { timeout: 30_000 }).not.toEqual(before);
  }
  await use.click();
  await confirmed(page, "Image saved");
}

/** An EmDash editor's field by its label; an editor without it fails with that plain reason. */
export async function field(page, label, editor) {
  const box = page.getByRole("textbox", { name: label, exact: true });
  if (!await box.waitFor({ timeout: 30_000 }).then(() => true, () => false)) throw new Error(`${editor} has no "${label}" field.`);
  return box;
}

/** The slug EmDash makes from the title, once it has made one. */
export async function slugOf(page) {
  const slug = page.getByRole("textbox", { name: "Slug", exact: true });
  await expect.poll(() => slug.inputValue(), quick).not.toBe("");
  return slug.inputValue();
}

/**
 * Saves a new EmDash entry and returns its editor's address. When the editor doesn't move there, the
 * address comes from EmDash's answer to the save; null when neither says, though the entry may exist.
 */
export async function saveNew(page, collection) {
  const saved = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname === `/_emdash/api/content/${collection}`, { timeout: 30_000 });
  saved.catch(() => {});
  await page.getByRole("button", { name: "Save", exact: true }).click();
  if (await page.waitForURL(url => !url.pathname.endsWith("/new"), { timeout: 30_000 }).then(() => true, () => false)) return page.url();
  const id = await saved.then(response => response.json()).then(body => body?.data?.item?.id, () => null);
  return typeof id === "string" && id ? `${config.store}/_emdash/admin/content/${collection}/${id}` : null;
}

/** Publishes the open EmDash entry; a refusal fails with the reason the admin gives. */
export async function publish(page, collection) {
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
 * Adds a category and publishes it. `made` learns its store address before the save and its editor
 * once saved (or that the save left it somewhere unknown), so a caller can take it off the store again.
 */
export async function addCategory(content, title, made) {
  await openAdmin(content, `${config.store}/_emdash/admin/content/categories/new`);
  await (await field(content, "Category title", "The new category editor")).fill(title);
  made.categoryPath = `/categories/${await slugOf(content)}`;
  made.category = await saveNew(content, "categories") ?? "";
  if (!made.category) {
    made.lost.push(`category "${title}"`);
    throw new Error(`Saving the category "${title}" never opened its editor, and EmDash's answer didn't say where it is.`);
  }
  await publish(content, "categories").catch(error => { throw new Error(`Publishing the category failed: ${firstLine(error)}`); });
}

/**
 * Adds a product page for the Commerce product `productId` in the category `category`, drawn in
 * `style`, and publishes it. `made` learns its address and editor as `addCategory` tells them.
 */
export async function addProductPage(content, { title, style, productId, category }, made) {
  await openAdmin(content, `${config.store}/_emdash/admin/content/products/new`);
  const editor = "The new product page editor";
  await (await field(content, "Product title", editor)).fill(title);
  await fillProductPage(content, { style, productId }, editor);
  made.pagePath = `/products/${await slugOf(content)}`;
  made.page = await saveNew(content, "products") ?? "";
  if (!made.page) {
    made.lost.push(`product page "${title}"`);
    throw new Error(`Saving the product page "${title}" never opened its editor, and EmDash's answer didn't say where it is.`);
  }
  await fileAndPublish(content, category);
}

/**
 * Finishes the saved but unpublished product page whose editor is at `editor`: it gets the Commerce
 * product `productId`, the style `style` and the category `category`, and is published.
 */
export async function finishProductPage(content, editor, { style, productId, category }) {
  await openAdmin(content, editor);
  await fillProductPage(content, { style, productId }, "The product page editor");
  await fileAndPublish(content, category, { mayBeFiled: true });
}

async function fillProductPage(content, { style, productId }, editor) {
  await (await field(content, "Illustration style (TEE, HOODIE, CAP, or BEANIE)", editor)).fill(style);
  await (await field(content, "Commerce product (optional)", editor)).fill(productId);
}

/** Puts the open product page in `category` unless it already is, saves it and publishes it. */
async function fileAndPublish(content, category, { mayBeFiled = false } = {}) {
  const filed = content.getByRole("button", { name: `Remove ${category}` });
  if (!mayBeFiled || !await filed.waitFor({ timeout: 5_000 }).then(() => true, () => false)) {
    await content.getByRole("button", { name: "Add reference" }).click();
    const picker = content.getByRole("dialog", { name: "Add references" });
    await picker.getByPlaceholder("Search content...").fill(category);
    await picker.locator("label").filter({ hasText: category }).first().click({ timeout: 15_000 });
    await picker.getByRole("button", { name: "Add selected" }).click();
    await filed.waitFor({ timeout: 15_000 });
  }
  const save = content.getByRole("button", { name: "Save", exact: true });
  if (await save.isEnabled()) {
    await save.click();
    await expect(save).toBeDisabled({ timeout: 15_000 }).catch(() => {});
  }
  await publish(content, "products").catch(error => { throw new Error(`Publishing the product page failed: ${firstLine(error)}`); });
}

/**
 * EmDash's `collection` entry titled `title`, as its list shows it once searched for: its editor's
 * address, and where its "View published" link goes when the list shows it as Published (else null).
 * Null when the list has no entry by that title.
 */
async function listedEntry(page, title, collection) {
  await openAdmin(page, `${config.store}/_emdash/admin/content/${collection}`);
  await page.getByRole("searchbox", { name: `Search ${collection}` }).fill(title);
  const edit = page.getByRole("link", { name: `Edit ${title}`, exact: true });
  // The list answers the search with the entry's row or says it has no results, so a missing entry isn't waited out.
  const none = page.getByText(`No results for "${title}"`, { exact: true });
  if (!await edit.first().or(none).first().waitFor({ timeout: 15_000 }).then(() => true, () => false) || !await edit.count()) return null;
  const view = page.getByRole("row").filter({ has: page.getByRole("cell", { name: "Published", exact: true }) })
    .getByRole("link", { name: `View published ${title}`, exact: true }).first();
  const href = await view.count() ? await view.getAttribute("href") : null;
  return { editor: new URL(await edit.first().getAttribute("href"), config.store).href, view: href === null ? null : new URL(href, config.store).href };
}

/**
 * The full address the "View published" link in EmDash's list of `collection` entries (product pages
 * unless named) goes to for this title, once the list shows the entry as Published; null when it doesn't.
 */
export async function publishedLink(page, title, collection = "products") {
  return (await listedEntry(page, title, collection))?.view ?? null;
}

/**
 * EmDash's product page titled `title`: its editor's address and whether it's published; null when
 * EmDash's list of product pages has none.
 */
export async function productPageEntry(page, title) {
  const entry = await listedEntry(page, title, "products");
  return entry && { editor: entry.editor, published: entry.view !== null };
}

/** Moves an EmDash entry to the Trash, so the store stops showing it. */
export async function trash(page, url) {
  await openAdmin(page, url);
  await page.getByRole("button", { name: "Move to Trash" }).click();
  await answer(page, "Move to Trash?", "Move to Trash");
  await page.waitForURL(next => !next.href.startsWith(url.split("?")[0]), { timeout: 30_000 });
}
