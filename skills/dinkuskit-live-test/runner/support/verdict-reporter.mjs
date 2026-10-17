import { config } from "./env.mjs";
import { failUnrecorded, verdicts } from "./proof.mjs";

const firstLine = text => String(text ?? "").replace(/\u001b\[[0-9;]*m/g, "").split("\n").map(line => line.trim()).find(Boolean) ?? "";

/**
 * Prints the run's verdict last, once Playwright has every journey's outcome. A journey Playwright
 * failed without recording the failure itself (its browser wouldn't open, the run stopped before
 * it), an error outside every journey, or a run Playwright reports interrupted fails the proof too,
 * so the verdict never says PASS when the run failed.
 */
export default class VerdictReporter {
  errors = [];

  onBegin(_config, suite) {
    this.suite = suite;
  }

  onError(error) {
    this.errors.push(error);
  }

  onEnd(result) {
    for (const test of this.suite?.allTests() ?? []) {
      const last = test.results.at(-1);
      if (!last) failUnrecorded(test.title, "The journey ran", "the run stopped before this journey started");
      else if (!["passed", "skipped"].includes(last.status)) {
        failUnrecorded(test.title, "The journey finished without an error", firstLine(last.error?.message) || `Playwright reported it ${last.status}`);
      }
    }
    for (const error of this.errors) failUnrecorded("Test run", "The test run finished without an error", firstLine(error.message));
    // A run Playwright reports interrupted or timed out fails, even when every journey it ran passed.
    if (result.status !== "passed" && verdicts().verdict !== "FAIL") failUnrecorded("Test run", "The test run finished", `Playwright reported the run ${result.status}`);
    const { verdict, journeys } = verdicts();
    if (!journeys.length) return;
    console.log(`\n${journeys.map(entry => `${entry.name}: ${entry.verdict}`).join("\n")}`);
    console.log(`Verdict: ${verdict}. Proof: ${config.runDir}/PROOF.md\n`);
  }

  printsToStdio() {
    return true;
  }
}
