import { defineConfig } from "@playwright/test";
import { config } from "./support/env.mjs";

export default defineConfig({
  testDir: "./tests",
  // A full run waits on Stripe, Pitney Bowes and Commerce's 5-minute background check.
  timeout: 30 * 60 * 1000,
  workers: 1,
  retries: 0,
  outputDir: config.runDir + "/test-results",
  // The verdict reporter goes last, so the run's verdict prints after Playwright's own summary.
  reporter: [["list"], ["json", { outputFile: config.runDir + "/playwright.json" }], ["./support/verdict-reporter.mjs"]],
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Playwright Test lets a click or a page load wait forever, so a button the page never shows, or a
    // page that never finishes loading, would hold the run until the test timeout. With these it fails
    // its step within a minute or two instead. They reach every window the runner opens itself.
    actionTimeout: 60_000,
    navigationTimeout: 90_000,
  },
});
