import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AntigravityAcpBroker, terminateProcessGroup, wrapWorkerInProcessGroup } from "../broker.mjs";

const FIXTURE_DIR = path.dirname(fileURLToPath(import.meta.url));
const SLEEP_PEER = path.resolve(FIXTURE_DIR, "fixtures/sleep-peer.mjs");
const STUBBORN_PEER = path.resolve(FIXTURE_DIR, "fixtures/stubborn-sleep-peer.mjs");

function isProcessAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code !== "ESRCH";
  }
}

async function waitUntil(predicate, { timeoutMs = 15_000, intervalMs = 50 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

test("cancel kills the whole process tree and leaves no surviving processes after 15s", { timeout: 30_000 }, async () => {
  const stateRoot = await mkdtemp(path.join(tmpdir(), "agy-cancel-tree-state-"));
  const workspace = await mkdtemp(path.join(tmpdir(), "agy-cancel-tree-ws-"));
  const pidFile = path.join(stateRoot, "sleep-pids.json");

  const broker = new AntigravityAcpBroker({
    stateRoot,
    defaultWorkspace: workspace,
    defaultHostConversationId: "conv-cancel-tree",
    runtimeServer: SLEEP_PEER,
    helperPath: process.execPath,
    readAuthPolicy: async () => ({
      settingsPresent: true,
      authType: "oauth-personal",
      overageState: "never",
    }),
    processEnv: {
      PATH: process.env.PATH,
      TMPDIR: stateRoot,
    },
  });

  try {
    const delegateResult = await broker.delegate({
      workspace,
      model: "gemini-3.8-flash-high",
      prompt: "Start long operation",
    });

    const jobId = delegateResult.jobId;

    // Wait until the child process (sleep 600) is spawned and pids are recorded
    const pidsReady = await waitUntil(async () => {
      try {
        const content = await readFile(pidFile, "utf8");
        const parsed = JSON.parse(content);
        return parsed.workerPid && parsed.childPid;
      } catch {
        return false;
      }
    });

    assert.ok(pidsReady, "Expected workerPid and childPid to be written by sleep-peer");

    const { workerPid, childPid } = JSON.parse(await readFile(pidFile, "utf8"));

    // Verify both worker and child process (sleep 600) are alive
    assert.equal(isProcessAlive(workerPid), true, "Worker process should be alive");
    assert.equal(isProcessAlive(childPid), true, "sleep 600 child process should be alive");

    // Cancel the job
    const cancelResult = await broker.cancel({ jobId, reason: "parent cancelled task" });
    assert.equal(cancelResult.status, "cancellation-requested");

    // Await terminal outcome
    const completed = await broker.result({ jobId, waitMs: 15_000 });

    // The job must end as cancelled, not stay at cancel_requested
    assert.equal(completed.status, "cancelled", "Job must end as cancelled, not stay at cancel_requested");
    assert.equal(completed.taskComplete, true);

    // Read events.jsonl
    const eventsPath = path.join(stateRoot, "runs", jobId, "events.jsonl");
    const eventsRaw = await readFile(eventsPath, "utf8");
    const events = eventsRaw.trim().split("\n").map((line) => JSON.parse(line));

    // Verify worker_exited was recorded with exit signal
    const workerExitedEvent = events.find((e) => e.event === "worker_exited");
    assert.ok(workerExitedEvent, "worker_exited event must be recorded in events.jsonl");
    assert.ok(
      workerExitedEvent.details.exitSignal === "SIGTERM" || workerExitedEvent.details.exitSignal === "SIGKILL",
      `Expected SIGTERM or SIGKILL, got ${workerExitedEvent.details.exitSignal}`,
    );

    // Assert that no process from that job survives after 15s
    const startTime = Date.now();
    const dead = await waitUntil(() => !isProcessAlive(childPid) && !isProcessAlive(workerPid), { timeoutMs: 15_000 });
    const elapsed = Date.now() - startTime;

    assert.ok(dead, `No process from that job should survive (checked up to 15s, elapsed: ${elapsed}ms)`);
    assert.equal(isProcessAlive(childPid), false, "sleep 600 child must not survive");
    assert.equal(isProcessAlive(workerPid), false, "worker process must not survive");
  } finally {
    await broker.close();
    await new Promise((r) => setTimeout(r, 100));
    await rm(stateRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
    await rm(workspace, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
});

test("cancel escalates to SIGKILL if processes ignore SIGTERM", { timeout: 30_000 }, async () => {
  const stateRoot = await mkdtemp(path.join(tmpdir(), "agy-cancel-stubborn-state-"));
  const workspace = await mkdtemp(path.join(tmpdir(), "agy-cancel-stubborn-ws-"));
  const pidFile = path.join(stateRoot, "stubborn-pids.json");

  const broker = new AntigravityAcpBroker({
    stateRoot,
    defaultWorkspace: workspace,
    defaultHostConversationId: "conv-cancel-stubborn",
    runtimeServer: STUBBORN_PEER,
    helperPath: process.execPath,
    workerExitWaitMs: 1_000, // Escalates after 1s for test efficiency
    readAuthPolicy: async () => ({
      settingsPresent: true,
      authType: "oauth-personal",
      overageState: "never",
    }),
    processEnv: {
      PATH: process.env.PATH,
      TMPDIR: stateRoot,
    },
  });

  try {
    const delegateResult = await broker.delegate({
      workspace,
      model: "gemini-3.8-flash-high",
      prompt: "Start stubborn operation",
    });

    const jobId = delegateResult.jobId;

    const pidsReady = await waitUntil(async () => {
      try {
        const content = await readFile(pidFile, "utf8");
        const parsed = JSON.parse(content);
        return parsed.workerPid && parsed.childPid;
      } catch {
        return false;
      }
    });

    assert.ok(pidsReady, "Expected workerPid and childPid to be written by stubborn-sleep-peer");
    const { workerPid, childPid } = JSON.parse(await readFile(pidFile, "utf8"));

    assert.equal(isProcessAlive(workerPid), true);
    assert.equal(isProcessAlive(childPid), true);

    await broker.cancel({ jobId, reason: "cancel stubborn" });

    const completed = await broker.result({ jobId, waitMs: 15_000 });
    assert.equal(completed.status, "cancelled");

    const eventsPath = path.join(stateRoot, "runs", jobId, "events.jsonl");
    const eventsRaw = await readFile(eventsPath, "utf8");
    const events = eventsRaw.trim().split("\n").map((line) => JSON.parse(line));

    const workerExitedEvent = events.find((e) => e.event === "worker_exited");
    assert.ok(workerExitedEvent, "worker_exited event must be recorded in events.jsonl");
    assert.equal(workerExitedEvent.details.exitSignal, "SIGKILL", "Stubborn worker must be killed with SIGKILL");

    const dead = await waitUntil(() => !isProcessAlive(childPid) && !isProcessAlive(workerPid), { timeoutMs: 15_000 });
    assert.ok(dead, "Stubborn processes must not survive after SIGKILL escalation");
  } finally {
    await broker.close();
    await new Promise((r) => setTimeout(r, 100));
    await rm(stateRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
    await rm(workspace, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
});

test("worker launch falls back to direct command when python3 is unavailable", () => {
  assert.deepEqual(
    wrapWorkerInProcessGroup("mycmd", ["a"], { platform: "linux", hasPython3: () => false }),
    ["mycmd", "a"],
  );
  assert.deepEqual(
    wrapWorkerInProcessGroup("mycmd", ["a"], { platform: "win32", hasPython3: () => true }),
    ["mycmd", "a"],
  );
  assert.equal(
    wrapWorkerInProcessGroup("mycmd", ["a"], { platform: "linux", hasPython3: () => true })[0],
    "python3",
  );
});

test("termination on win32 signals the positive pid, never a process group", async () => {
  const calls = [];
  const taskkillCalls = [];
  let alive = true;
  const kill = (target, sig) => {
    calls.push([target, sig]);
    if (!alive) {
      const error = new Error("no such process");
      error.code = "ESRCH";
      throw error;
    }
    if (sig !== 0) alive = false;
  };
  const taskkill = async (target, force) => {
    taskkillCalls.push([target, force]);
    alive = false;
  };
  const result = await terminateProcessGroup(4321, {
    platform: "win32",
    kill,
    taskkill,
    graceMs: 1_000,
    pollMs: 10,
  });
  assert.equal(result.exited, true);
  assert.ok(calls.every(([target]) => target === 4321), `negative pid used: ${JSON.stringify(calls)}`);
  assert.deepEqual(taskkillCalls[0], [4321, false], "win32 tree kill must use taskkill /T");
});

test("termination without a process group also signals descendants", async () => {
  const alive = new Set([4321, 5001]);
  const calls = [];
  const kill = (target, sig) => {
    calls.push([target, sig]);
    if (target < 0 || !alive.has(target)) {
      const error = new Error("no such process");
      error.code = "ESRCH";
      throw error;
    }
    if (sig !== 0) alive.delete(target);
  };
  const result = await terminateProcessGroup(4321, {
    platform: "linux",
    kill,
    descendantsOf: async () => [5001],
    graceMs: 1_000,
    pollMs: 10,
  });
  assert.equal(result.exited, true);
  assert.equal(alive.size, 0, "descendant must not survive fallback termination");
  assert.ok(calls.some(([target, sig]) => target === 5001 && sig === "SIGTERM"));
});
