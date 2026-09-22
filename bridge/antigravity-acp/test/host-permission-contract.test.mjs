import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { chmod, cp, mkdir, mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  ACPX_ARTIFACT_PATH,
  ACPX_CANDIDATE_RUNTIME_ROOT,
  materializeVerifiedCandidateAcpx,
} from "../../cursor-acp/puppet-adapter.mjs";
import {
  HOST_PERMISSION_DECISION_LIMIT,
  HOST_PERMISSION_KINDS,
  HOST_PERMISSION_SCHEMA,
  INTENDED_WRITE_RELATIVE,
  OPTION_KINDS,
  PERMISSION_REASONS,
  bodyFreePermissionReceipt,
  createHostPermissionContract,
  createHostPermissionContractRegistry,
  decideHostPermission,
  intendedWritePath,
  rejectCallerTurnPermissionHooks,
} from "../host-permission-contract.mjs";

const DRIVER = fileURLToPath(new URL("./controller-runtime-driver.mjs", import.meta.url));
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const LOCAL_ARTIFACT = path.join(REPO_ROOT, ACPX_ARTIFACT_PATH);
const REAL_ARTIFACT_SKIP = existsSync(LOCAL_ARTIFACT)
  ? false
  : "exact local acpx artifact is task-owned proof input";
const FIXTURE_TEMPLATE = path.join(
  REPO_ROOT,
  "proof/puppet-acp/20260921/antigravity/inputs/v2-fixture/normalize-lines-fixture",
);
const INTENDED_BIN = path.join(
  REPO_ROOT,
  "proof/puppet-acp/20260921/antigravity/inputs/v2-fixture/intended/bin/normalize-lines.mjs",
);
const PROTECTED_RELATIVE = "test/normalize-lines.test.mjs";

function createClient(child) {
  const lines = createInterface({ input: child.stdout, crlfDelay: Infinity });
  const pending = [];
  lines.on("line", (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const waiter = pending.shift();
    if (!waiter) return;
    try {
      waiter.resolve(JSON.parse(trimmed));
    } catch (error) {
      waiter.reject(error);
    }
  });
  child.once("exit", (code) => {
    while (pending.length) {
      pending.shift().reject(new Error(`driver exited ${code}`));
    }
  });
  return {
    async rpc(op, payload = {}) {
      const response = await new Promise((resolve, reject) => {
        pending.push({ resolve, reject });
        child.stdin.write(`${JSON.stringify({ op, payload })}\n`);
      });
      if (response.ok !== true) {
        const error = new Error(response.error || "driver failed");
        error.code = response.code;
        throw error;
      }
      return response.value;
    },
  };
}

async function digest(filePath) {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

async function createFixture(destination) {
  await cp(FIXTURE_TEMPLATE, destination, { recursive: true });
}

function runFixtureTests(workspace) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    delete env.NODE_TEST_CONTEXT;
    const child = spawn(
      process.execPath,
      ["--test", "--test-reporter=tap", "test/normalize-lines.test.mjs"],
      { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] },
    );
    let stream = "";
    child.stdout.on("data", (chunk) => {
      stream += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stream += chunk;
    });
    child.once("error", reject);
    child.once("close", (code) => {
      const pass = Number((stream.match(/(?:#|ℹ)\s+pass\s+(\d+)/) || [])[1] || 0);
      const fail = Number((stream.match(/(?:#|ℹ)\s+fail\s+(\d+)/) || [])[1] || 0);
      resolve({ exitCode: code, pass, fail, streamRetained: false });
    });
  });
}

function writeRequest(workspaceRoot, {
  toolCallId = "call_opaque_1",
  kind = "edit",
  inferredKind,
  filePath,
  locations,
  title = "write",
  omitKind = false,
  options = [
    { optionId: "allow-once", kind: "allow_once" },
    { optionId: "reject-once", kind: "reject_once" },
  ],
} = {}) {
  const toolCall = {
    toolCallId,
    title,
    status: "pending",
  };
  if (!omitKind && kind !== undefined) toolCall.kind = kind;
  if (filePath !== undefined) toolCall.rawInput = filePath ? { path: filePath } : {};
  if (locations !== undefined) toolCall.locations = locations;
  const request = {
    raw: {
      sessionId: "synthetic-session",
      toolCall,
      options,
    },
  };
  if (inferredKind !== undefined) request.inferredKind = inferredKind;
  return request;
}

function freshState(workspace, extras = {}) {
  return {
    sessionKey: "session-a",
    workspaceRoot: workspace,
    grantedWriteOnce: false,
    decisions: [],
    ...extras,
  };
}

function assertBodyFree(receipt, forbidden) {
  const serialized = JSON.stringify(receipt);
  assert.equal(receipt.body_retained, false);
  assert.ok(!Object.hasOwn(receipt, "options"));
  assert.ok(!Object.hasOwn(receipt, "rawInput"));
  assert.ok(!Object.hasOwn(receipt, "title"));
  assert.ok(!Object.hasOwn(receipt, "toolCallId"));
  for (const value of forbidden) {
    assert.equal(serialized.includes(value), false, value);
  }
}

test("host contract allows the intended write once from official shapes and fails closed otherwise", () => {
  const workspace = "/tmp/agy-permission-fixture";
  const intended = intendedWritePath(workspace);
  const protectedPath = path.join(workspace, PROTECTED_RELATIVE);
  const rawInput = decideHostPermission(
    writeRequest(workspace, { toolCallId: "call_raw_1", filePath: intended }),
    freshState(workspace),
  );
  assert.equal(rawInput.outcome, "allow_once");
  assert.equal(rawInput.permission_kind, "edit");
  assert.equal(rawInput.kind, "edit");
  assert.equal(rawInput.kind_source, "standardized");
  assert.equal(rawInput.id_class, "opaque");
  assert.equal(rawInput.path_source, "raw_input");
  assert.equal(rawInput.path_cardinality, "one");
  assert.equal(rawInput.path_class, "intended");
  assert.deepEqual(rawInput.offered_option_kinds, ["allow_once", "reject_once"]);
  assert.equal(rawInput.reason, "granted_once");
  const locations = decideHostPermission(
    writeRequest(workspace, {
      toolCallId: "call_loc_1",
      locations: [{ path: intended }],
    }),
    freshState(workspace),
  );
  assert.equal(locations.outcome, "allow_once");
  assert.equal(locations.path_source, "locations");
  assert.equal(locations.id_class, "opaque");
  const both = decideHostPermission(
    writeRequest(workspace, {
      toolCallId: "call_both_1",
      filePath: intended,
      locations: [{ path: intended }],
    }),
    freshState(workspace),
  );
  assert.equal(both.outcome, "allow_once");
  assert.equal(both.path_source, "both");
  const replayState = freshState(workspace);
  decideHostPermission(writeRequest(workspace, { filePath: intended }), replayState);
  const replay = decideHostPermission(writeRequest(workspace, { filePath: intended }), replayState);
  assert.equal(replay.outcome, "reject_once");
  assert.equal(replay.reason, "replay");
  const denied = decideHostPermission(
    writeRequest(workspace, { filePath: protectedPath }),
    freshState(workspace),
  );
  assert.equal(denied.outcome, "reject_once");
  assert.equal(denied.reason, "non_intended_path");
  assert.equal(denied.path_class, "non_intended");
  const absentPath = decideHostPermission(writeRequest(workspace, {}), freshState(workspace));
  assert.equal(absentPath.outcome, "cancel");
  assert.equal(absentPath.reason, "absent_path");
  const multiple = decideHostPermission(
    writeRequest(workspace, {
      locations: [{ path: intended }, { path: protectedPath }],
    }),
    freshState(workspace),
  );
  assert.equal(multiple.outcome, "cancel");
  assert.equal(multiple.reason, "multiple_paths");
  const conflicting = decideHostPermission(
    writeRequest(workspace, {
      filePath: intended,
      locations: [{ path: protectedPath }],
    }),
    freshState(workspace),
  );
  assert.equal(conflicting.outcome, "cancel");
  assert.equal(conflicting.reason, "conflicting_paths");
  const absentKind = decideHostPermission(
    writeRequest(workspace, { omitKind: true, filePath: intended }),
    freshState(workspace),
  );
  assert.equal(absentKind.outcome, "cancel");
  assert.equal(absentKind.reason, "absent_kind");
  const otherKind = decideHostPermission(
    writeRequest(workspace, { kind: "execute", filePath: intended }),
    freshState(workspace),
  );
  assert.equal(otherKind.outcome, "cancel");
  assert.equal(otherKind.reason, "other_kind");
  const titleOnly = decideHostPermission(
    writeRequest(workspace, {
      omitKind: true,
      inferredKind: "edit",
      title: "write bin/normalize-lines.mjs",
      filePath: intended,
    }),
    freshState(workspace),
  );
  assert.equal(titleOnly.outcome, "cancel");
  assert.equal(titleOnly.reason, "inferred_kind_only");
  assert.equal(titleOnly.kind_source, "inferred");
  const absentAllow = decideHostPermission(
    writeRequest(workspace, {
      filePath: intended,
      options: [{ optionId: "allow-always", kind: "allow_always" }],
    }),
    freshState(workspace),
  );
  assert.equal(absentAllow.outcome, "cancel");
  assert.equal(absentAllow.reason, "absent_allow_once");
  const namedId = decideHostPermission(
    writeRequest(workspace, { toolCallId: "fs_write_file", filePath: intended }),
    freshState(workspace),
  );
  assert.equal(namedId.outcome, "allow_once");
  assert.equal(namedId.id_class, "opaque");
  const interaction = decideHostPermission(
    writeRequest(workspace, {
      toolCallId: "interaction_choose",
      filePath: intended,
    }),
    freshState(workspace),
  );
  assert.equal(interaction.outcome, "cancel");
  assert.equal(interaction.reason, "interaction");
  assert.equal(interaction.id_class, "interaction");
  assert.equal(INTENDED_WRITE_RELATIVE, "bin/normalize-lines.mjs");
});

test("host contract isolates one-time grants across sessions and keeps receipts body-free", () => {
  const registry = createHostPermissionContractRegistry();
  const workspace = "/tmp/agy-permission-fixture";
  const intended = intendedWritePath(workspace);
  const first = registry.forSession({ sessionKey: "session-a", workspaceRoot: workspace });
  const second = registry.forSession({ sessionKey: "session-b", workspaceRoot: workspace });
  assert.equal(first.os_sandbox, false);
  assert.equal(first.approve_all, false);
  assert.equal(first.ordinary_launch, "unavailable");
  return Promise.all([
    first.onPermissionRequest(writeRequest(workspace, {
      toolCallId: "call_session_a",
      filePath: intended,
    })),
    second.onPermissionRequest(writeRequest(workspace, {
      toolCallId: "call_session_b",
      filePath: intended,
    })),
  ]).then(async ([left, right]) => {
    assert.equal(left.outcome, "allow_once");
    assert.equal(right.outcome, "allow_once");
    const replay = await first.onPermissionRequest(writeRequest(workspace, {
      toolCallId: "call_session_a_replay",
      filePath: intended,
    }));
    assert.equal(replay.outcome, "reject_once");
    const receipt = first.snapshot();
    assert.equal(receipt.schema, HOST_PERMISSION_SCHEMA);
    assert.equal(receipt.grant_count, 1);
    assert.equal(receipt.allowed, true);
    assert.equal(receipt.persisted, false);
    assert.equal(receipt.os_sandbox, false);
    assert.equal(receipt.reason, "replay");
    assert.equal(receipt.id_class, "opaque");
    assert.equal(receipt.path_class, "intended");
    assert.deepEqual(receipt.offered_option_kinds, ["allow_once", "reject_once"]);
    assertBodyFree(receipt, [
      intended,
      "call_session_a",
      "call_session_a_replay",
      "rawInput",
      "allow-once",
      "write",
    ]);
    for (const decision of receipt.decisions) {
      assert.equal(PERMISSION_REASONS.includes(decision.reason), true);
      for (const kind of decision.offered_option_kinds) {
        assert.equal(OPTION_KINDS.includes(kind), true);
      }
    }
    const empty = bodyFreePermissionReceipt({ sessionKey: "none", decisions: [] });
    assert.equal(empty.outcome, "cancelled");
    assert.equal(empty.allowed, false);
    assert.equal(empty.permission_id, "host");
    assert.equal(empty.permission_kind, "ambiguous");
    assert.equal(empty.decision_count, 0);
    assert.equal(empty.decisions_truncated, false);
    assert.equal(receipt.decision_count, 2);
    assert.equal(receipt.decisions_truncated, false);
    assert.equal(HOST_PERMISSION_KINDS.includes(receipt.permission_kind), true);
  });
});

function historyDecision(overrides = {}) {
  return {
    outcome: "reject_once",
    permission_kind: "denied",
    kind: "edit",
    kind_source: "standardized",
    id_class: "opaque",
    path_source: "raw_input",
    path_cardinality: "one",
    path_class: "non_intended",
    offered_option_kinds: ["reject_once"],
    reason: "non_intended_path",
    ...overrides,
  };
}

test("receipt omits list and object diagnostic values and keeps valid option order", () => {
  const receipt = bodyFreePermissionReceipt({
    sessionKey: "session-a",
    decisions: [
      historyDecision({
        outcome: "allow_once",
        permission_kind: ["edit"],
        kind: { name: "edit" },
        kind_source: ["standardized"],
        id_class: { class: "opaque" },
        path_source: ["raw_input"],
        path_cardinality: ["one"],
        path_class: { class: "intended" },
        reason: ["granted_once"],
        offered_option_kinds: [
          ["allow_once"],
          { kind: "allow_once" },
          "reject_once",
          "allow_once",
          "approve_all",
          "allow_once",
          "reject_always",
        ],
      }),
      historyDecision({
        outcome: ["denied"],
        permission_kind: { kind: "denied" },
        offered_option_kinds: { 0: "allow_once" },
      }),
      historyDecision({
        outcome: "reject_once",
        permission_kind: "denied",
        offered_option_kinds: ["reject_once", "reject_once", "yes"],
      }),
    ],
  });
  assert.equal(receipt.body_retained, false);
  assert.equal(receipt.decisions.length, 2);
  assert.equal(receipt.decision_count, 2);
  assert.equal(receipt.decisions_truncated, false);
  assert.equal(receipt.permission_kind, "denied");
  assert.equal(HOST_PERMISSION_KINDS.includes(receipt.permission_kind), true);
  assert.equal(receipt.kind, "edit");
  assert.equal(receipt.kind_source, "standardized");
  assert.equal(receipt.reason, "non_intended_path");
  assert.deepEqual(receipt.offered_option_kinds, ["reject_once"]);
  assert.equal(receipt.decisions[0].kind, "absent");
  assert.equal(receipt.decisions[0].kind_source, "absent");
  assert.equal(receipt.decisions[0].id_class, "absent");
  assert.equal(receipt.decisions[0].path_source, "absent");
  assert.equal(receipt.decisions[0].path_cardinality, "zero");
  assert.equal(receipt.decisions[0].path_class, "absent");
  assert.equal(receipt.decisions[0].reason, "ambiguous");
  assert.deepEqual(receipt.decisions[0].offered_option_kinds, [
    "reject_once",
    "allow_once",
    "reject_always",
  ]);
  assert.equal(receipt.decisions[0].permission_kind, "ambiguous");
  assert.equal(receipt.decisions[1].permission_kind, "denied");
  assert.equal(receipt.offered_option_kinds.includes("approve_all"), false);
  assert.equal(receipt.decisions[0].offered_option_kinds.includes("approve_all"), false);
  assert.equal(JSON.stringify(receipt).includes("yes"), false);
});

test("receipt bounds oversized decision history and cannot claim complete history", () => {
  const decisions = Array.from({ length: 10_000 }, (_, index) => historyDecision({
    outcome: index === 0 ? "allow_once" : "reject_once",
    permission_kind: index === 0 ? "edit" : "denied",
    reason: index === 0 ? "granted_once" : "non_intended_path",
    path_class: index === 0 ? "intended" : "non_intended",
  }));
  const receipt = bodyFreePermissionReceipt({
    sessionKey: "session-a",
    decisions,
  });
  assert.equal(receipt.decision_count, 10_000);
  assert.equal(receipt.decisions_truncated, true);
  assert.equal(receipt.decisions.length, HOST_PERMISSION_DECISION_LIMIT);
  assert.ok(receipt.decisions.length < receipt.decision_count);
  assert.equal(receipt.grant_count, 1);
  assert.equal(receipt.allowed, true);
  assert.equal(receipt.outcome, "denied");
  assert.equal(receipt.permission_kind, "denied");
  assert.equal(receipt.decisions[0].outcome, "denied");
  assert.equal(receipt.decisions[receipt.decisions.length - 1].outcome, "denied");
  assert.equal(receipt.decisions.some((item) => item.outcome === "allow_once"), false);
  assert.equal(receipt.body_retained, false);
  assert.ok(!Object.hasOwn(receipt, "rawInput"));
});

test("receipt keeps valid permission kinds and remaps invalid kinds to the host contract", () => {
  const valid = bodyFreePermissionReceipt({
    sessionKey: "session-a",
    decisions: [
      historyDecision({
        outcome: "allow_once",
        permission_kind: "edit",
        reason: "granted_once",
        path_class: "intended",
        offered_option_kinds: ["allow_once", "reject_once"],
      }),
      historyDecision({
        outcome: "reject_once",
        permission_kind: "denied",
      }),
    ],
  });
  assert.deepEqual(valid.decisions.map((item) => item.outcome), ["allow_once", "denied"]);
  assert.deepEqual(valid.decisions.map((item) => item.permission_kind), ["edit", "denied"]);
  assert.equal(valid.permission_id, "denied");
  assert.equal(valid.permission_kind, "denied");
  assert.equal(valid.grant_count, 1);
  assert.equal(valid.allowed, true);
  assert.equal(valid.decision_count, 2);
  assert.equal(valid.decisions_truncated, false);
  const invalid = bodyFreePermissionReceipt({
    sessionKey: "session-a",
    decisions: [
      historyDecision({
        outcome: "allow_once",
        permission_kind: "fs_write_file",
        reason: "granted_once",
      }),
    ],
  });
  assert.equal(invalid.permission_kind, "ambiguous");
  assert.equal(invalid.permission_id, "ambiguous");
  assert.equal(HOST_PERMISSION_KINDS.includes(invalid.permission_kind), true);
  assert.equal(invalid.permission_kind === "fs_write_file", false);
  assert.equal(invalid.decisions[0].permission_kind, "ambiguous");
});

test("caller turn permission hooks stay rejected as broker policy", () => {
  assert.throws(
    () => rejectCallerTurnPermissionHooks({ onPermissionRequest: () => ({}) }),
    (error) => error.code === "BROKER_POLICY",
  );
  assert.throws(
    () => rejectCallerTurnPermissionHooks({ permissionMode: "approve-all" }),
    (error) => error.code === "BROKER_POLICY",
  );
});

async function withPermissionDriver(t, payload, fn) {
  const root = await mkdtemp(path.join(os.tmpdir(), "agy-permission-"));
  const isolated = path.join(root, "isolated");
  const workspace = payload.cwd ?? path.join(root, "workspace");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  if (!payload.cwd) await mkdir(workspace);
  const child = spawn(process.execPath, [DRIVER], {
    cwd: REPO_ROOT,
    stdio: ["pipe", "pipe", "pipe"],
  });
  const client = createClient(child);
  t.after(() => {
    if (child.exitCode == null && child.signalCode == null) {
      child.kill("SIGTERM");
    }
  });
  const created = await client.rpc("create", {
    cwd: workspace,
    isolatedRoot: isolated,
    syntheticPeer: true,
    agent: "antigravity",
    syntheticPeerScript: "permission-peer.mjs",
    ...payload,
  });
  return fn({ client, created, workspace, isolated });
}

test("public startTurn rejects caller permission hooks", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  await withPermissionDriver(t, {}, async ({ client, workspace }) => {
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-permission-reject",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    await assert.rejects(
      () => client.rpc("startTurn", {
        handle,
        text: "antigravity-acp-runtime-turn",
        mode: "prompt",
        requestId: "agy-permission-reject-1",
        timeoutMs: 30_000,
        onPermissionRequest: { outcome: "allow_always" },
      }),
      (error) => error.code === "BROKER_POLICY",
    );
    await client.rpc("shutdown");
  });
});

test("pinned runtime allows the intended fixture write once and leaves the protected test unchanged", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "agy-permission-allow-"));
  const workspace = path.join(root, "fixture");
  await createFixture(workspace);
  const protectedBefore = await digest(path.join(workspace, PROTECTED_RELATIVE));
  const intendedDigest = await digest(INTENDED_BIN);
  const baseline = await runFixtureTests(workspace);
  assert.equal(baseline.pass, 1);
  assert.equal(baseline.fail, 1);
  await withPermissionDriver(t, {
    cwd: workspace,
    syntheticPeerPermission: "fs_write_file",
  }, async ({ client, created }) => {
    assert.equal(created.available, false);
    assert.equal(created.ordinary_launch, "unavailable");
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-permission-allow",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    const turn = await client.rpc("startTurn", {
      handle,
      text: "antigravity-acp-runtime-turn",
      mode: "prompt",
      requestId: "agy-permission-allow-1",
      timeoutMs: 30_000,
    });
    assert.equal(turn.result.status, "completed");
    assert.equal(turn.permission.outcome, "allow_once");
    assert.equal(turn.permission.allowed, true);
    assert.equal(turn.permission.grant_count, 1);
    assert.equal(turn.permission.persisted, false);
    assert.equal(turn.permission.approve_all, false);
    assert.equal(turn.permission.os_sandbox, false);
    assert.equal(turn.permission.fs, false);
    assert.equal(turn.permission.terminal, false);
    assert.equal(turn.permission.ordinary_launch, "unavailable");
    assert.equal(turn.permission.body_retained, false);
    assert.equal(turn.permission.permission_kind, "edit");
    assert.equal(turn.permission.kind, "edit");
    assert.equal(turn.permission.kind_source, "standardized");
    assert.equal(turn.permission.id_class, "opaque");
    assert.equal(turn.permission.path_source, "raw_input");
    assert.equal(turn.permission.path_class, "intended");
    assert.equal(turn.permission.reason, "granted_once");
    assert.ok(!Object.hasOwn(turn.permission, "options"));
    assert.ok(!Object.hasOwn(turn.result, "prompt"));
    assertBodyFree(turn.permission, [
      path.join(workspace, INTENDED_WRITE_RELATIVE),
      "rawInput",
      "allow-once",
      "call_1",
    ]);
    assert.equal(await digest(path.join(workspace, INTENDED_WRITE_RELATIVE)), intendedDigest);
    assert.equal(await digest(path.join(workspace, PROTECTED_RELATIVE)), protectedBefore);
    const after = await runFixtureTests(workspace);
    assert.equal(after.pass, 2);
    assert.equal(after.fail, 0);
    await client.rpc("shutdown");
  });
});

test("pinned runtime allows the official locations path write once", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "agy-permission-locations-"));
  const workspace = path.join(root, "fixture");
  await createFixture(workspace);
  const intendedDigest = await digest(INTENDED_BIN);
  await withPermissionDriver(t, {
    cwd: workspace,
    syntheticPeerPermission: "locations_path",
  }, async ({ client }) => {
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-permission-locations",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    const turn = await client.rpc("startTurn", {
      handle,
      text: "antigravity-acp-runtime-turn",
      mode: "prompt",
      requestId: "agy-permission-locations-1",
      timeoutMs: 30_000,
    });
    assert.equal(turn.permission.outcome, "allow_once");
    assert.equal(turn.permission.path_source, "locations");
    assert.equal(turn.permission.id_class, "opaque");
    assert.equal(turn.permission.kind_source, "standardized");
    assertBodyFree(turn.permission, [path.join(workspace, INTENDED_WRITE_RELATIVE), "rawInput"]);
    assert.equal(await digest(path.join(workspace, INTENDED_WRITE_RELATIVE)), intendedDigest);
    await client.rpc("shutdown");
  });
});

test("denial, interaction, and elicitation perform no fixture edit", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  for (const mode of [
    "deny_protected",
    "interaction",
    "elicitation",
    "ambiguous",
    "absent_path",
    "multiple_paths",
    "conflicting_paths",
    "absent_kind",
    "other_kind",
    "absent_allow_once",
    "title_only",
  ]) {
    const root = await mkdtemp(path.join(os.tmpdir(), `agy-permission-${mode}-`));
    const workspace = path.join(root, "fixture");
    await createFixture(workspace);
    const protectedBefore = await digest(path.join(workspace, PROTECTED_RELATIVE));
    await withPermissionDriver(t, {
      cwd: workspace,
      syntheticPeerPermission: mode,
    }, async ({ client }) => {
      const handle = await client.rpc("ensureSession", {
        sessionKey: `agy-permission-${mode}`,
        agent: "antigravity",
        mode: "oneshot",
        cwd: workspace,
      });
      const turn = await client.rpc("startTurn", {
        handle,
        text: "antigravity-acp-runtime-turn",
        mode: "prompt",
        requestId: `agy-permission-${mode}-1`,
        timeoutMs: 30_000,
      });
      assert.equal(turn.result.status, "completed", mode);
      assert.notEqual(turn.permission?.outcome, "allow_once", mode);
      assert.notEqual(turn.permission?.allowed, true, JSON.stringify(turn.permission));
      assert.notEqual(turn.permission?.reason, "granted_once", mode);
      if (turn.permission) {
        assertBodyFree(turn.permission, [
          path.join(workspace, INTENDED_WRITE_RELATIVE),
          path.join(workspace, PROTECTED_RELATIVE),
          "rawInput",
          "allow-once",
          "write bin/normalize-lines.mjs",
        ]);
      } else {
        assert.equal(mode, "elicitation");
      }
      assert.equal(existsSync(path.join(workspace, INTENDED_WRITE_RELATIVE)), false, mode);
      assert.equal(await digest(path.join(workspace, PROTECTED_RELATIVE)), protectedBefore);
      await client.rpc("shutdown");
    });
  }
});

test("one-time grant is consumed and sessions stay isolated", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "agy-permission-isolate-"));
  const workspace = path.join(root, "fixture");
  await createFixture(workspace);
  const intendedDigest = await digest(INTENDED_BIN);
  await withPermissionDriver(t, {
    cwd: workspace,
    syntheticPeerPermission: "fs_write_twice",
  }, async ({ client }) => {
    const firstHandle = await client.rpc("ensureSession", {
      sessionKey: "agy-permission-session-a",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    const first = await client.rpc("startTurn", {
      handle: firstHandle,
      text: "antigravity-acp-runtime-turn",
      mode: "prompt",
      requestId: "agy-permission-session-a-1",
      timeoutMs: 30_000,
    });
    assert.deepEqual(first.permission.decisions.map((item) => item.outcome), [
      "allow_once",
      "denied",
    ]);
    assert.deepEqual(first.permission.decisions.map((item) => item.reason), [
      "granted_once",
      "replay",
    ]);
    assert.equal(first.permission.grant_count, 1);
    assert.equal(first.permission.allowed, true);
    assert.equal(first.permission.id_class, "opaque");
    assertBodyFree(first.permission, [path.join(workspace, INTENDED_WRITE_RELATIVE), "rawInput"]);
    assert.equal(await digest(path.join(workspace, INTENDED_WRITE_RELATIVE)), intendedDigest);
    const secondHandle = await client.rpc("ensureSession", {
      sessionKey: "agy-permission-session-b",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    const second = await client.rpc("startTurn", {
      handle: secondHandle,
      text: "antigravity-acp-runtime-turn",
      mode: "prompt",
      requestId: "agy-permission-session-b-1",
      timeoutMs: 30_000,
    });
    assert.equal(second.permission.grant_count, 1);
    assert.equal(second.permission.allowed, true);
    assert.equal(secondHandle.sessionKey, "agy-permission-session-b");
    assert.notEqual(firstHandle.sessionKey, secondHandle.sessionKey);
    assert.equal(await digest(path.join(workspace, INTENDED_WRITE_RELATIVE)), intendedDigest);
    await client.rpc("shutdown");
  });
});

function constValues(definition) {
  if (!definition) return [];
  if (definition.const != null) return [definition.const];
  if (Array.isArray(definition.oneOf)) {
    return definition.oneOf.flatMap((item) => constValues(item));
  }
  if (Array.isArray(definition.anyOf)) {
    return definition.anyOf.flatMap((item) => constValues(item));
  }
  if (Array.isArray(definition.enum)) return definition.enum;
  return [];
}

test("pinned SDK and runtime schema keep toolCallId opaque and expose official edit paths", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async () => {
  const materialized = await materializeVerifiedCandidateAcpx({
    runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT),
  });
  const schemaCandidates = [
    path.join(materialized.runtimeRoot, "node_modules/@agentclientprotocol/sdk/schema/schema.json"),
    path.join(
      materialized.runtimeRoot,
      "node_modules/acpx/node_modules/@agentclientprotocol/sdk/schema/schema.json",
    ),
  ];
  const schemaPath = schemaCandidates.find((candidate) => existsSync(candidate));
  assert.ok(schemaPath, "pinned ACP SDK schema is missing");
  const schema = JSON.parse(await readFile(schemaPath, "utf8"));
  const defs = schema.$defs ?? schema.definitions;
  assert.equal(defs.ToolCallId.type, "string");
  assert.match(defs.ToolCallId.description, /unique identifier for a tool call within a session/i);
  assert.equal(Array.isArray(defs.ToolCallId.enum), false);
  assert.equal(constValues(defs.ToolKind).includes("edit"), true);
  assert.equal(constValues(defs.ToolKind).includes("fs_write_file"), false);
  assert.equal(defs.ToolCallLocation.required.includes("path"), true);
  assert.equal(defs.ToolCallLocation.properties.path.type, "string");
  assert.equal(constValues(defs.PermissionOptionKind).includes("allow_once"), true);
  assert.equal(defs.RequestPermissionRequest.required.includes("toolCall"), true);
  assert.equal(defs.RequestPermissionRequest.required.includes("options"), true);
  assert.ok(Object.hasOwn(defs.ToolCallUpdate.properties, "rawInput"));
  assert.ok(Object.hasOwn(defs.ToolCallUpdate.properties, "locations"));
  const sdkPackage = JSON.parse(await readFile(
    path.join(path.dirname(path.dirname(schemaPath)), "package.json"),
    "utf8",
  ));
  assert.equal(sdkPackage.name, "@agentclientprotocol/sdk");
  const runtimePackage = JSON.parse(await readFile(
    path.join(materialized.runtimeRoot, "node_modules/acpx/package.json"),
    "utf8",
  ));
  assert.match(String(runtimePackage.dependencies["@agentclientprotocol/sdk"]), /\d/);
  const { readdir } = await import("node:fs/promises");
  const distDir = path.join(materialized.runtimeRoot, "node_modules/acpx/dist");
  const files = existsSync(distDir) ? await readdir(distDir) : [];
  const typed = files.filter((name) => name.endsWith(".d.ts") || name.endsWith(".js"));
  const sources = await Promise.all(typed.map((name) => readFile(path.join(distDir, name), "utf8")));
  assert.equal(sources.some((source) => source.includes("inferredKind")), true);
  assert.equal(sources.some((source) => source.includes("RequestPermissionRequest")), true);
});
