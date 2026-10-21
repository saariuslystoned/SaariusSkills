import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";
import { firstLine, forProof, withoutQueries } from "../support/errors.mjs";

const FIRST = "apiRequestContext.get: Timeout 30000ms exceeded.";
const FRAME = "    at readApi (file:///runner/tests/update-store.spec.mjs:25:26)";
const LINK = "https://dinkuskit.com/api/auth/magic-link/verify?token=synthetic-token&callbackURL=%2Faccount";

/** Playwright's error for a request the test sent itself, whose call log lists every header. */
function requestError() {
  const message = `${FIRST}\nCall log:\n  - → GET https://store.example/api/guest-cart/snapshot\n`
    + "  -   cookie: CF_Authorization=synthetic-access; emdash_session=synthetic-session\n"
    + "  - ← 200 OK\n  -   set-cookie: emdash_session=synthetic-new\n";
  const error = new Error(message);
  error.stack = `${message}\n${FRAME}`;
  return error;
}

/** An error Playwright made, as it makes them: its stack starts with the whole message. */
function playwrightError(message, name = "Error") {
  const error = new Error(message);
  error.name = name;
  error.stack = `${message}\n${FRAME}`;
  return error;
}

const nothingSynthetic = (error, label) => {
  for (const text of [error.message, error.stack, JSON.stringify(error)]) assert.doesNotMatch(text, /synthetic/, label);
};

test("a failure keeps what Playwright says went wrong and drops its call log", () => {
  const error = requestError();
  assert.equal(forProof(error), error);
  assert.equal(error.message, FIRST);
  assert.equal(error.stack, `Error: ${FIRST}\n${FRAME}`);
  assert.equal(forProof(error).message, FIRST);
});

test("a wait that times out keeps no list of the addresses the page went to", () => {
  const error = playwrightError(`page.waitForURL: Timeout 120000ms exceeded.\n${"=".repeat(27)} logs ${"=".repeat(27)}\n`
    + `waiting for navigation until "load"\n  navigated to "https://beta.sm0ky.dev/cdn-cgi/access/callback?code=synthetic-code"\n${"=".repeat(60)}`, "TimeoutError");
  forProof(error);
  assert.equal(error.message, "page.waitForURL: Timeout 120000ms exceeded.");
  assert.equal(error.name, "TimeoutError");
  nothingSynthetic(error, "the waiter's logs");
});

test("a locator that matches two elements keeps no element's markup", () => {
  const error = playwrightError("locator.getAttribute: Error: strict mode violation: getByRole('link', { name: 'Print label' }) resolved to 2 elements:\n"
    + "    1) <a href=\"https://ship.dinkuskit.com/print/synthetic-print-token\">Print label</a> aka getByRole('link', { name: 'Print label' }).first()\n"
    + "    2) <a href=\"/account/connect?connection_id=synthetic-connection\">Print label</a> aka getByRole('link', { name: 'Print label' }).nth(1)\n\nCall log:\n  - waiting for getByRole('link', { name: 'Print label' })\n");
  forProof(error);
  assert.equal(error.message, "locator.getAttribute: Error: strict mode violation: getByRole('link', { name: 'Print label' }) resolved to 2 elements:");
  nothingSynthetic(error, "the matched elements");
});

test("a failed assertion keeps its first line, without colours, what it received or its snapshot of the page", () => {
  const error = playwrightError("Commerce didn't keep the weight\n\n\u001b[2mexpect(\u001b[22m\u001b[31mlocator\u001b[39m\u001b[2m).\u001b[22mtoHaveValue\u001b[2m(\u001b[22m\u001b[32mexpected\u001b[39m\u001b[2m)\u001b[22m failed\n\n"
    + "Locator:  getByLabel('Code')\nExpected: \u001b[32m\"8\"\u001b[39m\nReceived: \u001b[31m\"synthetic-field\"\u001b[39m\nTimeout:  15000ms\n");
  error.matcherResult = { pass: false, actual: "synthetic-field", ariaSnapshot: "- textbox \"Code\": synthetic-field\n- link \"Print label\":\n  - /url: https://ship.dinkuskit.com/print/synthetic-print-token" };
  forProof(error);
  assert.equal(error.message, "Commerce didn't keep the weight");
  assert.equal("matcherResult" in error, false);
  nothingSynthetic(error, "the assertion");
  const plain = playwrightError("\u001b[2mexpect(\u001b[22m\u001b[31mlocator\u001b[39m\u001b[2m).\u001b[22mtoBeVisible\u001b[2m(\u001b[22m\u001b[2m)\u001b[22m failed\n\nLocator: getByText('Missing')\n");
  assert.equal(forProof(plain).message, "expect(locator).toBeVisible() failed");
});

test("an error's cause goes with it", () => {
  const error = new Error("The store answered nothing.", { cause: new Error("fetch https://ship.dinkuskit.com/print/synthetic-print-token failed") });
  assert.equal(forProof(error), error);
  assert.equal(error.message, "The store answered nothing.");
  assert.equal("cause" in error, false);
  nothingSynthetic(error, "the cause");
});

test("an address in a failure keeps no query or fragment, and a print link keeps no token", () => {
  const error = new Error(`page.goto: net::ERR_ABORTED at ${LINK}\nCall log:\n  - navigating to "${LINK}", waiting until "load"\n`);
  assert.equal(forProof(error).message, "page.goto: net::ERR_ABORTED at https://dinkuskit.com/api/auth/magic-link/verify");
  assert.equal(withoutQueries(`Navigation to "${LINK}" is interrupted by another navigation to "https://dinkuskit.com/account/connect?connection_id=synthetic"`),
    'Navigation to "https://dinkuskit.com/api/auth/magic-link/verify" is interrupted by another navigation to "https://dinkuskit.com/account/connect"');
  assert.equal(withoutQueries("last page https://checkout.stripe.com/c/pay/cs_test_synthetic#fidsynthetic."), "last page https://checkout.stripe.com/c/pay/cs_test_synthetic");
  assert.equal(withoutQueries('<a href="/account/connect?connection_id=synthetic">Authorize</a> went to "/cdn-cgi/access/callback?code=synthetic"'),
    '<a href="/account/connect">Authorize</a> went to "/cdn-cgi/access/callback"');
  assert.equal(withoutQueries("Print label opened https://ship.dinkuskit.com/print/synthetic-print-token."), "Print label opened https://ship.dinkuskit.com/print/");
  assert.equal(withoutQueries("socket wss://ship.dinkuskit.com/ws?token=synthetic failed"), "socket wss://ship.dinkuskit.com/ws failed");
  // An address can start after any mark; what follows its query up to the next space goes with it.
  assert.equal(withoutQueries("went to [/cdn-cgi/access/callback?code=synthetic] and `/x?code=synthetic` then :/y?code=synthetic"),
    "went to [/cdn-cgi/access/callback and `/x then :/y");
  // Words with a slash aren't addresses.
  assert.equal(withoutQueries("Processing/Completed? and/or?"), "Processing/Completed? and/or?");
});

test("the first line of anything thrown, without colours or queries", () => {
  assert.equal(firstLine(requestError()), FIRST);
  assert.equal(firstLine("thrown text"), "thrown text");
  assert.equal(firstLine(undefined), "undefined");
  assert.equal(firstLine(new Error("\nThe store answered HTTP 500 for /shop?x=synthetic.\nIts second line")), "The store answered HTTP 500 for /shop");
});

test("a failure with nothing to cut is left as it is, and one of the runner's own keeps its first line", () => {
  const own = new Error("The store answered HTTP 500 for /_emdash/api/admin/plugins.");
  const stack = own.stack;
  assert.equal(forProof(own), own);
  assert.equal(own.stack, stack);
  assert.equal(forProof(new Error("None of the products opens.\nhttps://beta.sm0ky.dev/shop")).message, "None of the products opens.");
  assert.equal(forProof("thrown text"), "thrown text");
  assert.equal(forProof(undefined), undefined);
});

test("an error that can't change gives way to a copy of the same kind, without what it can't keep", () => {
  class CaptchaShown extends Error {}
  const original = new CaptchaShown(`Stripe showed a captcha.\nCall log:\n  - navigating to "${LINK}"`);
  original.name = "CaptchaShown";
  original.missed = ["photo.png"];
  original.matcherResult = { ariaSnapshot: "- textbox: synthetic-field" };
  const frozen = Object.freeze(original);
  const kept = forProof(frozen);
  assert.notEqual(kept, frozen);
  assert.ok(kept instanceof CaptchaShown);
  assert.equal(kept.name, "CaptchaShown");
  assert.equal(kept.message, "Stripe showed a captcha.");
  assert.match(kept.stack, /^CaptchaShown: Stripe showed a captcha\.\n {4}at /);
  assert.deepEqual(kept.missed, ["photo.png"]);
  assert.equal("matcherResult" in kept, false);
  nothingSynthetic(kept, "the copy");
  // A message set after the error was made is one of the error's own properties.
  const late = new Error();
  late.message = `Stripe showed a captcha.\nCall log:\n  - navigating to "${LINK}"`;
  const lateKept = forProof(Object.freeze(late));
  assert.equal(lateKept.message, "Stripe showed a captcha.");
  nothingSynthetic(lateKept, "the copy of an error whose message was set later");
});

// Read as text: this offline check runs without Playwright installed.
test("the run keeps no Playwright trace or page snapshot, and no journey turns a trace on", () => {
  const settings = readFileSync(new URL("../playwright.config.mjs", import.meta.url), "utf8");
  assert.deepEqual(settings.match(/\btrace\s*:.*/g), ['trace: "off",']);
  assert.match(settings, /^process\.env\.PLAYWRIGHT_NO_COPY_PROMPT = "1";$/m);
  for (const file of readdirSync(new URL("../tests/", import.meta.url))) {
    assert.doesNotMatch(readFileSync(new URL(`../tests/${file}`, import.meta.url), "utf8"), /\btrace\s*:/, file);
  }
});
