import { config } from "./env.mjs";
import { mailBaseline, waitForMail } from "./mail.mjs";

const HUMAN_WAIT_MS = 10 * 60 * 1000;
const at = (page, base) => page.url().startsWith(base);

/**
 * Opens a Ship page, signing in with DinkusKit.com when Ship asks. Ship sends
 * the browser to dinkuskit.com/account/ship-sign-in, which goes to the magic-link
 * sign-in when nobody is signed in there, then back to Ship's callback.
 */
export async function openShip(page, path) {
  const target = config.ship + path;
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.goto(target);
    await page.waitForLoadState("domcontentloaded");
    if (at(page, `${config.account}/account/sign-in`)) {
      await signInToDinkusKit(page);
      await page.waitForURL(url => url.href.startsWith(config.ship), { timeout: 120_000 });
    }
    if (!at(page, config.ship)) continue;
    const text = await page.locator("body").innerText();
    // The first sign-in after a key change may say this once; Ship's own guidance is to wait a minute.
    if (/could not (sign in|confirm the sign-in)/i.test(text)) { await page.waitForTimeout(60_000); continue; }
    if (page.url().startsWith(target)) return;
  }
  throw new Error(`Could not open ${target} signed in; last page ${page.url()}.`);
}

/** The magic-link sign-in on dinkuskit.com. The link opens in this same browser so Ship's sign-in cookie is still there. */
async function signInToDinkusKit(page) {
  if (!config.ownerEmail) throw new Error("DINKUS_E2E_OWNER_EMAIL is not set, so the test cannot ask DinkusKit.com for a sign-in link.");
  const baseline = mailBaseline("dinkuskit");
  await page.locator("#email").fill(config.ownerEmail);
  await page.getByRole("button", { name: /email me a sign-in link/i }).click();
  await page.waitForLoadState("domcontentloaded");
  const link = await waitForMail("dinkuskit", baseline);
  if (link) {
    await page.goto(link);
    return;
  }
  console.log(`\n>>> Open the "Sign in to DinkusKit" email for ${config.ownerEmail} and paste its link into this test's browser window.\n`);
  await page.waitForURL(url => !url.href.startsWith(`${config.account}/account/sign-in`), { timeout: HUMAN_WAIT_MS });
}

/**
 * Opens a page in the store's EmDash admin, which Cloudflare Access fronts.
 * The test stores' Access app signs in with Google; the saved profile keeps that
 * sign-in, so only the first run on a new profile needs a person. Returns false
 * when a sign-in is needed and `waitForPerson` is off (or the window is hidden).
 */
export async function openStoreAdmin(page, url, { waitForPerson = true } = {}) {
  await page.goto(url);
  await page.waitForLoadState("domcontentloaded");
  if (at(page, config.store)) return true;
  if (!waitForPerson || config.headless) return false;
  console.log(`\n>>> Sign in to the store admin as ${config.ownerEmail || "the test account"} in this test's browser window (once per profile).\n`);
  await page.waitForURL(next => next.href.startsWith(config.store), { timeout: HUMAN_WAIT_MS });
  await page.waitForLoadState("domcontentloaded");
  return true;
}
