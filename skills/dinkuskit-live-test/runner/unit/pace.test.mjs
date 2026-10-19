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
  const replays = new WeakSet();
  watchStoreRequests(context, { replayed: request => replays.has(request) });
  // A browser is watched once, however often it's handed over.
  watchStoreRequests(context, { replayed: () => false });
  const done = (url, { replay = false, failed = false } = {}) => {
    const request = { url: () => url };
    if (replay) replays.add(request);
    context.emit(failed ? "requestfailed" : "requestfinished", request);
  };
  // A file answered from the browser's own copy never reaches the store; its first load does.
  done("https://store.example/_astro/page.js");
  done("https://store.example/_astro/page.js", { replay: true });
  // A request that fails on the way may still have reached the store.
  done("https://store.example/", { failed: true });
  // Other sites, and a local development server's own scripts, never count.
  done("https://dinkuskit.com/account");
  done("https://store.example/@vite/client");
  done("https://store.example/src/pages/index.astro");
  done("https://store.example/node_modules/.vite/deps/react.js");
  countStoreRequest("https://checkout.stripe.com/pay");
  countStoreRequest("https://store.example/products/cap");
  // Three count: the file's first load, the failed page and the probe.
  await paceStore(STORE_BUDGET - 3);
  let ready = false;
  const waiting = paceStore(STORE_BUDGET - 2).then(() => { ready = true; });
  t.mock.timers.tick(59_000);
  await Promise.resolve();
  assert.equal(ready, false);
  t.mock.timers.tick(1_500);
  await waiting;
  assert.equal(ready, true);
});
