import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  AntigravityAcpBroker,
  BridgeError,
  classifyOwnerIdentity,
  createDefaultRuntime,
  createProcessLifecycleTracker,
  isCanonicalComplete,
  isCleanupReady,
  isInteractionQuestion,
  isUnsupportedBackendSessionClose,
  needsCleanupFence,
  processIdentitiesMatch,
  redactSensitive,
  resolveAntigravityModelChoice,
  resolvePreferredDefaultAntigravityModel,
  resolveRequestedAntigravityModel,
  shouldRecoverCleanupFence,
  shouldRecoverOwnedJob,
} from "../broker.mjs";
import {
  PREFERRED_DEFAULT_MODEL_ID,
  currentPlatformId,
  defaultRuntimeDir,
  platformLaunch,
  settingsPath,
} from "../contract.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class FixtureRuntime {
  constructor({
    model = FIXTURE_MODEL,
    available = fixtureCatalog.availableModelIds,
    delayMs = 10,
    failWith,
    permissionRequest,
    closeHold,
    closeError,
    processLifecycle,
    workerPid = 4242,
    workerStartedAt = "fixture-worker-start",
    emitWorkerExitOnClose = false,
  } = {}) {
    this.model = model;
    this.available = available;
    this.delayMs = delayMs;
    this.failWith = failWith;
    this.permissionRequest = permissionRequest;
    this.closeHold = closeHold;
    this.closeError = closeError;
    this.processLifecycle = processLifecycle;
    this.workerPid = workerPid;
    this.workerStartedAt = workerStartedAt;
    this.emitWorkerExitOnClose = emitWorkerExitOnClose;
    this.permissionDecisions = [];
    this.ensureCalls = [];
    this.turns = [];
    this.closed = [];
    this.closeStarted = [];
    this.started = [];
  }

  async ensureSession(input) {
    this.ensureCalls.push(input);
    if (this.failWith === "ensure") {
      throw new BridgeError("AUTHENTICATION_REQUIRED", "Authentication required");
    }
    const started = {
      launchId: `fixture-launch-${this.ensureCalls.length}`,
      scope: { kind: "runtime-session", sessionKey: input.sessionKey },
      command: "fixture",
      args: [],
      cwd: input.cwd,
      pid: this.workerPid,
      startedAt: this.workerStartedAt,
    };
    this.started.push(started);
    this.processLifecycle?.onSpawned?.(started);
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
            text: "Changed files: bridge/antigravity-acp/broker.mjs\nTests: fixture pass",
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
    setTimeout(async () => {
      if (state.cancelled) return;
      if (this.permissionRequest && input.onPermissionRequest) {
        try {
          const decision = await input.onPermissionRequest(this.permissionRequest);
          this.permissionDecisions.push(decision);
          if (decision?.outcome === "cancel" && this.permissionRequest?.raw?.toolCall?.toolCallId?.startsWith("interaction_")) {
            finish({ status: "completed", stopReason: "fixture complete" });
            return;
          }
          if (decision === undefined || decision?.outcome === "cancel") {
            finish({
              status: "completed",
              stopReason: "fixture permission denied by runtime policy",
            });
            return;
          }
        } catch (error) {
          this.permissionDecisions.push({ outcome: "failed", code: error.code });
          finish({
            status: "failed",
            error: { code: error.code ?? "PERMISSION_PROMPT_UNAVAILABLE", message: error.message },
          });
          return;
        }
      }
      if (this.failWith === "auth-turn") {
        finish({
          status: "failed",
          error: { code: "AUTHENTICATION_REQUIRED", message: "Authentication required" },
        });
        return;
      }
      finish({ status: "completed", stopReason: "fixture complete" });
    }, this.delayMs);
    return turn;
  }

  async close(input) {
    this.closeStarted.push(input);
    if (this.closeHold) await this.closeHold;
    if (this.emitWorkerExitOnClose || !this.closeError) {
      const started = this.started.at(-1);
      if (started) {
        this.processLifecycle?.onExit?.({
          ...started,
          exitCode: 0,
          signal: "SIGTERM",
          exitedAt: "fixture-worker-exit",
        });
      }
    }
    if (this.closeError) {
      throw this.closeError instanceof Error ? this.closeError : new Error(String(this.closeError));
    }
    this.closed.push(input);
  }

  async shutdown() {}
}

async function makeBroker(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-antigravity-acp-test-"));
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
  const geminiHome = path.join(root, "gemini-home");
  await mkdir(path.dirname(settingsPath(geminiHome)), { recursive: true });
  await writeFile(
    settingsPath(geminiHome),
    JSON.stringify({ auth: { type: "oauth-personal" }, useG1Credits: false }),
  );
  const processLifecycleTracker = options.processLifecycleTracker ?? createProcessLifecycleTracker();
  const runtime = options.runtime ?? new FixtureRuntime({
    ...options.runtimeOptions,
    processLifecycle: options.runtimeOptions?.processLifecycle ?? processLifecycleTracker.processLifecycle,
  });
  const broker = new AntigravityAcpBroker({
    stateRoot: path.join(root, "state"),
    runtimeDir,
    geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    runtime,
    processLifecycleTracker,
    workerExitWaitMs: options.workerExitWaitMs ?? 100,
    defaultHostConversationId: options.defaultHostConversationId ?? `conv-${path.basename(root)}`,
    defaultBinderId: options.defaultBinderId ?? "test-owner",
    ...options,
  });
  await broker.init();
  return { broker, runtime, workspace, root, executable, helper, geminiHome };
}

async function waitUntil(predicate, timeoutMs = 1_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await sleep(5);
  }
  assert.fail("condition did not become true before timeout");
}

test("default runtime directory follows the pinned platform archive layout", () => {
  assert.match(
    defaultRuntimeDir("darwin-aarch64"),
    /\.local\/share\/saarius-skills\/antigravity-acp\/1\.1\.1-darwin-arm64$/,
  );
  assert.match(
    defaultRuntimeDir("linux-x86_64"),
    /\.local\/share\/saarius-skills\/antigravity-acp\/1\.1\.1-linux-x86_64$/,
  );
});

test("readiness proves advertised models without a turn", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(report.pin.version, "1.1.1");
  assert.equal(report.pin.acpxRelease, "0.19.1");
  assert.equal(report.pin.acpxSourceCommit, null);
  assert.equal(
    report.pin.lastInspectedSourceCommit,
    "50a47ad10a75431cbc276ec9b555d11fe1f69c84",
  );
  assert.equal(report.pin.lastInspectedSourceRelease, "0.17.1");
  assert.equal(report.model.availableModelCount, fixtureCatalog.availableModelIds.length);
  assert.equal(report.model.preferredDefaultModelId, PREFERRED_DEFAULT_MODEL_ID);
  assert.equal(report.model.preferredDefaultAvailable, true);
  assert.equal(report.model.selectedModelId, PREFERRED_DEFAULT_MODEL_ID);
  assert.equal(report.auth.mode, "oauth-personal");
  assert.equal(report.ultraAttribution, "unclaimed");
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.ensureCalls[0].mode, "oneshot");
  await broker.close();
});

test("exact advertised model selection fails closed on unknown, ambiguous, or substituted IDs", () => {
  assert.equal(
    resolveRequestedAntigravityModel("gemini-3.8-flash-high", fixtureCatalog.availableModelIds),
    "gemini-3.8-flash-high",
  );
  assert.throws(
    () => resolveRequestedAntigravityModel("gemini-flash", fixtureCatalog.availableModelIds),
    (error) => error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE",
  );
  assert.throws(
    () => resolveRequestedAntigravityModel("gemini-3.8-flash-high", [
      "gemini-3.8-flash-high",
      "gemini-3.8-flash-high",
    ]),
    (error) => error instanceof BridgeError && error.code === "MODEL_AMBIGUOUS",
  );
});

test("omitted model prefers exact advertised gemini-3.8-flash-high and does not use 3.7", () => {
  assert.equal(PREFERRED_DEFAULT_MODEL_ID, "gemini-3.8-flash-high");
  assert.equal(
    resolveAntigravityModelChoice(undefined, [
      "gemini-3.7-flash-high",
      "gemini-3.8-flash-high",
    ]),
    "gemini-3.8-flash-high",
  );
  assert.equal(
    resolvePreferredDefaultAntigravityModel([
      "gemini-3.7-flash-high",
      "gemini-3.8-flash-high",
    ]),
    "gemini-3.8-flash-high",
  );
  assert.throws(
    () => resolveAntigravityModelChoice(undefined, ["gemini-3.7-flash-high"]),
    (error) =>
      error instanceof BridgeError &&
      error.code === "MODEL_REQUIRED" &&
      error.message.includes("gemini-3.8-flash-high") &&
      !error.message.includes("gemini-3.7-flash-high is advertised"),
  );
  assert.throws(
    () => resolvePreferredDefaultAntigravityModel(["gemini-3.7-flash-high"]),
    (error) => error instanceof BridgeError && error.code === "MODEL_REQUIRED",
  );
  assert.throws(
    () => resolveAntigravityModelChoice(undefined, [
      "gemini-3.8-flash-high",
      "gemini-3.8-flash-high",
    ]),
    (error) => error instanceof BridgeError && error.code === "MODEL_AMBIGUOUS",
  );
});

test("delegation binds one workspace and exact model, then returns a bounded handoff", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
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
  assert.equal(runtime.turns[0].input.mode, "prompt");
  assert.notEqual(path.dirname(completed.proof.proof), workspace);
  await broker.close();
});

test("relative workspace and missing model fail closed before a turn", async () => {
  const { broker } = await makeBroker();
  await assert.rejects(
    () => broker.delegate({ workspace: "relative", model: FIXTURE_MODEL, prompt: "no" }),
    (error) => error instanceof BridgeError && error.code === "INVALID_WORKSPACE",
  );
  await assert.rejects(
    () => broker.delegate({
      workspace: broker.defaultWorkspace,
      model: FIXTURE_MODEL,
      prompt: "no",
      effort: "high",
    }),
    (error) => error instanceof BridgeError && error.code === "EFFORT_UNSUPPORTED",
  );
  await broker.close();
});

test("omitted model uses plugin default when advertised even if current is 3.7", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: {
      model: "gemini-3.7-flash-high",
      available: ["gemini-3.7-flash-high", PREFERRED_DEFAULT_MODEL_ID],
    },
  });
  const readiness = await broker.discover({ workspace });
  assert.equal(readiness.ready, true);
  assert.equal(readiness.model.currentModelId, PREFERRED_DEFAULT_MODEL_ID);
  assert.equal(readiness.model.selectedModelId, PREFERRED_DEFAULT_MODEL_ID);
  assert.equal(readiness.model.preferredDefaultAvailable, true);
  assert.equal(runtime.turns.length, 0);
  const submitted = await broker.delegate({
    workspace,
    prompt: "Make the smallest bounded implementation change and report the handoff.",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.model, PREFERRED_DEFAULT_MODEL_ID);
  assert.equal(completed.route.model, PREFERRED_DEFAULT_MODEL_ID);
  assert.equal(runtime.model, PREFERRED_DEFAULT_MODEL_ID);
  await broker.close();
});

test("omitted model fails closed when plugin default is not advertised", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: {
      model: "gemini-3.7-flash-high",
      available: ["gemini-3.7-flash-high"],
    },
  });
  const readiness = await broker.discover({ workspace });
  assert.equal(readiness.ready, true);
  assert.equal(readiness.model.currentModelId, "gemini-3.7-flash-high");
  assert.equal(readiness.model.selectedModelId, null);
  assert.equal(readiness.model.preferredDefaultModelId, PREFERRED_DEFAULT_MODEL_ID);
  assert.equal(readiness.model.preferredDefaultAvailable, false);
  assert.equal(runtime.turns.length, 0);
  await assert.rejects(
    () => broker.delegate({
      workspace,
      prompt: "This must not run on a 3.7 fallback.",
    }),
    (error) =>
      error instanceof BridgeError &&
      error.code === "MODEL_REQUIRED" &&
      /gemini-3\.8-flash-high/.test(error.message),
  );
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("substituted current model fails closed instead of accepting a fallback", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: { model: "gemini-3.1-pro", available: ["gemini-3.1-pro"] },
  });
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "This must not run.",
    }),
    (error) => error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("auth fallbacks and missing personal OAuth fail closed as setup/input", async () => {
  const { broker, workspace, geminiHome } = await makeBroker();
  broker.processEnv = { PATH: process.env.PATH ?? "", GEMINI_API_KEY: "placeholder" };
  await assert.rejects(
    () => broker.diagnoseAuth(),
    (error) => error instanceof BridgeError && error.code === "AUTH_FALLBACK_FORBIDDEN",
  );
  broker.processEnv = { PATH: process.env.PATH ?? "", GOOGLE_CLOUD_PROJECT: "placeholder" };
  await assert.rejects(
    () => broker.diagnoseAuth(),
    (error) => error instanceof BridgeError && error.code === "AUTH_FALLBACK_FORBIDDEN",
  );
  broker.processEnv = { PATH: process.env.PATH ?? "" };
  await writeFile(settingsPath(geminiHome), JSON.stringify({ auth: { type: "api-key" } }));
  await assert.rejects(
    () => broker.diagnoseAuth(),
    (error) => error instanceof BridgeError && error.code === "INPUT_REQUIRED",
  );
  const readiness = await broker.discover({ workspace });
  assert.equal(readiness.ready, false);
  assert.equal(readiness.error.code, "INPUT_REQUIRED");
  await broker.close();
});

test("authentication required during a session is needs-input, not invented login", async () => {
  const { broker, workspace } = await makeBroker({
    runtimeOptions: { failWith: "ensure" },
  });
  const readiness = await broker.discover({ workspace });
  assert.equal(readiness.ready, false);
  assert.equal(readiness.status, "needs-input");
  assert.equal(readiness.error.code, "INPUT_REQUIRED");
  await broker.close();
});

test("fixed-choice interaction questions cancel and never persist options", async () => {
  assert.equal(
    isInteractionQuestion({ raw: { toolCall: { toolCallId: "interaction_1" } } }),
    true,
  );
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: {
      delayMs: 20,
      permissionRequest: { raw: { toolCall: { toolCallId: "interaction_choose" } } },
    },
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Do not answer a hidden multiple-choice question.",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "needs-input");
  assert.equal(completed.question.outcome, "cancelled");
  assert.equal(completed.question.humanRequired, true);
  assert.equal(completed.cleanup.status, "completed");
  assert.equal(runtime.closed.length, 1);
  const rawState = await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8");
  assert.equal(rawState.includes("interaction_choose"), false);
  assert.equal(rawState.includes("\"options\""), false);
  await broker.close();
});

test("non-interaction write permission stays under pinned runtime policy", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: {
      delayMs: 20,
      permissionRequest: { raw: { toolCall: { toolCallId: "fs_write_file" } } },
    },
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Make a bounded implementation change with permission.",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(runtime.permissionDecisions.length, 1);
  assert.equal(runtime.permissionDecisions[0], undefined);
  await broker.close();
});

test("steering fails closed before starting an unowned queued turn", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: { delayMs: 100 },
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Hold the bounded turn briefly.",
  });
  await waitUntil(() => broker.active.get(submitted.jobId)?.turn);
  await assert.rejects(
    () => broker.steer({ jobId: submitted.jobId, message: "Continue the work." }),
    (error) => error instanceof BridgeError && error.code === "STEERING_UNSUPPORTED",
  );
  assert.equal(runtime.turns.length, 1);
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(runtime.turns.length, 1);
  await broker.close();
});

test("cancellation returns an explicit cancelled outcome", async () => {
  const { broker, workspace } = await makeBroker({
    runtimeOptions: { delayMs: 5_000 },
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Run a bounded long operation, then report.",
  });
  await waitUntil(() => broker.active.get(submitted.jobId)?.turn);
  const requested = await broker.cancel({ jobId: submitted.jobId, reason: "parent stopped the bounded task" });
  assert.equal(requested.status, "cancellation-requested");
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "cancelled");
  assert.equal(completed.complete, true);
  await broker.close();
});

test("safe summaries redact credentials and do not persist prompt bodies", async () => {
  assert.equal(redactSensitive("token=ghp_12345678901234567890"), "token=[redacted]");
  const { broker, workspace } = await makeBroker();
  const prompt = "Do not persist this unique prompt body 9f5e61d7.";
  const submitted = await broker.delegate({ workspace, model: FIXTURE_MODEL, prompt });
  const rawState = await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8");
  assert.equal(rawState.includes(prompt), false);
  assert.equal(rawState.includes("Do not persist"), false);
  await broker.close();
});

test("owner identity recovery fails closed when identity is incomplete or ambiguous", () => {
  const owner = { brokerId: "11111111-1111-4111-8111-111111111111", pid: 4242, startTime: "owner-start" };
  assert.equal(classifyOwnerIdentity({ pid: 4242 }, { status: "missing" }), "unknown");
  assert.equal(classifyOwnerIdentity(owner, { status: "unknown" }), "unknown");
  assert.equal(classifyOwnerIdentity(owner, { status: "missing" }), "dead");
  assert.equal(classifyOwnerIdentity(owner, { status: "alive", startTime: "other-start" }), "reused");
  assert.equal(classifyOwnerIdentity(owner, { status: "alive", startTime: owner.startTime }), "live");
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, { ...owner }, { status: "missing" }), true);
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, null, { status: "missing" }), false);
});

test("a live owner's in-flight job survives another broker and remains cancellable by its owner", async () => {
  const first = await makeBroker({ runtimeOptions: { delayMs: 5_000 } });
  const submitted = await first.broker.delegate({
    workspace: first.workspace,
    model: FIXTURE_MODEL,
    prompt: "Hold until the bridge restarts.",
  });
  await waitUntil(() => first.broker.active.get(submitted.jobId)?.turn);
  const secondRuntime = new FixtureRuntime();
  const second = new AntigravityAcpBroker({
    stateRoot: first.broker.stateRoot,
    runtimeDir: path.dirname(first.executable),
    geminiHome: first.geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    runtime: secondRuntime,
  });
  await second.init();
  const recovered = await second.result({ jobId: submitted.jobId });
  assert.equal(recovered.status, "running");
  assert.equal(recovered.error, undefined);
  const requested = await first.broker.cancel({ jobId: submitted.jobId, reason: "owner cancellation" });
  assert.equal(requested.status, "cancellation-requested");
  assert.equal((await first.broker.result({ jobId: submitted.jobId, waitMs: 1_000 })).status, "cancelled");
  await first.broker.close();
  await second.close();
});

test("a genuinely dead owner is recovered as a bridge restart", async () => {
  const first = await makeBroker({
    pid: 4242,
    startTime: "dead-owner-start",
    inspectProcess: async () => ({ status: "alive", startTime: "dead-owner-start" }),
    runtimeOptions: { delayMs: 5_000 },
  });
  const submitted = await first.broker.delegate({
    workspace: first.workspace,
    model: FIXTURE_MODEL,
    prompt: "Hold until the owning broker is proven dead.",
  });
  await waitUntil(() => first.broker.getJob(submitted.jobId).then((job) => job.status === "running"));
  const second = new AntigravityAcpBroker({
    stateRoot: first.broker.stateRoot,
    runtimeDir: path.dirname(first.executable),
    geminiHome: first.geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    pid: 5252,
    startTime: "replacement-start",
    inspectProcess: async (pid) => pid === 4242
      ? { status: "missing" }
      : { status: "alive", startTime: "replacement-start" },
    runtime: new FixtureRuntime(),
  });
  await second.init();
  const recovered = await second.result({ jobId: submitted.jobId });
  assert.equal(recovered.status, "failed");
  assert.equal(recovered.error.code, "BRIDGE_RESTARTED");
  assert.notEqual(recovered.cleanup?.status, "recovered");
  assert.equal(recovered.cleanupReady, false);
  assert.equal(recovered.complete, false);
  await first.broker.close();
  await second.close();
});

test("completed jobs close their persistent ACP session before cleanup", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const submitted = await broker.delegate({ workspace, model: FIXTURE_MODEL, prompt: "Complete and clean up." });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.cleanup.status, "completed");
  assert.equal(runtime.closed.length, 1);
  await broker.close();
});

test("result keeps task completion separate while terminal cleanup is pending", async () => {
  let releaseClose;
  const closeHold = new Promise((resolve) => { releaseClose = resolve; });
  const { broker, runtime, workspace } = await makeBroker({ runtimeOptions: { closeHold } });
  const submitted = await broker.delegate({ workspace, model: FIXTURE_MODEL, prompt: "Complete with delayed cleanup." });
  const completion = broker.active.get(submitted.jobId)?.promise;
  await waitUntil(() => runtime.closeStarted.length === 1);

  const pending = await broker.result({ jobId: submitted.jobId, waitMs: 20 });
  assert.equal(pending.status, "completed");
  assert.equal(pending.taskComplete, true);
  assert.equal(pending.cleanupReady, false);
  assert.equal(pending.complete, false);
  assert.equal(pending.waitExpired, true);
  assert.equal(pending.cleanup.status, "pending");
  assert.equal(runtime.closed.length, 0);

  releaseClose();
  await completion;
  const cleaned = await broker.result({ jobId: submitted.jobId, waitMs: 0 });
  assert.equal(cleaned.complete, true);
  assert.equal(cleaned.cleanupReady, true);
  assert.equal(cleaned.cleanup.status, "completed");
  await broker.close();
});

test("failed terminal cleanup fences replacement in one workspace but not another", async () => {
  const { broker, runtime, workspace, root } = await makeBroker({
    runtimeOptions: { closeError: "injected close failure" },
    defaultHostConversationId: null,
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Complete with failed cleanup.",
    hostConversationId: "conv-fenced-workspace",
  });
  const failedCleanup = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(failedCleanup.status, "completed");
  assert.equal(failedCleanup.taskComplete, true);
  assert.equal(failedCleanup.cleanupReady, false);
  assert.equal(failedCleanup.complete, false);
  assert.equal(failedCleanup.cleanup.status, "uncertain");
  assert.equal(broker.active.size, 0);
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "Do not replace an uncleared session.",
      hostConversationId: "conv-fenced-workspace",
    }),
    (error) => error instanceof BridgeError &&
      error.code === "WORKSPACE_CLEANUP_PENDING" &&
      error.details?.jobId === submitted.jobId,
  );

  const independentWorkspace = path.join(root, "independent-workspace");
  await mkdir(independentWorkspace);
  const independent = await broker.delegate({
    workspace: independentWorkspace,
    model: FIXTURE_MODEL,
    prompt: "Independent workspace remains admissible.",
    hostConversationId: "conv-independent-workspace",
  });
  const independentResult = await broker.result({ jobId: independent.jobId, waitMs: 1_000 });
  assert.equal(independentResult.status, "completed");
  await broker.close();
});

test("a second broker observes the shared cleanup fence while its owner remains live", async () => {
  const first = await makeBroker({
    runtimeOptions: { closeError: "injected close failure" },
    defaultHostConversationId: null,
  });
  const submitted = await first.broker.delegate({
    workspace: first.workspace,
    model: FIXTURE_MODEL,
    prompt: "Leave a cleanup fence for a second broker to observe.",
    hostConversationId: "conv-shared-fence",
  });
  const failedCleanup = await first.broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(failedCleanup.cleanup.status, "uncertain");

  const second = new AntigravityAcpBroker({
    stateRoot: first.broker.stateRoot,
    runtimeDir: path.dirname(first.executable),
    geminiHome: first.geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    runtime: new FixtureRuntime(),
    defaultHostConversationId: first.broker.defaultHostConversationId,
    defaultBinderId: first.broker.defaultBinderId,
  });
  await second.init();
  await assert.rejects(
    () => second.delegate({
      workspace: first.workspace,
      model: FIXTURE_MODEL,
      prompt: "Blocked by shared cleanup.",
      hostConversationId: "conv-shared-fence",
    }),
    (error) => error instanceof BridgeError && error.code === "WORKSPACE_CLEANUP_PENDING",
  );

  const independentWorkspace = path.join(first.root, "second-broker-independent");
  await mkdir(independentWorkspace);
  const independent = await second.delegate({
    workspace: independentWorkspace,
    model: FIXTURE_MODEL,
    prompt: "Run independently while another workspace is fenced.",
    hostConversationId: "conv-second-broker-independent",
  });
  const independentResult = await second.result({ jobId: independent.jobId, waitMs: 1_000 });
  assert.equal(independentResult.status, "completed");
  await first.broker.close();
  await second.close();
});

test("default runtime session store never writes conversation records to disk", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "antigravity-store-policy-"));
  const runtime = createDefaultRuntime({
    stateRoot: root,
    launch: { command: "/fixture/agy_acp_server.par", args: [], helper: "/fixture/localharness_external" },
    geminiHome: path.join(root, "gemini-home"),
    timeoutMs: 1000,
    processEnv: { PATH: "/usr/bin" },
  });
  const record = { acpxRecordId: "synthetic-session", title: "synthetic prompt", messages: [] };
  await runtime.options.sessionStore.save(record);
  assert.deepEqual(await readdir(root), []);
  const loaded = await runtime.options.sessionStore.load(record.acpxRecordId);
  assert.deepEqual(loaded, record);
  loaded.title = "changed copy";
  assert.equal((await runtime.options.sessionStore.load(record.acpxRecordId)).title, "synthetic prompt");
  const restarted = createDefaultRuntime({
    stateRoot: root,
    launch: { command: "/fixture/agy_acp_server.par", args: [], helper: "/fixture/localharness_external" },
    geminiHome: path.join(root, "gemini-home"),
    timeoutMs: 1000,
    processEnv: { PATH: "/usr/bin" },
  });
  assert.equal(await restarted.options.sessionStore.load(record.acpxRecordId), undefined);
  await runtime.shutdown();
  assert.equal(await runtime.options.sessionStore.load(record.acpxRecordId), undefined);
  await restarted.shutdown();
});

function unsupportedSessionCloseError() {
  const error = new Error("Agent does not support session/close for fixture-record.");
  error.code = "ACP_BACKEND_UNSUPPORTED_CONTROL";
  return error;
}

test("unsupported session/close is distinct from matched worker identity", () => {
  assert.equal(isUnsupportedBackendSessionClose(unsupportedSessionCloseError()), true);
  assert.equal(isUnsupportedBackendSessionClose(new Error("injected close failure")), false);
  assert.equal(
    isUnsupportedBackendSessionClose({
      code: "ACP_BACKEND_UNSUPPORTED_CONTROL",
      message: "ACP session does not advertise config option 'model'.",
    }),
    false,
  );
  const started = {
    launchId: "launch-1",
    scope: { kind: "runtime-session", sessionKey: "session-1" },
    pid: 4242,
    startedAt: "start-1",
  };
  assert.equal(processIdentitiesMatch(started, { ...started, signal: "SIGTERM" }), true);
  assert.equal(processIdentitiesMatch(started, { ...started, pid: 4343 }), false);
  assert.equal(processIdentitiesMatch(started, { ...started, startedAt: "other-start" }), false);
  assert.equal(
    processIdentitiesMatch(started, { ...started, scope: { kind: "runtime-session", sessionKey: "other" } }),
    false,
  );
});

test("unsupported session/close becomes cleanup-ready only after matched owned worker exit", async () => {
  const { broker, runtime, workspace } = await makeBroker({
    runtimeOptions: {
      closeError: unsupportedSessionCloseError(),
      emitWorkerExitOnClose: true,
    },
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Complete with unsupported session/close and observed worker exit.",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.taskComplete, true);
  assert.equal(completed.cleanupReady, true);
  assert.equal(completed.complete, true);
  assert.equal(completed.cleanup.status, "completed");
  assert.equal(
    completed.cleanup.observed,
    "local_worker_terminated_backend_session_discard_unsupported",
  );
  assert.equal(completed.cleanup.backendSessionDiscard, "unsupported");
  assert.equal(completed.cleanup.worker.pid, 4242);
  assert.equal(completed.cleanup.worker.startedAt, "fixture-worker-start");
  assert.equal(completed.cleanup.worker.launchId, runtime.started[0].launchId);
  assert.equal(completed.cleanup.message.includes("backend session discard unsupported"), true);
  const replacement = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Same workspace is admissible after observed local worker termination.",
  });
  const replaced = await broker.result({ jobId: replacement.jobId, waitMs: 1_000 });
  assert.equal(replaced.status, "completed");
  await broker.close();
});

test("unsupported session/close without owned worker-exit proof stays uncertain and fenced", async () => {
  const { broker, workspace } = await makeBroker({
    runtimeOptions: {
      closeError: unsupportedSessionCloseError(),
      emitWorkerExitOnClose: false,
    },
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Complete with unsupported session/close and a surviving worker.",
  });
  const failedCleanup = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(failedCleanup.status, "completed");
  assert.equal(failedCleanup.taskComplete, true);
  assert.equal(failedCleanup.cleanupReady, false);
  assert.equal(failedCleanup.complete, false);
  assert.equal(failedCleanup.cleanup.status, "uncertain");
  assert.equal(failedCleanup.cleanup.observed, "runtime_close_failed");
  await assert.rejects(
    () => broker.delegate({ workspace, model: FIXTURE_MODEL, prompt: "Stay fenced." }),
    (error) => error instanceof BridgeError && error.code === "WORKSPACE_CLEANUP_PENDING",
  );
  await broker.close();
});

test("readiness unsupported close waits for the owned probe worker without fencing workspaces", async () => {
  const { broker, runtime, workspace, root } = await makeBroker({
    runtimeOptions: {
      closeError: unsupportedSessionCloseError(),
      emitWorkerExitOnClose: true,
    },
  });
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(runtime.closeStarted.length, 1);
  assert.equal(broker.processLifecycleTracker.exits.length, 1);
  assert.equal(
    processIdentitiesMatch(runtime.started[0], broker.processLifecycleTracker.exits[0]),
    true,
  );
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "Readiness cleanup must not fence the same workspace.",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  const independentWorkspace = path.join(root, "readiness-independent");
  await mkdir(independentWorkspace);
  const independent = await broker.delegate({
    workspace: independentWorkspace,
    model: FIXTURE_MODEL,
    prompt: "Independent workspace remains admissible after readiness.",
  });
  const independentResult = await broker.result({ jobId: independent.jobId, waitMs: 1_000 });
  assert.equal(independentResult.status, "completed");
  await broker.close();
});
