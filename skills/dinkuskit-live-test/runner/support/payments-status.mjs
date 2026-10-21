import { APPROVE_PAYMENTS, AUTHORIZE_LINK, PAYMENTS_BETA_STATUS_PATH, betaPaymentsStatusLinks, consentReading } from "./connect-dinkuskit.mjs";
import { config } from "./env.mjs";
import { mailBaseline, waitForMail } from "./mail.mjs";
import { filterPage } from "./request-policy.mjs";

// Payments status in the store admin. The menu label and path are the plugin's admin page
// (dinkuskit/payments emdash-plugin.jsonc). The screen is Block Kit from
// src/registry/setup.ts renderSetupScreen: Connect, Sign in again, Continue and Check connection
// are buttons; Authorize Payments at DinkusKit is an external link. That link opens
// dinkuskit.com/account/connect, whose submit button is "Approve payments"
// (src/pages/account/connect.astro). registry_session is written only by that flow.
// Reconnect, Deny, and Set up or resume Stripe are on those pages and this journey never presses them.

const CONNECTION_ID = /^[A-Za-z0-9_-]{1,200}$/;
const SECRET = /sk_(?:test|live)_[0-9A-Za-z]+|rk_(?:test|live)_[0-9A-Za-z]+|whsec_[0-9A-Za-z]+|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/;

export { AUTHORIZE_LINK };
export const CONNECT_LINE = "Connect your DinkusKit account to check payment setup.";
const BANNERS = ["Not ready to sell", "Connected: Stripe test mode", "Payment status not checked"];
const PRESSABLE = ["Connect", "Sign in again", "Continue", "Check connection"];

/** DinkusKit's connect page for one connection, and nothing else that could carry a token. */
export function authorizeHref(href, account) {
  let url;
  try { url = new URL(href); } catch { return false; }
  if (url.origin !== account || url.username || url.password || url.hash || url.pathname !== "/account/connect") return false;
  const keys = [...url.searchParams.keys()];
  const id = url.searchParams.get("connection_id");
  return keys.length === 1 && keys[0] === "connection_id" && url.searchParams.getAll("connection_id").length === 1 && CONNECTION_ID.test(id ?? "");
}

/** A store key or session token in text the proof might keep. */
export function showsSecret(text) {
  return SECRET.test(String(text ?? ""));
}

/** Proof text with store keys, session tokens and connection ids removed. */
export function redact(text) {
  return String(text ?? "")
    .replace(new RegExp(SECRET.source, "g"), "[secret]")
    .replace(/connection_id=[^&\s]+/gi, "connection_id=[redacted]");
}

/**
 * What the open Payments status page is saying, from its visible text. The connect line is the
 * unconfigured Connect payments step. Connected: Stripe test mode is the verified TEST banner.
 */
export function readStatusText(text) {
  const lines = String(text ?? "").split("\n").map(line => line.trim()).filter(Boolean);
  const connect = lines.find(line => line.startsWith("Connect payments:")) ?? "";
  const banner = lines.find(line => BANNERS.includes(line)) ?? "";
  return {
    header: lines.includes("Payment setup"),
    banner,
    connect,
    connectedTest: banner === "Connected: Stripe test mode" || connect.includes("Connected: Stripe test mode"),
    asksToConnect: connect.includes(CONNECT_LINE),
  };
}

/**
 * The next connect control, or leave. Never Reconnect, Deny, Set up or resume Stripe, or any
 * other control. `approved` means DinkusKit's Approve payments was already pressed this run.
 */
export function nextPress(reading, controls, { approved = false } = {}) {
  const buttons = controls?.buttons ?? [];
  const links = controls?.links ?? [];
  if (reading?.connectedTest) {
    return {
      action: "leave",
      because: buttons.includes("Sign in again")
        ? "Last check was Connected: Stripe test mode. Sign in again was left alone."
        : "Connected: Stripe test mode. Reconnect and Stripe setup were left alone.",
    };
  }
  if (reading?.asksToConnect) {
    return buttons.includes("Connect")
      ? { action: "press", name: "Connect" }
      : { action: "blocked", because: "The page asks to connect a DinkusKit account, but it has no Connect button." };
  }
  if (buttons.includes("Sign in again")) return { action: "press", name: "Sign in again" };
  if (!approved && links.includes(AUTHORIZE_LINK)) return { action: "authorize" };
  if (buttons.includes("Continue")) return { action: "press", name: "Continue" };
  if (buttons.includes("Set up or resume Stripe") || links.includes("Continue setup at Stripe")) {
    return { action: "leave", because: "DinkusKit Payments status was checked. Set up or resume Stripe was left alone." };
  }
  if (buttons.includes("Check connection")) return { action: "press", name: "Check connection" };
  return { action: "blocked", because: "The Payments status page shows no connect control from its status screen." };
}

/**
 * The beta Payments plugin's status page among the admin menu's Payments status links. The beta
 * store also runs the release listing, which has its own Payments status page; that one is left alone.
 */
export async function paymentsStatusAdmin(page) {
  const { openAdmin } = await import("./store-admin.mjs");
  await openAdmin(page, `${config.store}/_emdash/admin`);
  const links = page.getByRole("link", { name: "Payments status", exact: true });
  await links.first().waitFor({ timeout: 30_000 }).catch(() => {});
  const [beta] = betaPaymentsStatusLinks(await links.evaluateAll(anchors => anchors.map(anchor => anchor.href)), config.store);
  if (beta) return beta;
  throw new Error("The store admin's menu showed no Payments status page for dinkus-payments-beta within 30 seconds: the plugin isn't installed, is switched off, or the admin didn't finish loading. The release listing's page is not used.");
}

/** Opens Payments status and waits until Payment setup is on the page. A plugin error is not kept if it carries a secret. */
export async function openPaymentsStatus(page, url) {
  const { openAdmin } = await import("./store-admin.mjs");
  await openAdmin(page, url);
  const heading = page.getByRole("heading", { name: "Payment setup", exact: true });
  const failed = page.getByRole("heading", { name: "Plugin Error", exact: true });
  await heading.or(failed).first().waitFor({ timeout: 60_000 });
  if (await failed.isVisible()) await failClosed(page, `Payments status didn't open. ${await page.locator("main").innerText()}`);
}

/** The open page's reading and the button and link labels in main. Blanks the page if a secret is visible. */
export async function readPaymentsScreen(page) {
  const main = page.locator("main");
  const text = await main.innerText();
  if (showsSecret(text)) await failClosed(page, "Payments status showed a store key or session secret. It was not kept.");
  const buttons = (await main.getByRole("button").allInnerTexts()).map(label => label.trim()).filter(Boolean);
  const links = (await main.getByRole("link").allInnerTexts()).map(label => label.replace(/\s+/g, " ").trim()).filter(Boolean);
  return { reading: readStatusText(text), controls: { buttons, links } };
}

/** Presses one connect button. Any other name is refused. */
export async function pressNamed(page, name) {
  if (!PRESSABLE.includes(name)) throw new Error("That control is not part of the Payments status connect path.");
  const main = page.locator("main");
  const before = await main.innerText();
  await main.getByRole("button", { name, exact: true }).click();
  await page.waitForFunction(previous => {
    const shown = document.querySelector("main");
    return shown && shown.innerText !== previous;
  }, before, { timeout: 60_000 }).catch(() => {});
}

/** The Authorize link's address, when it is DinkusKit's connect page and nothing else. */
export async function authorizeLink(page) {
  const href = await page.locator("main").getByRole("link", { name: AUTHORIZE_LINK, exact: true }).getAttribute("href");
  if (!authorizeHref(href, config.account)) await failClosed(page, "Authorize Payments at DinkusKit does not open DinkusKit's connect page.");
  return href;
}

/**
 * Opens Authorize Payments at DinkusKit and presses Approve payments, only when the page asks to
 * connect this store to Payments. Deny is never pressed.
 * A signed-out account is signed in with the test inbox first; the connect page sends that
 * sign-in to /account with no way back, so the same connect address is opened again after.
 * The address is not written down.
 */
export async function approvePayments(page, href) {
  if (!authorizeHref(href, config.account)) await failClosed(page, "Authorize Payments at DinkusKit does not open DinkusKit's connect page.");
  const popupPromise = page.context().waitForEvent("page", { timeout: 15_000 }).catch(() => null);
  await page.locator("main").getByRole("link", { name: AUTHORIZE_LINK, exact: true }).click();
  const popup = await popupPromise;
  const consent = popup ?? page;
  try {
    if (popup) await filterPage(popup, config);
    await consent.waitForLoadState("domcontentloaded");
    if (consent.url().startsWith(`${config.account}/account/sign-in`)) {
      await signInToAccount(consent);
      await consent.goto(href);
      await consent.waitForLoadState("domcontentloaded");
    }
    const heading = consent.getByRole("heading", { name: "Connect this store?", exact: true });
    await heading.waitFor({ timeout: 30_000 }).catch(async () => {
      await failClosed(consent, "DinkusKit did not show Connect this store?.");
    });
    const reading = consentReading(await consent.locator("main").innerText(), config.store);
    if (!reading.ok) await failClosed(consent, reading.reason);
    const approve = consent.getByRole("button", { name: APPROVE_PAYMENTS, exact: true });
    if (!await approve.count()) {
      const said = (await consent.locator("body").innerText()).split("\n").map(line => line.trim()).find(Boolean) ?? "";
      await failClosed(consent, said || "DinkusKit's connect page has no Approve payments button.");
    }
    await approve.click();
    // DinkusKit answers by sending the page on: back to the store, back to the connect page with
    // ?error=<reason>, or to another account page (sites, sign-in) for a refusal it can't show there.
    const landed = await consent.waitForURL(next => {
      try {
        const url = new URL(next);
        if (url.origin === config.store) return true;
        return url.origin === config.account && (url.pathname !== "/account/connect" || url.searchParams.has("error"));
      } catch { return false; }
    }, { timeout: 60_000 }).then(() => new URL(consent.url()), () => null);
    if (!landed) await failClosed(consent, "DinkusKit did not answer Approve payments within a minute.");
    // Only dinkus-payments-beta's page counts: the beta store's release listing has its own.
    if (landed.origin !== config.store || landed.pathname !== PAYMENTS_BETA_STATUS_PATH) {
      const reason = landed.searchParams.get("error") ?? "";
      const where = landed.origin === config.store ? "another store page" : `DinkusKit's ${landed.pathname}`;
      await failClosed(consent, `DinkusKit.com did not approve this connection${/^[a-z_]{1,64}$/.test(reason) ? ` (${reason})` : ""}; it sent the owner to ${where}.`);
    }
    // The status page's own load finishes the connection. Closing before Payment setup is shown would cut that off.
    await consent.getByRole("heading", { name: "Payment setup", exact: true }).waitFor({ timeout: 60_000 }).catch(async () => {
      await failClosed(consent, "Payments status did not show Payment setup after Approve payments.");
    });
  } finally {
    if (popup) await popup.close().catch(() => {});
  }
}

/** DinkusKit.com's magic-link sign-in. The link is opened and never written down. */
async function signInToAccount(popup) {
  if (!config.ownerEmail) await failClosed(popup, "DINKUS_E2E_OWNER_EMAIL is not set, so the test cannot ask DinkusKit.com for a sign-in link.");
  if (!config.mailCmd) await failClosed(popup, "DinkusKit.com asked for a sign-in link and no mail command is set.");
  const baseline = mailBaseline("dinkuskit");
  await popup.locator("#email").fill(config.ownerEmail);
  await popup.getByRole("button", { name: "Email me a sign-in link", exact: true }).click();
  const link = await waitForMail("dinkuskit", baseline);
  if (!link) await failClosed(popup, "No DinkusKit sign-in link arrived.");
  await popup.goto(link).catch(async () => {
    await failClosed(popup, "The DinkusKit sign-in link did not open.");
  });
}

/** Leaves a blank page so a later screenshot cannot keep a key, token or connection address. */
async function failClosed(page, message) {
  await page.goto("about:blank").catch(() => {});
  throw new Error(redact(message).split("\n")[0]);
}
