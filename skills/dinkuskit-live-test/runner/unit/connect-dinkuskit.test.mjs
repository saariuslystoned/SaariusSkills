import assert from "node:assert/strict";
import test from "node:test";
import {
  accountReading, betaPaymentsStatusLinks, consentReading, CONNECT_INSTRUCTION, isSignInLink,
} from "../support/connect-dinkuskit.mjs";

const STORE = "https://beta.sm0ky.dev";
const ACCOUNT = "https://dinkuskit.com";
const account = lines => lines.join("\n");

test("a store the account already lists is left connected", () => {
  const text = account([
    "Signed in as owner@example.com",
    "Smoky",
    "Your stores",
    "Your store is connected",
    "Status: Approved",
    STORE,
    "Set up your store",
    "Your businesses",
  ]);
  assert.deepEqual(accountReading(text, STORE), { next: "connected" });
});

test("another store, a second business, a wait, or a staff sign-in does not start Connect", () => {
  assert.equal(accountReading(account(["Your store is connected", "https://other.example"]), STORE).next, "stop");
  assert.equal(accountReading(account(["Connect your store", CONNECT_INSTRUCTION, "Your businesses"]), STORE).next, "stop");
  assert.match(accountReading(account(["Waiting for approval", "Status: Waiting for approval"]), STORE).reason, /waiting for approval/);
  assert.match(accountReading(account(["Finish creating your account"]), STORE).reason, /does not create one/);
  assert.match(accountReading(account(["You're on the staff of Smoky", "Status: Approved"]), STORE).reason, /staff/);
  assert.equal(accountReading(account(["Connect your store", "Press something else."]), STORE).next, "stop");
});

test("Connect is only the Payments instruction on an account with one business and no store", () => {
  assert.deepEqual(accountReading(account([
    "Connect your store",
    "Status: Approved",
    CONNECT_INSTRUCTION,
  ]), STORE), { next: "connect" });
});

test("Approve stays unpressed unless the page is this store's Payments consent", () => {
  const ready = account([
    "Connect this store?",
    "Service: payments",
    "Payments status and processor setup access; this does not grant checkout access.",
    `Site origin: ${STORE}`,
  ]);
  assert.deepEqual(consentReading(ready, STORE), { ok: true });
  assert.equal(consentReading(ready.replace(STORE, "https://other.example"), STORE).ok, false);
  assert.equal(consentReading(ready.replace("Service: payments", "Service: inventory"), STORE).ok, false);
  assert.match(consentReading(`${ready}\nThis connection is no longer waiting for consent.`, STORE).reason, /no longer waiting/);
});

test("a DinkusKit sign-in link is told apart from the account page", () => {
  assert.equal(isSignInLink(`${ACCOUNT}/api/auth/magic-link/verify?token=secret`), true);
  assert.equal(isSignInLink(`${ACCOUNT}/account`), false);
});

test("only the beta Payments status page on this store is the Connect page", () => {
  const beta = `${STORE}/_emdash/admin/plugins/r_sffx6l4z6mpqliki/status`;
  const stable = `${STORE}/_emdash/admin/plugins/r_3brsc2on3bu673rn/status`;
  assert.deepEqual(betaPaymentsStatusLinks([
    `${STORE}/_emdash/admin`,
    stable,
    beta,
    "https://other.example/_emdash/admin/plugins/r_sffx6l4z6mpqliki/status",
    `${beta}?view=full`,
    "/_emdash/admin/plugins/r_sffx6l4z6mpqliki/status",
  ], STORE), [beta]);
});
