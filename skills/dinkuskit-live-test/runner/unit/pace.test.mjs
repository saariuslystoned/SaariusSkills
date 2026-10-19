import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { after } from "node:test";

// Each test file runs in its own process, so this file's settings and request counts stay its own.
const dir = mkdtempSync(join(tmpdir(), "dinkus-pace-"));
after(() => rmSync(dir, { recursive: true, force: true }));
Object.assign(process.env, {
  DINKUS_E2E_ENV_FILE: join(dir, "no-settings"),
  DINKUS_E2E_PROOF: dir,
  DINKUS_E2E_PROFILE: join(dir, "profile"),
  DINKUS_E2E_STORE: "https://store.example",
});
const { STORE_BUDGET, countStoreRequest, paceStore, waitFor, watchStoreRequests } = await import("../support/pace.mjs");

const now = 1_000_000;
const sentAt = (count, from) => Array.from({ length: count }, (_, i) => from + i);

test("requests that fit under the budget go at once", () => {
  assert.equal(waitFor([], 1, now), 0);
  assert.equal(waitFor(sentAt(STORE_BUDGET - 40, now - 30_000), 40, now), 0);
  // Requests more than a minute old no longer count.
  assert.equal(waitFor(sentAt(STORE_BUDGET, now - 90_000), STORE_BUDGET, now), 0);
});

test("requests that don't fit wait until enough of the oldest are a minute old", () => {
  const times = sentAt(STORE_BUDGET, now - 30_000);
  // One more waits for the oldest to age out; ten more wait for the tenth oldest.
  assert.equal(waitFor(times, 1, now), times[0] + 60_000 - now);
  assert.equal(waitFor(times, 10, now), times[9] + 60_000 - now);
  // More than the whole budget waits for the minute to empty, rather than forever.
  assert.equal(waitFor(times, STORE_BUDGET * 2, now), times.at(-1) + 60_000 - now);
});

test("only requests that reach the store count, and a step waits for room", { timeout: 10_000 }, async t => {
  t.mock.timers.enable({ apis: ["Date", "setTimeout"], now: 5_000_000 });
  const context = new EventEmitter();
  watchStoreRequests(context);
  watchStoreRequests(context);
  const request = url => context.emit("request", { url: () => url });
  const response = (url, cacheControl) => context.emit("response", { url: () => url, headers: () => ({ "cache-control": cacheControl }) });
  // A file the store sends as immutable reaches it only the first time; the run replays it after that.
  request("https://store.example/_astro/page.js");
  response("https://store.example/_astro/page.js", "public, max-age=31536000, immutable");
  request("https://store.example/_astro/page.js");
  // A page that may change reaches the store every time.
  request("https://store.example/");
  response("https://store.example/", "no-cache");
  request("https://store.example/");
  // Other sites, and a local development server's own scripts, never count.
  request("https://dinkuskit.com/account");
  request("https://store.example/@vite/client");
  request("https://store.example/src/pages/index.astro");
  request("https://store.example/node_modules/.vite/deps/react.js");
  countStoreRequest("https://checkout.stripe.com/pay");
  countStoreRequest("https://store.example/products/cap");
  // Four count, once each though the browser is watched twice: the file once, the page twice and the probe.
  await paceStore(STORE_BUDGET - 4);
  let done = false;
  const waiting = paceStore(STORE_BUDGET - 3).then(() => { done = true; });
  t.mock.timers.tick(59_000);
  await Promise.resolve();
  assert.equal(done, false);
  t.mock.timers.tick(1_500);
  await waiting;
  assert.equal(done, true);
});
