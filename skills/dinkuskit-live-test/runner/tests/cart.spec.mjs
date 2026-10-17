import { test, expect, shopperPage } from "../support/browser.mjs";
import { config } from "../support/env.mjs";
import { STORE_OPENS, openShopperPage, storeOpens } from "../support/shopper.mjs";
import { journey, step } from "../support/steps.mjs";
import { cartCount, cartTotal, dollars, money } from "../support/storefront-text.mjs";

const quick = { timeout: 5_000 };
// innerText also reads an element the page hides, so only the first one a shopper can see counts.
const text = async (locator) => (await locator.filter({ visible: true }).first().innerText(quick).catch(() => "")).replace(/\s+/g, " ").trim();
const items = count => count === null ? "nothing readable" : `${count} item${count === 1 ? "" : "s"}`;

/** The header cart link's item count, once it reads `expected` or a few seconds have passed; null when unreadable. */
async function headerCount(page, expected) {
  const read = async () => cartCount(await page.locator("[data-guest-cart-nav]").first().getAttribute("aria-label", quick).catch(() => null));
  await expect.poll(read, quick).toBe(expected).catch(() => {});
  return read();
}

/** The price a shopper pays: the sale price when the page shows one. */
async function shownPrice(scope) {
  const sale = scope.locator("[data-sale-price]").filter({ visible: true });
  return text(await sale.count() ? sale : scope.locator("[data-regular-price]"));
}

/** The Add to cart button once the page has wired it to the cart and it can be pressed; null when there is none. */
async function ready(buttons) {
  if (!await buttons.count()) return null;
  const button = buttons.first();
  await expect(button).toHaveAttribute("data-guest-cart-ready", "1", { timeout: 15_000 }).catch(() => {});
  return await button.getAttribute("data-guest-cart-ready") === "1" && await button.isEnabled() ? button : null;
}

/** The product on the page the browser is on, with its Add to cart; null when the page offers none. */
async function onProductPage(page, path) {
  const button = await ready(page.locator("[data-add-to-cart]"));
  const product = page.locator("[data-product-page]");
  return button && { where: path, name: await text(product.locator("h1")), price: await shownPrice(product.locator("[data-product-price]")), button };
}

/**
 * A product a new shopper can add: DINKUS_E2E_PRODUCT_PATH's, else the first in the Shop list with
 * a working Add to cart, on its own page or, for a product with no page, on its Shop card. Leaves
 * the browser on the page with the button.
 */
async function findProduct(page) {
  if (config.productPath) {
    await openShopperPage(page, config.productPath);
    const found = await onProductPage(page, config.productPath);
    if (!found) throw new Error(`${config.productPath} offers no working Add to cart.`);
    return found;
  }
  const cards = await page.locator("[data-commerce-catalog] [data-commerce-product]")
    .evaluateAll(all => all.map(card => ({ id: card.getAttribute("data-commerce-product"), href: card.getAttribute("href") })));
  if (!cards.length) throw new Error("The homepage's Shop list shows no products to add.");
  // A product page that won't open is Storefront's finding; Cart tries the next product.
  const unopened = [];
  for (const { id, href } of cards) {
    if (href) {
      const opened = await openShopperPage(page, href).then(() => true, error => { unopened.push(error.message.replace(/\.$/, "")); return false; });
      const found = opened && await onProductPage(page, href);
      if (found) return found;
      continue;
    }
    if (new URL(page.url()).pathname !== "/") await openShopperPage(page, "/");
    const card = page.locator(`[data-commerce-catalog] [data-commerce-product="${id}"]`);
    const button = await ready(card.locator("[data-add-to-cart]"));
    if (button) return { where: "the homepage's Shop list", name: await text(card.locator("h3")), price: await shownPrice(card), button };
  }
  throw new Error(`None of the Shop list's ${cards.length} products offers a working Add to cart${unopened.length ? ` (${unopened.join("; ")})` : ""}.`);
}

/** The cart's lines once their product details have loaded: the name, unit price and quantity a shopper sees. */
async function cartLines(page) {
  const lines = page.locator("[data-guest-cart-line]");
  await expect.poll(() => lines.evaluateAll(all => all.length > 0 && all.every(line => line.querySelector("[data-regular-price], [data-sale-price]"))), { timeout: 15_000 })
    .toBe(true).catch(() => {});
  return lines.evaluateAll(all => all.map(line => {
    // Text the page hides counts as missing, as it is to a shopper.
    const shown = el => el.getClientRects().length && getComputedStyle(el).visibility !== "hidden" ? el.innerText.trim() : "";
    return {
      name: [...line.querySelectorAll("h2")].map(shown).find(Boolean) ?? "",
      price: [...line.querySelectorAll("[data-sale-price]"), ...line.querySelectorAll("[data-regular-price]")].map(shown).find(Boolean) ?? "",
      quantity: line.querySelector("[data-guest-cart-qty]")?.value ?? "",
    };
  }));
}

/** What the cart tells the shopper about itself (a price it couldn't load, a quantity it refused), for a finding. */
async function cartSays(page) {
  const said = await text(page.locator("[data-guest-cart-status]"));
  return said ? ` (the cart says "${said}")` : "";
}

/** Checks the cart's total against its lines: each shown unit price times its quantity, added up. */
async function totalIsRight(page) {
  const lines = await cartLines(page);
  if (!lines.length) throw new Error(`The cart lists nothing to total${await cartSays(page)}.`);
  const unreadable = lines.filter(line => money(line.price) === null || !/^\d+$/.test(line.quantity));
  if (unreadable.length) throw new Error(`The cart shows no price or quantity for ${unreadable.map(line => `"${line.name}"`).join(", ")}${await cartSays(page)}.`);
  const expected = lines.reduce((sum, line) => sum + money(line.price) * Number(line.quantity), 0);
  const sum = lines.map(line => `${line.quantity} × ${line.price}`).join(" + ");
  const total = cartTotal(await page.locator("[data-guest-cart]").first().innerText());
  if (!total) throw new Error(`The cart shows no total; it lists ${sum}, which comes to ${dollars(expected)}.`);
  if (total.cents !== expected) throw new Error(`The cart's ${total.label.toLowerCase()} reads ${dollars(total.cents)}, but ${sum} comes to ${dollars(expected)}.`);
  return `${total.label} ${dollars(total.cents)} for ${sum}`;
}

// A shopper's cart: add a product, change its quantity and remove it, with the cart total right each time.
test("Cart", { tag: "@next" }, journey(async () => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const page = await shopperPage();
  // Once the cart has a product every step is soft, so one finding never hides the next.
  const soft = { soft: true };
  try {
    await step(page, STORE_OPENS, () => storeOpens(page));

    // A cart with nothing in it has nothing to change, so this step stops the journey too.
    await step(page, "Add to cart puts the product in the cart", async () => {
      const product = await findProduct(page);
      await product.button.click();
      const status = product.button.locator("xpath=..").locator("[data-add-to-cart-status]");
      if (!await expect(status).toHaveText(/added to cart/i, { timeout: 10_000 }).then(() => true, () => false)) {
        const said = await text(status);
        throw new Error(`Add to cart on ${product.where} ${said ? `said "${said}"` : "showed no message"} instead of "Added to cart."`);
      }
      const count = await headerCount(page, 1);
      if (count !== 1) throw new Error(`After Add to cart the header's cart shows ${items(count)}, not 1 item.`);
      await openShopperPage(page, "/cart");
      const lines = await cartLines(page);
      if (lines.length !== 1) throw new Error(`After adding one product the cart lists ${lines.length} lines${await cartSays(page)}.`);
      const [line] = lines;
      const problems = [];
      if (line.quantity !== "1") problems.push(`quantity ${line.quantity || "none"}`);
      if (money(line.price) === null) problems.push("no price");
      else if (money(product.price) !== null && money(line.price) !== money(product.price)) problems.push(`${line.price}, though ${product.where} showed ${product.price}`);
      if (problems.length) throw new Error(`The cart lists "${line.name}" with ${problems.join(" and ")}${await cartSays(page)}.`);
      return `"${product.name}" at ${product.price} from ${product.where}: the header shows 1 item, and the cart lists "${line.name}" at ${line.price}, quantity 1`;
    });

    await step(page, "The cart total matches the item's price", () => totalIsRight(page), soft);

    await step(page, "Changing the quantity updates the cart", async () => {
      const quantity = page.locator("[data-guest-cart-qty]").first();
      await quantity.fill("2");
      // The cart applies a typed quantity when the field loses focus, as when a shopper tabs on.
      await quantity.press("Tab");
      const problems = [];
      const count = await headerCount(page, 2);
      if (count !== 2) problems.push(`the header's cart shows ${items(count)}`);
      const said = await cartSays(page);
      // The cart is kept in the shopper's browser, so coming back shows the same quantity.
      await page.reload();
      const [line] = await cartLines(page);
      if (line?.quantity !== "2") problems.push(`after a reload the cart shows quantity ${line?.quantity || "none"}`);
      if (problems.length) throw new Error(`The quantity was set to 2, but ${problems.join(" and ")}${said}.`);
      return "the cart keeps quantity 2 after a reload, and the header shows 2 items";
    }, soft);

    await step(page, "The cart total follows the new quantity", () => totalIsRight(page), soft);

    await step(page, "Removing the item empties the cart", async () => {
      await page.locator("[data-guest-cart-remove]").first().click();
      const lines = page.locator("[data-guest-cart-line]");
      const empty = page.locator("[data-guest-cart-empty]");
      const problems = [];
      if (!await expect(lines).toHaveCount(0, quick).then(() => true, () => false)) problems.push(`the cart still lists ${await lines.count()} line(s)`);
      if (!await empty.isVisible()) problems.push("the cart doesn't say it's empty");
      const count = await headerCount(page, 0);
      if (count !== 0) problems.push(`the header's cart shows ${items(count)}`);
      await page.reload();
      // The cart draws its lines from the browser's saved cart when its script runs, and shows the empty message then.
      await empty.waitFor({ timeout: 10_000 }).catch(() => {});
      if (await lines.count()) problems.push("after a reload the cart lists the item again");
      if (problems.length) throw new Error(`After Remove, ${problems.join(", ")}.`);
      return `the cart says "${(await text(empty)).split(/(?<=\.)\s/)[0]}" and the header shows no items, also after a reload`;
    }, soft);
  } finally {
    await page.context().browser().close();
  }
}, { profile: false }));
