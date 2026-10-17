import { defineConfig } from "@playwright/test";
import { config } from "./support/env.mjs";

export default defineConfig({
  testDir: "./tests",
  // A full run waits on Stripe, Pitney Bowes and Commerce's 5-minute background check.
  timeout: 30 * 60 * 1000,
  workers: 1,
  retries: 0,
  outputDir: config.runDir + "/test-results",
  reporter: [["list"], ["json", { outputFile: config.runDir + "/playwright.json" }]],
  use: { trace: "retain-on-failure", screenshot: "only-on-failure" },
});
