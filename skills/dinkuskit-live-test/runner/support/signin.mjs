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
 * Opens a page in the store's EmDash admin, which Cloudflare Access fronts. When
 * Access offers a one-time PIN, the test asks for one and reads it from the test
 * inbox. Otherwise (Google only) the saved profile has to carry a sign-in a person
 * made once. Returns false when a sign-in is needed and nobody can make it:
 * `waitForPerson` is off, or the window is hidden.
 */
export async function openStoreAdmin(page, url, { waitForPerson = true } = {}) {
  await page.goto(url);
  await page.waitForLoadState("domcontentloaded");
  if (at(page, config.store)) return true;
  if (await signInToAccessByCode(page)) {
    await page.waitForURL(next => next.href.startsWith(config.store), { timeout: 120_000 });
    await page.waitForLoadState("domcontentloaded");
    return true;
  }
  if (!waitForPerson || config.headless) return false;
  console.log(`\n>>> Sign in to the store admin as ${config.ownerEmail || "the test account"} in this test's browser window (once per profile).\n`);
  await page.waitForURL(next => next.href.startsWith(config.store), { timeout: HUMAN_WAIT_MS });
  await page.waitForLoadState("domcontentloaded");
  return true;
}

/**
 * Opens a store page as a shopper. A test store can put every page, not only its admin, behind
 * Cloudflare Access; then the test signs in to Access with a one-time PIN, as it does for the
 * admin, and opens the page again. Returns the page's response. When nobody could sign in, the
 * page is left on Access's login, away from the store.
 */
export async function openStorePage(page, url) {
  const response = await page.goto(url);
  if (at(page, config.store) || !await signInToAccessByCode(page)) return response;
  await page.waitForURL(next => next.href.startsWith(config.store), { timeout: 120_000 });
  return page.goto(url);
}

/**
 * Cloudflare Access's one-time PIN login: email in, code from the test inbox, sign in.
 * Returns false, having changed nothing, when this isn't Access's login page or it
 * offers no PIN login (a Google-only app sends the browser straight to Google).
 */
async function signInToAccessByCode(page) {
  if (!config.mailCmd || !config.ownerEmail || !/\.cloudflareaccess\.com$/.test(new URL(page.url()).hostname)) return false;
  const email = page.locator('input[type="email"], input[name="email"]').first();
  const pinChoice = page.getByRole("button", { name: /one-time pin/i }).or(page.getByRole("link", { name: /one-time pin/i })).first();
  // The login page draws its choices with script; give it a moment.
  await email.or(pinChoice).first().waitFor({ timeout: 15_000 }).catch(() => {});
  if (!await email.isVisible() && await pinChoice.isVisible()) {
    await pinChoice.click();
    await email.waitFor({ timeout: 10_000 }).catch(() => {});
  }
  if (!await email.isVisible()) return false;
  const baseline = mailBaseline("access");
  await email.fill(config.ownerEmail);
  await page.getByRole("button", { name: /send me a code|send code|get a login code|send/i }).first().click();
  const code = await waitForMail("access", baseline);
  const field = page.locator('input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"]')
    .or(page.getByLabel(/code|pin/i)).first();
  await field.waitFor({ timeout: 30_000 });
  // Hide what gets typed, so screenshots and recordings never show the code.
  await page.addStyleTag({ content: "input { -webkit-text-security: disc !important; color: transparent !important; caret-color: transparent !important; }" });
  await field.fill(code);
  await page.getByRole("button", { name: /sign in|submit|verify|log in|continue/i }).first().click();
  return true;
}
