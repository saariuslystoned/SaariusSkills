import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";
import { siteOnlyReason, withoutCallLog } from "../support/errors.mjs";

const FIRST = "apiRequestContext.get: Timeout 30000ms exceeded.";
const FRAME = "    at readApi (file:///runner/tests/update-store.spec.mjs:25:26)";

/** Playwright's error for a request the test sent itself, whose call log lists every header. */
function requestError() {
  const message = `${FIRST}\nCall log:\n  - → GET https://store.example/api/guest-cart/snapshot\n`
    + "  -   cookie: CF_Authorization=synthetic-access; emdash_session=synthetic-session\n"
    + "  - ← 200 OK\n  -   set-cookie: emdash_session=synthetic-new\n";
  const error = new Error(message);
  error.stack = `${message}\n${FRAME}`;
  return error;
}

test("a failure keeps what Playwright says went wrong and drops its call log", () => {
  const error = requestError();
  assert.equal(withoutCallLog(error), error);
  assert.equal(error.message, FIRST);
  assert.equal(error.stack, `${FIRST}\n${FRAME}`);
  assert.equal(withoutCallLog(error).message, FIRST);
});

test("an error with no call log, or no message, is left as it is", () => {
  const own = new Error("The store answered HTTP 500 for /_emdash/api/admin/plugins.\nIts second line");
  assert.equal(withoutCallLog(own).message, "The store answered HTTP 500 for /_emdash/api/admin/plugins.\nIts second line");
  assert.equal(withoutCallLog("thrown text"), "thrown text");
  assert.equal(withoutCallLog(undefined), undefined);
});

test("an error whose message can't change gives way to a plain one without the call log", () => {
  const frozen = Object.freeze(requestError());
  const kept = withoutCallLog(frozen);
  assert.notEqual(kept, frozen);
  assert.equal(kept.message, FIRST);
});

test("a sign-in link that won't open is named by its site alone", () => {
  const link = "https://dinkuskit.com/api/auth/magic-link/verify?token=synthetic-token&callbackURL=%2Faccount";
  const error = new Error(`page.goto: net::ERR_ABORTED at ${link}\nCall log:\n  - navigating to "${link}", waiting until "load"\n`);
  assert.equal(siteOnlyReason(error), "page.goto: net::ERR_ABORTED at https://dinkuskit.com");
  assert.equal(siteOnlyReason(new Error(`Navigation to "${link}" is interrupted`)), 'Navigation to "https://dinkuskit.com" is interrupted');
});

// Read as text: this offline check runs without Playwright installed.
test("the run keeps no Playwright trace, and no journey turns one on", () => {
  const settings = readFileSync(new URL("../playwright.config.mjs", import.meta.url), "utf8");
  assert.deepEqual(settings.match(/\btrace\s*:.*/g), ['trace: "off",']);
  for (const file of readdirSync(new URL("../tests/", import.meta.url))) {
    assert.doesNotMatch(readFileSync(new URL(`../tests/${file}`, import.meta.url), "utf8"), /\btrace\s*:/, file);
  }
});
