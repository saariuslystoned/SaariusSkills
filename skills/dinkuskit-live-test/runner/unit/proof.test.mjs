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

test("a run id used again keeps its journeys but drops an earlier invocation's run-level failure", (t) => {
  quiet(t);
  proof.startJourney("Storefront");
  proof.record("A new shopper can open the store", "PASS");
  // The invocation before matched no journey.
  const first = new VerdictReporter();
  first.onError({ message: "Error: No tests found" });
  first.onEnd({ status: "failed" });
  assert.equal(proof.verdicts().verdict, "FAIL");
  // The next one, under the same run id, starts without it.
  new VerdictReporter();
  assert.deepEqual(proof.verdicts(), { verdict: "PASS", journeys: [{ name: "Storefront", verdict: "PASS" }] });
  assert.doesNotMatch(readFileSync(join(dir, "reused", "PROOF.md"), "utf8"), /Test run|No tests found/);
});

test("listing the journeys fails none of them, but a run that stops before one fails it", (t) => {
  quiet(t);
  const unstarted = { allTests: () => [{ title: "Cart", results: [] }] };
  const listed = new VerdictReporter();
  listed.onBegin({}, unstarted);
  listed.onEnd({ status: "passed" });
  assert.ok(!proof.verdicts().journeys.some(entry => entry.name === "Cart"));
  const stopped = new VerdictReporter();
  stopped.onBegin({}, unstarted);
  stopped.onEnd({ status: "interrupted" });
  assert.equal(proof.journeyVerdict("Cart"), "FAIL");
});
