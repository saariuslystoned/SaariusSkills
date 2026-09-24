import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { BridgeError, CursorAcpBroker } from "../broker.mjs";
import {
  ADMISSION_STATE_RELEASED,
  ADMISSION_STATE_STARTING,
  ADMISSION_STATE_STARTED,
  ADMISSION_STATE_UNSTARTED,
  CONVERSATION_BIND_SCHEMA,
  conversationBindPath,
} from "../host-policy.mjs";

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
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-cursor-admission-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "cursor-agent");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const runtime = options.runtime ?? new Runtime(options.runtimeOptions);
  const ids = options.jobIds ?? [];
  let nextId = 0;
  const broker = new CursorAcpBroker({
    stateRoot: path.join(root, "state"),
    cursorExecutable: executable,
    runtime,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    processEnv: options.processEnv ?? { PATH: process.env.PATH ?? "" },
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
    schema: "saarius.cursor-acp.job.v1",
    jobId,
    status,
    createdAt: "2026-09-24T00:00:00.000Z",
    updatedAt: "2026-09-24T00:00:00.000Z",
    route: { agent: "cursor", transport: "acp", executable: "synthetic", argv: ["synthetic"], model: "synthetic" },
    workspace,
    owner,
    admission: {
      state: admissionState,
      hostConversationId,
      binderId: "owner-a",
    },
    request: { promptSha256: "synthetic", promptChars: 9 },
    sessionKey: `cursor-acp:${jobId}`,
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
    handle: { sessionKey: "cursor-acp:surviving", backend: "fixture" },
  });
  await assert.rejects(
    () => broker.delegate({
      workspace,
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

test("worker startup intent is durable before ensureSession and fences unknown startup after restart", async () => {
  const runtime = new Runtime();
  let broker;
  let observed;
  runtime.ensureSession = async () => {
    observed = await readJob(broker, FIRST_JOB);
    throw new BridgeError("RUNTIME_START_FAILED", "simulated failure after startup side effect");
  };
  const h = await harness({ runtime, jobIds: [FIRST_JOB] });
  broker = h.broker;
  await assert.rejects(
    () => broker.delegate({
      workspace: h.workspace,
      prompt: "startup intent",
      hostConversationId: "conv-starting",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "RUNTIME_START_FAILED",
  );
  assert.equal(observed.admission.state, ADMISSION_STATE_STARTING);
  assert.equal(runtime.closed.length, 0);
  const failed = await readJob(broker, FIRST_JOB);
  assert.equal(failed.admission.state, ADMISSION_STATE_STARTING);
  assert.equal(failed.status, "admitted");
  assert.equal(failed.error.code, "RUNTIME_START_FAILED");
  await assert.rejects(
    () => broker.bindConversation({
      hostConversationId: "conv-starting",
      binderId: "owner-a",
      jobId: SECOND_JOB,
      workspace: h.workspace,
    }),
    (error) => error instanceof BridgeError &&
      error.code === "CONVERSATION_REBIND_UNSAFE" &&
      error.details?.reason === "previous_job_nonterminal",
  );

  const deadOwner = { brokerId: "dead-owner", pid: DEAD_PID, startTime: "old-start" };
  const restarted = await writeCrashAdmission(broker, {
    jobId: SECOND_JOB,
    hostConversationId: "conv-restarted-starting",
    workspace: h.workspace,
    owner: deadOwner,
    admissionState: ADMISSION_STATE_STARTING,
    status: "failed",
  });
  restarted.error = { code: "BRIDGE_RESTARTED", message: "owner disappeared during startup" };
  await writeFile(
    path.join(broker.jobsRoot, `${SECOND_JOB}.json`),
    `${JSON.stringify(restarted, null, 2)}\n`,
  );
  await assert.rejects(
    () => broker.bindConversation({
      hostConversationId: "conv-restarted-starting",
      binderId: "owner-a",
      jobId: FIRST_JOB,
      workspace: h.workspace,
    }),
    (error) => error instanceof BridgeError &&
      error.code === "WORKSPACE_CLEANUP_PENDING" &&
      error.details?.reason === "previous_job_cleanup_unproven",
  );
  await broker.close();
});

test("BRIDGE_RESTARTED with an unknown worker handle stays fenced until cleanup is recorded", async () => {
  const { broker, workspace } = await harness({
    inspectProcess: async (pid) => pid === DEAD_PID ? { status: "missing" } : { status: "alive", startTime: "live-start" },
  });
  const restarted = await writeCrashAdmission(broker, {
    jobId: FIRST_JOB,
    hostConversationId: "conv-restarted-handle",
    workspace,
    owner: { brokerId: "dead-owner", pid: DEAD_PID, startTime: "old-start" },
    admissionState: ADMISSION_STATE_STARTED,
    status: "failed",
    handle: { sessionKey: "cursor-acp:unknown", backend: "fixture" },
  });
  restarted.error = { code: "BRIDGE_RESTARTED", message: "owner disappeared" };
  await writeFile(path.join(broker.jobsRoot, `${FIRST_JOB}.json`), `${JSON.stringify(restarted, null, 2)}\n`);
  await assert.rejects(
    () => broker.bindConversation({
      hostConversationId: "conv-restarted-handle",
      binderId: "owner-a",
      jobId: SECOND_JOB,
      workspace,
    }),
    (error) => error instanceof BridgeError &&
      error.code === "WORKSPACE_CLEANUP_PENDING" &&
      error.details?.reason === "previous_job_cleanup_unproven",
  );
  restarted.cleanup = { status: "completed", observed: "runtime_close_returned" };
  await writeFile(path.join(broker.jobsRoot, `${FIRST_JOB}.json`), `${JSON.stringify(restarted, null, 2)}\n`);
  const rebound = await broker.bindConversation({
    hostConversationId: "conv-restarted-handle",
    binderId: "owner-a",
    jobId: SECOND_JOB,
    workspace,
  });
  assert.equal(rebound.replacedJobId, FIRST_JOB);
  await broker.close();
});

test("model verification releases a returned handle only after cleanup succeeds", async () => {
  const successfulRuntime = new Runtime();
  successfulRuntime.getStatus = async () => {
    throw new BridgeError("MODEL_CHECK_FAILED", "simulated model verification failure");
  };
  const successful = await harness({ runtime: successfulRuntime, jobIds: [FIRST_JOB, SECOND_JOB] });
  await assert.rejects(
    () => successful.broker.delegate({
      workspace: successful.workspace,
      prompt: "model failure with cleanup",
      hostConversationId: "conv-model-cleanup",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "MODEL_CHECK_FAILED",
  );
  const released = await readJob(successful.broker, FIRST_JOB);
  assert.equal(released.admission.state, ADMISSION_STATE_RELEASED);
  assert.equal(released.cleanup.status, "completed");
  delete successfulRuntime.getStatus;
  const rebound = await successful.broker.delegate({
    workspace: successful.workspace,
    prompt: "replacement after cleanup",
    hostConversationId: "conv-model-cleanup",
    binderId: "owner-a",
  });
  assert.equal(rebound.binding.replacedJobId, FIRST_JOB);
  await successful.broker.close();

  const fencedRuntime = new Runtime();
  fencedRuntime.getStatus = async () => {
    throw new BridgeError("MODEL_CHECK_FAILED", "simulated model verification failure");
  };
  fencedRuntime.close = async (input) => {
    fencedRuntime.closed.push(input);
    throw new Error("simulated cleanup failure");
  };
  const fenced = await harness({ runtime: fencedRuntime, jobIds: [FIRST_JOB, SECOND_JOB] });
  await assert.rejects(
    () => fenced.broker.delegate({
      workspace: fenced.workspace,
      prompt: "model failure without cleanup",
      hostConversationId: "conv-model-fenced",
      binderId: "owner-a",
    }),
    (error) => error instanceof BridgeError && error.code === "MODEL_CHECK_FAILED",
  );
  const uncertain = await readJob(fenced.broker, FIRST_JOB);
  assert.equal(uncertain.admission.state, ADMISSION_STATE_STARTING);
  assert.equal(uncertain.status, "admitted");
  assert.equal(fencedRuntime.closed.length, 1);
  await assert.rejects(
    () => fenced.broker.bindConversation({
      hostConversationId: "conv-model-fenced",
      binderId: "owner-a",
      jobId: SECOND_JOB,
      workspace: fenced.workspace,
    }),
    (error) => error instanceof BridgeError &&
      error.code === "CONVERSATION_REBIND_UNSAFE" &&
      error.details?.reason === "previous_job_nonterminal",
  );
  await fenced.broker.close();
});
