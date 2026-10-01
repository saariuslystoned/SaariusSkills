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
  ACPX_ARTIFACT_PATH,
  ACPX_ARTIFACT_SHA256,
  ACPX_CANDIDATE_PACKAGE_VERSION,
  ACPX_MERGE_COMMIT,
  ACPX_OPENCLAW_EXTENSIONS_PACKAGE,
  ACPX_OPENCLAW_MAIN_COMMIT,
  ACPX_ORDINARY_PINNED_PACKAGE,
  ACPX_PUBLISHED_AGENT_REGISTRY_JS_SHA256,
  ACPX_PUBLISHED_NPM_INTEGRITY,
  ACPX_PUBLISHED_NPM_VERSION,
  ACPX_PUBLISHED_SOURCE_COMMIT,
  ACPX_PUBLISHED_RUNTIME_JS_SHA256,
  ACPX_PUBLISHED_TARBALL_SHA256,
  ACPX_PUBLISHED_TARBALL_URL,
  ACPX_QUALIFICATION,
  createProcessLifecycleTracker,
  discardCandidateTurnEvents,
} from "../puppet-adapter.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const installedPackage = path.join(root, "node_modules/acpx/package.json");
const installedRuntime = path.join(root, "node_modules/acpx/dist/runtime.js");
const installedRegistry = path.join(root, "node_modules/acpx/dist/agent-registry.js");
const lockfile = path.join(root, "package-lock.json");
const HISTORICAL_PUBLISHED_NPM_VERSION = "0.19.0";
const HISTORICAL_PUBLISHED_NPM_INTEGRITY =
  "sha512-sgG0CkhuvVxgfiksXjIPEl9hsHZW0CpxywPdQeoIP5D31gwZE4nrnddLUUqaSCLb1UIM7LFPBL5qdvy15/+B6Q==";
const HISTORICAL_PUBLISHED_TARBALL_SHA256 =
  "5a61820401cfed668ce3ad77a2feaebdd9e496a037ba28b2afca3224e7505c6d";
const HISTORICAL_PUBLISHED_RUNTIME_JS_SHA256 =
  "88a9799088146a191360a297bec94fb9006853a4420bef6257635a6b10520e1b";
const EXPECTED_EXPORTS = {
  ".": "./dist/cli.js",
  "./runtime": "./dist/runtime.js",
  "./flows": "./dist/flows.js",
  "./dist/*": "./dist/*",
  "./package.json": "./package.json",
  "./agent-registry": "./dist/agent-registry.js",
};
const EXPECTED_DECLARED_DEPENDENCIES = {
  "@agentclientprotocol/sdk": "^1.5.0",
  "@openclaw/fs-safe": "^0.21.1",
  commander: "^15.0.0",
  skillflag: "^0.2.1",
  tsx: "^4.23.15",
  zod: "^4.6.5",
};
const EXPECTED_DEPENDENCY_VERSIONS = {
  "@agentclientprotocol/sdk": "1.5.1",
  "@openclaw/fs-safe": "0.21.3",
  commander: "15.0.0",
  skillflag: "0.2.1",
  tsx: "4.23.15",
  zod: "4.6.5",
};

function requirePublishedInstall() {
  assert.equal(
    existsSync(installedPackage),
    true,
    "published acpx@0.19.4 must be installed by local npm ci in this bridge",
  );
}

test("native pin exercises published acpx 0.19.4 public runtime and agent-registry exports", async () => {
  requirePublishedInstall();
  const manifest = JSON.parse(readFileSync(installedPackage, "utf8"));
  const lock = JSON.parse(readFileSync(lockfile, "utf8"));
  const pinned = lock.packages["node_modules/acpx"];
  const runtimeDigest = createHash("sha256").update(readFileSync(installedRuntime)).digest("hex");
  const registryDigest = createHash("sha256").update(readFileSync(installedRegistry)).digest("hex");

  assert.equal(manifest.version, "0.19.4");
  assert.equal(manifest.version, ACPX_PUBLISHED_NPM_VERSION);
  assert.equal(ACPX_ORDINARY_PINNED_PACKAGE, "0.19.4");
  assert.equal(ACPX_PUBLISHED_SOURCE_COMMIT, "8e396609238086dee6a407fdb3b3ac46dbdedd70");
  assert.equal(manifest.gitHead, undefined);
  assert.equal(manifest.engines.node, ">=22.13.0");
  assert.deepEqual(manifest.exports, EXPECTED_EXPORTS);
  assert.equal(pinned.version, "0.19.4");
  assert.equal(pinned.resolved, ACPX_PUBLISHED_TARBALL_URL);
  assert.equal(pinned.integrity, ACPX_PUBLISHED_NPM_INTEGRITY);
  assert.equal(
    pinned.integrity,
    "sha512-fN1c3Ype4LrwZoeJwcZEnyO+1ArThgymwswmJyd52dHKaz+3hjkR6lYdlyBPOZYIIcCVARezcfvkFUNxsylSBA==",
  );
  assert.equal(runtimeDigest, ACPX_PUBLISHED_RUNTIME_JS_SHA256);
  assert.equal(registryDigest, ACPX_PUBLISHED_AGENT_REGISTRY_JS_SHA256);
  assert.equal(ACPX_PUBLISHED_TARBALL_SHA256, "ccb1e4ad1cb1468493769af3a2ba0df6aeffb4e1e176541f1f231f3ec5782311");
  assert.equal(ACPX_CANDIDATE_PACKAGE_VERSION, "0.18.0");
  assert.equal(ACPX_MERGE_COMMIT, "2e05de525dd1ab62e9e74bf02d91e3638920fcf3");
  assert.notEqual(ACPX_PUBLISHED_NPM_VERSION, ACPX_CANDIDATE_PACKAGE_VERSION);
  assert.notEqual(ACPX_PUBLISHED_TARBALL_SHA256, ACPX_ARTIFACT_SHA256);
  assert.match(ACPX_ARTIFACT_PATH, /acpx-0\.18\.0\.tgz$/);
  assert.notEqual(ACPX_PUBLISHED_NPM_VERSION, HISTORICAL_PUBLISHED_NPM_VERSION);
  assert.notEqual(pinned.integrity, HISTORICAL_PUBLISHED_NPM_INTEGRITY);
  assert.notEqual(ACPX_PUBLISHED_TARBALL_SHA256, HISTORICAL_PUBLISHED_TARBALL_SHA256);
  assert.notEqual(runtimeDigest, HISTORICAL_PUBLISHED_RUNTIME_JS_SHA256);
  assert.equal(ACPX_OPENCLAW_MAIN_COMMIT, "482a4b2c499a053b173c5d36d78cf67b9137e013");
  assert.equal(ACPX_OPENCLAW_EXTENSIONS_PACKAGE, "2026.9.7");
  assert.notEqual(ACPX_OPENCLAW_MAIN_COMMIT, ACPX_MERGE_COMMIT);
  for (const [name, range] of Object.entries(EXPECTED_DECLARED_DEPENDENCIES)) {
    assert.equal(manifest.dependencies[name], range, name);
  }
  for (const [name, version] of Object.entries(EXPECTED_DEPENDENCY_VERSIONS)) {
    assert.equal(lock.packages[`node_modules/${name}`].version, version, name);
  }
  assert.equal(typeof createAcpRuntime, "function");
  assert.equal(typeof createAgentRegistry, "function");
  assert.equal(ACPX_QUALIFICATION, "synthetic_only");

  const registry = createAgentRegistry({
    overrides: { cursor: [process.execPath, "--version"] },
  });
  const sessions = new Map();
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0191-cursor-"));
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

test("installed acpx 0.19.4 Cursor runtime completes a local synthetic-peer turn and retires the owned child", {
  timeout: 60_000,
}, async () => {
  requirePublishedInstall();
  const peer = fileURLToPath(new URL("./candidate-peer.mjs", import.meta.url));
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0193-cursor-lifecycle-"));
  const tracker = createProcessLifecycleTracker();
  const sessions = new Map();
  const sessionKey = "cursor-acp-published-0193";
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
      requestId: "published-0193-turn",
    });
    const discarded = await discardCandidateTurnEvents(turn);
    assert.equal(discarded.body_retained, false);
    const result = await turn.result;
    assert.equal(result.status, "completed");
    await runtime.close({
      handle,
      reason: "published-0193-lifecycle-complete",
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
  assert.equal(ACPX_CANDIDATE_PACKAGE_VERSION, "0.18.0");
});

test("installed acpx 0.19.4 keeps reused backend session ids separate from local records", {
  timeout: 60_000,
}, async () => {
  requirePublishedInstall();
  const peer = fileURLToPath(new URL("./candidate-peer.mjs", import.meta.url));
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0194-cursor-records-"));
  const tracker = createProcessLifecycleTracker();
  const sessions = new Map();
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
    agentRegistry: createAgentRegistry({ overrides: { cursor: [process.execPath, peer] } }),
    fs: false,
    terminal: false,
    timeoutMs: 30_000,
    processLifecycle: tracker.processLifecycle,
  });
  try {
    const first = await runtime.ensureSession({
      sessionKey: "cursor-record-one",
      agent: "cursor",
      mode: "persistent",
      cwd,
    });
    const second = await runtime.ensureSession({
      sessionKey: "cursor-record-two",
      agent: "cursor",
      mode: "persistent",
      cwd,
    });
    assert.equal(first.backendSessionId, second.backendSessionId);
    assert.notEqual(first.acpxRecordId, second.acpxRecordId);
    assert.equal(sessions.size, 2);
    await runtime.close({ handle: first, reason: "record-separation-first", discardPersistentState: true });
    await runtime.close({ handle: second, reason: "record-separation-second", discardPersistentState: true });
    for (const sessionKey of ["cursor-record-one", "cursor-record-two"]) {
      const proof = await tracker.waitForOwnedExit(sessionKey, { timeoutMs: 10_000 });
      assert.equal(proof.status, "exited");
      assert.equal(proof.exits.length, proof.started.length);
    }
  } finally {
    await runtime.shutdown().catch(() => {});
    rmSync(cwd, { recursive: true, force: true });
  }
});
