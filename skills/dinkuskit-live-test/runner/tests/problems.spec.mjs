import { test, expect } from "../support/browser.mjs";
import {
  CaptchaShown, checkoutStatus, confirmCheckout, failBankCheck, leaveStripe, openCheckout, payOnStripe, requireTestMode, resumeCheckout,
  stopIfCaptcha, stripeRefusal, submitCard,
} from "../support/checkout.mjs";
import { stripeSession, thankYouShown } from "../support/checkout-text.mjs";
import { config } from "../support/env.mjs";
import { note, record } from "../support/proof.mjs";
import { numberOf, openOrder, orderShown, ordersListed, testOrders } from "../support/orders-admin.mjs";
import { openStorePage } from "../support/signin.mjs";
import { confirmed, notePlugins, openAdmin } from "../support/store-admin.mjs";
import { journey, step } from "../support/steps.mjs";

// Stripe's test cards that never take a payment, each a problem real shoppers run into, with the words
// of the message Stripe gives for it. The bank check (3D Secure) comes last, so a check the test
// can't get past costs no other card.
const REFUSED_CARDS = [
  { name: "A declined card is turned down with a clear message and no order", card: "4000000000000002", says: /card (has been|was) declined/i },
  { name: "A card without enough funds is turned down with a clear message and no order", card: "4000000000009995", says: /insufficient funds/i },
  {
    name: "A card that fails the bank's security check is turned down with a clear message and no order",
    card: "4000002760003184", says: /unable to authenticate/i, bankCheck: true,
  },
];

const ALREADY_PAID = "Stripe already took a payment for this checkout, so the test pays nothing more";

/**
 * Submits one refused card on Stripe Checkout and checks what follows: Stripe's message, and Commerce
 * still waiting for payment with no order. Sets `paid` when Stripe or Commerce shows a payment instead.
 */
async function refuse(page, shopper, { card, says, bankCheck }) {
  let answer;
  try {
    await submitCard(page, shopper.email, card);
    if (bankCheck) await failBankCheck(page);
    answer = await stripeRefusal(page, says, { bankCheck });
  } catch (error) {
    // A captcha stops the journey as it is, also one that made an action time out before anything
    // checked for it.
    if (error instanceof CaptchaShown) throw error;
    await stopIfCaptcha(page);
    // Whatever else went wrong on Stripe's page, a payment Commerce recorded is never paid again or
    // left open.
    if (await paidInCommerce(page)) {
      shopper.paid = true;
      // The proof keeps a step's first line, so the reason goes on that line.
      const reason = String(error?.message ?? error).split("\n")[0].replace(/\.?$/, ".");
      throw new Error(`${reason} Commerce reports the checkout paid, so the test pays nothing more.`);
    }
    throw error;
  }
  if (answer.paid) {
    shopper.paid = true;
    throw new Error("Stripe took the payment instead of turning the card down, so the test pays nothing more.");
  }
  const { checkout } = await checkoutStatus(page);
  if (!checkout) throw new Error(`Stripe said "${answer.message}", but Commerce gave no status for the checkout.`);
  if (checkout.order || checkout.state === "paid") {
    shopper.paid = true;
    throw new Error(`Stripe said "${answer.message}", but Commerce reports the checkout paid, so the test pays nothing more.`);
  }
  if (checkout.state !== "pending") throw new Error(`Stripe said "${answer.message}", but Commerce reports the checkout as "${checkout.state}", not still waiting for payment.`);
  return `Stripe said "${answer.message}"; Commerce still waits for payment, with no order`;
}

/** Whether Commerce reports this browser's checkout paid; false when it can't be asked. */
async function paidInCommerce(page) {
  const { checkout } = await checkoutStatus(page).catch(() => ({}));
  return Boolean(checkout?.order || checkout?.state === "paid");
}

/**
 * On the cart after leaving Stripe: the shopper presses "Check checkout status", and the cart says the
 * checkout is still open and links back to its Stripe page, while it won't start a second checkout.
 */
async function cartWayBack(page, shopper) {
  const at = new URL(page.url());
  if (at.origin !== config.store || at.pathname !== "/cart") await openStorePage(page, `${config.store}/cart`);
  const status = page.locator("[data-guest-cart-status]");
  const recheck = page.locator("[data-guest-cart-recover]");
  const resume = page.locator("[data-guest-cart-resume]");
  const says = async () => {
    const shown = (await status.innerText({ timeout: 5_000 }).catch(() => "")).trim();
    return shown ? `it says "${shown}"` : "it shows no message";
  };
  await expect.poll(async () => await resume.isVisible() || await recheck.isVisible(), { timeout: 45_000 }).toBe(true)
    .catch(async () => { throw new Error(`The cart offers neither "Check checkout status" nor a way back to Stripe; ${await says()}`); });
  if (!await resume.isVisible()) {
    await recheck.click();
    await resume.waitFor({ timeout: 30_000 })
      .catch(async () => { throw new Error(`After "Check checkout status" the cart offers no way back to the open Stripe checkout; ${await says()}`); });
  }
  const label = (await resume.innerText()).trim();
  const target = stripeSession(await resume.getAttribute("href") ?? "");
  if (!target) throw new Error(`The cart's "${label}" link doesn't go to Stripe Checkout.`);
  if (target !== shopper.session) throw new Error(`The cart's "${label}" link goes to a different Stripe checkout than the one the shopper left.`);
  // The open checkout keeps the cart locked, so the shopper can't start a second one.
  if (await page.locator("[data-guest-cart-checkout]").isEnabled()) throw new Error(`The cart links back to Stripe, but it also lets the shopper start a second checkout.`);
  return `the cart's "${label}" link goes back to the same Stripe checkout; ${await says()}`;
}

// A shopper's checkout going wrong: Stripe turns down cards that can't pay, the shopper leaves Stripe
// for the cart and comes back, and pays once with the test card. One checkout and one order per run,
// which the owner then completes so no open TEST order is left for Buy and ship to trip over.
test("Problems", { tag: "@running" }, journey(async ({ page }) => {
  expect(config.store, `Set DINKUS_E2E_STORE to the store's address (in ${config.settingsFile})`).not.toBe("");
  const soft = { soft: true };

  // The orders listed now are what shows that the refused cards made none, so this step stops the journey.
  let newestBefore;
  await step(page, "The owner can open Commerce Orders", async () => {
    await openAdmin(page, config.ordersAdmin);
    await ordersListed(page);
    await notePlugins(page);
    newestBefore = Math.max(0, ...(await testOrders(page)).map(order => order.number));
    return newestBefore ? `Commerce Orders opened; the newest TEST order is #${newestBefore}` : "Commerce Orders opened, with no TEST orders yet";
  });

  // The whole run works in one checkout, so without it the journey stops.
  const shopper = { paid: false };
  await step(page, "A shopper opens Stripe Checkout for one product", async () => {
    const opened = await openCheckout(page);
    Object.assign(shopper, { email: opened.email, session: stripeSession(page.url()) });
    if (!shopper.session) throw new Error("Stripe Checkout opened without a checkout session the test can follow.");
    // The whole journey stays in this session, so one that isn't in test mode stops it here, before any card.
    requireTestMode(page);
    return opened.resumed ? "the shopper went back to the Stripe Checkout an earlier run left open" : "Stripe Checkout opened for one product";
  });

  // Each refused card is soft, so one run reports every message. A captcha is the exception, here and
  // when the shopper leaves Stripe: nobody answers it for the test, so it stops the journey before
  // another card or the payment.
  const unlessCaptcha = { soft: error => !(error instanceof CaptchaShown) };
  for (const refused of REFUSED_CARDS) {
    if (shopper.paid) {
      record(refused.name, "SKIP", ALREADY_PAID);
      continue;
    }
    const passed = await step(page, refused.name, () => refuse(page, shopper, refused), unlessCaptcha);
    // A bank check left open would cover the page, and Stripe draws a fresh form on a reload.
    if (!passed && !shopper.paid && stripeSession(page.url())) await page.reload();
  }

  let wayBack;
  if (shopper.paid) {
    record("The shopper leaves Stripe by its back link and lands on the cart", "SKIP", ALREADY_PAID);
    record("The cart offers a way back to the same Stripe checkout", "SKIP", ALREADY_PAID);
  } else {
    await step(page, "The shopper leaves Stripe by its back link and lands on the cart", async () => {
      await leaveStripe(page);
      return "Stripe's back link opened the store's cart";
    }, unlessCaptcha);
    wayBack = await step(page, "The cart offers a way back to the same Stripe checkout", () => cartWayBack(page, shopper), soft);
  }

  // Without the payment there is no order to check, so this step stops the journey.
  let placed;
  if (shopper.paid) await step(page, "Commerce records the payment Stripe took", async () => {
    if (new URL(page.url()).origin === config.store) placed = await confirmCheckout(page);
    else {
      const { checkout } = await checkoutStatus(page);
      placed = { orderId: checkout?.order?.orderId ?? null, state: checkout?.state ?? "unknown", thankYou: null };
    }
    if (placed.orderId) note("Problems order", placed.orderId);
    if (placed.state !== "paid") throw new Error(`Commerce reports this checkout as "${placed.state}", not paid.`);
    if (!placed.orderId) throw new Error("Commerce's checkout status named no order.");
    return `Commerce recorded the payment for ${placed.orderId}`;
  });
  else await step(page, "The shopper goes back to Stripe and pays once with the 4242 test card", async () => {
    if (wayBack) await page.locator("[data-guest-cart-resume]").click();
    // With no way back on the cart, the test reopens the checkout's own Stripe page, as Buy and ship does after a failed run.
    else if (!await resumeCheckout(page)) throw new Error("Commerce no longer holds the shopper's checkout open, so there is nothing to pay; the test starts no other checkout.");
    await page.waitForURL(url => url.hostname === "checkout.stripe.com", { timeout: 60_000 });
    if (stripeSession(page.url()) !== shopper.session) throw new Error("The way back opened a different Stripe checkout than the one the shopper left; the test paid nothing.");
    await payOnStripe(page, shopper.email);
    placed = await confirmCheckout(page);
    if (placed.orderId) note("Problems order", placed.orderId);
    if (placed.state !== "paid") throw new Error(`Commerce reports this checkout as "${placed.state}", not paid.`);
    if (!placed.orderId) throw new Error("Commerce's checkout status named no order.");
    const how = wayBack ? "the shopper went back through the cart's link and paid" : "with no way back on the cart, the test reopened the checkout's Stripe page and the shopper paid";
    return `${how}; Commerce recorded the payment for ${placed.orderId}`;
  });

  if (!placed.thankYou) record("The thank-you page confirms the order and empties the cart", "SKIP", "Stripe never sent the shopper back to the store");
  else await step(page, "The thank-you page confirms the order and empties the cart", async () => thankYouShown(placed.thankYou), soft);

  let number;
  await step(page, "Commerce Orders lists one new order for the checkout, Processing", async () => {
    const found = await numberOf(page, placed.orderId, "Processing");
    number = found;
    note("Problems order number", `#${found}`);
    const added = (await testOrders(page)).filter(order => order.number > newestBefore).map(order => `#${order.number}`);
    if (added.length !== 1) throw new Error(`Commerce Orders lists ${added.length} TEST orders newer than #${newestBefore} (${added.join(", ")}), not just this checkout's #${found}.`);
    return `#${found} is Processing and the only new TEST order${shopper.paid ? "" : ", so the refused cards made none"}`;
  }, soft);

  if (!number) record("The owner marks the order completed, so the run leaves no order open", "SKIP", "Commerce Orders didn't list the order");
  else await step(page, "The owner marks the order completed, so the run leaves no order open", async () => {
    const before = await openOrder(page, number);
    // The test only ever completes TEST orders.
    if (!before.test) throw new Error(`Order #${number} isn't a TEST order, so the test leaves it alone.`);
    if (before.status !== "Processing") throw new Error(`Order #${number} shows ${before.status ?? "no status"}, not Processing, so it can't be marked completed.`);
    await page.getByRole("button", { name: "Complete order", exact: true }).click();
    // Nothing was sent, so the optional carrier and tracking number stay empty.
    await page.getByRole("textbox", { name: "Carrier (optional)", exact: true }).waitFor();
    await page.getByRole("button", { name: "Complete order", exact: true }).click();
    await confirmed(page, "Order completed");
    const after = await orderShown(page);
    if (after.status !== "Completed") throw new Error(`Commerce said "Order completed", but #${number} shows ${after.status ?? "no status"}.`);
    return `#${number} Completed, with no carrier or tracking number`;
  }, soft);
}));
