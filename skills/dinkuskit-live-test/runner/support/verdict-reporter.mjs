import { config } from "./env.mjs";
import { withoutQueries } from "./errors.mjs";
import { TEST_RUN, failUnrecorded, startRun, verdicts } from "./proof.mjs";

const firstLine = text => withoutQueries(String(text ?? "").replace(/\u001b\[[0-9;]*m/g, "").split("\n").map(line => line.trim()).find(Boolean) ?? "");

/**
 * Prints the run's verdict last, once Playwright has every journey's outcome. A journey Playwright
 * failed without recording the failure itself (its browser wouldn't open, the run stopped before
 * it), an error outside every journey, or a run Playwright reports interrupted fails the proof too,
 * so the verdict never says PASS when the run failed.
 */
export default class VerdictReporter {
  errors = [];
  // Listing the journeys (--list) runs none, so it leaves the proof as it is and gives no verdict.
  listOnly = process.argv.includes("--list");

  constructor() {
    // Playwright makes the reporter before it loads the journeys, so even a run that finds none starts clean.
    if (!this.listOnly) startRun();
  }

  onBegin(_config, suite) {
    this.suite = suite;
  }

  onError(error) {
    this.errors.push(error);
  }

  onEnd(result) {
    if (this.listOnly) return;
    for (const test of this.suite?.allTests() ?? []) {
      const last = test.results.at(-1);
      if (!last) failUnrecorded(test.title, "The journey ran", "the run stopped before this journey started");
      else if (!["passed", "skipped"].includes(last.status)) {
        failUnrecorded(test.title, "The journey finished without an error", firstLine(last.error?.message) || `Playwright reported it ${last.status}`);
      }
    }
    for (const error of this.errors) failUnrecorded(TEST_RUN, "The test run finished without an error", firstLine(error.message));
    // A run Playwright reports interrupted or timed out fails, even when every journey it ran passed.
    if (result.status !== "passed" && verdicts().verdict !== "FAIL") failUnrecorded(TEST_RUN, "The test run finished", `Playwright reported the run ${result.status}`);
    const { verdict, journeys } = verdicts();
    if (!journeys.length) return;
    console.log(`\n${journeys.map(entry => `${entry.name}: ${entry.verdict}`).join("\n")}`);
    console.log(`Verdict: ${verdict}. Proof: ${config.runDir}/PROOF.md\n`);
  }

  printsToStdio() {
    return true;
  }
}
