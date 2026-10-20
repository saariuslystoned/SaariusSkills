// What the DinkusKit.com account and connect pages actually show, and the one
// Payments control that starts a connection. Decisions only. The journey clicks.

// /account, when the owner is signed in and the business is approved with no store yet.
export const CONNECT_INSTRUCTION = "Install the DinkusKit Payments plugin in your EmDash store, open its setup page and press Connect. You'll come back here to approve it.";

// /account/connect. The service name is the registered id, "payments", not a label.
export const CONSENT_HEADING = "Connect this store?";
export const CONSENT_SERVICE = "Service: payments";
export const CONSENT_PAYMENTS = "Payments status and processor setup access; this does not grant checkout access.";
export const APPROVE_PAYMENTS = "Approve payments";

// dinkus-payments-beta's admin page. The menu label is "Payments status".
// dinkuskit/payments src/registry/identity.ts and emdash-plugin.jsonc.
export const PAYMENTS_BETA_STATUS_PATH = "/_emdash/admin/plugins/r_sffx6l4z6mpqliki/status";
export const PAYMENTS_STATUS_LABEL = "Payments status";
export const PAYMENT_SETUP_HEADING = "Payment setup";
export const AUTHORIZE_LINK = "Authorize Payments at DinkusKit";

const linesOf = text => text.split("\n").map(line => line.trim()).filter(Boolean);
const originOf = value => {
  try { return new URL(value).origin; } catch { return ""; }
};

/**
 * What to do with the account page. "connected" means this store is already listed:
 * leave it. "connect" means the page says to press Connect in Payments. Anything else
 * stops, so the journey never switches business, approves a business, or starts Connect.
 */
export function accountReading(text, store) {
  const storeOrigin = originOf(store);
  const lines = linesOf(text);
  const listed = lines.some(line => line === storeOrigin);
  if (lines.includes("Finish creating your account")) return { next: "stop", reason: "The account isn't finished. This journey does not create one." };
  if (lines.includes("Your store is connected") && listed) return { next: "connected" };
  if (lines.includes("Your store is connected")) return { next: "stop", reason: "The account says a store is connected, but not this one. This journey will not switch business or press Connect." };
  if (lines.includes("Waiting for approval")) return { next: "stop", reason: "This business is waiting for approval. A store can connect after that. This journey does not approve a business." };
  if (lines.includes("Your businesses")) return { next: "stop", reason: "This account has more than one business. This journey will not pick one." };
  if (lines.includes("Connect your store")) {
    if (!text.includes(CONNECT_INSTRUCTION)) return { next: "stop", reason: "The account says to connect a store, but not by pressing Connect in the Payments plugin." };
    return { next: "connect" };
  }
  if (lines.some(line => line.startsWith("You're on the staff of"))) return { next: "stop", reason: "This sign-in is staff, not the owner. Only the owner can approve a store connection." };
  return { next: "stop", reason: "The account page did not say this store is connected or ask to connect it." };
}

/** The consent page is this store and Payments, still waiting. Otherwise Approve stays unpressed. */
export function consentReading(text, store) {
  const lines = linesOf(text);
  if (!lines.includes(CONSENT_HEADING)) return { ok: false, reason: "The page is not Connect this store? Approve was not pressed." };
  if (!lines.includes(CONSENT_SERVICE)) return { ok: false, reason: "The page is not asking to connect Payments. Approve was not pressed." };
  if (!text.includes(CONSENT_PAYMENTS)) return { ok: false, reason: "The page does not describe Payments access the way DinkusKit.com does. Approve was not pressed." };
  if (!lines.includes(`Site origin: ${originOf(store)}`)) return { ok: false, reason: "The page is not this store. Approve was not pressed." };
  if (lines.includes("This connection is no longer waiting for consent.")) return { ok: false, reason: "This connection is no longer waiting for consent. Approve was not pressed." };
  return { ok: true };
}

/** Authorize Payments at DinkusKit must open this account's connect page and nothing else. */
export function isDinkusConnectLink(href, account) {
  let url;
  try { url = new URL(href); } catch { return false; }
  if (url.origin !== originOf(account)) return false;
  if (url.pathname !== "/account/connect") return false;
  const ids = url.searchParams.getAll("connection_id");
  if (ids.length !== 1 || !ids[0]) return false;
  if ([...url.searchParams.keys()].some(key => key !== "connection_id")) return false;
  return !url.hash;
}

/** A DinkusKit.com magic-link address. The journey never records one. */
export function isSignInLink(href) {
  try { return new URL(href).pathname.startsWith("/api/auth/magic-link/"); } catch { return false; }
}

/** Menu links that are the beta Payments status page on this store, and no other. */
export function betaPaymentsStatusLinks(hrefs, store) {
  const storeOrigin = originOf(store);
  return hrefs.filter(href => {
    try {
      const url = new URL(href, store);
      return url.origin === storeOrigin && url.pathname === PAYMENTS_BETA_STATUS_PATH && !url.search && !url.hash;
    } catch { return false; }
  });
}
