import { config } from "./env.mjs";
import { note } from "./proof.mjs";
import { openStorePage } from "./signin.mjs";

const accessLogin = url => /\.cloudflareaccess\.com$/.test(new URL(url).hostname);

/** Where a request that left the store ended up, for a finding. */
export const elsewhere = url => accessLogin(url) ? "a Cloudflare Access sign-in" : new URL(url).hostname;

/** Opens a store page as a shopper; ending up off the store (a sign-in elsewhere) or anything but HTTP 200 fails the step that opened it. */
export async function openShopperPage(page, path) {
  const response = await openStorePage(page, new URL(path, config.store).href);
  if (new URL(page.url()).origin !== config.store) {
    const how = accessLogin(page.url()) ? "; the test gets past Access only with a one-time PIN it reads from the test inbox" : "";
    throw new Error(`${path} sent the shopper to ${elsewhere(page.url())} instead of the store${how}.`);
  }
  if (response?.status() !== 200) throw new Error(`${path} answered HTTP ${response?.status() ?? "nothing"}.`);
}

/** The first step of every shopper journey; a store nobody can open has nothing else to check. */
export const STORE_OPENS = "A new shopper can open the store";

/** Opens the homepage in a new shopper's browser and says how it answered. */
export async function storeOpens(page) {
  await openShopperPage(page, "/");
  // A test store may keep every page behind Cloudflare Access; the shopper's browser then signed in to it first.
  const gated = (await page.context().cookies(config.store)).some(cookie => cookie.name === "CF_Authorization");
  if (gated) note("store access", "behind Cloudflare Access; the shopper's browser signed in to it with a one-time PIN");
  return `the homepage "${await page.title()}" answered HTTP 200${gated ? " after a Cloudflare Access sign-in" : ""}`;
}
