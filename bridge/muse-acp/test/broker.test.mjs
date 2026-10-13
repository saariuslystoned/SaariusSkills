import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chmod, mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { randomUUID } from "node:crypto";
import {
  adapterProcessEnv,
  BridgeError,
  MuseAcpBroker,
  classifyOwnerIdentity,
  createDefaultRuntime,
  DEFAULT_MUSE_COMMAND,
  redactSensitive,
  resolveMuseExecutable,
  resolveRequestedMuseModel,
  shouldRecoverOwnedJob,
} from "../broker.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function runNode(source, env = process.env) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["--input-type=module", "-e", source], {
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (code, signal) => resolve({
      code,
      signal,
      stdout: Buffer.concat(stdout).toString("utf8"),
      stderr: Buffer.concat(stderr).toString("utf8"),
    }));
  });
}

class FixtureRuntime {
  constructor({
    model = FIXTURE_MODEL,
    available = fixtureCatalog.availableModelIds,
    delayMs = 10,
    permissionRequest = null,
  } = {}) {
    this.model = model;
    this.available = available;
    this.delayMs = delayMs;
    this.permissionRequest = permissionRequest;
    this.ensureCalls = [];
    this.turns = [];
    this.closed = [];
    this.permissionDecisions = [];
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
      details: {
        configOptions: [{
          id: "reasoning_effort",
          category: "thought_level",
          type: "select",
          currentValue: this.reasoningEffort ?? "xhigh",
          options: ["xhigh", "high", "medium", "low"].map((value) => ({ value, name: value })),
        }],
      },
    };
  }

  async setModel({ model }) {
    if (this.available.includes(model)) this.model = model;
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
      promptStarted: Promise.resolve(),
      events: (async function* () {
        yield { type: "status", tag: "session_info_update", text: "fixture" };
        if (input.mode === "prompt") {
          await sleep(5);
          yield {
            type: "text_delta",
            stream: "output",
            text: "Changed files: bridge/muse-acp/broker.mjs\nTests: fixture pass",
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
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-muse-acp-test-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "muse");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const runtime = options.runtime ?? new FixtureRuntime(options.runtimeOptions);
  const broker = new MuseAcpBroker({
    stateRoot: path.join(root, "state"),
    museExecutable: executable,
    runtime,
    execFile: async (_exe, args) => ({ stdout: args?.includes("serve") ? "muse serve \u2014 serve an MSP session host over stdio\n" : "2026.08.11-e8db854\n", stderr: "" }),
    // Hermetic policy env: the runner's own SAARIUS_ACP_PERMISSION_MODE must
    // not leak into readiness or receipt assertions (see #92). Everything else
    // stays so spawned helper processes keep HOME, TMPDIR and friends.
    processEnv: hermeticProcessEnv(),
    defaultHostConversationId: options.defaultHostConversationId ?? `conv-${path.basename(root)}`,
    defaultBinderId: options.defaultBinderId ?? "test-owner",
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

test("readiness reports the resolved permission mode and warns on approve-reads (#92)", async () => {
  const everyday = await makeBroker();
  const report = await everyday.broker.discover({ workspace: everyday.workspace });
  assert.equal(report.ready, true);
  assert.equal(report.permission.permissionMode, "approve-reads");
  assert.deepEqual(report.permission.supportedModes, ["approve-reads", "approve-all"]);
  assert.deepEqual(report.permission.toolApproval, { read: true, write: false, exec: false });
  assert.equal(report.permission.breakGlass, false);
  assert.equal(report.permission.source, "default");
  assert.match(report.permission.warning, /PERMISSION_PROMPT_UNAVAILABLE/);
  await everyday.broker.close();

  const glass = await makeBroker({ processEnv: { PATH: process.env.PATH ?? "", SAARIUS_ACP_PERMISSION_MODE: "approve-all" } });
  const glassReport = await glass.broker.discover({ workspace: glass.workspace });
  assert.equal(glassReport.ready, true);
  assert.equal(glassReport.permission.permissionMode, "approve-all");
  assert.equal(glassReport.permission.breakGlass, true);
  assert.equal(glassReport.permission.source, "SAARIUS_ACP_PERMISSION_MODE");
  assert.equal(glassReport.permission.warning, undefined);
  const glassJob = await glass.broker.delegate({ workspace: glass.workspace, prompt: "Write one bounded file and report." });
  assert.equal(glassJob.permission.permissionMode, "approve-all");
  assert.deepEqual(glassJob.permission, glassReport.permission);
  assert.equal(glassJob.permission.breakGlass, true);
  assert.equal(glassJob.permission.source, "SAARIUS_ACP_PERMISSION_MODE");
  assert.equal(glassJob.permission.warning, undefined);
  const glassDone = await glass.broker.result({ jobId: glassJob.jobId, waitMs: 1_000 });
  assert.equal(glassDone.status, "completed");
  assert.equal(glassDone.permission.permissionMode, "approve-all");
  await glass.broker.close();
});

test("readiness proves the exact advertised Muse model without a turn", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(report.model.selectedModelId, FIXTURE_MODEL);
  assert.equal(report.model.availableModelCount, fixtureCatalog.availableModelIds.length);
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.ensureCalls[0].mode, "oneshot");
  await broker.close();
});

test("MUSE_EXECUTABLE or PATH muse is resolved without a machine-specific default", () => {
  const configured = resolveMuseExecutable({ museExecutable: "/tmp/explicit-muse", env: { PATH: "" } });
  assert.equal(configured, path.resolve("/tmp/explicit-muse"));
  const fromEnv = resolveMuseExecutable({ env: { MUSE_EXECUTABLE: "/tmp/env-muse", PATH: "" } });
  assert.equal(fromEnv, path.resolve("/tmp/env-muse"));
  const missing = resolveMuseExecutable({ env: { PATH: "/tmp/empty-muse-path" } });
  assert.equal(missing, "muse");
  assert.equal(missing.includes("/Users/"), false);
});

test("PATH muse resolution accepts only executable regular files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-muse-path-"));
  const command = process.platform === "win32" ? "muse.exe" : DEFAULT_MUSE_COMMAND;
  try {
    const validDir = path.join(root, "valid");
    const blockedFileDir = path.join(root, "blocked-file");
    const blockedDirDir = path.join(root, "blocked-dir");
    const laterDir = path.join(root, "later");
    await mkdir(validDir);
    await mkdir(blockedFileDir);
    await mkdir(blockedDirDir);
    await mkdir(laterDir);

    const valid = path.join(validDir, command);
    const later = path.join(laterDir, command);
    await writeFile(valid, "#!/bin/sh\nexit 0\n", { mode: 0o755 });
    await chmod(valid, 0o755);
    await writeFile(later, "#!/bin/sh\nexit 0\n", { mode: 0o755 });
    await chmod(later, 0o755);
    await writeFile(path.join(blockedFileDir, command), "not executable\n", { mode: 0o644 });
    await chmod(path.join(blockedFileDir, command), 0o644);
    await mkdir(path.join(blockedDirDir, command));

    assert.equal(resolveMuseExecutable({ env: { PATH: validDir } }), valid);
    assert.equal(
      resolveMuseExecutable({
        env: { PATH: [blockedFileDir, laterDir].join(path.delimiter) },
      }),
      later,
    );
    assert.equal(
      resolveMuseExecutable({
        env: { PATH: [blockedDirDir, laterDir].join(path.delimiter) },
      }),
      later,
    );

    const explicitMissing = path.join(root, "explicit-missing-muse");
    assert.equal(
      resolveMuseExecutable({
        env: { MUSE_EXECUTABLE: explicitMissing, PATH: validDir },
      }),
      path.resolve(explicitMissing),
    );
    assert.equal(
      resolveMuseExecutable({
        museExecutable: explicitMissing,
        env: { PATH: validDir },
      }),
      path.resolve(explicitMissing),
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("exact requested model is accepted only when advertised", () => {
  assert.equal(
    resolveRequestedMuseModel("fixture-c", ["fixture-c", "fixture-b"]),
    "fixture-c",
  );
  assert.throws(
    () => resolveRequestedMuseModel("fixture-c", ["fixture-b"]),
    (error) => error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE",
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
  assert.equal(submitted.permission.permissionMode, "approve-reads");
  assert.equal(submitted.permission.breakGlass, false);
  assert.equal(submitted.permission.source, "default");
  assert.match(submitted.permission.warning, /PERMISSION_PROMPT_UNAVAILABLE/);
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.complete, true);
  assert.equal(completed.permission.permissionMode, "approve-reads");
  assert.match(completed.handoff, /Changed files/);
  assert.equal(runtime.ensureCalls[0].cwd, workspace);
  assert.equal(runtime.ensureCalls[0].sessionOptions.model, undefined);
  assert.equal(runtime.turns[0].input.mode, "prompt");
  assert.notEqual(path.dirname(completed.proof.proof), workspace);
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
  const submitted = await broker.delegate({ workspace, prompt: "Hold the bounded turn briefly." });
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
  const { broker, runtime, workspace } = await makeBroker({
    model: "fixture-c",
    runtimeOptions: { available: ["fixture-b"], model: "fixture-b" },
  });
  await assert.rejects(
    () => broker.delegate({ workspace, prompt: "This must not run." }),
    (error) => error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(runtime.turns.length, 0);
  assert.equal(broker.model, "fixture-c");
  await broker.close();
});

test("missing Muse executable is an actionable preflight error", async () => {
  const { broker, workspace } = await makeBroker();
  broker.museExecutable = path.join(path.dirname(broker.museExecutable), "missing-muse");
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

test("owner identity classification recovers proven PID reuse and fails safe on ambiguous identity", () => {
  const owner = { brokerId: "11111111-1111-4111-8111-111111111111", pid: 4242, startTime: "ps-utc-v1:2020-01-01T03:03:15.000Z" };
  const lease = { ...owner };
  assert.equal(classifyOwnerIdentity(undefined, { status: "missing" }), "unknown");
  assert.equal(classifyOwnerIdentity({ pid: 4242 }, { status: "missing" }), "unknown");
  assert.equal(classifyOwnerIdentity({ brokerId: owner.brokerId, pid: 4242 }, { status: "missing" }), "unknown");
  assert.equal(classifyOwnerIdentity(owner, { status: "unknown" }), "unknown");
  assert.equal(classifyOwnerIdentity(owner, { status: "alive" }), "unknown");
  assert.equal(classifyOwnerIdentity({ ...owner, startTime: "" }, { status: "alive", startTime: owner.startTime }), "unknown");
  assert.equal(classifyOwnerIdentity(owner, { status: "missing" }), "dead");
  assert.equal(classifyOwnerIdentity(owner, { status: "alive", startTime: "ps-utc-v1:2020-01-01T08:28:51.000Z" }), "reused");
  assert.equal(classifyOwnerIdentity(owner, { status: "alive", startTime: owner.startTime }), "live");
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, lease, { status: "missing" }), true);
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, lease, { status: "alive", startTime: "ps-utc-v1:2020-01-01T08:28:51.000Z" }), true);
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, lease, { status: "alive" }), false);
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, lease, { status: "unknown" }), false);
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, null, { status: "missing" }), false);
  assert.equal(shouldRecoverOwnedJob({ status: "running", owner }, { ...owner, startTime: "ps-utc-v1:2020-01-01T17:19:06.000Z" }, { status: "missing" }), false);
  assert.equal(shouldRecoverOwnedJob({ status: "completed", owner }, lease, { status: "missing" }), false);
  assert.equal(
    shouldRecoverOwnedJob(
      { status: "running", owner: { brokerId: owner.brokerId, pid: 4242 } },
      { brokerId: owner.brokerId, pid: 4242 },
      { status: "missing" },
    ),
    false,
  );
});

test("a live owner's in-flight job is preserved when another broker initializes", async () => {
  const first = await makeBroker({ runtimeOptions: { delayMs: 5_000 } });
  const submitted = await first.broker.delegate({ workspace: first.workspace, prompt: "Hold while a second broker starts." });
  await waitUntil(() => first.broker.getJob(submitted.jobId).then((job) => job.status === "running"));
  const secondRuntime = new FixtureRuntime();
  const second = new MuseAcpBroker({
    stateRoot: first.broker.stateRoot,
    museExecutable: first.executable,
    runtime: secondRuntime,
    execFile: async (_exe, args) => ({ stdout: args?.includes("serve") ? "muse serve \u2014 serve an MSP session host over stdio\n" : "2026.08.11-e8db854\n", stderr: "" }),
  });
  await second.init();
  const readiness = await second.discover({ workspace: first.workspace });
  assert.equal(readiness.ready, true);
  const observed = await second.result({ jobId: submitted.jobId });
  assert.equal(observed.status, "running");
  assert.equal(observed.error, undefined);
  const raw = JSON.parse(await readFile(path.join(first.broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(raw.owner.brokerId, first.broker.brokerId);
  await first.broker.close();
  await second.close();
});

test("readiness during a live job does not recover it as a restarted job", async () => {
  const { broker, workspace } = await makeBroker({ runtimeOptions: { delayMs: 200 } });
  try {
    const submitted = await broker.delegate({ workspace, prompt: "Keep working while readiness is checked." });
    await waitUntil(() => broker.active.get(submitted.jobId)?.turn);
    await broker.discover({ workspace });
    const status = await broker.status({ jobId: submitted.jobId });
    assert.equal(status.status, "running");
    assert.equal(status.error, undefined);
    assert.equal((await broker.result({ jobId: submitted.jobId, waitMs: 1000 })).status, "completed");
  } finally {
    await broker.close();
  }
});


test("default runtime session store never writes conversation records to disk", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "cursor-store-policy-"));
  const runtime = createDefaultRuntime({ stateRoot: root, museExecutable: "/fixture/muse", timeoutMs: 1000 });
  const record = { acpxRecordId: "synthetic-session", title: "synthetic prompt", messages: [] };
  await runtime.options.sessionStore.save(record);
  assert.deepEqual(await readdir(root), []);
  const loaded = await runtime.options.sessionStore.load(record.acpxRecordId);
  assert.deepEqual(loaded, record);
  loaded.title = "changed copy";
  assert.equal((await runtime.options.sessionStore.load(record.acpxRecordId)).title, "synthetic prompt");
  const restarted = createDefaultRuntime({ stateRoot: root, museExecutable: "/fixture/muse", timeoutMs: 1000 });
  assert.equal(await restarted.options.sessionStore.load(record.acpxRecordId), undefined);
  await runtime.shutdown();
  assert.equal(await runtime.options.sessionStore.load(record.acpxRecordId), undefined);
  await restarted.shutdown();
});

test("adapter env overlay forwards only allowlisted adapter knobs", () => {
  const overlay = adapterProcessEnv({
    MUSE_EXECUTABLE: "/opt/muse",
    MUSE_AGENT_ACP_PROVIDER: "echo",
    MUSE_AGENT_ACP_SERVE_ARGS: "[\"--no-session-log\"]",
    XDG_CONFIG_HOME: "/tmp/cfg",
    XAI_API_KEY: "synthetic-xai-sentinel",
    SOME_OTHER_SECRET: "synthetic-secret-sentinel",
    PATH: "/usr/bin",
  });
  assert.deepEqual(overlay, {
    MUSE_EXECUTABLE: "/opt/muse",
    MUSE_AGENT_ACP_PROVIDER: "echo",
    MUSE_AGENT_ACP_SERVE_ARGS: "[\"--no-session-log\"]",
    XDG_CONFIG_HOME: "/tmp/cfg",
  });
  assert.doesNotMatch(JSON.stringify(overlay), /synthetic/);
  assert.deepEqual(adapterProcessEnv({}), {});
  assert.deepEqual(adapterProcessEnv({ MUSE_EXECUTABLE: "  " }), {});
});

test("pinned acpx runtime drives the real adapter into a fake MSP host with broker env knobs", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-muse-env-"));
  const observedPath = path.join(root, "observed.json");
  const brokerModule = new URL("../broker.mjs", import.meta.url).href;
  const fakeMsp = new URL("../../muse-agent-acp/test/fake-msp.mjs", import.meta.url).href;
  // Fake `muse` binary: records the env the adapter spawned it with, then
  // serves MSP so the ACP initialize/session handshake completes.
  const wrapper = `#!${process.execPath}
import { writeFileSync } from "node:fs";
writeFileSync(${JSON.stringify(observedPath)}, JSON.stringify({
  provider: process.env.MUSE_AGENT_ACP_PROVIDER ?? null,
  serveArgv: process.argv.slice(2),
}));
await import(${JSON.stringify(fakeMsp)});
`;
  const scenario = `
    import { chmod, mkdtemp, writeFile } from "node:fs/promises";
    import os from "node:os";
    import path from "node:path";
    import { createDefaultRuntime } from ${JSON.stringify(brokerModule)};
    const root = await mkdtemp(path.join(os.tmpdir(), "saarius-muse-runtime-"));
    const executable = path.join(root, "muse");
    await writeFile(executable, ${JSON.stringify(wrapper)}, { mode: 0o700 });
    await chmod(executable, 0o700);
    const runtime = createDefaultRuntime({
      stateRoot: path.join(root, "state"),
      museExecutable: executable,
      timeoutMs: 30_000,
      processEnv: { ...process.env, MUSE_EXECUTABLE: executable, MUSE_AGENT_ACP_PROVIDER: "echo" },
    });
    const handle = await runtime.ensureSession({
      sessionKey: "synthetic-muse-env",
      agent: "muse",
      mode: "persistent",
      cwd: root,
    });
    await runtime.close({ handle, reason: "synthetic-env-complete", discardPersistentState: true });
    await runtime.shutdown();
  `;
  const sanitizedEnv = Object.fromEntries(
    Object.entries(process.env).filter(([key]) => !["MUSE_EXECUTABLE", "MUSE_AGENT_ACP_PROVIDER"].includes(key)),
  );
  try {
    const result = await runNode(scenario, sanitizedEnv);
    assert.equal(result.code, 0, result.stderr);
    const observed = JSON.parse(await readFile(observedPath, "utf8"));
    assert.equal(observed.provider, "echo");
    assert.deepEqual(observed.serveArgv, ["serve", "--provider", "echo"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
