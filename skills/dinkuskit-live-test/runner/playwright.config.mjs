import { defineConfig } from "@playwright/test";
import { config } from "./support/env.mjs";

// "Update the store" (tests/update-store.spec.mjs) changes the beta store's plugins, so it runs only
// from `npm run update-store`, which sets this; every other run leaves it out, whatever it picks. It
// keeps its own Playwright record, since the journeys run straight after it under the same run id.
const updating = process.env.DINKUS_E2E_UPDATE === "1";
const record = updating ? "-update" : "";

// On a failure Playwright's notes (error-context.md) also take a snapshot of the open page, with its
// links (sign-in, connect and print links among them) and what its fields hold. Each step's screenshot
// shows the page, so the run takes none; Playwright takes no such snapshot while this is set.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";

export default defineConfig({
  testDir: "./tests",
  grepInvert: updating ? undefined : /@update/,
  // A full run waits on Stripe, Pitney Bowes and Commerce's 5-minute background check.
  timeout: 30 * 60 * 1000,
  workers: 1,
  retries: 0,
  outputDir: `${config.runDir}/test-results${record}`,
  // The verdict reporter goes last, so the run's verdict prints after Playwright's own summary.
  reporter: [["list"], ["json", { outputFile: `${config.runDir}/playwright${record}.json` }], ["./support/verdict-reporter.mjs"]],
  use: {
    // A Playwright trace keeps every request's headers, and with them the sign-in cookies for the
    // store's Cloudflare Access and DinkusKit.com, so a run keeps none. Each step's screenshot and
    // notes are its proof.
    trace: "off",
    screenshot: "only-on-failure",
    // Playwright Test lets a click or a page load wait forever, so a button the page never shows, or a
    // page that never finishes loading, would hold the run until the test timeout. With these it fails
    // its step within a minute or two instead. They reach every window the runner opens itself.
    actionTimeout: 60_000,
    navigationTimeout: 90_000,
  },
});
