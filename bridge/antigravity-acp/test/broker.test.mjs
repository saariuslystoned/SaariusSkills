import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  AntigravityAcpBroker,
  BridgeError,
  createDefaultRuntime,
  isInteractionQuestion,
  redactSensitive,
  resolveRequestedAntigravityModel,
} from "../broker.mjs";
import { currentPlatformId, defaultRuntimeDir, platformLaunch, settingsPath } from "../contract.mjs";

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
  } = {}) {
    this.model = model;
    this.available = available;
    this.delayMs = delayMs;
    this.failWith = failWith;
    this.permissionRequest = permissionRequest;
    this.permissionDecisions = [];
    this.ensureCalls = [];
    this.turns = [];
    this.closed = [];
  }

  async ensureSession(input) {
    this.ensureCalls.push(input);
    if (this.failWith === "ensure") {
      throw new BridgeError("AUTHENTICATION_REQUIRED", "Authentication required");
    }
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
        const decision = await input.onPermissionRequest(this.permissionRequest);
        this.permissionDecisions.push(decision);
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
  const runtime = options.runtime ?? new FixtureRuntime(options.runtimeOptions);
  const broker = new AntigravityAcpBroker({
    stateRoot: path.join(root, "state"),
    runtimeDir,
    geminiHome,
    processEnv: { PATH: process.env.PATH ?? "" },
    runtime,
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
  assert.equal(report.pin.acpxRelease, "0.17.1");
  assert.equal(report.model.availableModelCount, fixtureCatalog.availableModelIds.length);
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
    () => broker.delegate({ workspace: broker.defaultWorkspace, prompt: "no" }),
    (error) => error instanceof BridgeError && error.code === "MODEL_REQUIRED",
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

test("substituted current model fails closed instead of accepting a fallback", async () => {
  const { broker, workspace } = await makeBroker({
    runtimeOptions: { model: "gemini-3.1-pro", available: ["gemini-3.1-pro"] },
  });
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "This must not run.",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_UNAVAILABLE");
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
  const { broker, workspace } = await makeBroker({
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
  const rawState = await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8");
  assert.equal(rawState.includes("interaction_choose"), false);
  assert.equal(rawState.includes("\"options\""), false);
  await broker.close();
});

test("non-interaction permission requests delegate and record allow_once", async () => {
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
  assert.equal(completed.complete, true);
  assert.equal(runtime.permissionDecisions.length, 1);
  assert.equal(runtime.permissionDecisions[0]?.outcome, "allow_once");
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

test("a bridge restart fails a persisted in-flight job closed distinctly", async () => {
  const first = await makeBroker({ runtimeOptions: { delayMs: 5_000 } });
  const submitted = await first.broker.delegate({
    workspace: first.workspace,
    model: FIXTURE_MODEL,
    prompt: "Hold until the bridge restarts.",
  });
  await waitUntil(() => first.broker.getJob(submitted.jobId).then((job) => job.status === "running"));
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
  assert.equal(recovered.status, "failed");
  assert.equal(recovered.error.code, "BRIDGE_RESTARTED");
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
