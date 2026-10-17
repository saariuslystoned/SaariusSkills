import { expect } from "@playwright/test";
import { config } from "./env.mjs";

// The storefront's own localStorage keys (template-store guest-cart intent.ts and checkout-protocol.ts).
const CART_KEY = "dinkus.guest-cart.v1";
const CHECKOUT_KEY = "dinkus.guest-checkout.v1";
const HUMAN_WAIT_MS = 10 * 60 * 1000;

/**
 * Buys one physical product as a guest, the way a shopper does: product page, Add to cart,
 * /cart with a US delivery address, Stripe's hosted Checkout with the 4242 test card, and back.
 *
 * Returns { number, orderId, checkoutToken, state }. The storefront never learns the short
 * order number: Commerce's guest checkout status carries only `order:<attempt id>`, and Orders
 * numbers the order (1001, 1002...) when it keeps its copy. So `number` is normally null and the
 * caller finds the newest TEST order in Commerce Orders; Ship's order links end in `orderId`, so
 * that also picks the order there. `checkoutToken` is the Stripe Checkout Session id from the
 * return URL, and `state` is Commerce's checkout state ("paid" once it has recorded the order).
 */
export async function placeTestOrder(page) {
  const email = config.shopper.email || config.ownerEmail;
  if (!email) throw new Error("Set DINKUS_E2E_SHOPPER_EMAIL (or DINKUS_E2E_OWNER_EMAIL) for the checkout contact.");

  // The saved profile keeps an earlier run's cart and checkout; a leftover checkout locks the cart.
  await page.goto(config.store + "/");
  await page.evaluate(keys => keys.forEach(key => localStorage.removeItem(key)), [CART_KEY, CHECKOUT_KEY]);
  const path = config.productPath || await findPhysicalProduct(page);

  await page.goto(new URL(path, config.store).href);
  await orFail(page.locator('[data-add-to-cart][data-guest-cart-ready="1"]').waitFor({ timeout: 15_000 }), async () =>
    `${path} offers no Add to cart: ${await texts(page, ".product-detail__notice, [data-product-status]")}`);
  await page.locator("[data-add-to-cart]").click();
  await orFail(expect(page.locator("[data-add-to-cart-status]")).toHaveText(/added to cart/i, { timeout: 10_000 }), async () =>
    `Add to cart failed: ${await texts(page, "[data-add-to-cart-status]")}`);

  // The checkout button turns on once the cart's catalog snapshot and Commerce's prepare both answer.
  await page.goto(config.store + "/cart");
  const checkout = page.locator("[data-guest-cart-checkout]");
  await orFail(expect(checkout).toBeEnabled({ timeout: 45_000 }), async () => `The cart never offered checkout: ${await cartMessage(page)}`);
  await orFail(page.locator("[data-guest-cart-delivery]").waitFor({ timeout: 5_000 }), async () =>
    `The cart asks for no delivery address, so ${path} is not a physical product; set DINKUS_E2E_PRODUCT_PATH.`);
  const { shopper } = config;
  await page.locator("[data-guest-cart-email]").fill(email);
  await page.locator("[data-guest-cart-delivery-name]").fill(shopper.name);
  await page.locator("[data-guest-cart-delivery-line1]").fill(shopper.line1);
  await page.locator("[data-guest-cart-delivery-city]").fill(shopper.city);
  await page.locator("[data-guest-cart-delivery-region]").fill(shopper.region);
  await page.locator("[data-guest-cart-delivery-postal-code]").fill(shopper.postalCode);
  await page.locator("[data-guest-cart-delivery-country]").selectOption("US");
  await checkout.click();
  await orFail(page.waitForURL(url => url.hostname === "checkout.stripe.com", { timeout: 60_000 }), async () =>
    `The store did not open Stripe Checkout: ${await cartMessage(page)}`);

  await payOnStripe(page, email);
  // Payments sends Stripe back to <store>/checkout/success?session_id=cs_test_...; that page may not be deployed.
  const sessionId = new URL(page.url()).searchParams.get("session_id");
  const status = await settle(page);
  const shown = await page.locator("main").innerText({ timeout: 5_000 }).catch(() => "");
  // A number only, never the digits that start a UUID ("Order 1234abcd-...").
  const number = shown.match(/(?:#|\bOrder\s+#?)(\d{4,})(?![\w-])/)?.[1] ?? null;
  return {
    number,
    orderId: status.checkout?.order?.orderId ?? (status.attemptId ? `order:${status.attemptId}` : null),
    checkoutToken: sessionId ?? status.attemptId ?? null,
    state: status.checkout?.state ?? "unknown",
  };
}

/** With no DINKUS_E2E_PRODUCT_PATH: the first catalog product that can be added and is not digital. */
async function findPhysicalProduct(page) {
  const paths = await page.locator("a[data-product-link]").evaluateAll(links => links.map(link => link.getAttribute("href")));
  for (const path of paths) {
    await page.goto(new URL(path, config.store).href);
    const id = await page.locator("[data-add-to-cart]").getAttribute("data-add-to-cart", { timeout: 3_000 }).catch(() => null);
    if (!id) continue;
    const response = await page.request.get(`${config.store}/api/guest-cart/snapshot?ids=${encodeURIComponent(id)}`);
    const product = response.ok() ? (await response.json()).products?.[0] : null;
    if (product?.found && product.fulfillment !== "digital") return path;
  }
  throw new Error(`No product on ${config.store} can be added to the cart and shipped; set DINKUS_E2E_PRODUCT_PATH.`);
}

/** Stripe's hosted Checkout keeps its fields on the page itself, not in frames, under stable ids. */
async function payOnStripe(page, email) {
  const card = page.locator("#cardNumber");
  // A card-only session shows the card form at once; with more methods on, Card is an accordion row.
  const cardRow = page.locator('[data-testid="card-accordion-item-button"]');
  await card.or(cardRow).first().waitFor({ timeout: 60_000 });
  if (!await card.isVisible()) await cardRow.click();
  // A prefilled email is shown as text, not an input.
  const emailInput = page.locator("#email");
  if (await emailInput.isVisible() && await emailInput.isEditable() && !await emailInput.inputValue()) await emailInput.fill(email);
  await card.pressSequentially("4242424242424242");
  await page.locator("#cardExpiry").pressSequentially("1234");
  await page.locator("#cardCvc").pressSequentially("123");
  const name = page.locator("#billingName");
  if (await name.isVisible()) await name.fill(config.shopper.name);
  const country = page.locator("#billingCountry");
  if (await country.isVisible()) await country.selectOption("US");
  const zip = page.locator("#billingPostalCode");
  if (await zip.isVisible()) await zip.fill(config.shopper.postalCode);
  // Link's "save my information" would also ask for a phone number.
  const saveInfo = page.locator("#enableStripePass");
  if (await saveInfo.isVisible() && await saveInfo.isChecked()) await saveInfo.uncheck();
  await page.getByTestId("hosted-payment-submit-button").or(page.locator(".SubmitButton")).first().click();

  const back = url => url.origin === config.store;
  await page.waitForURL(back, { timeout: 120_000 }).catch(async () => {
    const problem = await texts(page, '[role="alert"], .FieldError');
    if (config.headless) throw new Error(`Stripe did not send the shopper back to the store: ${problem}`);
    console.log("\n>>> Finish paying on the Stripe page in this test's browser window (card 4242 4242 4242 4242, 12/34, CVC 123).\n");
    await page.waitForURL(back, { timeout: HUMAN_WAIT_MS });
  });
}

/**
 * Asks Commerce for this checkout's status until it leaves "pending". Status is also what makes
 * Commerce check the payment and record the order, so this runs even when the return page cannot.
 */
async function settle(page) {
  const plugin = config.ordersAdmin.match(/\/plugins\/([^/]+)\//)?.[1];
  const routes = ["/api/checkout/status", ...(plugin ? [`/_emdash/api/plugins/${plugin}/checkout/guest/status`] : [])];
  const deadline = Date.now() + 90_000;
  let last;
  do {
    last = await page.evaluate(readStatus, { key: CHECKOUT_KEY, routes });
    if (!last.attemptId || (last.checkout && last.checkout.state !== "pending")) return last;
    await page.waitForTimeout(5_000);
  } while (Date.now() < deadline);
  return last;
}

// Runs in the store page: the capability the cart saved is the only key to the checkout's status.
const readStatus = async ({ key, routes }) => {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(key) ?? "null"); } catch {}
  const attemptId = saved?.attemptId ?? null;
  if (!saved?.capability) return { attemptId };
  for (const route of routes) {
    try {
      const response = await fetch(route, {
        method: "POST", cache: "no-store", redirect: "error",
        headers: { "content-type": "application/json", accept: "application/json", "x-commerce-guest-capability": saved.capability },
        body: JSON.stringify(attemptId ? { attemptId } : {}),
      });
      const body = await response.json();
      const value = body?.success === true ? body.data : body;
      if (value?.ok) return { attemptId, checkout: value.checkout };
    } catch {}
  }
  return { attemptId };
};

/** Awaits `work`; on failure throws `reason()` instead, so the proof report's one line says what happened. */
async function orFail(work, reason) {
  try { return await work; } catch { throw new Error(await reason()); }
}

async function texts(page, selector) {
  const found = await page.locator(selector).allInnerTexts().catch(() => []);
  return found.map(text => text.trim()).filter(Boolean).join(" / ") || "no message on the page";
}

const cartMessage = page => texts(page, "[data-guest-cart-status], [data-guest-cart-checkout-reason], [data-store-demo-banner]");
