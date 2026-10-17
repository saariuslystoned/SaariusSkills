import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "./browser.mjs";
import { config } from "./env.mjs";
import { record, shot, startJourney } from "./proof.mjs";

/**
 * Runs one step, recording PASS or FAIL with the reason and a screenshot. A `soft` step's
 * failure is recorded and the run goes on; it returns undefined.
 */
export async function step(page, name, body, { soft = false } = {}) {
  return test.step(name, async () => {
    try {
      const detail = await body();
      await shot(page, name.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
      record(name, "PASS", detail && typeof detail === "object" ? JSON.stringify(detail) : detail ?? "");
      return detail;
    } catch (error) {
      await shot(page, `fail-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`);
      record(name, "FAIL", error.message.split("\n")[0]);
      if (!soft) throw error;
    }
  });
}

/**
 * Wraps one journey's body as a Playwright test function; PROOF.md groups its steps under the
 * test's title. Tag the test with its stage in the journeys plan: `npm test` runs every
 * `@running` journey. The body gets the saved profile's page, signed in to the store admin and
 * Ship, unless `profile` is false (a shopper journey that opens its own clean browser).
 *
 *   test("Storefront", { tag: "@next" }, journey(async () => { ... }, { profile: false }));
 */
export function journey(body, { profile = true } = {}) {
  const run = async page => {
    const name = test.info().title;
    startJourney(name);
    await body({ page });
    const report = JSON.parse(readFileSync(join(config.runDir, "report.json"), "utf8"));
    const verdict = report.journeys.find(entry => entry.name === name)?.verdict ?? "INCOMPLETE";
    console.log(`\n${name}: ${verdict}\n`);
    // A step that failed softly still fails its journey, so "run the test" exits non-zero.
    expect(verdict, `see ${config.runDir}/PROOF.md`).toBe("PASS");
  };
  // Playwright starts only the fixtures a test names, so a profile-free journey never opens the saved profile.
  return profile ? async ({ page }) => run(page) : async ({}) => run(undefined);
}
