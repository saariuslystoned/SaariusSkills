import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { z } from "zod";
import {
  BridgeError,
  DEFAULT_TIMEOUT_MS,
  GrokAcpBroker,
  MAX_TIMEOUT_MS,
  MIN_TIMEOUT_MS,
  RUNTIME_CONTROL_TIMEOUT_MS,
  createDefaultRuntime,
  timeoutMsZod,
} from "../broker.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;
const FORTY_FIVE_MIN_MS = 45 * 60 * 1000;

class TimeoutFixtureRuntime {
  constructor({ delayMs = 10 } = {}) {
    this.delayMs = delayMs;
    this.ensureCalls = [];
    this.turns = [];
    this.closed = [];
  }

  async ensureSession(input) {
    this.ensureCalls.push(input);
    return {
      sessionKey: input.sessionKey,
      backend: "fixture",
      runtimeSessionName: `fixture:${input.sessionKey}`,
      cwd: input.cwd,
      backendSessionId: `backend-${this.ensureCalls.length}`,
      agentSessionId: `agent-${this.ensureCalls.length}`,
    };
  }

  async getStatus() {
    return {
      models: {
        currentModelId: FIXTURE_MODEL,
        availableModelIds: fixtureCatalog.availableModelIds,
        availableModels: fixtureCatalog.availableModelIds.map((modelId) => ({ modelId, name: modelId })),
      },
      details: {
        configOptions: [{
          id: "reasoning_effort",
          category: "thought_level",
          type: "select",
          currentValue: this.reasoningEffort ?? "high",
          options: ["xhigh", "high", "medium", "low"].map((value) => ({ value, name: value })),
        }],
      },
    };
  }

  async setModel({ model }) {
    if (fixtureCatalog.availableModelIds.includes(model)) this.model = model;
  }

  async setConfigOption({ key, value }) {
    if (key === "reasoning_effort") this.reasoningEffort = value;
  }

  startTurn(input) {
    const state = { cancelled: false, resolve: null };
    const result = new Promise((resolve) => {
      state.resolve = resolve;
    });
    const finish = (value) => {
      if (!state.resolve) return;
      const resolve = state.resolve;
      state.resolve = null;
      resolve(value);
    };
    const turn = {
      requestId: input.requestId,
      timeoutMs: input.timeoutMs,
      promptStarted: Promise.resolve(),
      events: (async function* () {
        yield { type: "status", tag: "session_info_update", text: "fixture" };
      })(),
      result,
      cancel: async () => {
        state.cancelled = true;
        finish({ status: "cancelled", stopReason: "fixture cancel" });
      },
      closeStream: async () => undefined,
    };
    this.turns.push({ input, turn });
    const turnTimeoutMs = Number.isInteger(input.timeoutMs) ? input.timeoutMs : Number.POSITIVE_INFINITY;
    if (turnTimeoutMs < this.delayMs) {
      setTimeout(() => {
        if (state.cancelled || !state.resolve) return;
        finish({
          status: "failed",
          error: { code: "TIMEOUT", message: "Grok ACP timed out" },
        });
      }, turnTimeoutMs);
      return turn;
    }
    setTimeout(() => {
      if (state.cancelled || !state.resolve) return;
      finish({ status: "completed", stopReason: "fixture complete" });
    }, this.delayMs);
    return turn;
  }

  async close(input) {
    this.closed.push(input);
  }

  async shutdown() {}
}

function hermeticProcessEnv() {
  const env = { ...process.env };
  delete env.SAARIUS_ACP_PERMISSION_MODE;
  return env;
}

async function makeBroker(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-grok-acp-timeout-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "grok");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const runtime = options.runtime ?? new TimeoutFixtureRuntime(options.runtimeOptions);
  const broker = new GrokAcpBroker({
    stateRoot: path.join(root, "state"),
    grokExecutable: executable,
    runtime,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    processEnv: hermeticProcessEnv(),
    defaultHostConversationId: options.defaultHostConversationId ?? `conv-${path.basename(root)}`,
    defaultBinderId: options.defaultBinderId ?? "test-owner",
    ...options,
  });
  await broker.init();
  return { broker, runtime, workspace, root };
}

async function persistedJob(broker, jobId) {
  return JSON.parse(await readFile(path.join(broker.jobsRoot, `${jobId}.json`), "utf8"));
}

async function waitUntil(predicate, timeoutMs = 2_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 15));
  }
  assert.fail("condition did not become true before timeout");
}

test("job timeout policy constants stay 60 minutes default and 4 hours max", () => {
  assert.equal(MIN_TIMEOUT_MS, 1_000);
  assert.equal(DEFAULT_TIMEOUT_MS, 3_600_000);
  assert.equal(MAX_TIMEOUT_MS, 14_400_000);
  assert.equal(RUNTIME_CONTROL_TIMEOUT_MS, 10 * 60 * 1000);
  assert.notEqual(RUNTIME_CONTROL_TIMEOUT_MS, DEFAULT_TIMEOUT_MS);
});

test("native MCP timeout schema uses exported policy constants", () => {
  const schema = timeoutMsZod(z);
  assert.equal(schema.parse(undefined), undefined);
  assert.equal(schema.parse(FORTY_FIVE_MIN_MS), FORTY_FIVE_MIN_MS);
  assert.equal(schema.parse(MAX_TIMEOUT_MS), MAX_TIMEOUT_MS);
  assert.throws(() => schema.parse(MAX_TIMEOUT_MS + 1), /too_big|max/i);
  assert.throws(() => schema.parse(MIN_TIMEOUT_MS - 1), /too_small|min/i);
});

test("server delegate schema imports timeoutMsZod instead of a hardcoded cap", async () => {
  const source = await readFile(new URL("../server.mjs", import.meta.url), "utf8");
  assert.match(source, /timeoutMsZod/);
  assert.match(source, /timeoutMs:\s*timeoutMsZod\(z\)/);
  assert.doesNotMatch(source, /1_800_000/);
  assert.match(source, /waitMs: z\.number\(\)\.int\(\)\.min\(0\)\.max\(10_000\)/);
  assert.match(source, /waitMs: z\.number\(\)\.int\(\)\.min\(0\)\.max\(300_000\)/);
});

test("omitted timeout defaults to 60 minutes on public job, persisted job, and runtime turn", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const submitted = await broker.delegate({
    workspace,
    prompt: "Apply one bounded change and report.",
  });
  assert.equal(submitted.timeoutMs, DEFAULT_TIMEOUT_MS);
  assert.equal((await persistedJob(broker, submitted.jobId)).timeoutMs, DEFAULT_TIMEOUT_MS);
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.timeoutMs, DEFAULT_TIMEOUT_MS);
  assert.equal(runtime.turns[0].input.timeoutMs, DEFAULT_TIMEOUT_MS);
  await broker.close();
});

test("explicit 45 minute and 4 hour timeouts are accepted and reach the runtime turn", async () => {
  for (const timeoutMs of [FORTY_FIVE_MIN_MS, MAX_TIMEOUT_MS]) {
    const { broker, runtime, workspace } = await makeBroker();
    const submitted = await broker.delegate({
      workspace,
      prompt: "Apply one bounded change and report.",
      timeoutMs,
    });
    assert.equal(submitted.timeoutMs, timeoutMs);
    assert.equal((await persistedJob(broker, submitted.jobId)).timeoutMs, timeoutMs);
    const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
    assert.equal(completed.status, "completed");
    assert.equal(completed.timeoutMs, timeoutMs);
    assert.equal(runtime.turns[0].input.timeoutMs, timeoutMs);
    await broker.close();
  }
});

test("4 hours plus one millisecond is rejected at the broker before a runtime turn", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  await assert.rejects(
    () => broker.delegate({
      workspace,
      prompt: "This must not start.",
      timeoutMs: MAX_TIMEOUT_MS + 1,
    }),
    (error) => error instanceof BridgeError
      && error.code === "INVALID_INPUT"
      && error.message.includes(String(MAX_TIMEOUT_MS)),
  );
  assert.equal(runtime.ensureCalls.length, 0);
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("short synthetic timeout fails closed and still completes cleanup", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: { delayMs: 5_000 },
  });
  const submitted = await broker.delegate({
    workspace,
    prompt: "Hold the turn past a short synthetic budget.",
    timeoutMs: MIN_TIMEOUT_MS,
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 2_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error?.code, "TIMEOUT");
  assert.equal(completed.timeoutMs, MIN_TIMEOUT_MS);
  await waitUntil(async () => (await broker.result({ jobId: submitted.jobId })).cleanupReady === true
    && !broker.active.has(submitted.jobId));
  const cleaned = await broker.result({ jobId: submitted.jobId });
  assert.equal(cleaned.cleanupReady, true);
  assert.equal(cleaned.cleanup?.status, "completed");
  assert.equal(runtime.turns[0].input.timeoutMs, MIN_TIMEOUT_MS);
  assert.equal(runtime.closed.length, 1);
  assert.equal(broker.active.has(submitted.jobId), false);
  await broker.close();
});

test("default ACpx runtime keeps the 10-minute control-plane timeout", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-grok-acp-control-timeout-"));
  const runtime = createDefaultRuntime({
    stateRoot: root,
    grokExecutable: "/fixture/grok",
  });
  assert.equal(runtime.options.timeoutMs, RUNTIME_CONTROL_TIMEOUT_MS);
  await runtime.shutdown();
});
