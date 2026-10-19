import assert from "node:assert/strict";
import test from "node:test";
import { catalogPlan } from "../support/catalog.mjs";
import { accessQuery, clean, extract } from "../support/mail-patterns.mjs";
import { parseSettings } from "../support/settings-file.mjs";
import { describePlugins, pluginVersion, versionAtLeast } from "../support/store-plugins.mjs";
import { cantBuyClaims, cartCount, cartTotal, dollars, money } from "../support/storefront-text.mjs";

test("the DinkusKit sign-in link survives quoted-printable and HTML encoding", () => {
  const body = [
    "Sign in to DinkusKit",
    '<a href=3D"https://dinkuskit.com/api/auth/magic-link/verify?token=3Dtok_1&amp;callbackURL=3D%2Fac=',
    'count">Sign in</a>',
  ].join("\n");
  assert.deepEqual(extract.dinkuskit(clean(body)), ["https://dinkuskit.com/api/auth/magic-link/verify?token=tok_1&callbackURL=%2Faccount"]);
});

test("the Access code is the six digits after the word code, never a colour", () => {
  const body = '<td style="color:#333333">Here is your login code for example.cloudflareaccess.com:</td><td style="color: #445566">482913</td>';
  assert.deepEqual(extract.access(clean(body)), ["482913"]);
});

test("the Access code is found after PIN on its own line", () => {
  assert.deepEqual(extract.access("Your one-time PIN\n\n105729\n\nIt expires in 10 minutes."), ["105729"]);
});

test("longer numbers, dates and ids are not codes", () => {
  assert.deepEqual(extract.access("Order 1234567 placed 2026-10-17, ref ab123456, id=654321"), []);
});

test("the Access code search looks only for the store under test", () => {
  assert.equal(accessQuery("https://beta.store.example"), 'from:(notify.cloudflare.com OR cloudflareaccess.com) newer_than:1h "beta.store.example"');
  assert.equal(accessQuery("http://localhost:4321"), 'from:(notify.cloudflare.com OR cloudflareaccess.com) newer_than:1h "localhost"');
  assert.equal(accessQuery(""), "from:(notify.cloudflare.com OR cloudflareaccess.com) newer_than:1h");
});

test("the settings file takes only DINKUS_E2E_ keys", () => {
  const settings = parseSettings([
    "# this machine's test store",
    "DINKUS_E2E_STORE=https://store.example",
    "export DINKUS_E2E_SITE_ID='site-1'",
    'DINKUS_E2E_ACCESS_MAIL_QUERY="from:a@example.com newer_than:1h"',
    "DINKUS_E2E_PRODUCT_PATH=/p?x=1",
    "PATH=/tmp/evil",
    "NODE_OPTIONS=--require /tmp/evil.js",
    "",
  ].join("\n"));
  assert.deepEqual(settings, {
    DINKUS_E2E_STORE: "https://store.example",
    DINKUS_E2E_SITE_ID: "site-1",
    DINKUS_E2E_ACCESS_MAIL_QUERY: "from:a@example.com newer_than:1h",
    DINKUS_E2E_PRODUCT_PATH: "/p?x=1",
  });
});

test("the proof names each running plugin by its Registry slug and version", () => {
  const body = { success: true, data: { items: [
    { id: "r_commerce", name: "DinkusKit Commerce", version: "0.2.2", enabled: true, source: "registry", registrySlug: "dinkus-commerce" },
    { id: "r_payments", name: "DinkusKit Payments", version: "0.2.8", enabled: true, source: "registry", registrySlug: "dinkus-payments" },
    { id: "r_old", name: "Old plugin", version: "0.1.0", enabled: false, source: "registry", registrySlug: "old-plugin" },
    { id: "forms", name: "Forms", version: "1.0.0", enabled: true, source: "config" },
  ] } };
  assert.equal(describePlugins(body), "dinkus-commerce 0.2.2, dinkus-payments 0.2.8, Forms 1.0.0");
  assert.throws(() => describePlugins({ success: false }), /no items/);
});

test("the header cart count reads the storefront's cart link label", () => {
  assert.equal(cartCount("Cart"), 0);
  assert.equal(cartCount("Cart, 1 item"), 1);
  assert.equal(cartCount("Cart, 12 items"), 12);
  assert.equal(cartCount(null), null);
  assert.equal(cartCount("Basket"), null);
});

test("a product notice that says it can't be bought is a can't-buy claim", () => {
  const product = ["Cart test mug", "$12.50", "In stock", "Add to cart", "This product can\u2019t be bought right now."].join("\n");
  assert.deepEqual(cantBuyClaims(product), ["This product can\u2019t be bought right now."]);
  assert.deepEqual(cantBuyClaims("Checkout is unavailable right now, so this product can't be bought."), ["Checkout is unavailable right now, so this product can't be bought."]);
  assert.deepEqual(cantBuyClaims("It cannot be bought in stores."), ["It cannot be bought in stores."]);
  assert.deepEqual(cantBuyClaims("Bought together often. Can be bought as a gift."), []);
});

test("a page's claims that shoppers can't buy are found sentence by sentence", () => {
  const homepage = [
    "Demo / Test Store — Synthetic demonstration. Purchases and checkout are unavailable.",
    "Browse the current catalog.",
    "Eligible products can be added to your cart. Checkout is unavailable, so no purchase will be completed.",
    "Shop",
    "Product browsing is available. Checkout is not available yet.",
  ].join("\n");
  assert.deepEqual(cantBuyClaims(homepage), [
    "Purchases and checkout are unavailable.",
    "Checkout is unavailable, so no purchase will be completed.",
    "Checkout is not available yet.",
  ]);
  assert.deepEqual(cantBuyClaims("In stock\nAdd to cart\nThis is an editorial preview. It is not purchasable."), ["It is not purchasable."]);
  assert.deepEqual(cantBuyClaims("Apparel\nExplore the apparel category. Editorial previews cannot be purchased.\nE2E Tee\nPreview only · not purchasable"), [
    "Editorial previews cannot be purchased.",
    "Preview only · not purchasable",
  ]);
  assert.deepEqual(cantBuyClaims("Cart\nYour cart is empty.\nCheckout unavailable\nCheckout is not available yet."), [
    "Checkout unavailable",
    "Checkout is not available yet.",
  ]);
  assert.deepEqual(cantBuyClaims("Test checkout is available. No live purchases.\nIn stock\nAdd to cart"), []);
  assert.deepEqual(cantBuyClaims(null), []);
});

test("prices read as cents, whatever their commas and cents", () => {
  assert.equal(money("$12.50"), 1250);
  assert.equal(money("Now $15 (was $20.00)"), 1500);
  assert.equal(money("$1,234.5"), 123450);
  assert.equal(money("$ 1234.05"), 123405);
  assert.equal(money("Free"), null);
  assert.equal(money(undefined), null);
  assert.equal(dollars(123405), "$1234.05");
  assert.equal(dollars(0), "$0.00");
});

test("the cart's total is its subtotal, on the label's line or the next", () => {
  const cart = ["Cart", "Cart test mug", "$12.50", "Quantity", "Remove", "Subtotal", "$25.00", "Shipping", "$5.00", "Total", "$30.00"].join("\n");
  assert.deepEqual(cartTotal(cart), { label: "Subtotal", cents: 2500 });
  assert.deepEqual(cartTotal("Order total: $30.00"), { label: "Order total", cents: 3000 });
  assert.deepEqual(cartTotal("Estimated total (2 items) $41.20"), { label: "Estimated total", cents: 4120 });
});

test("a cart that lists only unit prices shows no total", () => {
  const cart = [
    "Cart", "Cart test mug", "$12.50", "Quantity", "Remove",
    "Totals are confirmed at checkout", "Checkout", "Commerce will confirm the final amount and availability.",
  ].join("\n");
  assert.equal(cartTotal(cart), null);
  assert.equal(cartTotal("Total"), null);
});

test("a product whose name starts with Total is no cart total", () => {
  assert.equal(cartTotal(["Cart", "Total Eclipse Mug", "$15.00", "Quantity", "Remove"].join("\n")), null);
  assert.equal(cartTotal("Subtotal sale mug $15.00"), null);
  assert.equal(cartTotal(["Subtotal", "Free shipping over $50.00"].join("\n")), null);
  const cart = ["Cart", "Total Eclipse Mug", "$15.00", "Quantity", "Remove", "Subtotal", "$30.00"].join("\n");
  assert.deepEqual(cartTotal(cart), { label: "Subtotal", cents: 3000 });
});

test("the plugin list gives a plugin's version by its runtime id", () => {
  const body = { data: { items: [{ id: "r_beta", registrySlug: "dinkus-commerce-beta", version: "0.3.0-beta.4" }, { id: "r_old", version: 2 }] } };
  assert.equal(pluginVersion(body, "r_beta"), "0.3.0-beta.4");
  assert.equal(pluginVersion(body, "r_old"), null);
  assert.equal(pluginVersion(body, "r_none"), null);
  assert.equal(pluginVersion(null, "r_beta"), null);
});

test("a release comes after its betas, and an unreadable version is never late enough", () => {
  assert.equal(versionAtLeast("0.3.0-beta.4", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.0-beta.10", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.0", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.1-beta.1", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.0-beta.3", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.2.2", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast(null, "0.3.0-beta.4"), false);
  // Any pre-release reads, in semver's order.
  assert.equal(versionAtLeast("0.3.0-rc.1", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.1-alpha.0", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.0-alpha.9", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.3.0-beta", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.3.0-beta.4.1", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.0-7", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.3.0-beta.4", "0.3.0-7"), true);
  // Build details don't count.
  assert.equal(versionAtLeast("0.3.0+abc123", "0.3.0-beta.4"), true);
  assert.equal(versionAtLeast("0.3.0-beta.3+abc123", "0.3.0-beta.4"), false);
  // A pre-release or build part can't be empty.
  assert.equal(versionAtLeast("0.3.0-beta.", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.3.0-beta..4", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.3.0-.beta", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.3.0+", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("latest", "0.3.0-beta.4"), false);
  assert.equal(versionAtLeast("0.3", "0.3.0-beta.4"), false);
});

test("the catalog's products each have their own name, SKU, price and photo, in their category", () => {
  const plan = catalogPlan("3x8");
  assert.deepEqual(plan.map(category => category.title), ["Catalog Tees", "Catalog Hoodies", "Catalog Caps"]);
  const products = plan.flatMap(category => category.products);
  assert.equal(products.length, 24);
  for (const key of ["name", "sku", "cents", "photo"]) assert.equal(new Set(products.map(product => product[key])).size, 24, key);
  const all = catalogPlan("4x50").flatMap(category => category.products);
  assert.equal(new Set(all.map(product => product.cents)).size, 200);
  assert.deepEqual(products[0], { name: "Catalog Tee 01", sku: "CATALOG-TEE-01", cents: 1800, ounces: 6, photo: "catalog-tee-01.png", category: "Catalog Tees", style: "TEE" });
  assert.equal(products[23].name, "Catalog Cap 08");
  assert.equal(products[23].category, "Catalog Caps");
  // No name is the start of another, so a search for one finds only it.
  const big = catalogPlan("1x50").flatMap(category => category.products).map(product => product.name);
  assert.equal(big.filter(name => big.some(other => other !== name && other.startsWith(name))).length, 0);
});

test("a catalog size the catalog can't take is refused, naming the sizes it can", () => {
  for (const size of ["", "3", "0x8", "5x8", "3x0", "3x51", "three by eight"]) assert.throws(() => catalogPlan(size), /from 1x1 to 4x50, such as 3x8/, size);
  assert.equal(catalogPlan(" 4 X 2 ").length, 4);
});
