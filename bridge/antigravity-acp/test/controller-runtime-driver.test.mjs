import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { chmod, mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { existsSync } from "node:fs";
import { ACPX_ARTIFACT_PATH } from "../../cursor-acp/puppet-adapter.mjs";

const DRIVER = fileURLToPath(new URL("./controller-runtime-driver.mjs", import.meta.url));
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const LOCAL_ARTIFACT = path.join(REPO_ROOT, ACPX_ARTIFACT_PATH);
const REAL_ARTIFACT_SKIP = existsSync(LOCAL_ARTIFACT)
  ? false
  : "exact local acpx artifact is task-owned proof input";

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

test("actual public runtime driver stays unavailable and maps gemini catalog", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "agy-acp-driver-"));
  const isolated = path.join(root, "isolated");
  const workspace = path.join(root, "workspace");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  await mkdir(workspace);
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
  });
  assert.equal(created.available, false);
  assert.equal(created.ordinary_launch, "unavailable");
  const handle = await client.rpc("ensureSession", {
    sessionKey: "agy-acp-session",
    agent: "antigravity",
    mode: "oneshot",
    cwd: workspace,
  });
  assert.equal(handle.sessionKey, "agy-acp-session");
  assert.notEqual(handle.backendSessionId, "agy-acp-session");
  assert.notEqual(handle.acpxRecordId, "agy-acp-session");
  const status = await client.rpc("getStatus", { handle });
  assert.equal(status.models.currentModelId, "gemini-3.8-flash-high");
  const advertised = (status.models.availableModels || status.models.availableModelIds || []).map(
    (item) => (typeof item === "string" ? item : item.modelId),
  );
  assert.ok(advertised.includes("gemini-3.8-flash-high"));
  const turn = await client.rpc("startTurn", {
    handle,
    text: "antigravity-acp-runtime-turn",
    mode: "prompt",
    requestId: "agy-acp-request-1",
    timeoutMs: 300_000,
    intendedRelativePath: "bin/normalize-lines.mjs",
  });
  assert.equal(turn.requestId, "agy-acp-request-1");
  assert.equal(turn.timeoutMs, 300_000);
  assert.equal(turn.result.status, "completed");
  assert.equal(turn.result.stopReason, "end_turn");
  assert.equal(turn.discarded.body_retained, false);
  assert.ok(!Object.hasOwn(turn.result, "prompt"));
  assert.ok(turn.process_lifecycle.started.length >= 1, JSON.stringify(turn.process_lifecycle));
  assert.equal(turn.process_lifecycle.started[0].scope.kind, "runtime-session");
  assert.equal(turn.process_lifecycle.started[0].scope.sessionKey, handle.sessionKey);
  assert.notEqual(turn.process_lifecycle.started[0].pid, child.pid);
  await assert.rejects(
    () => client.rpc("close", {
      handle,
      reason: "antigravity-acp-owned-close",
      discardPersistentState: true,
    }),
    (error) => error.code === "ACP_BACKEND_UNSUPPORTED_CONTROL",
  );
  const lifecycle = await client.rpc("waitForOwnedExit", {
    sessionKey: handle.sessionKey,
    timeoutMs: 30_000,
  });
  assert.equal(lifecycle.status, "exited", JSON.stringify(lifecycle));
  assert.ok(lifecycle.exits.length >= 1, JSON.stringify(lifecycle));
  await client.rpc("shutdown");
});

test("official candidate create fails closed without allowed process env", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "agy-acp-env-"));
  const isolated = path.join(root, "isolated");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  const child = spawn(process.execPath, [DRIVER], {
    cwd: REPO_ROOT,
    stdio: ["pipe", "pipe", "pipe"],
  });
  const client = createClient(child);
  try {
    await assert.rejects(
      () => client.rpc("create", {
        cwd: REPO_ROOT,
        isolatedRoot: isolated,
        syntheticPeer: false,
        agent: "antigravity",
        candidate: {
          kind: "qualified_archive",
          agent: "antigravity",
          executable: process.execPath,
          args: [],
        },
      }),
      /official candidate process environment is missing/,
    );
  } finally {
    if (child.exitCode == null && child.signalCode == null) {
      child.kill("SIGTERM");
    }
  }
});

async function withDriver(t, payload, fn) {
  const root = await mkdtemp(path.join(os.tmpdir(), "agy-acp-driver-"));
  const isolated = path.join(root, "isolated");
  const workspace = path.join(root, "workspace");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  await mkdir(workspace);
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
    ...payload,
  });
  return fn({ client, child, created, workspace });
}

test("candidate startTurn rejects missing or unbounded timeout", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  await withDriver(t, {}, async ({ client, workspace }) => {
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-acp-session",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    await assert.rejects(
      () => client.rpc("startTurn", {
        handle,
        text: "antigravity-acp-runtime-turn",
        mode: "prompt",
        requestId: "agy-acp-request-missing-timeout",
      }),
      /candidate prompt timeoutMs must be an integer/,
    );
    await assert.rejects(
      () => client.rpc("startTurn", {
        handle,
        text: "antigravity-acp-runtime-turn",
        mode: "prompt",
        requestId: "agy-acp-request-unlimited-timeout",
        timeoutMs: 0,
      }),
      /candidate prompt timeoutMs must be an integer/,
    );
    await client.rpc("shutdown");
  });
});

test("candidate startTurn fails closed without a task-owned relative path", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  await withDriver(t, {}, async ({ client, workspace }) => {
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-acp-session",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    await assert.rejects(
      () => client.rpc("startTurn", {
        handle,
        text: "antigravity-acp-runtime-turn",
        mode: "prompt",
        requestId: "agy-acp-request-missing-path",
        timeoutMs: 30_000,
      }),
      /intended relative path is missing/,
    );
    await client.rpc("shutdown");
  });
});

test("actual public runtime binds the candidate prompt timeout and retains failure evidence", {
  timeout: 30_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  await withDriver(t, { syntheticPeerHangPrompt: true }, async ({ client, child, workspace }) => {
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-acp-timeout-session",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    const startedAt = Date.now();
    const turn = await client.rpc("startTurn", {
      handle,
      text: "antigravity-acp-runtime-turn",
      mode: "prompt",
      requestId: "agy-acp-request-timeout",
      timeoutMs: 1_000,
      intendedRelativePath: "bin/normalize-lines.mjs",
    });
    const elapsed = Date.now() - startedAt;
    assert.equal(turn.timeoutMs, 1_000);
    assert.equal(turn.result.status, "failed");
    assert.ok(turn.result.errorCode, JSON.stringify(turn.result));
    assert.ok(!Object.hasOwn(turn.result, "error"));
    assert.ok(!Object.hasOwn(turn.result, "prompt"));
    assert.ok(elapsed < 10_000, `prompt timeout leaked past the bound: ${elapsed}ms`);
    assert.ok(turn.process_lifecycle.started.length >= 1, JSON.stringify(turn.process_lifecycle));
    assert.notEqual(turn.process_lifecycle.started[0].pid, child.pid);
    await client.rpc("shutdown");
  });
});

test("actual public runtime attributes a short-lived worker during startTurn", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  await withDriver(t, {}, async ({ client, child, workspace }) => {
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-acp-short-lived",
      agent: "antigravity",
      mode: "oneshot",
      cwd: workspace,
    });
    const turn = await client.rpc("startTurn", {
      handle,
      text: "antigravity-acp-runtime-turn",
      mode: "prompt",
      requestId: "agy-acp-request-short-lived",
      timeoutMs: 300_000,
      intendedRelativePath: "bin/normalize-lines.mjs",
    });
    assert.equal(turn.result.status, "completed");
    const started = turn.process_lifecycle.started;
    assert.ok(started.length >= 1, JSON.stringify(turn.process_lifecycle));
    assert.equal(typeof started[0].launchId, "string");
    assert.equal(typeof started[0].startedAt, "string");
    assert.equal(started[0].scope.sessionKey, handle.sessionKey);
    assert.notEqual(started[0].pid, child.pid);
    await assert.rejects(
      () => client.rpc("close", {
        handle,
        reason: "antigravity-acp-owned-close",
        discardPersistentState: true,
      }),
      (error) => error.code === "ACP_BACKEND_UNSUPPORTED_CONTROL",
    );
    const lifecycle = await client.rpc("waitForOwnedExit", {
      sessionKey: handle.sessionKey,
      timeoutMs: 10_000,
    });
    assert.equal(lifecycle.status, "exited", JSON.stringify(lifecycle));
    assert.ok(lifecycle.exits.some((exit) => (
      exit.pid === started[0].pid
      && exit.launchId === started[0].launchId
      && exit.startedAt === started[0].startedAt
    )), JSON.stringify({ started, lifecycle }));
    await client.rpc("shutdown");
  });
});

test("actual public runtime rejects a surviving worker without helper-PID proof", {
  timeout: 180_000,
  skip: REAL_ARTIFACT_SKIP,
}, async (t) => {
  await withDriver(t, { syntheticPeerSurvive: true }, async ({ client, child, workspace }) => {
    const handle = await client.rpc("ensureSession", {
      sessionKey: "agy-acp-survivor",
      agent: "antigravity",
      mode: "persistent",
      cwd: workspace,
    });
    const turn = await client.rpc("startTurn", {
      handle,
      text: "antigravity-acp-runtime-turn",
      mode: "prompt",
      requestId: "agy-acp-request-survivor",
      timeoutMs: 300_000,
      intendedRelativePath: "bin/normalize-lines.mjs",
    });
    assert.equal(turn.result.status, "completed");
    assert.ok(turn.process_lifecycle.started.length >= 1, JSON.stringify(turn.process_lifecycle));
    assert.notEqual(turn.process_lifecycle.started[0].pid, child.pid);
    const during = await client.rpc("processLifecycleSnapshot", {
      sessionKey: handle.sessionKey,
    });
    assert.ok(during.started.length >= 1, JSON.stringify(during));
    assert.equal(during.exits.length, 0, JSON.stringify(during));
    const lifecycle = await client.rpc("waitForOwnedExit", {
      sessionKey: handle.sessionKey,
      timeoutMs: 250,
    });
    assert.notEqual(lifecycle.status, "exited", JSON.stringify(lifecycle));
    assert.ok(lifecycle.started.length >= 1, JSON.stringify(lifecycle));
    assert.equal(lifecycle.exits.length, 0, JSON.stringify(lifecycle));
    await client.rpc("shutdown");
    for (const worker of lifecycle.started) {
      try {
        process.kill(worker.pid, "SIGKILL");
      } catch {
        // Worker may already be gone after driver shutdown.
      }
    }
  });
});
