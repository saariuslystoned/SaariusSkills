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
import { ACPX_ARTIFACT_PATH } from "../../cursor-acp/puppet-adapter.mjs";
import {
  HOST_PERMISSION_SCHEMA,
  INTENDED_WRITE_RELATIVE,
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

function writeRequest(workspaceRoot, toolCallId, filePath) {
  return {
    raw: {
      sessionId: "synthetic-session",
      toolCall: {
        toolCallId,
        title: "write",
        kind: "edit",
        rawInput: filePath ? { path: filePath } : {},
      },
      options: [
        { optionId: "allow-once", kind: "allow_once" },
        { optionId: "reject-once", kind: "reject_once" },
      ],
    },
  };
}

test("host contract allows the intended write once and fails closed otherwise", () => {
  const workspace = "/tmp/agy-permission-fixture";
  const intended = intendedWritePath(workspace);
  const state = {
    sessionKey: "session-a",
    workspaceRoot: workspace,
    grantedWriteOnce: false,
    decisions: [],
  };
  const first = decideHostPermission(writeRequest(workspace, "fs_write_file", intended), state);
  assert.equal(first.outcome, "allow_once");
  const second = decideHostPermission(writeRequest(workspace, "fs_write_file", intended), state);
  assert.equal(second.outcome, "reject_once");
  const denied = decideHostPermission(
    writeRequest(workspace, "fs_write_file", path.join(workspace, PROTECTED_RELATIVE)),
    { ...state, grantedWriteOnce: false },
  );
  assert.equal(denied.outcome, "reject_once");
  const ambiguous = decideHostPermission(
    writeRequest(workspace, "fs_write_file"),
    { ...state, grantedWriteOnce: false },
  );
  assert.equal(ambiguous.outcome, "cancel");
  const interaction = decideHostPermission(
    { raw: { toolCall: { toolCallId: "interaction_choose" } } },
    state,
  );
  assert.equal(interaction.outcome, "cancel");
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
    first.onPermissionRequest(writeRequest(workspace, "fs_write_file", intended)),
    second.onPermissionRequest(writeRequest(workspace, "fs_write_file", intended)),
  ]).then(async ([left, right]) => {
    assert.equal(left.outcome, "allow_once");
    assert.equal(right.outcome, "allow_once");
    const replay = await first.onPermissionRequest(writeRequest(workspace, "fs_write_file", intended));
    assert.equal(replay.outcome, "reject_once");
    const receipt = first.snapshot();
    assert.equal(receipt.schema, HOST_PERMISSION_SCHEMA);
    assert.equal(receipt.grant_count, 1);
    assert.equal(receipt.allowed, true);
    assert.equal(receipt.persisted, false);
    assert.equal(receipt.os_sandbox, false);
    assert.equal(receipt.body_retained, false);
    assert.equal(JSON.stringify(receipt).includes("options"), false);
    assert.equal(JSON.stringify(receipt).includes("rawInput"), false);
    assert.equal(JSON.stringify(receipt).includes(intended), false);
    const empty = bodyFreePermissionReceipt({ sessionKey: "none", decisions: [] });
    assert.equal(empty.outcome, "cancelled");
    assert.equal(empty.allowed, false);
  });
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
    assert.ok(!Object.hasOwn(turn.permission, "options"));
    assert.ok(!Object.hasOwn(turn.result, "prompt"));
    assert.equal(await digest(path.join(workspace, INTENDED_WRITE_RELATIVE)), intendedDigest);
    assert.equal(await digest(path.join(workspace, PROTECTED_RELATIVE)), protectedBefore);
    const after = await runFixtureTests(workspace);
    assert.equal(after.pass, 2);
    assert.equal(after.fail, 0);
    await client.rpc("shutdown");
  });
});

test("denial, interaction, and elicitation perform no fixture edit", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  for (const mode of ["deny_protected", "interaction", "elicitation", "ambiguous"]) {
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
    assert.equal(first.permission.grant_count, 1);
    assert.equal(first.permission.allowed, true);
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
