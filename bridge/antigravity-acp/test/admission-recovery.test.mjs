import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { AntigravityAcpBroker, BridgeError, createProcessLifecycleTracker } from "../broker.mjs";
import {
  ADMISSION_STATE_RELEASED,
  ADMISSION_STATE_STARTED,
  ADMISSION_STATE_UNSTARTED,
  CONVERSATION_BIND_SCHEMA,
  conversationBindPath,
} from "../host-policy.mjs";
import { currentPlatformId, platformLaunch, settingsPath } from "../contract.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;
const DEAD_PID = 8_888_888;
const FIRST_JOB = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SECOND_JOB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

class Runtime {
  constructor({ failEnsure = false } = {}) {
    this.failEnsure = failEnsure;
    this.ensureCalls = [];
    this.turns = [];
    this.closed = [];
    this.model = FIXTURE_MODEL;
    this.available = fixtureCatalog.availableModelIds;
  }
  async ensureSession(input) {
    this.ensureCalls.push(input);
    if (this.failEnsure) throw new BridgeError("RUNTIME_MISSING", "runtime missing");
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

async function harness(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-agy-admission-"));
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
  const runtime = new Runtime(options.runtimeOptions);
  const ids = options.jobIds ?? [];
  let nextId = 0;
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
    brokerId: options.brokerId,
    pid: options.pid,
    startTime: options.startTime,
    inspectProcess: options.inspectProcess,
    onAdmissionBoundary: options.onAdmissionBoundary,
    idFactory: options.jobIds
      ? () => ids[nextId++] ?? ids.at(-1)
      : undefined,
  });
  await broker.init();
  return { broker, runtime, workspace, root };
}

async function readJob(broker, jobId) {
  return JSON.parse(await readFile(path.join(broker.jobsRoot, `${jobId}.json`), "utf8"));
}

async function readBind(broker, conversationId) {
  return JSON.parse(await readFile(conversationBindPath(broker.bindingsRoot, conversationId), "utf8"));
}

async function writeCrashAdmission(broker, {
  jobId,
  hostConversationId,
  workspace,
  owner,
  admissionState = ADMISSION_STATE_UNSTARTED,
  status = "admitted",
  handle,
}) {
  await mkdir(broker.jobsRoot, { recursive: true, mode: 0o700 });
  await mkdir(broker.bindingsRoot, { recursive: true, mode: 0o700 });
  const runDir = path.join(broker.runsRoot, jobId);
  await mkdir(runDir, { recursive: true, mode: 0o700 });
  const job = {
    schema: "saarius.antigravity-acp.job.v1",
    jobId,
    status,
    createdAt: "2026-09-24T00:00:00.000Z",
    updatedAt: "2026-09-24T00:00:00.000Z",
    route: { agent: "antigravity", transport: "acp", model: null },
    workspace,
    owner,
    admission: {
      state: admissionState,
      hostConversationId,
      binderId: "owner-a",
    },
    request: { promptSha256: "synthetic", promptChars: 9 },
    sessionKey: `antigravity-acp:${jobId}`,
    runDir,
    proof: {
      state: path.join(runDir, "STATE.md"),
      events: path.join(runDir, "events.jsonl"),
      proof: path.join(runDir, "PROOF.md"),
    },
  };
  if (handle) job.handle = handle;
  await writeFile(path.join(broker.jobsRoot, `${jobId}.json`), `${JSON.stringify(job, null, 2)}\n`);
  await writeFile(
    conversationBindPath(broker.bindingsRoot, hostConversationId),
    `${JSON.stringify({
      schema: CONVERSATION_BIND_SCHEMA,
      hostConversationId,
      binderId: "owner-a",
      jobId,
      workspace,
      boundAt: "2026-09-24T00:00:00.000Z",
    }, null, 2)}\n`,
  );
  return job;
}

test("injected failure after bind leaves a readable released job the same owner can replace", async () => {
  let injected = false;
  const { broker, workspace } = await harness({
    jobIds: [FIRST_JOB, SECOND_JOB],
    onAdmissionBoundary: async (phase) => {
      if (phase === "bound" && !injected) {
        injected = true;
        throw new BridgeError("INJECTED_PERSISTENCE_FAILURE", "injected bind/job boundary");
      }
    },
  });
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "first admission",
      hostConversationId: "conv-boundary",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "INJECTED_PERSISTENCE_FAILURE",
  );
  const failed = await readJob(broker, FIRST_JOB);
  const bind = await readBind(broker, "conv-boundary");
  assert.equal(bind.jobId, FIRST_JOB);
  assert.equal(failed.admission.state, ADMISSION_STATE_RELEASED);
  assert.equal(failed.status, "failed");
  assert.equal(failed.owner.brokerId, broker.brokerId);
  assert.ok(failed.owner.pid > 0);
  assert.ok(failed.owner.startTime);
  const rebound = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "recover released admission",
    hostConversationId: "conv-boundary",
    binderId: "owner-a",
  });
  assert.equal(rebound.jobId, SECOND_JOB);
  assert.equal(rebound.binding.replacedJobId, FIRST_JOB);
  await broker.close();
});

test("injected failure before bind leaves an unbound released job and a free conversation", async () => {
  let injected = false;
  const { broker, workspace } = await harness({
    jobIds: [FIRST_JOB, SECOND_JOB],
    onAdmissionBoundary: async (phase) => {
      if (phase === "unstarted" && !injected) {
        injected = true;
        throw new BridgeError("INJECTED_PERSISTENCE_FAILURE", "injected before bind");
      }
    },
  });
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "first admission",
      hostConversationId: "conv-prebind",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "INJECTED_PERSISTENCE_FAILURE",
  );
  const failed = await readJob(broker, FIRST_JOB);
  assert.equal(failed.admission.state, ADMISSION_STATE_RELEASED);
  await assert.rejects(() => readBind(broker, "conv-prebind"), (error) => error?.code === "ENOENT");
  const submitted = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "conversation still free",
    hostConversationId: "conv-prebind",
    binderId: "owner-a",
  });
  assert.equal(submitted.jobId, SECOND_JOB);
  await broker.close();
});

test("crash after bind with a dead owner is recoverable; live and unobservable owners stay fenced", async () => {
  const deadOwner = { brokerId: "dead-owner", pid: DEAD_PID, startTime: "old-start" };
  const { broker, workspace } = await harness({
    inspectProcess: async (pid) => {
      if (pid === DEAD_PID) return { status: "missing" };
      return { status: "alive", startTime: "live-start" };
    },
  });
  await writeCrashAdmission(broker, {
    jobId: FIRST_JOB,
    hostConversationId: "conv-crash",
    workspace,
    owner: deadOwner,
    admissionState: ADMISSION_STATE_UNSTARTED,
  });
  const recovered = await broker.delegate({
    workspace,
    model: FIXTURE_MODEL,
    prompt: "recover unstarted dead owner",
    hostConversationId: "conv-crash",
    binderId: "owner-a",
  });
  assert.equal(recovered.binding.replacedJobId, FIRST_JOB);
  await broker.result({ jobId: recovered.jobId, waitMs: 1_000 });

  await writeCrashAdmission(broker, {
    jobId: SECOND_JOB,
    hostConversationId: "conv-live",
    workspace,
    owner: broker.ownerIdentity(),
    admissionState: ADMISSION_STATE_UNSTARTED,
  });
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "do not steal in-progress admission",
      hostConversationId: "conv-live",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError &&
      error.code === "CONVERSATION_REBIND_UNSAFE" &&
      error.details?.reason === "previous_admission_in_progress",
  );

  const unknownBroker = await harness({
    inspectProcess: async () => ({ status: "unknown" }),
  });
  await writeCrashAdmission(unknownBroker.broker, {
    jobId: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    hostConversationId: "conv-unknown",
    workspace: unknownBroker.workspace,
    owner: { brokerId: "opaque-owner", pid: 7_777_777, startTime: "opaque-start" },
    admissionState: ADMISSION_STATE_UNSTARTED,
  });
  await assert.rejects(
    () => unknownBroker.broker.delegate({
      workspace: unknownBroker.workspace,
      model: FIXTURE_MODEL,
      prompt: "do not guess an unobservable owner",
      hostConversationId: "conv-unknown",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError &&
      error.code === "CONVERSATION_REBIND_UNSAFE" &&
      error.details?.reason === "previous_admission_owner_unobservable",
  );
  await broker.close();
  await unknownBroker.broker.close();
});

test("started or unreadable previous jobs stay fenced", async () => {
  const deadOwner = { brokerId: "dead-owner", pid: DEAD_PID, startTime: "old-start" };
  const { broker, workspace } = await harness({
    inspectProcess: async (pid) => {
      if (pid === DEAD_PID) return { status: "missing" };
      return { status: "alive", startTime: "live-start" };
    },
  });
  await writeCrashAdmission(broker, {
    jobId: FIRST_JOB,
    hostConversationId: "conv-started",
    workspace,
    owner: deadOwner,
    admissionState: ADMISSION_STATE_STARTED,
    status: "submitted",
    handle: { sessionKey: "antigravity-acp:surviving", backend: "fixture" },
  });
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "do not replace a surviving worker",
      hostConversationId: "conv-started",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError &&
      error.code === "CONVERSATION_REBIND_UNSAFE" &&
      error.details?.reason === "previous_job_nonterminal",
  );

  await mkdir(broker.bindingsRoot, { recursive: true, mode: 0o700 });
  await writeFile(
    conversationBindPath(broker.bindingsRoot, "conv-missing"),
    `${JSON.stringify({
      schema: CONVERSATION_BIND_SCHEMA,
      hostConversationId: "conv-missing",
      binderId: "owner-a",
      jobId: SECOND_JOB,
      workspace,
      boundAt: "2026-09-24T00:00:00.000Z",
    }, null, 2)}\n`,
  );
  await assert.rejects(
    () => broker.delegate({
      workspace,
      model: FIXTURE_MODEL,
      prompt: "do not guess a missing job",
      hostConversationId: "conv-missing",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError &&
      error.code === "CONVERSATION_REBIND_UNSAFE" &&
      error.details?.reason === "previous_job_unreadable",
  );
  await broker.close();
});
