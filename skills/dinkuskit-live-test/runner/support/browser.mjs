import { test as base, chromium } from "@playwright/test";
import { config } from "./env.mjs";

const launch = () => ({
  channel: config.channel === "chromium" ? undefined : config.channel,
  executablePath: process.env.DINKUS_E2E_CHROME_PATH || undefined,
  headless: config.headless,
});

/**
 * One saved browser profile for every run, so sign-ins to DinkusKit.com, Ship
 * and the store's admin carry over and most runs need no email at all.
 */
export const test = base.extend({
  persistent: [async ({}, use) => {
    const context = await chromium.launchPersistentContext(config.profileDir, {
      ...launch(),
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

/**
 * A page in a separate browser with no sign-ins, cookies or saved cart, so a journey sees the
 * store exactly as a new shopper does. Close it with `page.context().browser().close()`.
 */
export async function shopperPage() {
  const browser = await chromium.launch(launch());
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  return context.newPage();
}

export { expect } from "@playwright/test";
