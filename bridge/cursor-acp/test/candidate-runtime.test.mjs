import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, chmod, readFile, readdir, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import test from "node:test";
import {
  ACPX_ARTIFACT_SHA256,
  ACPX_ARTIFACT_PATH,
  ACPX_CANDIDATE_RUNTIME_MODULE,
  ACPX_CANDIDATE_RUNTIME_ROOT,
  ACPX_QUALIFICATION,
  AdapterError,
  CursorAcpxAdapter,
  adapterAvailable,
  auditDurableArtifacts,
  bindCandidateRuntime,
  boundedCandidateTurnResult,
  callerOutcomes,
  claimIsolatedRoot,
  createVerifiedCandidateAcpRuntime,
  markCleanupUnknown,
  materializeVerifiedCandidateAcpx,
  proveInstalledCandidateModule,
  recordBoundCandidateTurn,
  rejectCandidateRuntimeConversationParams,
  resolveContainedOwnedPath,
} from "../puppet-adapter.mjs";

const execFile = promisify(execFileCallback);

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PEER = fileURLToPath(new URL("./candidate-peer.mjs", import.meta.url));
const TEST_PROMPT = "candidate runtime proof ping";
const LOCAL_ARTIFACT = path.join(REPO_ROOT, ACPX_ARTIFACT_PATH);
const REAL_ARTIFACT_SKIP = existsSync(LOCAL_ARTIFACT)
  ? false
  : "exact local acpx artifact is task-owned proof input";

function memorySessionStore() {
  const sessions = new Map();
  return {
    async load(id) {
      const record = sessions.get(id);
      return record === undefined ? undefined : structuredClone(record);
    },
    async save(record) {
      sessions.set(record.acpxRecordId, structuredClone(record));
    },
  };
}

async function privateRoot() {
  const root = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-candidate-"));
  const isolated = path.join(root, "isolated");
  const workspace = path.join(root, "workspace");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  await mkdir(workspace);
  return { root, isolated, workspace };
}

const HOST = Object.freeze({
  owner: "puppet-owner",
  session: "cursor-acp-session",
  conversationId: "conv-cursor-acp-1",
  requestId: "candidate-runtime-turn",
});

class FakePublicRuntime {
  constructor({
    handle = {},
    turnRequestId,
    statusLastRequestId,
    omitLastRequestId = false,
    result = { status: "completed", stopReason: "end_turn" },
    closeError,
  } = {}) {
    this.handleOverrides = handle;
    this.turnRequestId = turnRequestId;
    this.statusLastRequestId = statusLastRequestId;
    this.omitLastRequestId = omitLastRequestId;
    this.result = result;
    this.closeError = closeError;
    this.ensureCalls = [];
    this.statusCalls = [];
    this.startCalls = [];
    this.closeCalls = [];
  }

  async ensureSession(input) {
    this.ensureCalls.push({
      keys: Object.keys(input).sort(),
      sessionKey: input.sessionKey,
      agent: input.agent,
      mode: input.mode,
      cwd: input.cwd,
    });
    return {
      sessionKey: input.sessionKey,
      backend: "acpx",
      runtimeSessionName: `acpx:${input.sessionKey}`,
      cwd: input.cwd,
      acpxRecordId: `record-${input.sessionKey}`,
      backendSessionId: "backend-session-1",
      agentSessionId: "agent-session-1",
      ...this.handleOverrides,
    };
  }

  async getStatus(input) {
    this.statusCalls.push({
      keys: Object.keys(input).sort(),
      sessionKey: input.handle?.sessionKey,
    });
    if (this.omitLastRequestId || (this.startCalls.length === 0 && this.statusLastRequestId === undefined)) {
      return {};
    }
    return {
      lastRequestId: this.startCalls.length
        ? (this.statusLastRequestId ?? this.startCalls.at(-1).requestId)
        : this.statusLastRequestId,
    };
  }

  startTurn(input) {
    this.startCalls.push({
      keys: Object.keys(input).sort(),
      mode: input.mode,
      requestId: input.requestId,
      sessionKey: input.handle?.sessionKey,
      hasText: typeof input.text === "string" && input.text.length > 0,
    });
    return {
      requestId: this.turnRequestId ?? input.requestId,
      promptStarted: Promise.resolve(),
      result: Promise.resolve(this.result),
    };
  }

  async close(input) {
    this.closeCalls.push({
      keys: Object.keys(input).sort(),
      sessionKey: input.handle?.sessionKey,
      reason: input.reason,
      discardPersistentState: input.discardPersistentState,
    });
    if (this.closeError) throw this.closeError;
  }
}

async function claimHost(isolated) {
  return claimIsolatedRoot(isolated, {
    owner: HOST.owner,
    session: HOST.session,
    conversationId: HOST.conversationId,
  });
}

function boundTurnOptions(isolated, workspace, runtime, extra = {}) {
  return {
    isolatedRoot: isolated,
    workspaceRoot: workspace,
    owner: HOST.owner,
    hostSession: HOST.session,
    hostConversationId: HOST.conversationId,
    requestId: HOST.requestId,
    runtime,
    agent: "candidate",
    mode: "oneshot",
    text: TEST_PROMPT,
    ...extra,
  };
}

async function readEvents(isolated) {
  const raw = await readFile(path.join(isolated, "events.jsonl"), "utf8");
  return raw.split("\n").filter(Boolean).map((line) => JSON.parse(line));
}

async function readClaim(isolated) {
  return JSON.parse(await readFile(path.join(isolated, "ownership.json"), "utf8"));
}

function assertNoRuntimeCalls(runtime) {
  assert.equal(runtime.ensureCalls.length, 0);
  assert.equal(runtime.statusCalls.length, 0);
  assert.equal(runtime.startCalls.length, 0);
  assert.equal(runtime.closeCalls.length, 0);
}

function assertOwnedUnfenced(claim) {
  assert.equal(claim.cleanup, "owned");
  assert.equal(claim.replacement_blocked, false);
}

function assertFencedClaim(claim) {
  assert.equal(claim.cleanup, "unknown");
  assert.equal(claim.replacement_blocked, true);
}

function eventNamed(events, name) {
  return events.filter((item) => item.event === name);
}

test("owned runtime path rejects symlink escape and accepts contained roots", async () => {
  const owned = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-owned-"));
  const escape = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-escape-"));
  try {
    const runtime = path.join(owned, "runtime");
    const contained = path.join(owned, "runtime-real");
    await mkdir(contained, { mode: 0o700 });
    await chmod(contained, 0o700);
    const accepted = await resolveContainedOwnedPath(owned, contained);
    assert.equal(accepted, await realpath(contained));

    await symlink(escape, runtime);
    await assert.rejects(
      () => resolveContainedOwnedPath(owned, runtime),
      (error) => error instanceof AdapterError && /escapes the owned root/.test(error.message),
    );

    const moduleDir = path.join(contained, "node_modules", "acpx", "dist");
    await mkdir(moduleDir, { recursive: true });
    const modulePath = path.join(moduleDir, "runtime.js");
    const escapedModule = path.join(escape, "runtime.js");
    await writeFile(escapedModule, "export function createAcpRuntime() { return { escaped: true }; }\n");
    await symlink(escapedModule, modulePath);
    await assert.rejects(
      () => resolveContainedOwnedPath(contained, modulePath),
      (error) => error instanceof AdapterError && /escapes the owned root/.test(error.message),
    );
  } finally {
    await rm(owned, { recursive: true, force: true });
    await rm(escape, { recursive: true, force: true });
  }
});

test("installed candidate runtime bytes are bound and cache drift fails closed", async () => {
  const fixture = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-integrity-"));
  try {
    const payloadDir = path.join(fixture, "package", "dist");
    await mkdir(payloadDir, { recursive: true });
    const expectedSource = "export function createAcpRuntime() { return { fixture: true }; }\n";
    await writeFile(path.join(payloadDir, "runtime.js"), expectedSource);
    const artifact = path.join(fixture, "acpx-fixture.tgz");
    await execFile("tar", ["-czf", artifact, "package"], { cwd: fixture });

    const modulePath = path.join(fixture, "runtime", "node_modules", "acpx", "dist", "runtime.js");
    await mkdir(path.dirname(modulePath), { recursive: true });
    await writeFile(modulePath, expectedSource);
    const proved = await proveInstalledCandidateModule({
      modulePath,
      artifactPath: artifact,
    });
    assert.equal(proved.module_sha256, createHash("sha256").update(expectedSource).digest("hex"));

    await writeFile(modulePath, "export function createAcpRuntime() { return { tampered: true }; }\n");
    await assert.rejects(
      () => proveInstalledCandidateModule({
        modulePath,
        artifactPath: artifact,
      }),
      (error) => error instanceof AdapterError && /installed candidate runtime digest drifted/.test(error.message),
    );
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test("installed candidate imported chunk bytes are bound and cache drift fails closed", async () => {
  const fixture = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-chunk-"));
  try {
    const payloadDir = path.join(fixture, "package", "dist");
    await mkdir(payloadDir, { recursive: true });
    const chunkName = "ipc-B0t1qnI2.js";
    const chunkSource = "export const marker = \"archive-chunk\";\n";
    const expectedSource = [
      `import { marker } from "./${chunkName}";`,
      "export function createAcpRuntime() { return { fixture: true, marker }; }",
      "",
    ].join("\n");
    await writeFile(path.join(payloadDir, "runtime.js"), expectedSource);
    await writeFile(path.join(payloadDir, chunkName), chunkSource);
    const artifact = path.join(fixture, "acpx-fixture.tgz");
    await execFile("tar", ["-czf", artifact, "package"], { cwd: fixture });

    const moduleDir = path.join(fixture, "runtime", "node_modules", "acpx", "dist");
    const modulePath = path.join(moduleDir, "runtime.js");
    const chunkPath = path.join(moduleDir, chunkName);
    await mkdir(moduleDir, { recursive: true });
    await writeFile(modulePath, expectedSource);
    await writeFile(chunkPath, chunkSource);
    const proved = await proveInstalledCandidateModule({
      modulePath,
      artifactPath: artifact,
    });
    assert.equal(proved.module_sha256, createHash("sha256").update(expectedSource).digest("hex"));
    assert.deepEqual(proved.imported_chunks, [{
      artifact_entry: `package/dist/${chunkName}`,
      sha256: createHash("sha256").update(chunkSource).digest("hex"),
    }]);

    await writeFile(chunkPath, `${chunkSource}// stale chunk review marker\n`);
    await assert.rejects(
      () => proveInstalledCandidateModule({
        modulePath,
        artifactPath: artifact,
      }),
      (error) => error instanceof AdapterError && /installed candidate imported chunk digest drifted/.test(error.message),
    );
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test("candidate runtime rejects bridge, shared modules, and arbitrary roots", async () => {
  await assert.rejects(
    () => materializeVerifiedCandidateAcpx({
      runtimeRoot: path.join(REPO_ROOT, "bridge", "cursor-acp"),
    }),
    (error) => error instanceof AdapterError && /bridge directory/.test(error.message),
  );
  await assert.rejects(
    () => materializeVerifiedCandidateAcpx({
      runtimeRoot: path.join(REPO_ROOT, "bridge", "cursor-acp", "node_modules"),
    }),
    (error) => error instanceof AdapterError && /shared node_modules/.test(error.message),
  );
  await assert.rejects(
    () => materializeVerifiedCandidateAcpx({ runtimeRoot: os.tmpdir() }),
    (error) => error instanceof AdapterError && /task-owned runtime directory/.test(error.message),
  );
});

test("candidate runtime helper stays unavailable and omits prompt bodies", async () => {
  assert.equal(CursorAcpxAdapter.available(), false);
  assert.equal(adapterAvailable(), false);
  await assert.rejects(
    () => createVerifiedCandidateAcpRuntime({
      cwd: "/tmp/isolated",
      sessionStore: memorySessionStore(),
      agentRegistry: { resolve() { return ["candidate"]; }, list() { return ["candidate"]; } },
      fs: false,
      terminal: false,
      permissionMode: "approve-all",
    }, { runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT) }),
    (error) => error instanceof AdapterError && error.code === "BROKER_POLICY",
  );
  await assert.rejects(
    () => createVerifiedCandidateAcpRuntime({
      cwd: "/tmp/isolated",
      sessionStore: memorySessionStore(),
      agentRegistry: { resolve() { return ["candidate"]; }, list() { return ["candidate"]; } },
      fs: true,
      terminal: false,
    }, { runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT) }),
    (error) => error instanceof AdapterError && error.code === "CALLBACKS_ENABLED",
  );
  const bounded = boundedCandidateTurnResult({ status: "completed", stopReason: "end_turn" });
  assert.deepEqual(Object.keys(bounded).sort(), [
    "availability",
    "body_retained",
    "status",
    "stopReason",
  ]);
  assert.equal(bounded.availability.available, false);
  assert.equal(bounded.availability.ordinary_launch, "unavailable");
  assert.throws(
    () => boundedCandidateTurnResult({
      status: "completed",
      stopReason: "end_turn",
      prompt: TEST_PROMPT,
    }),
    (error) => error instanceof AdapterError && error.code === "BODY_RETAINED",
  );
});

test("candidate ownership binding rejects mismatches before a prompt", async () => {
  const { isolated, workspace } = await privateRoot();
  await claimHost(isolated);

  const foreignOwner = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, foreignOwner, {
      owner: "foreign-owner",
    })),
    (error) => error instanceof AdapterError && error.code === "OWNER_MISMATCH",
  );
  assertNoRuntimeCalls(foreignOwner);
  assertOwnedUnfenced(await readClaim(isolated));

  const { isolated: foreignRoot, workspace: foreignWorkspace } = await privateRoot();
  await claimIsolatedRoot(foreignRoot, {
    owner: "foreign-owner",
    session: HOST.session,
    conversationId: HOST.conversationId,
  });
  const foreignOwned = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(foreignRoot, foreignWorkspace, foreignOwned)),
    (error) => error instanceof AdapterError && error.code === "OWNER_MISMATCH",
  );
  assertNoRuntimeCalls(foreignOwned);
  const foreignClaim = await readClaim(foreignRoot);
  assert.equal(foreignClaim.owner, "foreign-owner");
  assertOwnedUnfenced(foreignClaim);

  const missingClaimRoot = await privateRoot();
  const missingClaim = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(
      missingClaimRoot.isolated,
      missingClaimRoot.workspace,
      missingClaim,
    )),
    (error) => error instanceof AdapterError && error.code === "PROOF_MISSING",
  );
  assertNoRuntimeCalls(missingClaim);

  const fencedUnknown = new FakePublicRuntime();
  await markCleanupUnknown(isolated);
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, fencedUnknown)),
    (error) => error instanceof AdapterError && error.code === "CLEANUP_UNKNOWN",
  );
  assertNoRuntimeCalls(fencedUnknown);
  assertFencedClaim(await readClaim(isolated));

  const { isolated: blockedRoot, workspace: blockedWorkspace } = await privateRoot();
  await claimIsolatedRoot(blockedRoot, {
    owner: HOST.owner,
    session: HOST.session,
    conversationId: HOST.conversationId,
  });
  const blockedClaim = await readClaim(blockedRoot);
  blockedClaim.replacement_blocked = true;
  await writeFile(path.join(blockedRoot, "ownership.json"), `${JSON.stringify(blockedClaim)}\n`);
  const blockedRuntime = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(blockedRoot, blockedWorkspace, blockedRuntime)),
    (error) => error instanceof AdapterError && error.code === "CLEANUP_UNKNOWN",
  );
  assertNoRuntimeCalls(blockedRuntime);
  const stillBlocked = await readClaim(blockedRoot);
  assert.equal(stillBlocked.cleanup, "owned");
  assert.equal(stillBlocked.replacement_blocked, true);

  const { isolated: hostIsolated, workspace: hostWorkspace } = await privateRoot();
  await claimIsolatedRoot(hostIsolated, {
    owner: HOST.owner,
    session: HOST.session,
    conversationId: HOST.conversationId,
  });

  const foreignSession = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(hostIsolated, hostWorkspace, foreignSession, {
      hostSession: "foreign-session",
    })),
    (error) => error instanceof AdapterError && error.code === "SESSION_MISMATCH",
  );
  assertNoRuntimeCalls(foreignSession);
  assertOwnedUnfenced(await readClaim(hostIsolated));

  const foreignConversation = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(hostIsolated, hostWorkspace, foreignConversation, {
      hostConversationId: "foreign-conversation",
    })),
    (error) => error instanceof AdapterError && error.code === "SESSION_MISMATCH",
  );
  assertNoRuntimeCalls(foreignConversation);
  assertOwnedUnfenced(await readClaim(hostIsolated));

  const foreignHandleSession = new FakePublicRuntime({
    handle: { sessionKey: "foreign-runtime-session" },
  });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(hostIsolated, hostWorkspace, foreignHandleSession)),
    (error) => error instanceof AdapterError && error.code === "SESSION_MISMATCH",
  );
  assert.equal(foreignHandleSession.ensureCalls.length, 1);
  assert.equal(foreignHandleSession.statusCalls.length, 0);
  assert.equal(foreignHandleSession.startCalls.length, 0);
  assert.equal(foreignHandleSession.closeCalls.length, 0);
  assertFencedClaim(await readClaim(hostIsolated));

  const { isolated: cwdIsolated, workspace: cwdWorkspace } = await privateRoot();
  await claimIsolatedRoot(cwdIsolated, {
    owner: HOST.owner,
    session: HOST.session,
    conversationId: HOST.conversationId,
  });
  const foreignCwd = new FakePublicRuntime({
    handle: { cwd: path.join(cwdWorkspace, "other") },
  });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(cwdIsolated, cwdWorkspace, foreignCwd)),
    (error) => error instanceof AdapterError && error.code === "WORKSPACE_MISMATCH",
  );
  assert.equal(foreignCwd.ensureCalls.length, 1);
  assert.equal(foreignCwd.startCalls.length, 0);
  assert.equal(foreignCwd.closeCalls.length, 0);
  assertFencedClaim(await readClaim(cwdIsolated));

  const { isolated: bindIsolated, workspace: bindWorkspace } = await privateRoot();
  await claimIsolatedRoot(bindIsolated, {
    owner: HOST.owner,
    session: HOST.session,
    conversationId: HOST.conversationId,
  });
  await assert.rejects(
    () => bindCandidateRuntime({
      isolatedRoot: bindIsolated,
      workspaceRoot: bindWorkspace,
      owner: HOST.owner,
      hostSession: HOST.session,
      hostConversationId: HOST.conversationId,
      requestId: HOST.requestId,
      handle: {
        sessionKey: HOST.session,
        backend: "acpx",
        runtimeSessionName: "acpx:cursor-acp-session",
        cwd: bindWorkspace,
        acpxRecordId: "record-cursor-acp-session",
        backendSessionId: "backend-session-1",
        prompt: TEST_PROMPT,
      },
    }),
    (error) => error instanceof AdapterError && error.code === "BODY_RETAINED",
  );

  const missingHandle = {
    backend: "acpx",
    runtimeSessionName: "acpx:cursor-acp-session",
    cwd: bindWorkspace,
    acpxRecordId: "record-cursor-acp-session",
    backendSessionId: "backend-session-1",
  };
  await assert.rejects(
    () => bindCandidateRuntime({
      isolatedRoot: bindIsolated,
      workspaceRoot: bindWorkspace,
      owner: HOST.owner,
      hostSession: HOST.session,
      hostConversationId: HOST.conversationId,
      requestId: HOST.requestId,
      handle: missingHandle,
    }),
    (error) => error instanceof AdapterError && error.code === "PROOF_MISSING",
  );
  assert.equal("sessionKey" in missingHandle, false);

  assert.throws(
    () => rejectCandidateRuntimeConversationParams({
      sessionKey: HOST.session,
      agent: "candidate",
      mode: "oneshot",
      cwd: bindWorkspace,
      conversation_id: HOST.conversationId,
    }, "ensureSession"),
    (error) => error instanceof AdapterError && error.code === "INVALID_RUNTIME",
  );
  const smuggled = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(bindIsolated, bindWorkspace, smuggled, {
      conversation_id: HOST.conversationId,
    })),
    (error) => error instanceof AdapterError && error.code === "INVALID_RUNTIME",
  );
  assertNoRuntimeCalls(smuggled);
  assertOwnedUnfenced(await readClaim(bindIsolated));

  const events = await readEvents(hostIsolated);
  assert.deepEqual(eventNamed(events, "runtime_bound"), []);
  assert.deepEqual(eventNamed(events, "runtime_turn_completed"), []);
  assert.equal(CursorAcpxAdapter.available(), false);
  assert.equal(adapterAvailable(), false);
});

test("candidate ownership binding rejects invalid turn evidence after prompt", async () => {
  const { isolated, workspace } = await privateRoot();
  await claimHost(isolated);

  const mismatchedTurn = new FakePublicRuntime({
    turnRequestId: "foreign-turn-request",
  });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, mismatchedTurn)),
    (error) => error instanceof AdapterError && error.code === "INVALID_TURN_EVIDENCE",
  );
  assert.equal(mismatchedTurn.startCalls.length, 1);
  assert.equal(mismatchedTurn.closeCalls.length, 1);
  assert.equal(mismatchedTurn.closeCalls[0].sessionKey, HOST.session);
  assert.equal(mismatchedTurn.closeCalls[0].discardPersistentState, true);
  assertOwnedUnfenced(await readClaim(isolated));

  const mismatchedStatus = new FakePublicRuntime({
    statusLastRequestId: "foreign-status-request",
  });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, mismatchedStatus)),
    (error) => error instanceof AdapterError && error.code === "INVALID_TURN_EVIDENCE",
  );
  assert.equal(mismatchedStatus.startCalls.length, 1);
  assert.equal(mismatchedStatus.closeCalls.length, 1);
  assertOwnedUnfenced(await readClaim(isolated));

  const missingTurnId = new FakePublicRuntime({
    turnRequestId: "",
  });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, missingTurnId)),
    (error) => error instanceof AdapterError && error.code === "INVALID_TURN_EVIDENCE",
  );
  assert.equal(missingTurnId.startCalls.length, 1);
  assert.equal(missingTurnId.closeCalls.length, 1);
  assertOwnedUnfenced(await readClaim(isolated));
});

test("owned session failures clean up or fence without marking success", async () => {
  async function claimedRoot() {
    const roots = await privateRoot();
    await claimHost(roots.isolated);
    return roots;
  }

  const rejectedResult = await claimedRoot();
  const resultRuntime = new FakePublicRuntime({
    result: { status: "completed", stopReason: "end_turn", prompt: TEST_PROMPT },
  });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(
      rejectedResult.isolated,
      rejectedResult.workspace,
      resultRuntime,
    )),
    (error) => error instanceof AdapterError && error.code === "BODY_RETAINED",
  );
  assert.equal(resultRuntime.closeCalls.length, 1);
  assert.equal(resultRuntime.closeCalls[0].sessionKey, HOST.session);
  assertOwnedUnfenced(await readClaim(rejectedResult.isolated));
  assert.deepEqual(eventNamed(await readEvents(rejectedResult.isolated), "runtime_turn_completed"), []);

  const persistFailure = await claimedRoot();
  await rm(path.join(persistFailure.isolated, "events.jsonl"));
  await mkdir(path.join(persistFailure.isolated, "events.jsonl"));
  const persistRuntime = new FakePublicRuntime();
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(
      persistFailure.isolated,
      persistFailure.workspace,
      persistRuntime,
    )),
    (error) => error && error.code === "EISDIR",
  );
  assert.equal(persistRuntime.ensureCalls.length, 1);
  assert.equal(persistRuntime.startCalls.length, 0);
  assert.equal(persistRuntime.closeCalls.length, 1);
  assertOwnedUnfenced(await readClaim(persistFailure.isolated));

  const closeFailure = await claimedRoot();
  const closeError = new Error("owned session close failed");
  const closeRuntime = new FakePublicRuntime({ closeError });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(
      closeFailure.isolated,
      closeFailure.workspace,
      closeRuntime,
    )),
    (error) => error === closeError,
  );
  assert.equal(closeRuntime.closeCalls.length, 1);
  assertFencedClaim(await readClaim(closeFailure.isolated));
  assert.deepEqual(eventNamed(await readEvents(closeFailure.isolated), "runtime_turn_completed").length, 1);

  const cleanupCloseFailure = await claimedRoot();
  const cleanupCloseError = new Error("owned cleanup close failed");
  const cleanupRuntime = new FakePublicRuntime({
    turnRequestId: "foreign-turn-request",
    closeError: cleanupCloseError,
  });
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(
      cleanupCloseFailure.isolated,
      cleanupCloseFailure.workspace,
      cleanupRuntime,
    )),
    (error) => error instanceof AdapterError
      && error.code === "INVALID_TURN_EVIDENCE"
      && error !== cleanupCloseError,
  );
  assert.equal(cleanupRuntime.closeCalls.length, 1);
  assertFencedClaim(await readClaim(cleanupCloseFailure.isolated));
});

test("fake public runtime records a bound turn without inventing conversation identity", async () => {
  const { isolated, workspace } = await privateRoot();
  await claimHost(isolated);
  const runtime = new FakePublicRuntime({ omitLastRequestId: true });
  const recorded = await recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, runtime));
  assert.deepEqual(runtime.ensureCalls[0].keys, ["agent", "cwd", "mode", "sessionKey"]);
  assert.deepEqual(runtime.startCalls[0].keys, ["handle", "mode", "requestId", "text"]);
  assert.equal(runtime.startCalls[0].hasText, true);
  assert.equal(runtime.closeCalls.length, 1);
  assert.equal(runtime.closeCalls[0].discardPersistentState, true);
  assert.equal(recorded.binding.host.session, HOST.session);
  assert.equal(recorded.binding.host.conversation_id, HOST.conversationId);
  assert.equal(recorded.binding.host.request_id, HOST.requestId);
  assert.equal(recorded.binding.runtime.sessionKey, HOST.session);
  assert.equal(recorded.binding.runtime.cwd, workspace);
  assert.equal(recorded.binding.runtime.backendSessionId, "backend-session-1");
  assert.equal(recorded.binding.runtime.acpxRecordId, `record-${HOST.session}`);
  assert.equal(recorded.binding.runtime.agentSessionId, "agent-session-1");
  assert.equal("conversation_id" in recorded.binding.runtime, false);
  assert.notEqual(recorded.binding.runtime.backendSessionId, HOST.conversationId);
  assert.equal("lastRequestId" in recorded.status, false);
  const events = await readEvents(isolated);
  const bound = eventNamed(events, "runtime_bound");
  const completed = eventNamed(events, "runtime_turn_completed");
  assert.equal(bound.length, 1);
  assert.equal(completed.length, 1);
  assert.deepEqual(bound[0].host, recorded.binding.host);
  assert.deepEqual(bound[0].runtime, recorded.binding.runtime);
  assert.equal(completed[0].turn.requestId, HOST.requestId);
  assert.equal("status" in completed[0], false);
  assert.equal("conversation_id" in bound[0].runtime, false);
  const outcomes = callerOutcomes({ workerCompletion: "reported" });
  assert.equal(outcomes.controller_acceptance, "none");
  assert.equal(outcomes.distinct, true);
  assert.equal(recorded.available, false);
  assert.equal(adapterAvailable(), false);
});

test("verified candidate acpx runtime binds the actual handle before one isolated turn", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async () => {
  const { isolated, workspace } = await privateRoot();
  const capabilitiesPath = path.join(isolated, "callback-capabilities.json");
  process.env.PUPPET_ACPX_CANDIDATE_PEER_CAPABILITIES = capabilitiesPath;
  await claimHost(isolated);
  const { runtime, provenance } = await createVerifiedCandidateAcpRuntime({
    cwd: workspace,
    sessionStore: memorySessionStore(),
    agentRegistry: {
      resolve() {
        return [process.execPath, PEER];
      },
      list() {
        return ["candidate"];
      },
    },
    fs: false,
    terminal: false,
    timeoutMs: 30_000,
  }, {
    runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT),
    isolatedRoot: isolated,
  });
  const ensureCalls = [];
  const startCalls = [];
  const statusCalls = [];
  const closeCalls = [];
  const original = {
    ensureSession: runtime.ensureSession.bind(runtime),
    getStatus: runtime.getStatus.bind(runtime),
    startTurn: runtime.startTurn.bind(runtime),
    close: runtime.close.bind(runtime),
  };
  runtime.ensureSession = async (input) => {
    ensureCalls.push({ keys: Object.keys(input).sort() });
    return original.ensureSession(input);
  };
  runtime.getStatus = async (input) => {
    statusCalls.push({ keys: Object.keys(input).sort() });
    return original.getStatus(input);
  };
  runtime.startTurn = (input) => {
    startCalls.push({ keys: Object.keys(input).sort() });
    return original.startTurn(input);
  };
  runtime.close = async (input) => {
    closeCalls.push({
      keys: Object.keys(input).sort(),
      discardPersistentState: input.discardPersistentState,
    });
    return original.close(input);
  };
  try {
    assert.equal(
      await realpath(provenance.module_path),
      await realpath(path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_MODULE)),
    );
    assert.equal(provenance.artifact_sha256, ACPX_ARTIFACT_SHA256);
    assert.equal(
      provenance.module_sha256,
      createHash("sha256").update(await readFile(provenance.module_path)).digest("hex"),
    );
    assert.equal(provenance.lifecycle_scripts, "disabled");
    assert.equal(provenance.available, false);
    assert.equal(provenance.ordinary_launch, "unavailable");
    assert.equal(provenance.qualification, ACPX_QUALIFICATION);
    assert.equal(CursorAcpxAdapter.available(), false);
    assert.equal(adapterAvailable(), false);

    const recorded = await recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, runtime));
    assert.deepEqual(ensureCalls[0].keys, ["agent", "cwd", "mode", "sessionKey"]);
    assert.deepEqual(startCalls[0].keys, ["handle", "mode", "requestId", "text"]);
    assert.deepEqual(statusCalls[0].keys, ["handle"]);
    assert.equal(closeCalls.length, 1);
    assert.equal(closeCalls[0].discardPersistentState, true);
    assert.equal(recorded.binding.host.session, HOST.session);
    assert.equal(recorded.binding.host.conversation_id, HOST.conversationId);
    assert.equal(recorded.binding.host.request_id, HOST.requestId);
    assert.equal(recorded.binding.runtime.sessionKey, HOST.session);
    assert.equal(path.resolve(recorded.binding.runtime.cwd), path.resolve(workspace));
    assert.equal(typeof recorded.binding.runtime.backend, "string");
    assert.equal(typeof recorded.binding.runtime.runtimeSessionName, "string");
    assert.equal(typeof recorded.binding.runtime.acpxRecordId, "string");
    assert.equal(typeof recorded.binding.runtime.backendSessionId, "string");
    assert.equal("conversation_id" in recorded.binding.runtime, false);
    assert.notEqual(recorded.binding.runtime.backendSessionId, HOST.conversationId);
    assert.notEqual(recorded.binding.runtime.acpxRecordId, HOST.conversationId);
    assert.equal(recorded.turn.requestId, HOST.requestId);
    assert.equal(recorded.result.status, "completed");
    assert.equal(recorded.result.stopReason, "end_turn");
    assert.equal(recorded.result.body_retained, false);
    assert.equal(recorded.result.availability.available, false);
    assert.equal(recorded.result.availability.ordinary_launch, "unavailable");
    assert.equal(recorded.available, false);
    assert.equal("prompt" in recorded.result, false);
    assert.equal("response" in recorded.result, false);
    assert.equal("transcript" in recorded.result, false);

    const events = await readEvents(isolated);
    const bound = eventNamed(events, "runtime_bound");
    const completed = eventNamed(events, "runtime_turn_completed");
    assert.equal(bound.length, 1);
    assert.equal(completed.length, 1);
    assert.deepEqual(bound[0].host, recorded.binding.host);
    assert.deepEqual(bound[0].runtime, recorded.binding.runtime);
    assert.equal(completed[0].turn.requestId, HOST.requestId);
    assert.equal(completed[0].turn.status, "completed");
    assert.equal(completed[0].turn.stopReason, "end_turn");
    if (completed[0].status) {
      assert.equal(completed[0].status.lastRequestId, HOST.requestId);
    }
    assert.equal("conversation_id" in bound[0].runtime, false);
    assert.equal("controller_acceptance" in bound[0], false);
    assert.equal("controller_acceptance" in completed[0], false);

    const capabilities = JSON.parse(await readFile(capabilitiesPath, "utf8"));
    assert.equal(capabilities.fs, false);
    assert.equal(capabilities.terminal, false);
    assert.deepEqual(Object.keys(capabilities).sort(), ["fs", "terminal"]);

    const audit = await auditDurableArtifacts(isolated);
    assert.equal(audit.body_retained, false);
    const names = await readdir(isolated);
    for (const name of names) {
      if (name.endsWith(".lock")) continue;
      const raw = await readFile(path.join(isolated, name), "utf8");
      assert.equal(raw.includes(TEST_PROMPT), false);
      assert.equal(raw.includes('"prompt"'), false);
      assert.equal(raw.includes('"transcript"'), false);
    }
    const outcomes = callerOutcomes({ workerCompletion: "reported" });
    assert.equal(outcomes.controller_acceptance, "none");
    assert.equal(outcomes.distinct, true);
    assert.equal(CursorAcpxAdapter.available(), false);
    assert.equal(adapterAvailable(), false);
  } finally {
    try {
      await runtime.shutdown();
    } catch {
      // Shutdown must not hide the turn proof.
    }
    delete process.env.PUPPET_ACPX_CANDIDATE_PEER_CAPABILITIES;
  }
});

test("verified candidate acpx runtime rejects foreign ownership before ensureSession", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async () => {
  const { isolated, workspace } = await privateRoot();
  await claimIsolatedRoot(isolated, {
    owner: "foreign-owner",
    session: HOST.session,
    conversationId: HOST.conversationId,
  });
  const { runtime } = await createVerifiedCandidateAcpRuntime({
    cwd: workspace,
    sessionStore: memorySessionStore(),
    agentRegistry: {
      resolve() {
        return [process.execPath, PEER];
      },
      list() {
        return ["candidate"];
      },
    },
    fs: false,
    terminal: false,
    timeoutMs: 30_000,
  }, {
    runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT),
    isolatedRoot: isolated,
  });
  const ensureCalls = [];
  const startCalls = [];
  const closeCalls = [];
  const original = {
    ensureSession: runtime.ensureSession.bind(runtime),
    startTurn: runtime.startTurn.bind(runtime),
    close: runtime.close.bind(runtime),
  };
  runtime.ensureSession = async (input) => {
    ensureCalls.push(input);
    return original.ensureSession(input);
  };
  runtime.startTurn = (input) => {
    startCalls.push(input);
    return original.startTurn(input);
  };
  runtime.close = async (input) => {
    closeCalls.push(input);
    return original.close(input);
  };
  await assert.rejects(
    () => recordBoundCandidateTurn(boundTurnOptions(isolated, workspace, runtime)),
    (error) => error instanceof AdapterError && error.code === "OWNER_MISMATCH",
  );
  assert.equal(ensureCalls.length, 0);
  assert.equal(startCalls.length, 0);
  assert.equal(closeCalls.length, 0);
  const claim = await readClaim(isolated);
  assert.equal(claim.owner, "foreign-owner");
  assertOwnedUnfenced(claim);
  assert.equal(adapterAvailable(), false);
});
