import { appendFileSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
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
// The store counts a visitor's requests, not one test process's: Playwright starts a new worker after a
// journey fails, and a run started straight after another still has that run's last minute against it.
// So each request that reached the store is also logged beside the proof folders, one log per store,
// and every worker starts from the log's last minute.
const log = config.store ? join(dirname(config.runDir), `.store-requests-${new URL(config.store).host.replace(/[^a-z0-9.-]/gi, "-")}.log`) : "";

/** When the logged store requests of the last minute were sent, oldest first. The log keeps only those. */
function logged() {
  let lines = [];
  try { lines = readFileSync(log, "utf8").split("\n").filter(Boolean); } catch { return []; }
  const since = Date.now() - MINUTE;
  const times = lines.map(Number).filter(time => time > since).sort((a, b) => a - b);
  // Older requests no longer count, so the log drops them, and with none left it starts over.
  try {
    if (!times.length) unlinkSync(log);
    else if (times.length < lines.length) writeFileSync(log, times.map(time => `${time}\n`).join(""));
  } catch {}
  return times;
}

// When each store request of the last minute was sent, oldest first, with the request itself until the
// run knows whether it reached the store.
const sent = log ? logged().map(at => ({ at })) : [];
const watched = new WeakSet();

const isStore = url => {
  try {
    const { protocol, origin } = new URL(url);
    // A blob: address carries the page's origin but never leaves the browser.
    return (protocol === "https:" || protocol === "http:") && origin === config.store;
  } catch { return false; }
};
// Scripts only a local development server sends (a deployed store bundles them under /_astro/).
const DEV_SERVER = /^\/(?:@|node_modules\/|src\/)/;

const logSent = at => {
  if (log) try { appendFileSync(log, `${at}\n`); } catch {}
};
// Requests more than a minute old no longer count.
const forgetOld = () => {
  while (sent.length && sent[0].at <= Date.now() - MINUTE) sent.shift();
};

/**
 * Counts `context`'s requests that reach the store, from when each is sent, since the store counts it
 * then. One the run answers from the browser's own copy of an immutable store file (see
 * request-policy.mjs) never reaches the store, and stops counting once it's answered. One that fails on
 * the way may still have reached the store, so it counts.
 */
export function watchStoreRequests(context, { replayed = wasReplayed } = {}) {
  if (watched.has(context)) return;
  watched.add(context);
  context.on("request", request => {
    const url = request.url();
    if (!isStore(url) || DEV_SERVER.test(new URL(url).pathname)) return;
    forgetOld();
    sent.push({ at: Date.now(), request });
  });
  const done = request => {
    const index = sent.findLastIndex(entry => entry.request === request);
    if (index < 0) return;
    if (replayed(request)) sent.splice(index, 1);
    else {
      logSent(sent[index].at);
      delete sent[index].request;
    }
  };
  context.on("requestfinished", done);
  context.on("requestfailed", done);
}

/** Counts a request the run sends to `url` outside a browser, such as a link probe. */
export function countStoreRequest(url) {
  if (!isStore(url)) return;
  forgetOld();
  const at = Date.now();
  sent.push({ at });
  logSent(at);
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
    forgetOld();
    const wait = waitFor(sent.map(entry => entry.at), room);
    if (!wait) return;
    await new Promise(resolve => setTimeout(resolve, wait + 250));
  }
}
