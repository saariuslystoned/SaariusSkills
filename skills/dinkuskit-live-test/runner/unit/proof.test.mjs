import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { after } from "node:test";

// Each test file runs in its own process, so this file's proof folder and run id stay its own.
const dir = mkdtempSync(join(tmpdir(), "dinkus-proof-"));
after(() => rmSync(dir, { recursive: true, force: true }));
Object.assign(process.env, {
  DINKUS_E2E_ENV_FILE: join(dir, "no-settings"),
  DINKUS_E2E_PROOF: dir,
  DINKUS_E2E_PROFILE: join(dir, "profile"),
  DINKUS_E2E_RUN: "reused",
});
const proof = await import("../support/proof.mjs");
const { default: VerdictReporter } = await import("../support/verdict-reporter.mjs");

const quiet = t => t.mock.method(console, "log", () => {});
const saved = () => ["report.json", "PROOF.md"].map(name => readFileSync(join(dir, "reused", name), "utf8"));

/** A passing Storefront under the run id, then an invocation that matched no journey. */
function passThenNoJourney() {
  proof.startJourney("Storefront");
  proof.record("A new shopper can open the store", "PASS");
  const first = new VerdictReporter();
  first.onError({ message: "Error: No tests found" });
  first.onEnd({ status: "failed" });
  assert.equal(proof.verdicts().verdict, "FAIL");
}

/** Runs `body` as Playwright's main process does for `playwright test --list`. */
function listing(body) {
  const argv = process.argv;
  process.argv = [...argv, "--list"];
  try { body(); } finally { process.argv = argv; }
}

test("listing the journeys leaves the proof as it is and prints no verdict", (t) => {
  const log = quiet(t);
  passThenNoJourney();
  const before = saved();
  log.mock.resetCalls();
  listing(() => {
    const listed = new VerdictReporter();
    listed.onBegin({}, { allTests: () => [{ title: "Storefront", results: [] }, { title: "Cart", results: [] }] });
    listed.onEnd({ status: "passed" });
  });
  assert.deepEqual(saved(), before);
  assert.equal(log.mock.callCount(), 0);
});

test("a run id used again keeps its journeys but drops an earlier invocation's run-level failure", (t) => {
  quiet(t);
  passThenNoJourney();
  // The next invocation, under the same run id, starts without it.
  new VerdictReporter();
  assert.deepEqual(proof.verdicts(), { verdict: "PASS", journeys: [{ name: "Storefront", verdict: "PASS" }] });
  assert.doesNotMatch(saved()[1], /Test run|No tests found/);
});

test("a run that stops before a journey starts fails that journey", (t) => {
  quiet(t);
  const stopped = new VerdictReporter();
  stopped.onBegin({}, { allTests: () => [{ title: "Cart", results: [] }] });
  stopped.onEnd({ status: "interrupted" });
  assert.equal(proof.journeyVerdict("Cart"), "FAIL");
});
