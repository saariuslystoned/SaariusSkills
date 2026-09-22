import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createAcpRuntime } from "acpx/runtime";
import { createAgentRegistry } from "acpx/agent-registry";
import {
  ACPX_PUBLISHED_NPM_INTEGRITY,
  ACPX_PUBLISHED_NPM_VERSION,
  ACPX_PUBLISHED_RUNTIME_JS_SHA256,
  ACPX_PUBLISHED_TARBALL_SHA256,
  ACPX_QUALIFICATION,
  createProcessLifecycleTracker,
  discardCandidateTurnEvents,
} from "../puppet-adapter.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const installedPackage = path.join(root, "node_modules/acpx/package.json");
const installedRuntime = path.join(root, "node_modules/acpx/dist/runtime.js");
const lockfile = path.join(root, "package-lock.json");

function requirePublishedInstall() {
  assert.equal(
    existsSync(installedPackage),
    true,
    "published acpx@0.19.0 must be installed by local npm ci in this bridge",
  );
}

test("native pin exercises published acpx 0.19.0 public runtime and agent-registry exports", async () => {
  requirePublishedInstall();
  const manifest = JSON.parse(readFileSync(installedPackage, "utf8"));
  const lock = JSON.parse(readFileSync(lockfile, "utf8"));
  const pinned = lock.packages["node_modules/acpx"];
  const runtimeDigest = createHash("sha256").update(readFileSync(installedRuntime)).digest("hex");

  assert.equal(manifest.version, "0.19.0");
  assert.equal(manifest.version, ACPX_PUBLISHED_NPM_VERSION);
  assert.equal(manifest.gitHead, undefined);
  assert.equal(pinned.version, "0.19.0");
  assert.equal(pinned.integrity, ACPX_PUBLISHED_NPM_INTEGRITY);
  assert.equal(
    pinned.integrity,
    "sha512-sgG0CkhuvVxgfiksXjIPEl9hsHZW0CpxywPdQeoIP5D31gwZE4nrnddLUUqaSCLb1UIM7LFPBL5qdvy15/+B6Q==",
  );
  assert.equal(runtimeDigest, ACPX_PUBLISHED_RUNTIME_JS_SHA256);
  assert.equal(ACPX_PUBLISHED_TARBALL_SHA256, "5a61820401cfed668ce3ad77a2feaebdd9e496a037ba28b2afca3224e7505c6d");
  assert.equal(typeof createAcpRuntime, "function");
  assert.equal(typeof createAgentRegistry, "function");
  assert.equal(ACPX_QUALIFICATION, "synthetic_only");

  const registry = createAgentRegistry({
    overrides: { cursor: [process.execPath, "--version"] },
  });
  const sessions = new Map();
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0190-cursor-"));
  const runtime = createAcpRuntime({
    cwd,
    sessionStore: {
      async load(id) {
        const record = sessions.get(id);
        return record === undefined ? undefined : structuredClone(record);
      },
      async save(record) {
        sessions.set(record.acpxRecordId, structuredClone(record));
      },
    },
    agentRegistry: registry,
    fs: false,
    terminal: false,
  });
  assert.equal(typeof runtime.ensureSession, "function");
  assert.equal(typeof runtime.getStatus, "function");
  assert.equal(typeof runtime.startTurn, "function");
  assert.equal(typeof runtime.close, "function");
  assert.equal(typeof runtime.shutdown, "function");
  await runtime.shutdown();
});

test("installed acpx 0.19.0 Cursor runtime completes a local synthetic-peer turn and retires the owned child", {
  timeout: 60_000,
}, async () => {
  requirePublishedInstall();
  const peer = fileURLToPath(new URL("./candidate-peer.mjs", import.meta.url));
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0190-cursor-lifecycle-"));
  const tracker = createProcessLifecycleTracker();
  const sessions = new Map();
  const sessionKey = "cursor-acp-published-0190";
  const registry = createAgentRegistry({
    overrides: { cursor: [process.execPath, peer] },
  });
  const runtime = createAcpRuntime({
    cwd,
    sessionStore: {
      async load(id) {
        const record = sessions.get(id);
        return record === undefined ? undefined : structuredClone(record);
      },
      async save(record) {
        sessions.set(record.acpxRecordId, structuredClone(record));
      },
    },
    agentRegistry: registry,
    fs: false,
    terminal: false,
    timeoutMs: 30_000,
    processLifecycle: tracker.processLifecycle,
  });
  try {
    const handle = await runtime.ensureSession({
      sessionKey,
      agent: "cursor",
      mode: "persistent",
      cwd,
    });
    const turn = runtime.startTurn({
      handle,
      text: "published runtime proof ping",
      mode: "prompt",
      requestId: "published-0190-turn",
    });
    const discarded = await discardCandidateTurnEvents(turn);
    assert.equal(discarded.body_retained, false);
    const result = await turn.result;
    assert.equal(result.status, "completed");
    await runtime.close({
      handle,
      reason: "published-0190-lifecycle-complete",
      discardPersistentState: true,
    });
    const proof = await tracker.waitForOwnedExit(sessionKey, { timeoutMs: 10_000 });
    assert.equal(proof.status, "exited");
    assert.ok(proof.started.length >= 1, JSON.stringify(proof));
    assert.equal(proof.exits.length, proof.started.length);
    for (const started of proof.started) {
      assert.equal(started.scope.kind, "runtime-session");
      assert.equal(started.scope.sessionKey, sessionKey);
      assert.notEqual(started.pid, process.pid);
    }
  } finally {
    try {
      await runtime.shutdown();
    } catch {
      // Shutdown must not hide the lifecycle proof.
    }
    rmSync(cwd, { recursive: true, force: true });
  }
  const settled = tracker.snapshotOwned(sessionKey);
  assert.ok(settled.started.length >= 1);
  assert.equal(settled.exits.length, settled.started.length);
  for (const started of settled.started) {
    assert.throws(
      () => process.kill(started.pid, 0),
      (error) => error && error.code === "ESRCH",
    );
  }
  assert.equal(ACPX_QUALIFICATION, "synthetic_only");
});
