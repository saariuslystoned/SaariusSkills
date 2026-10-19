import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
const log = join(dir, ".store-requests-store.example.log");
const now = 5_000_000;
const lines = (count, at) => Array(count).fill(`${at}\n`).join("");

test("a new worker counts the store requests sent in the last minute before it started", { timeout: 10_000 }, async t => {
  t.mock.timers.enable({ apis: ["Date", "setTimeout"], now });
  // Sixty requests 30 seconds ago still count; forty two minutes ago no longer do.
  writeFileSync(log, lines(40, now - 120_000) + lines(60, now - 30_000));
  const { STORE_BUDGET, countStoreRequest, paceStore } = await import("../support/pace.mjs");
  // The log keeps only those, so back-to-back runs don't grow it.
  assert.equal(readFileSync(log, "utf8"), lines(60, now - 30_000));
  await paceStore(STORE_BUDGET - 60);
  let ready = false;
  const waiting = paceStore(STORE_BUDGET - 59).then(() => { ready = true; });
  t.mock.timers.tick(29_000);
  await Promise.resolve();
  assert.equal(ready, false);
  t.mock.timers.tick(1_500);
  await waiting;
  assert.equal(ready, true);
  // Its own requests go in the log for the worker after it.
  countStoreRequest("https://store.example/products/cap");
  assert.equal(readFileSync(log, "utf8"), lines(60, now - 30_000) + lines(1, now + 30_500));
});

test("a log with nothing from the last minute starts over", async t => {
  t.mock.timers.enable({ apis: ["Date"], now: now + 600_000 });
  // A second copy of the module, as a later worker loads it.
  const { STORE_BUDGET, paceStore } = await import("../support/pace.mjs?later");
  assert.equal(existsSync(log), false);
  await paceStore(STORE_BUDGET);
});
