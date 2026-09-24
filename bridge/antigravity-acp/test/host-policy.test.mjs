import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  AntigravityAcpBroker,
  BridgeError,
  createDefaultRuntime,
  createProcessLifecycleTracker,
} from "../broker.mjs";
import { LIVE_PERMISSION_MODE } from "../host-policy.mjs";
import {
  currentPlatformId,
  platformLaunch,
  PREFERRED_DEFAULT_MODEL_ID,
  settingsPath,
} from "../contract.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;

async function harness(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-agy-host-policy-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const launch = platformLaunch(currentPlatformId());
  const runtimeDir = path.join(root, "runtime");
  await mkdir(runtimeDir);
  const executable = path.join(runtimeDir, path.basename(launch.runtimeCommand));
  const helper = path.join(runtimeDir, path.basename(launch.helper));
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await writeFile(helper, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  await chmod(helper, 0o700);
  await mkdir(path.dirname(settingsPath(path.join(root, "gemini-home"))), { recursive: true });
  await writeFile(
    settingsPath(path.join(root, "gemini-home")),
    JSON.stringify({ auth: { type: "oauth-personal" }, useG1Credits: false }),
  );
  class Runtime {
    constructor() {
      this.ensureCalls = [];
      this.turns = [];
      this.closed = [];
      this.model = options.model ?? FIXTURE_MODEL;
      this.available = options.available ?? fixtureCatalog.availableModelIds;
    }
    async ensureSession(input) {
      this.ensureCalls.push(input);
      if (options.failEnsure) throw new BridgeError("RUNTIME_MISSING", "runtime missing");
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
      const result = Promise.resolve({ status: "completed", stopReason: "ok" });
      const turn = {
        requestId: input.requestId,
        promptStarted: Promise.resolve(),
        events: (async function* () {})(),
        result,
        cancel: async () => undefined,
      };
      this.turns.push({ input });
      return turn;
    }
    async close(input) { this.closed.push(input); }
    async shutdown() {}
  }
  const runtime = new Runtime();
  const broker = new AntigravityAcpBroker({
    stateRoot: path.join(root, "state"),
    runtimeDir,
    geminiHome: path.join(root, "gemini-home"),
    processEnv: { PATH: process.env.PATH ?? "", ...options.processEnv },
    runtime,
    processLifecycleTracker: createProcessLifecycleTracker(),
    workerExitWaitMs: 50,
    defaultHostConversationId: options.defaultHostConversationId ?? null,
    defaultBinderId: options.defaultBinderId ?? "owner-a",
  });
  await broker.init();
  return { broker, runtime, workspace, root };
}

test("default live runtime uses approve-reads, not approve-all", () => {
  const runtime = createDefaultRuntime({
    stateRoot: "/tmp",
    launch: { command: "true", args: [], helper: "true" },
    geminiHome: "/tmp",
    timeoutMs: 1000,
    processEnv: { PATH: "/usr/bin" },
  });
  assert.equal(runtime.options.permissionMode, LIVE_PERMISSION_MODE);
  assert.equal(runtime.options.nonInteractivePermissions, "fail");
});

test("configured host conversation identity cannot be overridden by a request label", async () => {
  const { broker, workspace } = await harness({ defaultHostConversationId: "conv-configured" });
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "foreign conversation label",
      hostConversationId: "conv-foreign",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "HOST_CONVERSATION_NOT_HOST_CONTROLLED",
  );
  await broker.close();
});

test("delegate refuses when runtime, auth, model, or workspace is red", async () => {
  const missingConversation = await harness();
  await assert.rejects(
    () => missingConversation.broker.delegate({
      workspace: missingConversation.workspace,
      model: FIXTURE_MODEL,
      prompt: "no",
    }),
    (error) => error instanceof BridgeError && error.code === "HOST_CONVERSATION_REQUIRED",
  );
  await missingConversation.broker.close();

  const missingWorkspace = await harness();
  await assert.rejects(
    () => missingWorkspace.broker.delegate({
      workspace: path.join(missingWorkspace.root, "missing"),
      model: FIXTURE_MODEL,
      prompt: "no",
      hostConversationId: "conv-red",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "WORKSPACE_UNAVAILABLE",
  );
  await missingWorkspace.broker.close();

  const runtime = await harness({ failEnsure: true });
  await assert.rejects(
    () => runtime.broker.delegate({
      workspace: runtime.workspace,
      model: FIXTURE_MODEL,
      prompt: "no",
      hostConversationId: "conv-red",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "RUNTIME_MISSING",
  );
  await runtime.broker.close();

  const auth = await harness({ processEnv: { GEMINI_API_KEY: "placeholder" } });
  await assert.rejects(
    () => auth.broker.delegate({
      workspace: auth.workspace,
      model: FIXTURE_MODEL,
      prompt: "no",
      hostConversationId: "conv-red",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "AUTH_FALLBACK_FORBIDDEN",
  );
  await auth.broker.close();

  const model = await harness({ available: ["gemini-3.1-pro"], model: "gemini-3.1-pro" });
  await assert.rejects(
    () => model.broker.delegate({
      workspace: model.workspace,
      model: PREFERRED_DEFAULT_MODEL_ID,
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
  const first = await harness();
  const submitted = await first.broker.delegate({
    workspace: first.workspace,
    model: FIXTURE_MODEL,
    prompt: "first worker",
    hostConversationId: "conv-parent",
    binderId: "owner-a",
  });
  assert.equal(submitted.binding.hostConversationId, "conv-parent");
  assert.equal(submitted.binding.binderId, "owner-a");
  await first.broker.result({ jobId: submitted.jobId, waitMs: 1_000 });

  await assert.rejects(
    () => first.broker.delegate({
      workspace: first.workspace,
      model: FIXTURE_MODEL,
      prompt: "steal",
      hostConversationId: "conv-parent",
      binderId: "owner-b",
    }),
    (error) => error instanceof BridgeError && error.code === "BINDER_ID_NOT_HOST_CONTROLLED",
  );

  const rebound = await first.broker.delegate({
    workspace: first.workspace,
    model: FIXTURE_MODEL,
    prompt: "same owner rebind",
    hostConversationId: "conv-parent",
    binderId: "owner-a",
  });
  assert.equal(rebound.binding.replacedJobId, submitted.jobId);
  await first.broker.result({ jobId: rebound.jobId, waitMs: 1_000 });

  const otherWorkspace = path.join(first.root, "other-workspace");
  await mkdir(otherWorkspace);
  const otherConversation = await first.broker.delegate({
    workspace: otherWorkspace,
    model: FIXTURE_MODEL,
    prompt: "other conversation may share no cwd lock",
    hostConversationId: "conv-other",
    binderId: "owner-a",
  });
  assert.equal(otherConversation.binding.hostConversationId, "conv-other");
  assert.equal(otherConversation.workspace, otherWorkspace);
  await first.broker.close();
});
