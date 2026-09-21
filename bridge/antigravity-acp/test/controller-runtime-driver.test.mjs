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
  });
  assert.equal(turn.requestId, "agy-acp-request-1");
  assert.equal(turn.result.status, "completed");
  assert.equal(turn.discarded.body_retained, false);
  await client.rpc("close", {
    handle,
    reason: "antigravity-acp-owned-close",
    discardPersistentState: true,
  });
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
