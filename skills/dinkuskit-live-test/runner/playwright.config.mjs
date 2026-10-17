import { defineConfig } from "@playwright/test";
import { config } from "./support/env.mjs";

export default defineConfig({
  testDir: "./tests",
  // A full run waits on Stripe, Pitney Bowes and Commerce's 5-minute background check.
  timeout: 30 * 60 * 1000,
  workers: 1,
  retries: 0,
  outputDir: config.runDir + "/test-results",
  // Prints the run's verdict once every journey has finished.
  globalTeardown: "./support/teardown.mjs",
  reporter: [["list"], ["json", { outputFile: config.runDir + "/playwright.json" }]],
  use: { trace: "retain-on-failure", screenshot: "only-on-failure" },
});
