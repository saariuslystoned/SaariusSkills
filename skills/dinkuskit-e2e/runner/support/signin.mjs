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
    if (/start again/i.test(text) && !page.url().startsWith(target)) continue;
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
 * Opens a page in the store's EmDash admin. Cloudflare Access fronts /_emdash;
 * its email one-time code is read the same way as the DinkusKit.com link.
 */
export async function openStoreAdmin(page, url) {
  await page.goto(url);
  await page.waitForLoadState("domcontentloaded");
  if (!/cloudflareaccess\.com$/.test(new URL(page.url()).hostname)) return;
  if (!config.ownerEmail) throw new Error("The store admin asks for a Cloudflare Access sign-in and DINKUS_E2E_OWNER_EMAIL is not set.");
  const baseline = mailBaseline("access");
  await page.locator('input[type="email"], input[name="email"]').first().fill(config.ownerEmail);
  await page.getByRole("button", { name: /send me a code|send code|continue|submit/i }).first().click();
  const code = await waitForMail("access", baseline);
  if (code) {
    await page.locator('input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[type="text"]').first().fill(code);
    await page.getByRole("button", { name: /sign in|submit|verify|continue/i }).first().click();
  } else {
    console.log(`\n>>> Enter the Cloudflare Access code emailed to ${config.ownerEmail} in this test's browser window.\n`);
  }
  await page.waitForURL(next => next.href.startsWith(config.store), { timeout: code ? 120_000 : HUMAN_WAIT_MS });
  await page.waitForLoadState("domcontentloaded");
}
