import { get } from "./browser.mjs";
import { config } from "./env.mjs";
import { PAGE_ROOM, paceStore } from "./pace.mjs";
import { note } from "./proof.mjs";
import { openStoreAdmin } from "./signin.mjs";
import { describePlugins } from "./store-plugins.mjs";
import { text } from "./storefront-page.mjs";

const firstLine = error => String(error?.message ?? error).split("\n")[0];
const SIGN_IN_ONCE = "Run once with DINKUS_E2E_ADMIN_SIGNIN=wait and sign in by hand.";

/**
 * Opens a page of the store admin, signing in to its Access app with a one-time PIN when it asks. An
 * admin page sends many store requests as it opens (EmDash's and the plugins' calls, the photos it
 * lists), so it first waits its turn, as a store page does.
 */
export async function openAdmin(page, url) {
  await paceStore(PAGE_ROOM);
  if (!await openStoreAdmin(page, url, { waitForPerson: config.adminSignIn === "wait" })) {
    throw new Error("The store admin needs a sign-in the test can't make: its Access app offers no one-time PIN and the saved profile has no sign-in. Turn on One-time PIN in the Access app; the request filter blocks other sign-in providers such as Google.");
  }
  // A store whose admin isn't signed in through Access asks for EmDash's own sign-in (passkey or email link).
  if (!new URL(page.url()).pathname.startsWith("/_emdash/admin/login")) return;
  if (config.adminSignIn !== "wait" || config.headless) throw new Error(`The store admin asks for an EmDash sign-in (passkey or email link) that the saved profile doesn't have. ${SIGN_IN_ONCE}`);
  console.log(`\n>>> Sign in to the store admin in this test's browser window (once per profile).\n`);
  await page.waitForURL(next => !next.pathname.startsWith("/_emdash/admin/login"), { timeout: 10 * 60 * 1000 });
  await page.goto(url);
}

/**
 * Notes which plugin versions the store runs, so the proof says what it covers, and returns EmDash's
 * plugin list, or null when it couldn't be read.
 */
export async function notePlugins(page) {
  const response = await get(page, `${config.store}/_emdash/api/admin/plugins`, { headers: { "X-EmDash-Request": "1" } }).catch(error => error);
  if (response instanceof Error) note("plugins", `couldn't read the plugin list (${firstLine(response)})`);
  else if (!response.ok()) note("plugins", `couldn't read the plugin list (HTTP ${response.status()})`);
  else {
    const body = await response.json();
    note("plugins", describePlugins(body));
    return body;
  }
  return null;
}

/** Waits for Commerce to confirm an action ("Product saved"); a refusal fails with the reason Commerce shows. */
export async function confirmed(page, message) {
  const done = page.getByText(message, { exact: true }).first();
  const refused = page.locator('main [role="alert"]').first();
  await done.or(refused).waitFor({ timeout: 30_000 }).catch(() => {});
  if (await done.isVisible()) return;
  const reason = await text(refused);
  throw new Error(reason ? `Commerce refused it: "${reason}"` : `Commerce never said "${message}".`);
}
