import { config } from "./env.mjs";
import { wasReplayed } from "./request-policy.mjs";

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
// Each further page of Commerce's image picker shows twelve more photos.
export const PICKER_PAGE_ROOM = 15;

const MINUTE = 60_000;
const sent = [];
const watched = new WeakSet();

const isStore = url => {
  try { return new URL(url).origin === config.store; } catch { return false; }
};
// Scripts only a local development server sends (a deployed store bundles them under /_astro/).
const DEV_SERVER = /^\/(?:@|node_modules\/|src\/)/;

/**
 * Counts `context`'s requests that reach the store. Each counts once it's done, when the run knows
 * whether it went to the store or was answered from the browser's own copy of an immutable store file
 * (see request-policy.mjs); one that fails on the way may still have reached the store.
 */
export function watchStoreRequests(context, { replayed = wasReplayed } = {}) {
  if (watched.has(context)) return;
  watched.add(context);
  const done = request => {
    const url = request.url();
    if (isStore(url) && !replayed(request) && !DEV_SERVER.test(new URL(url).pathname)) sent.push(Date.now());
  };
  context.on("requestfinished", done);
  context.on("requestfailed", done);
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
