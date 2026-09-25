import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { BridgeError, GrokAcpBroker, createDefaultRuntime, defaultBinderIdForStateRoot } from "../broker.mjs";
import { LIVE_PERMISSION_MODE } from "../host-policy.mjs";

const fixtureCatalog = JSON.parse(
  await (await import("node:fs/promises")).readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;

class Runtime {
  constructor({ model = FIXTURE_MODEL, available = fixtureCatalog.availableModelIds, failEnsure = false } = {}) {
    this.model = model;
    this.available = available;
    this.failEnsure = failEnsure;
    this.ensureCalls = [];
    this.turns = [];
    this.closed = [];
  }
  async ensureSession(input) {
    this.ensureCalls.push(input);
    if (this.failEnsure) throw new BridgeError("EXECUTABLE_MISSING", "missing");
    return { sessionKey: input.sessionKey, cwd: input.cwd, backend: "fixture" };
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
    const turn = {
      requestId: input.requestId,
      promptStarted: Promise.resolve(),
      events: (async function* () {})(),
      result: Promise.resolve({ status: "completed", stopReason: "ok" }),
      cancel: async () => undefined,
    };
    this.turns.push({ input });
    return turn;
  }
  async close(input) { this.closed.push(input); }
  async shutdown() {}
}

async function harness(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-cursor-host-policy-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "grok");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const runtime = options.runtime ?? new Runtime(options.runtimeOptions);
  const broker = new GrokAcpBroker({
    stateRoot: options.stateRoot ?? path.join(root, "state"),
    grokExecutable: executable,
    runtime,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    processEnv: options.processEnv ?? { PATH: process.env.PATH ?? "" },
    defaultHostConversationId: options.defaultHostConversationId ?? null,
    ...(options.stableDefaultBinder ? {} : { defaultBinderId: options.defaultBinderId ?? "owner-a" }),
  });
  await broker.init();
  return { broker, runtime, workspace, root, executable };
}

async function waitForCleanup(broker, jobId, timeoutMs = 1_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await broker.getJob(jobId);
    if (job.cleanup?.status === "completed" && !broker.active.has(jobId)) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail(`cleanup did not complete for ${jobId}`);
}

test("default live runtime uses approve-reads, not approve-all", () => {
  const runtime = createDefaultRuntime({
    stateRoot: "/tmp",
    grokExecutable: "/tmp/grok",
    timeoutMs: 1000,
    processEnv: {},
  });
  assert.equal(runtime.options.permissionMode, LIVE_PERMISSION_MODE);
  assert.equal(runtime.options.nonInteractivePermissions, "fail");
});

test("configured host conversation identity cannot be overridden by a request label", async () => {
  const { broker, workspace } = await harness({ defaultHostConversationId: "conv-configured" });
  await assert.rejects(
    () => broker.delegate({
      workspace,
      prompt: "foreign conversation label",
      hostConversationId: "conv-foreign",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "HOST_CONVERSATION_NOT_HOST_CONTROLLED",
  );
  await broker.close();
});

test("delegate refuses when readiness is red", async () => {
  const missing = await harness();
  await assert.rejects(
    () => missing.broker.delegate({
      workspace: path.join(missing.root, "missing"),
      prompt: "no",
      hostConversationId: "conv-red",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "WORKSPACE_UNAVAILABLE",
  );
  await missing.broker.close();

  const runtime = await harness({ runtimeOptions: { failEnsure: true } });
  await assert.rejects(
    () => runtime.broker.delegate({
      workspace: runtime.workspace,
      prompt: "no",
      hostConversationId: "conv-red",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "EXECUTABLE_MISSING",
  );
  await runtime.broker.close();

  const model = await harness({
    runtimeOptions: { available: ["grok-4.6"], model: "grok-4.6" },
  });
  await assert.rejects(
    () => model.broker.delegate({
      workspace: model.workspace,
      prompt: "no",
      hostConversationId: "conv-red",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(model.runtime.turns.length, 0);
  await model.broker.close();
});

test("one conversation owns one worker; foreign rebind is refused; cwd is not exclusive", async () => {
  const { broker, workspace, root } = await harness();
  const submitted = await broker.delegate({
    workspace,
    prompt: "first worker",
    hostConversationId: "conv-parent",
    binderId: "owner-a",
  });
  assert.equal(submitted.binding.hostConversationId, "conv-parent");
  await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  await waitForCleanup(broker, submitted.jobId);

  await assert.rejects(
    () => broker.delegate({
      workspace,
      prompt: "steal",
      hostConversationId: "conv-parent",
      binderId: "owner-b",
    }),
    (error) => error instanceof BridgeError && error.code === "BINDER_ID_NOT_HOST_CONTROLLED",
  );

  const rebound = await broker.delegate({
    workspace,
    prompt: "owner rebind",
    hostConversationId: "conv-parent",
    binderId: "owner-a",
  });
  assert.equal(rebound.binding.replacedJobId, submitted.jobId);
  await broker.result({ jobId: rebound.jobId, waitMs: 1_000 });

  const otherWorkspace = path.join(root, "other-workspace");
  await mkdir(otherWorkspace);
  const other = await broker.delegate({
    workspace: otherWorkspace,
    prompt: "second conversation",
    hostConversationId: "conv-other",
    binderId: "owner-a",
  });
  assert.equal(other.binding.hostConversationId, "conv-other");
  await broker.close();
});

test("default binder survives a cleaned restart while foreign binders stay rejected", async () => {
  const first = await harness({ stableDefaultBinder: true });
  const submitted = await first.broker.delegate({
    workspace: first.workspace,
    prompt: "first restart-bound worker",
    hostConversationId: "conv-restart-default",
  });
  await first.broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  await waitForCleanup(first.broker, submitted.jobId);
  const stableBinderId = first.broker.defaultBinderId;
  assert.equal(stableBinderId, defaultBinderIdForStateRoot(first.broker.stateRoot));
  await first.broker.close();

  const second = await harness({
    stableDefaultBinder: true,
    stateRoot: path.join(first.root, "state"),
  });
  assert.equal(second.broker.defaultBinderId, stableBinderId);
  const rebound = await second.broker.delegate({
    workspace: second.workspace,
    prompt: "rebind after restart cleanup",
    hostConversationId: "conv-restart-default",
  });
  assert.equal(rebound.binding.replacedJobId, submitted.jobId);
  await assert.rejects(
    () => second.broker.delegate({
      workspace: second.workspace,
      prompt: "foreign binder",
      hostConversationId: "conv-foreign-default",
      binderId: "foreign-owner",
    }),
    (error) => error instanceof BridgeError && error.code === "BINDER_ID_NOT_HOST_CONTROLLED",
  );
  await second.broker.close();
});
