import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { after } from "node:test";

// Each test file runs in its own process, which here stands in for a worker Playwright starts after a
// journey fails, or for a run started straight after another.
const dir = mkdtempSync(join(tmpdir(), "dinkus-pace-log-"));
after(() => rmSync(dir, { recursive: true, force: true }));
Object.assign(process.env, {
  DINKUS_E2E_ENV_FILE: join(dir, "no-settings"),
  DINKUS_E2E_PROOF: dir,
  DINKUS_E2E_PROFILE: join(dir, "profile"),
  DINKUS_E2E_STORE: "https://store.example",
});
// Each minute's requests go in a log of their own, named for that minute (counted from 1970).
const log = minute => join(dir, `.store-requests-store.example-${minute}.log`);
const logs = () => readdirSync(dir).filter(name => name.startsWith(".store-requests-")).sort();
// 83 minutes and 20 seconds.
const now = 5_000_000;
const lines = (count, at) => Array(count).fill(`${at}\n`).join("");

test("a new worker counts the store requests sent in the last minute before it started", { timeout: 10_000 }, async t => {
  t.mock.timers.enable({ apis: ["Date", "setTimeout"], now });
  // Sixty requests sent 30 seconds ago, in minute 82, still count; forty sent two minutes ago, in minute
  // 81, no longer do.
  writeFileSync(log(81), lines(40, now - 120_000));
  writeFileSync(log(82), lines(60, now - 30_000));
  const { STORE_BUDGET, countStoreRequest, paceStore } = await import("../support/pace.mjs");
  // The older minute's log goes, so back-to-back runs don't pile them up.
  assert.deepEqual(logs(), [".store-requests-store.example-82.log"]);
  await paceStore(STORE_BUDGET - 60);
  let ready = false;
  const waiting = paceStore(STORE_BUDGET - 59).then(() => { ready = true; });
  t.mock.timers.tick(29_000);
  await Promise.resolve();
  assert.equal(ready, false);
  t.mock.timers.tick(1_500);
  await waiting;
  assert.equal(ready, true);
  // Its own requests go in the log of the minute they're sent in, for the worker after it, and the
  // earlier minute's log stays as it was.
  countStoreRequest("https://store.example/products/cap");
  assert.equal(readFileSync(log(83), "utf8"), lines(1, now + 30_500));
  assert.equal(readFileSync(log(82), "utf8"), lines(60, now - 30_000));
});

test("the log takes back a request the browser answered from its own copy", { timeout: 10_000 }, async t => {
  // Minute 88, so the earlier test's logs no longer count.
  const at = now + 300_000;
  t.mock.timers.enable({ apis: ["Date", "setTimeout"], now: at });
  const { STORE_BUDGET, watchStoreRequests } = await import("../support/pace.mjs?replays");
  assert.deepEqual(logs(), []);
  const context = new EventEmitter();
  const replays = new WeakSet();
  watchStoreRequests(context, { replayed: request => replays.has(request) });
  const first = { url: () => "https://store.example/_astro/page.js" };
  const again = { url: () => "https://store.example/_astro/page.js" };
  context.emit("request", first);
  context.emit("request", again);
  // Both are logged as they're sent, before anything says whether they reach the store.
  assert.equal(readFileSync(log(88), "utf8"), lines(2, at));
  context.emit("requestfinished", first);
  replays.add(again);
  context.emit("requestfinished", again);
  assert.equal(readFileSync(log(88), "utf8"), `${lines(2, at)}-${at}\n`);
  // A worker started after it counts only the one that reached the store.
  const later = await import("../support/pace.mjs?after-replays");
  await later.paceStore(STORE_BUDGET - 1);
  let ready = false;
  const waiting = later.paceStore(STORE_BUDGET).then(() => { ready = true; });
  await Promise.resolve();
  assert.equal(ready, false);
  t.mock.timers.tick(60_250);
  await waiting;
});

test("logs with nothing from the last minute start over", async t => {
  t.mock.timers.enable({ apis: ["Date"], now: now + 600_000 });
  // Another copy of the module, as a later worker loads it.
  const { STORE_BUDGET, paceStore } = await import("../support/pace.mjs?later");
  assert.deepEqual(logs(), []);
  await paceStore(STORE_BUDGET);
});
