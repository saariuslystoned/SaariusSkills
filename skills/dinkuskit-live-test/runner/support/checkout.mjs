import { newPage } from "./browser.mjs";
import { expect } from "@playwright/test";
import { config } from "./env.mjs";
import { openStorePage } from "./signin.mjs";
import { cartCount } from "./storefront-text.mjs";

// The storefront's own localStorage keys (template-store guest-cart intent.ts and checkout-protocol.ts).
const CART_KEY = "dinkus.guest-cart.v1";
const CHECKOUT_KEY = "dinkus.guest-checkout.v1";
const HUMAN_WAIT_MS = 10 * 60 * 1000;
// The Add to cart button findPhysicalProduct chose, when the page shows more than one.
let productId = null;

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
  const { email } = await openCheckout(page);
  await payOnStripe(page, email);
  return confirmCheckout(page);
}

/**
 * Takes a guest shopper to Stripe's hosted Checkout for one physical product: product page, Add to
 * cart, /cart with a US delivery address, then Continue to secure checkout. Returns the checkout
 * contact's email, and `resumed` when the browser already had a checkout pending in Commerce and
 * went back to its Stripe session instead.
 */
export async function openCheckout(page) {
  const email = config.shopper.email || config.ownerEmail;
  if (!email) throw new Error("Set DINKUS_E2E_SHOPPER_EMAIL (or DINKUS_E2E_OWNER_EMAIL) for the checkout contact.");

  let path = config.productPath || null;
  // Never two checkouts at once: a checkout an earlier run left pending in Commerce is paid on its
  // own Stripe session instead of starting another.
  const resumed = await resumeCheckout(page);
  if (!resumed) {
    // The saved profile keeps an earlier run's cart and checkout; a leftover checkout locks the cart.
    await page.evaluate(keys => keys.forEach(key => localStorage.removeItem(key)), [CART_KEY, CHECKOUT_KEY]);
    path = config.productPath || await findPhysicalProduct(page);

    await page.goto(new URL(path, config.store).href);
    await orFail(page.locator('[data-add-to-cart][data-guest-cart-ready="1"]').first().waitFor({ timeout: 15_000 }), async () =>
      `${path} offers no Add to cart: ${await texts(page, ".product-detail__notice, [data-product-status]")}`);
    await page.locator(productId ? `[data-add-to-cart="${productId}"]` : "[data-add-to-cart]").first().click();
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
  }
  return { email, resumed };
}

/**
 * Goes back to the Stripe page of the checkout this browser left pending in Commerce, as a shopper
 * returning to it would. False, leaving the browser on the store's homepage, when there is none.
 */
export async function resumeCheckout(page) {
  // A store behind Cloudflare Access sends the browser to Access's login once the saved sign-in lapses.
  await openStorePage(page, config.store + "/");
  const earlier = await page.evaluate(readStatus, { key: CHECKOUT_KEY, routes: statusRoutes() });
  const resume = earlier.checkout?.state === "pending" ? earlier.checkout.redirectUrl : null;
  if (!resume || new URL(resume).hostname !== "checkout.stripe.com") return false;
  await page.goto(resume);
  return true;
}

/**
 * Once Stripe has sent the shopper back to the store: what the thank-you page shows, and Commerce's
 * word on the checkout. See placeTestOrder for what it returns.
 */
export async function confirmCheckout(page) {
  // Payments sends Stripe back to <store>/checkout/success?session_id=cs_test_...
  const sessionId = new URL(page.url()).searchParams.get("session_id");
  // What the shopper sees comes first: the test's own status call below would record the order
  // even when the thank-you page can't.
  const thankYou = await readThankYou(page);
  const status = await settle(page);
  const shown = await page.locator("main").innerText({ timeout: 5_000 }).catch(() => "");
  // A number only, never the digits that start a UUID ("Order 1234abcd-...").
  const number = shown.match(/(?:#|\bOrder\s+#?)(\d{4,})(?![\w-])/)?.[1] ?? null;
  return {
    number,
    orderId: status.checkout?.order?.orderId ?? (status.attemptId ? `order:${status.attemptId}` : null),
    checkoutToken: sessionId ?? status.attemptId ?? null,
    state: status.checkout?.state ?? "unknown",
    thankYou,
  };
}

/**
 * The store's thank-you page as the shopper sees it once its own status check has answered:
 * heading, message, whether the order is shown, and the cart count in the header. While it says
 * the checkout is still pending, it presses "Check status again" the way a shopper would.
 */
async function readThankYou(page) {
  // Every read here is optional. The runner sets no action timeout, so without a short one a page
  // missing this markup would hold the order step, and the label and Completed checks after it,
  // until the 30-minute test timeout.
  const quick = { timeout: 5_000 };
  const root = page.locator("[data-guest-checkout-return]");
  const heading = async () => (await page.locator("main h1").first().innerText(quick).catch(() => "")).trim();
  if (!await root.count()) return { shown: false, heading: await heading() };
  const status = root.locator("[data-guest-checkout-return-status]");
  const recheck = root.locator("[data-guest-checkout-status-retry]");
  for (let presses = 0; ; presses++) {
    await expect(status).not.toHaveText(/^Checking the saved checkout status/, { timeout: 30_000 }).catch(() => {});
    if (presses === 4 || !await recheck.isVisible() || !await recheck.isEnabled(quick).catch(() => false)) break;
    await page.waitForTimeout(5_000);
    if (!await recheck.click(quick).then(() => true, () => false)) break;
  }
  return {
    shown: true,
    heading: await heading(),
    message: (await status.innerText(quick).catch(() => "")).trim(),
    confirmed: await root.locator("[data-guest-checkout-order]").isVisible(),
    items: await root.locator("[data-guest-checkout-order-items] li").count(),
    cart: cartCount(await page.locator("[data-guest-cart-nav]").first().getAttribute("aria-label", quick).catch(() => null)),
  };
}

/**
 * With no DINKUS_E2E_PRODUCT_PATH: the first catalog product that can be added and is not digital.
 * Product pages come first; a storefront whose shop cards carry Add to cart but no product links
 * falls back to the page it is on, remembering which button to press.
 */
async function findPhysicalProduct(page) {
  const listing = new URL(page.url()).pathname;
  const paths = await page.locator("a[data-product-link]").evaluateAll(links => links.map(link => link.getAttribute("href")));
  for (const path of [...paths, listing]) {
    await page.goto(new URL(path, config.store).href);
    const ids = await page.locator("[data-add-to-cart]").evaluateAll(buttons => buttons.map(button => button.getAttribute("data-add-to-cart")));
    for (const id of ids.filter(Boolean)) {
      const response = await page.request.get(`${config.store}/api/guest-cart/snapshot?ids=${encodeURIComponent(id)}`);
      const product = response.ok() ? (await response.json()).products?.[0] : null;
      if (product?.found && product.fulfillment !== "digital") { productId = id; return path; }
    }
  }
  throw new Error(`No product on ${config.store} can be added to the cart and shipped; set DINKUS_E2E_PRODUCT_PATH.`);
}

/** Pays on Stripe's hosted Checkout with the 4242 test card and waits for Stripe to send the shopper back. */
export async function payOnStripe(page, email) {
  await submitCard(page, email, "4242424242424242");
  const back = url => url.origin === config.store;
  await page.waitForURL(back, { timeout: 120_000 }).catch(async () => {
    const problem = await texts(page, '[role="alert"], .FieldError');
    if (await captchaShown(page)) throw new CaptchaShown();
    if (config.headless) throw new Error(`Stripe did not send the shopper back to the store: ${problem}`);
    console.log("\n>>> Finish paying on the Stripe page in this test's browser window (card 4242 4242 4242 4242, 12/34, CVC 123).\n");
    await page.waitForURL(back, { timeout: HUMAN_WAIT_MS });
  });
}

/**
 * Fills Stripe's hosted Checkout with one of Stripe's test cards and submits it. Stripe keeps the
 * fields on the page itself, not in frames, under stable ids.
 */
export async function submitCard(page, email, cardNumber) {
  requireTestMode(page);
  await orCaptcha(page, fillCard(page, email, cardNumber));
}

/** Only ever a TEST session: its URL carries a cs_test_ session id. Anything else stops the run unpaid. */
export function requireTestMode(page) {
  if (!/\/cs_test_/.test(new URL(page.url()).pathname)) throw new Error("Stripe opened a session that is not in test mode; nothing was paid.");
}

async function fillCard(page, email, cardNumber) {
  const card = page.locator("#cardNumber");
  // A card-only session shows the card form at once; with more methods on, Card is an accordion row.
  const cardRow = page.locator('[data-testid="card-accordion-item-button"]');
  // Stripe also renders the accordion button, hidden, when Card is already open, and it comes first
  // in the page, so `.or(...).first()` would wait on the hidden button: wait until either is visible.
  await expect.poll(async () => await card.isVisible() || await cardRow.isVisible(), { timeout: 60_000 }).toBe(true);
  if (!await card.isVisible()) await cardRow.click();
  // A prefilled email is shown as text, not an input.
  const emailInput = page.locator("#email");
  if (await emailInput.isVisible() && await emailInput.isEditable() && !await emailInput.inputValue()) await emailInput.fill(email);
  await retype(card, cardNumber);
  await retype(page.locator("#cardExpiry"), "1234");
  await retype(page.locator("#cardCvc"), "123");
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
}

/** Types into one of Stripe's card fields, emptying it first: after Stripe turns a card down, its fields can still hold that card. */
async function retype(field, value) {
  if (await field.inputValue()) await field.clear();
  await field.pressSequentially(value);
}

/**
 * After a card Stripe should turn down: Stripe's message saying why, as the shopper reads it. Returns
 * { paid: true } instead when Stripe took the payment and sent the shopper back to the store.
 */
export async function stripeRefusal(page, says) {
  const deadline = Date.now() + 60_000;
  for (;;) {
    if (new URL(page.url()).origin === config.store) return { paid: true };
    if (await captchaShown(page)) throw new CaptchaShown();
    const shown = await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "");
    const message = shown.split("\n").map(line => line.trim()).find(line => says.test(line));
    if (message) return { message };
    if (Date.now() > deadline) throw new Error(`Stripe showed no message saying why it turned the card down: ${await texts(page, '[role="alert"], .FieldError')}`);
    await page.waitForTimeout(1_000);
  }
}

/**
 * Fails Stripe's test bank check (3D Secure) as a shopper who can't verify would. Stripe's test page
 * opens in frames inside Checkout and offers Complete and Fail. Returns at once if Stripe takes the
 * payment without asking, which stripeRefusal then reports.
 */
export async function failBankCheck(page) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (new URL(page.url()).origin === config.store) return;
    if (await captchaShown(page)) throw new CaptchaShown();
    for (const frame of page.frames()) {
      for (const fail of [frame.locator("#test-source-fail-3ds"), frame.getByRole("button", { name: /^Fail( authentication)?$/i })]) {
        if (await fail.first().isVisible().catch(() => false)) return fail.first().click();
      }
    }
    await page.waitForTimeout(1_000);
  }
  throw new Error("Stripe never showed its test bank check with a Fail button.");
}

/** Leaves Stripe Checkout unpaid by its link back to the store: Payments gives Stripe the store's cart as the way back. */
export async function leaveStripe(page) {
  await orCaptcha(page, followBackLink(page));
}

async function followBackLink(page) {
  const back = page.locator(`a[href^="${config.store}/cart"]:visible`).first();
  await orFail(back.waitFor({ timeout: 15_000 }), async () => "Stripe's page shows no link back to the store.");
  await back.click();
  // A Stripe address carries the session, so only a store page is named by its path.
  await orFail(page.waitForURL(url => url.origin === config.store && url.pathname === "/cart", { timeout: 30_000 }), async () => {
    const at = new URL(page.url());
    return `Stripe's link back led to ${at.origin === config.store ? at.pathname : at.hostname}, not the store's cart.`;
  });
}

// A visible captcha is for a person to answer, never the test.
const captchaShown = page => page.locator('iframe[title*="hCaptcha challenge"]').isVisible().catch(() => false);

/** Throws CaptchaShown when Stripe has a captcha up. */
export async function stopIfCaptcha(page) {
  if (await captchaShown(page)) throw new CaptchaShown();
}

/**
 * Awaits `work`, actions on Stripe's page. A captcha over the page can make a click time out, or catch
 * it so nothing happens, before anything looks for the captcha, so when `work` fails with one up,
 * throws CaptchaShown instead.
 */
async function orCaptcha(page, work) {
  try {
    return await work;
  } catch (error) {
    await stopIfCaptcha(page);
    throw error;
  }
}

/** Stripe showed a captcha. Nobody answers it for the test, so a journey that meets one stops unpaid. */
export class CaptchaShown extends Error {
  constructor() {
    super("Stripe showed a captcha challenge; stopped without answering it.");
    this.name = "CaptchaShown";
  }
}

/** Commerce's status for the checkout this browser saved, read from a store page opened beside the shopper's. */
export async function checkoutStatus(page) {
  const storePage = await newPage(page.context());
  try {
    await openStorePage(storePage, config.store + "/");
    return await storePage.evaluate(readStatus, { key: CHECKOUT_KEY, routes: statusRoutes() });
  } finally {
    await storePage.close();
  }
}

/**
 * Asks Commerce for this checkout's status until it leaves "pending". Status is also what makes
 * Commerce check the payment and record the order, so this runs even when the thank-you page cannot.
 */
async function settle(page) {
  const routes = statusRoutes();
  const deadline = Date.now() + 90_000;
  let last;
  do {
    last = await page.evaluate(readStatus, { key: CHECKOUT_KEY, routes });
    if (!last.attemptId || (last.checkout && last.checkout.state !== "pending")) return last;
    await page.waitForTimeout(5_000);
  } while (Date.now() < deadline);
  return last;
}

/** Commerce's guest checkout status routes: the store's own proxy, then the plugin route. */
function statusRoutes() {
  const plugin = config.ordersAdmin.match(/\/plugins\/([^/]+)\//)?.[1];
  return ["/api/checkout/status", ...(plugin ? [`/_emdash/api/plugins/${plugin}/checkout/guest/status`] : [])];
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
