import { appendFileSync, readdirSync, readFileSync, unlinkSync } from "node:fs";
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
// So each store request is also logged beside the proof folders as it's sent, and every worker starts
// from the logs' last minute. Each minute of each store gets its own log, so a log is only ever added
// to, never rewritten while another process may be adding to it, and goes once none of it counts.
const logs = config.store ? dirname(config.runDir) : "";
const logPrefix = config.store ? `.store-requests-${new URL(config.store).host.replace(/[^a-z0-9.-]/gi, "-")}-` : "";
const minuteOf = time => Math.floor(time / MINUTE);

/**
 * This store's logs that can still hold a request of the last 60 seconds: this minute's and the one
 * before. Older minutes' logs are removed.
 */
function recentLogs(now = Date.now()) {
  let names = [];
  try { names = readdirSync(logs); } catch { return []; }
  const recent = [];
  for (const name of names) {
    const minute = name.startsWith(logPrefix) && name.endsWith(".log") ? Number(name.slice(logPrefix.length, -4)) : NaN;
    if (!Number.isInteger(minute)) continue;
    if (minute >= minuteOf(now) - 1) recent.push(join(logs, name));
    else try { unlinkSync(join(logs, name)); } catch {}
  }
  return recent;
}

let loggedMinute = 0;
/** Adds `line` to the log of the minute in which the request it's about was sent, at `at`. */
const logLine = (at, line) => {
  if (!logs) return;
  try { appendFileSync(join(logs, `${logPrefix}${minuteOf(at)}.log`), `${line}\n`); } catch {}
  // A new minute leaves the logs before the last one with nothing that counts.
  if (minuteOf(at) > loggedMinute) {
    loggedMinute = minuteOf(at);
    recentLogs();
  }
};

/**
 * When the logged store requests of the last minute were sent, oldest first. A line "-<time>" takes back
 * one request sent then, which the browser answered from its own copy.
 */
function logged() {
  const now = Date.now();
  const counts = new Map();
  for (const log of recentLogs(now)) {
    let lines = [];
    try { lines = readFileSync(log, "utf8").split("\n").filter(Boolean); } catch {}
    for (const line of lines) {
      const time = Math.abs(Number(line));
      if (time > now - MINUTE) counts.set(time, (counts.get(time) ?? 0) + (line.startsWith("-") ? -1 : 1));
    }
  }
  return [...counts].flatMap(([time, count]) => Array(Math.max(count, 0)).fill(time)).sort((a, b) => a - b);
}

// When each store request of the last minute was sent, oldest first, with the request itself until the
// run knows whether it reached the store.
const sent = logs ? logged().map(at => ({ at })) : [];
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

// Requests more than a minute old no longer count.
const forgetOld = () => {
  while (sent.length && sent[0].at <= Date.now() - MINUTE) sent.shift();
};

/**
 * Counts `context`'s requests that reach the store, from when each is sent, since the store counts it
 * then, and logs each as it's sent. One the run answers from the browser's own copy of an immutable store
 * file (see request-policy.mjs) never reaches the store, so once it's answered it stops counting and the
 * log takes it back. One that fails on the way may still have reached the store, so it counts.
 */
export function watchStoreRequests(context, { replayed = wasReplayed } = {}) {
  if (watched.has(context)) return;
  watched.add(context);
  context.on("request", request => {
    const url = request.url();
    if (!isStore(url) || DEV_SERVER.test(new URL(url).pathname)) return;
    forgetOld();
    const at = Date.now();
    sent.push({ at, request });
    logLine(at, at);
  });
  const done = request => {
    const index = sent.findLastIndex(entry => entry.request === request);
    if (index < 0) return;
    if (replayed(request)) {
      logLine(sent[index].at, `-${sent[index].at}`);
      sent.splice(index, 1);
    } else delete sent[index].request;
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
  logLine(at, at);
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
