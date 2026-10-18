import { join } from "node:path";
import { test as base, chromium } from "@playwright/test";
import { config } from "./env.mjs";
import { filterPage, filteredGet } from "./request-policy.mjs";

const SIZE = { width: 1280, height: 900 };
const launch = () => ({
  channel: config.channel === "chromium" ? undefined : config.channel,
  executablePath: process.env.DINKUS_E2E_CHROME_PATH || undefined,
  headless: config.headless,
});
// With DINKUS_E2E_VIDEO=1 every browser window is recorded into the run's proof folder.
const video = () => config.video ? { recordVideo: { dir: join(config.runDir, "video"), size: SIZE } } : {};

/**
 * One saved browser profile for every run, so sign-ins to DinkusKit.com, Ship
 * and the store's admin carry over and most runs need no email at all.
 */
export const test = base.extend({
  persistent: [async ({}, use) => {
    const context = await chromium.launchPersistentContext(config.profileDir, {
      ...launch(),
      ...video(),
      viewport: SIZE,
      acceptDownloads: true,
      serviceWorkers: "block",
    });
    await use(context);
    await context.close();
  }, { scope: "worker" }],
  page: async ({ persistent }, use) => {
    await accessListed();
    const page = await filterPage(persistent.pages()[0] ?? await persistent.newPage(), config);
    await use(page);
  },
});

/**
 * A page in a separate browser with no sign-ins, cookies or saved cart, so a journey sees the
 * store exactly as a new shopper does. Close it with `closeShopper`.
 */
export async function shopperPage() {
  const browser = await chromium.launch(launch());
  const context = await browser.newContext({ viewport: SIZE, ...video(), serviceWorkers: "block" });
  return newPage(context);
}

/**
 * Closes a page from `shopperPage` and its browser. The context closes first, since only that waits
 * for the window's video to be saved; a browser closed straight away leaves it empty for a while.
 */
export async function closeShopper(page) {
  const context = page.context();
  const browser = context.browser();
  await context.close();
  await browser?.close();
}

export { expect } from "@playwright/test";

/** Create a page with the same site filter before its first navigation. */
export async function newPage(context) {
  await accessListed();
  return filterPage(await context.newPage(), config);
}

let accessCheck;
/**
 * The filter blocks a Cloudflare Access sign-in it wasn't told about, which would fail the first step
 * with a bare "blocked" error. Ask the store once, without following redirects, and name the setting.
 */
function accessListed() {
  accessCheck ??= (async () => {
    if (!config.store) return;
    for (const path of ["/", "/_emdash/admin"]) {
      const response = await fetch(new URL(path, config.store), { redirect: "manual" }).catch(() => null);
      const location = response?.headers.get("location");
      const access = location ? new URL(location, config.store) : null;
      if (access?.hostname.endsWith(".cloudflareaccess.com") && !config.accessOrigins.includes(access.origin)) {
        throw new Error(`${config.store} sends visitors to Cloudflare Access at ${access.origin}, which the request filter blocks. Add DINKUS_E2E_ACCESS_ORIGINS=${access.origin} to ${config.settingsFile}.`);
      }
    }
  })();
  return accessCheck;
}

/** A link/photo/PDF probe with the same origin and redirect policy. */
export const get = (page, url, options) => filteredGet(page.context().request, url, config, options);
