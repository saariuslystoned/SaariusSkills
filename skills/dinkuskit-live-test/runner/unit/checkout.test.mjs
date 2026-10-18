import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { after } from "node:test";

// checkout.mjs reads the run's settings as it loads, so this file gives it a throwaway proof folder and profile.
const dir = mkdtempSync(join(tmpdir(), "dinkus-checkout-"));
after(() => rmSync(dir, { recursive: true, force: true }));
Object.assign(process.env, {
  DINKUS_E2E_ENV_FILE: join(dir, "no-settings"),
  DINKUS_E2E_PROOF: dir,
  DINKUS_E2E_PROFILE: join(dir, "profile"),
});
const { stripeSession, thankYouShown } = await import("../support/checkout.mjs");

test("a Stripe Checkout address names its session, with or without Stripe's fragment", () => {
  assert.equal(stripeSession("https://checkout.stripe.com/c/pay/cs_test_a1B2c3#fidabc"), "cs_test_a1B2c3");
  assert.equal(stripeSession("https://checkout.stripe.com/c/pay/cs_live_Z9"), "cs_live_Z9");
});

test("no other address names a Stripe session", () => {
  for (const address of [
    "https://checkout.stripe.com.example/c/pay/cs_test_a1",
    "https://store.example/checkout/success?session_id=cs_test_a1",
    "https://checkout.stripe.com/c/pay/",
    "not an address",
    "",
  ]) assert.equal(stripeSession(address), null, address);
});

test("the thank-you page passes only with the order confirmed and the cart empty", () => {
  const confirmed = { shown: true, heading: "Thank you", confirmed: true, message: "Order confirmed.", items: 1, cart: 0 };
  assert.equal(thankYouShown(confirmed), '"Order confirmed." with 1 item(s) listed; cart empty');
  assert.throws(() => thankYouShown({ shown: false, heading: "Page not found" }), /without the store's order confirmation \("Page not found"\)/);
  assert.throws(() => thankYouShown({ ...confirmed, confirmed: false, heading: "We couldn't confirm your order", message: "Try again." }),
    /saw "We couldn't confirm your order: Try again\." instead of their order/);
  assert.throws(() => thankYouShown({ ...confirmed, cart: 1 }), /the cart shows 1 item\(s\)/);
  assert.throws(() => thankYouShown({ ...confirmed, cart: null }), /an unreadable number of item\(s\)/);
});
