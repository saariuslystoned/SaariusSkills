import assert from "node:assert/strict";
import test from "node:test";
import { authorizeHref, nextPress, readStatusText, redact, showsSecret, statusPages } from "../support/payments-status.mjs";

const store = "https://store.example";
const account = "https://dinkuskit.com";
const connectLine = "Connect payments: Not complete. Connect your DinkusKit account to check payment setup. No Payments service endpoint is configured.";
const connectedLine = "Connect payments: Connected: Stripe test mode. Test card payments work at checkout. Real customer payments need a live Stripe connection, which isn't set up yet.";

test("the admin menu's Payments status links name each status page once", () => {
  assert.deepEqual(statusPages([
    "/_emdash/admin/plugins/dinkus-payments/status",
    `${store}/_emdash/admin/plugins/dinkus-payments/status`,
    "https://store.example/_emdash/admin/plugins/r_sffx6l4z6mpqliki/status",
  ], store), [
    `${store}/_emdash/admin/plugins/dinkus-payments/status`,
    `${store}/_emdash/admin/plugins/r_sffx6l4z6mpqliki/status`,
  ]);
});

test("no other link counts as Payments status", () => {
  assert.deepEqual(statusPages([
    "https://other.example/_emdash/admin/plugins/dinkus-payments/status",
    "/_emdash/admin/plugins/dinkus-payments/status?connection_id=abc",
    "/_emdash/admin/plugins/dinkus-payments/status#top",
    "/_emdash/admin/plugins/dinkus-payments/settings",
    "/_emdash/admin/status",
    "http://[not a url",
  ], store), []);
});

test("the known connect line asks for Connect and a verified test connection does not", () => {
  const asking = readStatusText(`Payment setup\nNot ready to sell\n${connectLine}\nPlace a test order: Not complete. Connect payments first, then place a test order.`);
  assert.equal(asking.header, true);
  assert.equal(asking.asksToConnect, true);
  assert.equal(asking.connectedTest, false);
  const connected = readStatusText(`Payment setup\nConnected: Stripe test mode\n${connectedLine}`);
  assert.equal(connected.asksToConnect, false);
  assert.equal(connected.connectedTest, true);
  const other = readStatusText("Connect payments: Not complete. Your payment connection is unavailable, so it could not be checked. Connect your DinkusKit account to continue.");
  assert.equal(other.asksToConnect, false);
});

test("Connect is the press when the page asks, and a verified test connection is left alone", () => {
  assert.deepEqual(nextPress(readStatusText(connectLine), { buttons: ["Connect"], links: [] }), { action: "press", name: "Connect" });
  assert.deepEqual(
    nextPress(readStatusText(`Connected: Stripe test mode\n${connectedLine}`), { buttons: ["Check connection", "Reconnect", "Check provider identity"], links: [] }),
    { action: "leave", because: "Connected: Stripe test mode. Reconnect and Stripe setup were left alone." },
  );
});

test("a lapsed sign-in that still shows Stripe test mode does not press Sign in again", () => {
  assert.equal(nextPress(
    readStatusText(`Connected: Stripe test mode\n${connectedLine}`),
    { buttons: ["Sign in again"], links: [] },
  ).action, "leave");
});

test("pending approval opens DinkusKit before Continue, and Continue is next once payments are approved", () => {
  const pending = readStatusText("Connect payments: Not complete. Select Authorize Payments at DinkusKit and select Approve there. DinkusKit brings you back here, and this page checks your approval on its own.");
  const controls = { buttons: ["Continue"], links: ["Authorize Payments at DinkusKit"] };
  assert.equal(nextPress(pending, controls).action, "authorize");
  assert.deepEqual(nextPress(pending, controls, { approved: true }), { action: "press", name: "Continue" });
});

test("Stripe setup and every other control stay unpressed", () => {
  const checked = readStatusText("Connect payments: Not complete. DinkusKit Payments status was checked. No processor account is connected. Select Set up Stripe to connect your processor account.");
  assert.equal(nextPress(checked, { buttons: ["Set up or resume Stripe", "Check connection", "Reconnect"], links: ["Continue setup at Stripe"] }).action, "leave");
  const saved = readStatusText("Connect payments: Not complete. Your DinkusKit authorization was saved. Use Check connection to read the payment account status. No processor setup was attempted.");
  assert.deepEqual(nextPress(saved, { buttons: ["Check connection", "Reconnect"], links: [] }), { action: "press", name: "Check connection" });
  assert.deepEqual(
    nextPress(readStatusText("Payment status not checked\nConnect payments: Not checked. Select Sign in again to refresh it."), { buttons: ["Sign in again"], links: [] }),
    { action: "press", name: "Sign in again" },
  );
  for (const name of ["Reconnect", "Deny", "Set up or resume Stripe", "Check provider identity", "Confirm recovery preparation"]) {
    const decision = nextPress(
      { connectedTest: false, asksToConnect: false },
      { buttons: [name], links: [] },
    );
    assert.notEqual(decision.name, name);
    assert.notEqual(decision.action, "press");
  }
});

test("an authorize address is DinkusKit's connect page with one connection id and nothing else", () => {
  assert.equal(authorizeHref("https://dinkuskit.com/account/connect?connection_id=6b0d4e18-7c3a-4f1e-9a2b-0c5d6e7f8091", account), true);
  for (const href of [
    "https://dinkuskit.com/account/connect?connection_id=6b0d4e18-7c3a-4f1e-9a2b-0c5d6e7f8091&token=eyJabc.def.ghi",
    "https://dinkuskit.com/account/connect",
    "https://evil.example/account/connect?connection_id=abc",
    "http://dinkuskit.com/account/connect?connection_id=abc",
    "https://dinkuskit.com/account/connect?connection_id=abc#key",
    "https://user:pass@dinkuskit.com/account/connect?connection_id=abc",
    "https://dinkuskit.com/account/sites?connection_id=abc",
  ]) assert.equal(authorizeHref(href, account), false, href);
});

test("a store key or session token is recognized and removed from proof text", () => {
  const leaked = "status sk_test_51Abc whsec_abc connection_id=6b0d4e18-7c3a-4f1e-9a2b-0c5d6e7f8091";
  assert.equal(showsSecret(leaked), true);
  assert.equal(showsSecret("Connected: Stripe test mode"), false);
  assert.equal(redact(leaked).includes("sk_test_"), false);
  assert.equal(redact(leaked).includes("connection_id=6b0d4e18"), false);
  assert.match(redact(leaked), /\[secret\]/);
});
