import { test as base, chromium } from "@playwright/test";
import { config } from "./env.mjs";

/**
 * One saved browser profile for every run, so sign-ins to DinkusKit.com, Ship
 * and the store's admin carry over and most runs need no email at all.
 */
export const test = base.extend({
  persistent: [async ({}, use) => {
    const context = await chromium.launchPersistentContext(config.profileDir, {
      channel: config.channel === "chromium" ? undefined : config.channel,
      executablePath: process.env.DINKUS_E2E_CHROME_PATH || undefined,
      headless: config.headless,
      viewport: { width: 1280, height: 900 },
      acceptDownloads: true,
    });
    await use(context);
    await context.close();
  }, { scope: "worker" }],
  page: async ({ persistent }, use) => {
    const page = persistent.pages()[0] ?? await persistent.newPage();
    await use(page);
  },
});

export { expect } from "@playwright/test";
