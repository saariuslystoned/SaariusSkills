import { config } from "./env.mjs";

// The store allows each visitor (each IP address) 120 requests a minute, and every page, photo and
// admin call counts against it. Every browser the run opens counts its store requests here, whichever
// journey sent them, and a step about to send many first waits until they fit under STORE_BUDGET for
// the last minute, leaving a margin for requests the run can't count.
export const STORE_BUDGET = 100;
// The most a store page sends when it opens: the page, its scripts the first time, and the photos in view.
export const PAGE_ROOM = 40;
// Scrolling to one product's photo brings its neighbours' photos into view too.
export const PHOTO_ROOM = 10;
// An upload opens the Media library, which shows a page of 35 photos, and choosing the new photo opens
// Commerce's image picker with twelve more.
export const MEDIA_ROOM = 70;

const MINUTE = 60_000;
const sent = [];
const watched = new WeakSet();

const isStore = url => {
  try { return new URL(url).origin === config.store; } catch { return false; }
};
// Scripts only a local development server sends (a deployed store bundles them under /_astro/).
const DEV_SERVER = /^\/(?:@|node_modules\/|src\/)/;

/** Counts `context`'s requests to the store. */
export function watchStoreRequests(context) {
  if (watched.has(context)) return;
  watched.add(context);
  // The run answers repeat loads of a file the store sent as immutable from the browser's own copy (see
  // request-policy.mjs), so only its first load reaches the store.
  const kept = new Set();
  context.on("response", response => {
    if (isStore(response.url()) && /\bimmutable\b/i.test(response.headers()["cache-control"] ?? "")) kept.add(response.url());
  });
  context.on("request", request => {
    const url = request.url();
    if (!isStore(url) || kept.has(url) || DEV_SERVER.test(new URL(url).pathname)) return;
    sent.push(Date.now());
  });
}

/** Counts a request the run sends to `url` outside a browser, such as a link probe. */
export function countStoreRequest(url) {
  if (isStore(url)) sent.push(Date.now());
}

/**
 * How long until `room` more requests fit under STORE_BUDGET, given when the earlier ones were sent,
 * oldest first: none while they fit, else until enough of the oldest are a minute old.
 */
export function waitFor(times, room, now = Date.now()) {
  const recent = times.filter(time => time > now - MINUTE);
  const over = recent.length + Math.min(room, STORE_BUDGET) - STORE_BUDGET;
  return over > 0 ? recent[over - 1] + MINUTE - now : 0;
}

/** Waits until `room` more store requests fit under STORE_BUDGET for the last minute. */
export async function paceStore(room = 1) {
  for (;;) {
    while (sent.length && sent[0] <= Date.now() - MINUTE) sent.shift();
    const wait = waitFor(sent, room);
    if (!wait) return;
    await new Promise(resolve => setTimeout(resolve, wait + 250));
  }
}
