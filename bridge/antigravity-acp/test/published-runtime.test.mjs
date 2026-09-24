import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createAcpRuntime } from "acpx/runtime";
import { createAgentRegistry } from "acpx/agent-registry";
import {
  ACPX_AGENT_REGISTRY_JS_SHA256,
  ACPX_LAST_INSPECTED_SOURCE_COMMIT,
  ACPX_LAST_INSPECTED_SOURCE_RELEASE,
  ACPX_NPM_INTEGRITY,
  ACPX_OPENCLAW_EXTENSIONS_PACKAGE,
  ACPX_OPENCLAW_MAIN_COMMIT,
  ACPX_RELEASE,
  ACPX_RUNTIME_JS_SHA256,
  ACPX_SOURCE_COMMIT,
  ACPX_TARBALL_SHA256,
  ACPX_TARBALL_URL,
  RUNTIME_PIN,
  currentPlatformId,
  platformLaunch,
  settingsPath,
  validateRuntimePin,
} from "../contract.mjs";
import { AntigravityAcpBroker, createProcessLifecycleTracker } from "../broker.mjs";
import {
  ACPX_ARTIFACT_PATH,
  ACPX_ARTIFACT_SHA256,
  ACPX_CANDIDATE_PACKAGE_VERSION,
  ACPX_MERGE_COMMIT,
  discardCandidateTurnEvents,
} from "../../cursor-acp/puppet-adapter.mjs";

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
  "@agentclientprotocol/sdk": "^1.4.0",
  "@openclaw/fs-safe": "^0.12.0",
  commander: "^15.0.0",
  skillflag: "^0.2.1",
  tsx: "^4.23.13",
  zod: "^4.6.2",
};
const EXPECTED_DEPENDENCY_VERSIONS = {
  "@agentclientprotocol/sdk": "1.4.0",
  "@openclaw/fs-safe": "0.12.0",
  commander: "15.0.0",
  skillflag: "0.2.1",
  tsx: "4.23.13",
  zod: "4.6.5",
};

function requirePublishedInstall() {
  assert.equal(
    existsSync(installedPackage),
    true,
    "published acpx@0.19.1 must be installed by local npm ci in this bridge",
  );
}

test("native pin exercises published acpx 0.19.1 public runtime and agent-registry exports", async () => {
  requirePublishedInstall();
  const manifest = JSON.parse(readFileSync(installedPackage, "utf8"));
  const lock = JSON.parse(readFileSync(lockfile, "utf8"));
  const pinned = lock.packages["node_modules/acpx"];
  const runtimeDigest = createHash("sha256").update(readFileSync(installedRuntime)).digest("hex");
  const registryDigest = createHash("sha256").update(readFileSync(installedRegistry)).digest("hex");

  assert.equal(manifest.version, "0.19.1");
  assert.equal(manifest.version, ACPX_RELEASE);
  assert.equal(manifest.gitHead, undefined);
  assert.equal(manifest.engines.node, ">=22.13.0");
  assert.deepEqual(manifest.exports, EXPECTED_EXPORTS);
  assert.equal(ACPX_SOURCE_COMMIT, null);
  assert.equal(RUNTIME_PIN.acpxSourceCommit, null);
  assert.equal(RUNTIME_PIN.lastInspectedSourceCommit, ACPX_LAST_INSPECTED_SOURCE_COMMIT);
  assert.equal(RUNTIME_PIN.lastInspectedSourceRelease, ACPX_LAST_INSPECTED_SOURCE_RELEASE);
  assert.equal(ACPX_LAST_INSPECTED_SOURCE_RELEASE, "0.17.1");
  assert.equal(validateRuntimePin(RUNTIME_PIN).acpxSourceCommit, null);
  assert.throws(
    () => validateRuntimePin({
      ...RUNTIME_PIN,
      acpxSourceCommit: ACPX_LAST_INSPECTED_SOURCE_COMMIT,
    }),
    /source commit is unknown/,
  );
  assert.throws(
    () => validateRuntimePin({
      ...RUNTIME_PIN,
      lastInspectedSourceRelease: ACPX_RELEASE,
    }),
    /not the published 0\.19\.1 release/,
  );
  assert.equal(pinned.version, "0.19.1");
  assert.equal(pinned.resolved, ACPX_TARBALL_URL);
  assert.equal(pinned.integrity, ACPX_NPM_INTEGRITY);
  assert.equal(runtimeDigest, ACPX_RUNTIME_JS_SHA256);
  assert.equal(registryDigest, ACPX_AGENT_REGISTRY_JS_SHA256);
  assert.equal(ACPX_TARBALL_SHA256, "f99d74e81085121563c917f4509758fb78bf1fa30424e469193c09837592bbf0");
  assert.notEqual(ACPX_RELEASE, HISTORICAL_PUBLISHED_NPM_VERSION);
  assert.notEqual(pinned.integrity, HISTORICAL_PUBLISHED_NPM_INTEGRITY);
  assert.notEqual(ACPX_TARBALL_SHA256, HISTORICAL_PUBLISHED_TARBALL_SHA256);
  assert.notEqual(runtimeDigest, HISTORICAL_PUBLISHED_RUNTIME_JS_SHA256);
  assert.equal(ACPX_CANDIDATE_PACKAGE_VERSION, "0.18.0");
  assert.equal(ACPX_MERGE_COMMIT, "2e05de525dd1ab62e9e74bf02d91e3638920fcf3");
  assert.notEqual(ACPX_RELEASE, ACPX_CANDIDATE_PACKAGE_VERSION);
  assert.notEqual(ACPX_TARBALL_SHA256, ACPX_ARTIFACT_SHA256);
  assert.match(ACPX_ARTIFACT_PATH, /acpx-0\.18\.0\.tgz$/);
  assert.equal(ACPX_OPENCLAW_MAIN_COMMIT, "482a4b2c499a053b173c5d36d78cf67b9137e013");
  assert.equal(ACPX_OPENCLAW_EXTENSIONS_PACKAGE, "2026.9.7");
  assert.notEqual(ACPX_OPENCLAW_MAIN_COMMIT, ACPX_LAST_INSPECTED_SOURCE_COMMIT);
  assert.notEqual(ACPX_OPENCLAW_MAIN_COMMIT, ACPX_MERGE_COMMIT);
  for (const [name, range] of Object.entries(EXPECTED_DECLARED_DEPENDENCIES)) {
    assert.equal(manifest.dependencies[name], range, name);
  }
  for (const [name, version] of Object.entries(EXPECTED_DEPENDENCY_VERSIONS)) {
    assert.equal(lock.packages[`node_modules/${name}`].version, version, name);
  }
  assert.equal(typeof createAcpRuntime, "function");
  assert.equal(typeof createAgentRegistry, "function");

  const registry = createAgentRegistry({
    overrides: { antigravity: [process.execPath, "--version"] },
  });
  const sessions = new Map();
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0191-agy-"));
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

test("installed acpx 0.19.1 Antigravity runtime completes a local synthetic-peer turn and retires the owned child", {
  timeout: 60_000,
}, async () => {
  requirePublishedInstall();
  const peer = fileURLToPath(new URL("../../cursor-acp/test/candidate-peer.mjs", import.meta.url));
  const cwd = mkdtempSync(path.join(tmpdir(), "acpx-0191-agy-lifecycle-"));
  const tracker = createProcessLifecycleTracker();
  const sessions = new Map();
  const sessionKey = "agy-acp-published-0191";
  const registry = createAgentRegistry({
    overrides: { antigravity: [process.execPath, peer] },
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
      agent: "antigravity",
      mode: "persistent",
      cwd,
    });
    const turn = runtime.startTurn({
      handle,
      text: "published runtime proof ping",
      mode: "prompt",
      requestId: "published-0191-agy-turn",
    });
    const discarded = await discardCandidateTurnEvents(turn);
    assert.equal(discarded.body_retained, false);
    const result = await turn.result;
    assert.equal(result.status, "completed");
    await runtime.close({
      handle,
      reason: "published-0191-agy-lifecycle-complete",
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
  assert.equal(ACPX_SOURCE_COMMIT, null);
  assert.equal(ACPX_CANDIDATE_PACKAGE_VERSION, "0.18.0");
});

test("broker leaves explicit approve-all permission decisions to the pinned runtime", {
  timeout: 60_000,
  skip: !existsSync(installedPackage),
}, async () => {
  const rootDir = mkdtempSync(path.join(tmpdir(), "acpx-0191-broker-permission-"));
  const stateRoot = path.join(rootDir, "state");
  const workspace = path.join(rootDir, "workspace");
  const runtimeDir = path.join(rootDir, "runtime");
  const geminiHome = path.join(rootDir, "gemini-home");
  mkdirSync(workspace, { recursive: true });
  mkdirSync(runtimeDir, { recursive: true });
  mkdirSync(path.dirname(settingsPath(geminiHome)), { recursive: true });
  const launch = platformLaunch(currentPlatformId());
  writeFileSync(path.join(runtimeDir, path.basename(launch.runtimeCommand)), "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  writeFileSync(path.join(runtimeDir, path.basename(launch.helper)), "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  writeFileSync(settingsPath(geminiHome), JSON.stringify({ auth: { type: "oauth-personal" }, useG1Credits: false }));

  const peer = fileURLToPath(new URL("./permission-peer.mjs", import.meta.url));
  const registry = createAgentRegistry({
    overrides: { antigravity: [process.execPath, peer, "--permission", "fs_write_file"] },
  });
  const sessions = new Map();
  const runtime = createAcpRuntime({
    cwd: stateRoot,
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
    permissionMode: "approve-all",
    nonInteractivePermissions: "fail",
    timeoutMs: 30_000,
  });
  const broker = new AntigravityAcpBroker({
    stateRoot,
    runtimeDir,
    geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    runtime,
    defaultHostConversationId: "conv-pinned-permission",
    defaultBinderId: "test-owner",
  });
  try {
    await broker.init();
    const submitted = await broker.delegate({
      workspace,
      model: "gemini-3.8-flash-high",
      prompt: "Ask the synthetic peer to perform its bounded permission probe.",
    });
    let job;
    const deadline = Date.now() + 30_000;
    do {
      job = await broker.getJob(submitted.jobId);
      if (job.status === "completed" || job.status === "failed") break;
      await new Promise((resolve) => setTimeout(resolve, 25));
    } while (Date.now() < deadline);
    assert.equal(job.status, "completed", JSON.stringify(job));
    assert.equal(job.error, undefined);
  } finally {
    await broker.close().catch(() => {});
    rmSync(rootDir, { recursive: true, force: true });
  }
});
