import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { randomUUID } from "node:crypto";
import {
  BridgeError,
  CursorAcpBroker,
  DEFAULT_CURSOR_MODEL,
  redactSensitive,
  resolveRequestedCursorModel,
} from "../broker.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class FixtureRuntime {
  constructor({ model = FIXTURE_MODEL, available = fixtureCatalog.availableModelIds, delayMs = 10 } = {}) {
    this.model = model;
    this.available = available;
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
        currentModelId: this.model,
        availableModelIds: this.available,
        availableModels: this.available.map((modelId) => ({ modelId, name: modelId })),
      },
    };
  }

  async setModel({ model }) {
    if (this.available.includes(model)) this.model = model;
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
      promptStarted: Promise.resolve(),
      events: (async function* () {
        yield { type: "status", tag: "session_info_update", text: "fixture" };
        if (input.mode === "prompt") {
          await sleep(5);
          yield {
            type: "text_delta",
            stream: "output",
            text: "Changed files: bridge/cursor-acp/broker.mjs\nTests: fixture pass",
          };
        }
      })(),
      result,
      cancel: async () => {
        state.cancelled = true;
        finish({ status: "cancelled", stopReason: "fixture cancel" });
      },
      closeStream: async () => undefined,
    };
    this.turns.push({ input, turn });
    setTimeout(() => {
      if (!state.cancelled) finish({ status: "completed", stopReason: "fixture complete" });
    }, this.delayMs);
    return turn;
  }

  async close(input) {
    this.closed.push(input);
  }

  async shutdown() {}
}

async function makeBroker(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-cursor-acp-test-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "cursor-agent");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const runtime = options.runtime ?? new FixtureRuntime(options.runtimeOptions);
  const broker = new CursorAcpBroker({
    stateRoot: path.join(root, "state"),
    cursorExecutable: executable,
    runtime,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    ...options,
  });
  await broker.init();
  return { broker, runtime, workspace, root, executable };
}

async function waitUntil(predicate, timeoutMs = 1_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await sleep(5);
  }
  assert.fail("condition did not become true before timeout");
}

test("readiness proves the exact advertised Cursor model without a turn", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(report.model.selectedModelId, FIXTURE_MODEL);
  assert.equal(report.model.availableModelCount, fixtureCatalog.availableModelIds.length);
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.ensureCalls[0].mode, "oneshot");
  await broker.close();
});

test("Cursor CLI selector resolves only one matching parameterized ACP model", () => {
  assert.equal(
    resolveRequestedCursorModel("cursor-grok-4.6-high", ["grok-4.6[effort=high,fast=true]"]),
    "grok-4.6[effort=high,fast=true]",
  );
  assert.throws(
    () => resolveRequestedCursorModel("cursor-grok-4.6-high", [
      "grok-4.6[effort=high,fast=true]",
      "cursor-grok-4.6[effort=high,fast=true]",
    ]),
    (error) => error instanceof BridgeError && error.code === "MODEL_AMBIGUOUS",
  );
});

test("delegation binds one workspace and exact model, then returns a bounded handoff", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const submitted = await broker.delegate({
    workspace,
    prompt: "Make the smallest bounded implementation change and report the handoff.",
    timeoutMs: 30_000,
  });
  assert.match(submitted.jobId, /^[0-9a-f-]{36}$/i);
  assert.equal(submitted.status, "submitted");
  assert.equal(submitted.workspace, workspace);
  assert.equal(submitted.route.model, FIXTURE_MODEL);
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.complete, true);
  assert.match(completed.handoff, /Changed files/);
  assert.equal(runtime.ensureCalls[0].cwd, workspace);
  assert.equal(runtime.ensureCalls[0].sessionOptions.model, undefined);
  assert.equal(runtime.turns[0].input.mode, "prompt");
  assert.notEqual(path.dirname(completed.proof.proof), workspace);
  await broker.close();
});

test("steering uses the active ACP session and preserves the parent job identity", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: { delayMs: 100 },
  });
  const submitted = await broker.delegate({ workspace, prompt: "Hold the bounded turn briefly." });
  await waitUntil(() => broker.active.get(submitted.jobId)?.turn);
  const steering = await broker.steer({ jobId: submitted.jobId, message: "Continue and finish the requested handoff." });
  assert.equal(steering.status, "accepted");
  assert.equal(steering.jobId, submitted.jobId);
  assert.equal(runtime.turns[1].input.mode, "steer");
  assert.equal(runtime.turns[1].input.handle.sessionKey, runtime.turns[0].input.handle.sessionKey);
  await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  await broker.close();
});

test("cancellation returns an explicit cancelled outcome", async () => {
  const { broker, workspace } = await makeBroker({
    runtimeOptions: { delayMs: 5_000 },
  });
  const submitted = await broker.delegate({ workspace, prompt: "Run a bounded long operation, then report." });
  await waitUntil(() => broker.active.get(submitted.jobId)?.turn);
  const requested = await broker.cancel({ jobId: submitted.jobId, reason: "parent stopped the bounded task" });
  assert.equal(requested.status, "cancellation-requested");
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "cancelled");
  assert.equal(completed.complete, true);
  await broker.close();
});

test("model mismatch fails closed instead of silently falling back", async () => {
  const { broker, workspace } = await makeBroker({
    runtimeOptions: { available: ["cursor-grok-4.6-medium"], model: "cursor-grok-4.6-medium" },
  });
  const submitted = await broker.delegate({ workspace, prompt: "This must not run." });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_UNAVAILABLE");
  await broker.close();
});

test("missing Cursor executable is an actionable preflight error", async () => {
  const { broker, workspace } = await makeBroker();
  broker.cursorExecutable = path.join(path.dirname(broker.cursorExecutable), "missing-cursor-agent");
  await assert.rejects(
    () => broker.checkExecutable(),
    (error) => error instanceof BridgeError && error.code === "EXECUTABLE_MISSING",
  );
  await broker.close();
  assert.equal(workspace.endsWith("workspace"), true);
});

test("safe summaries redact credentials and do not persist prompt bodies", async () => {
  assert.equal(redactSensitive("token=ghp_12345678901234567890"), "token=[redacted]");
  assert.equal(redactSensitive("Authorization: Bearer abc.def.ghi"), "Authorization=[redacted]");
  const { broker, workspace } = await makeBroker();
  const prompt = "Do not persist this unique prompt body 9f5e61d7.";
  const submitted = await broker.delegate({ workspace, prompt });
  const rawState = await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8");
  assert.equal(rawState.includes(prompt), false);
  await broker.close();
});

test("a bridge restart fails a persisted in-flight job closed", async () => {
  const first = await makeBroker({ runtimeOptions: { delayMs: 5_000 } });
  const submitted = await first.broker.delegate({ workspace: first.workspace, prompt: "Hold until the bridge restarts." });
  await waitUntil(() => first.broker.getJob(submitted.jobId).then((job) => job.status === "running"));
  const secondRuntime = new FixtureRuntime();
  const second = new CursorAcpBroker({
    stateRoot: first.broker.stateRoot,
    cursorExecutable: first.executable,
    runtime: secondRuntime,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
  });
  await second.init();
  const recovered = await second.result({ jobId: submitted.jobId });
  assert.equal(recovered.status, "failed");
  assert.equal(recovered.error.code, "BRIDGE_RESTARTED");
  await first.broker.close();
  await second.close();
});
