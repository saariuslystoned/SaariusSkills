import { test, expect } from "./browser.mjs";
import { config } from "./env.mjs";
import { firstLine, forProof } from "./errors.mjs";
import { journeyVerdict, record, shot, startJourney } from "./proof.mjs";

// Errors that stopped a journey inside a step, which recorded them already.
const recorded = new WeakSet();

/**
 * Runs one step, recording PASS or FAIL with the reason and a screenshot. A `soft` step's
 * failure is recorded and the run goes on; it returns undefined. `soft` can instead be a test of
 * the error, so the step stops the journey only on the errors that test refuses.
 */
export async function step(page, name, body, { soft = false } = {}) {
  return test.step(name, async () => {
    try {
      const detail = await body();
      await shot(page, name.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
      record(name, "PASS", detail && typeof detail === "object" ? JSON.stringify(detail) : detail ?? "");
      return detail;
    } catch (caught) {
      // What the proof and Playwright's report keep of the failure: its first line, with no address's query.
      const error = forProof(caught);
      await shot(page, `fail-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`);
      record(name, "FAIL", firstLine(error));
      if (typeof soft === "function" ? soft(error) : soft) return;
      if (Object(error) === error) recorded.add(error);
      throw error;
    }
  });
}

/**
 * Wraps one journey's body as a Playwright test function; PROOF.md groups its steps under the
 * test's title. Tag the test with its stage in the journeys plan: `npm test` runs every
 * `@running` journey. The body gets the saved profile's page, signed in to the store admin and
 * Ship, unless `profile` is false (a shopper journey that opens its own clean browser).
 *
 *   test("Storefront", { tag: "@running" }, journey(async () => { ... }, { profile: false }));
 */
export function journey(body, { profile = true } = {}) {
  const run = async page => {
    const name = test.info().title;
    startJourney(name);
    try {
      await body({ page });
    } catch (caught) {
      const error = forProof(caught);
      // An error between steps (a page that wouldn't open) still fails the journey in its proof.
      if (!recorded.has(error)) record("The journey finished without an error", "FAIL", firstLine(error));
      throw error;
    }
    const verdict = journeyVerdict(name);
    console.log(`\n${name}: ${verdict}\n`);
    // A step that failed softly still fails its journey, so "run the test" exits non-zero.
    expect(verdict, `see ${config.runDir}/PROOF.md`).toBe("PASS");
  };
  // Playwright starts only the fixtures a test names, so a profile-free journey never opens the saved profile.
  return profile ? async ({ page }) => run(page) : async ({}) => run(undefined);
}
