import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { randomUUID } from "node:crypto";
import { defaultBinderIdForStateRoot, createProcessLifecycleTracker } from "../lifecycle.mjs";

const lanes = { antigravity: "AntigravityAcpBroker", cursor: "CursorAcpBroker", grok: "GrokAcpBroker" };

async function fixture(lane, options = {}) {
  const root = await mkdtemp(path.join(tmpdir(), `acp-lifecycle-${lane}-`));
  const { [lanes[lane]]: Broker } = await import(`../../${lane}-acp/broker.mjs`);
  const broker = new Broker({ stateRoot: root, runtime: {}, processEnv: {},
    pid: 400, startTime: "ps-utc-v1:2020-01-01T07:05:34.000Z", inspectProcess: async () => ({ status: "missing" }), ...options });
  await Promise.all([broker.bindingsRoot, broker.jobsRoot, broker.ownersRoot].map(p => mkdir(p, { recursive: true })));
  const jobId = randomUUID();
  const owner = { brokerId: randomUUID(), pid: 500, startTime: "ps-utc-v1:2020-01-01T02:34:23.000Z" };
  const bind = { schema: "saarius.acp.conversation-bind.v1", hostConversationId: "real-conversation", binderId: owner.brokerId,
    jobId, workspace: root, boundAt: "original-time" };
  const runDir = path.join(broker.runsRoot, jobId);
  await mkdir(runDir, { recursive: true });
  const sessionKey = `${lane}-acp:${jobId}`;
  const job = { jobId, status: "failed", owner, binding: bind, sessionKey, workspace: root,
    route: { agent: lane === "grok" ? "grok-build" : lane, model: "fixture" }, request: { promptSha256: "fixture" },
    handle: { sessionKey }, admission: { state: "started" },
    cleanup: { status: "uncertain", observed: "runtime_close_failed", message: "original-error" },
    workers: [{ pid: 600, startedAt: "launch-time", processStartTime: "ps-utc-v1:2020-01-01T18:26:07.000Z", launchId: randomUUID(), scope: { kind: "runtime-session", sessionKey } }],
    runDir, proof: { events: path.join(runDir, "events.jsonl"), state: path.join(runDir, "STATE.md"), proof: path.join(runDir, "PROOF.md") },
    error: { code: "BRIDGE_RESTARTED", message: "original-task-error" } };
  await writeFile(job.proof.events, '{"event":"original"}\n');
  await broker.saveJob(job);
  await writeFile(path.join(broker.ownersRoot, `${owner.brokerId}.json`), JSON.stringify(owner));
  const policy = await import(`../../${lane}-acp/host-policy.mjs`);
  const bindPath = policy.conversationBindPath(broker.bindingsRoot, bind.hostConversationId);
  await writeFile(bindPath, JSON.stringify(bind));
  const input = { jobId, hostConversationId: bind.hostConversationId, expectedBinderId: bind.binderId };
  return { broker, Broker, job, bind, bindPath, input, policy };
}

for (const lane of Object.keys(lanes)) {
  test(`${lane}: restart retains logical owner, allows cleaned follow-up, denies foreign owner`, async () => {
    const { broker, Broker, job, bind, bindPath } = await fixture(lane);
    assert.equal(broker.defaultBinderId, defaultBinderIdForStateRoot(broker.stateRoot));
    const second = new Broker({ stateRoot: broker.stateRoot, runtime: {}, processEnv: {}, pid: 401, startTime: "ps-utc-v1:2020-01-01T03:17:42.000Z" });
    assert.notEqual(broker.brokerId, second.brokerId);
    assert.equal(broker.defaultBinderId, second.defaultBinderId);
    job.cleanup = { status: "completed" };
    bind.binderId = broker.defaultBinderId;
    job.binding = bind;
    await broker.saveJob(job);
    await writeFile(bindPath, JSON.stringify(bind));
    const next = await second.bindConversation({ hostConversationId: bind.hostConversationId, binderId: second.defaultBinderId,
      jobId: randomUUID(), workspace: job.workspace });
    assert.equal(next.replacedJobId, job.jobId);
    const foreign = new Broker({ stateRoot: broker.stateRoot, runtime: {}, processEnv: {}, defaultBinderId: "foreign" });
    await assert.rejects(foreign.bindConversation({ ...next, binderId: "foreign", jobId: randomUUID() }), { code: "CONVERSATION_REBIND_FORBIDDEN" });
  });

  test(`${lane}: existing-state plan and apply preserve outcome/history; retry cannot touch successor`, async () => {
    const { broker, job, bindPath, input } = await fixture(lane);
    const originalJob = await readFile(path.join(broker.jobsRoot, `${job.jobId}.json`), "utf8");
    const originalBind = await readFile(bindPath, "utf8");
    assert.equal((await broker.result({ jobId: job.jobId })).complete, false);
    const plan = await broker.recoverConversation(input);
    assert.equal(plan.applied, false);
    assert.equal(await readFile(bindPath, "utf8"), originalBind);
    assert.equal(await readFile(path.join(broker.jobsRoot, `${job.jobId}.json`), "utf8"), originalJob);
    const recovered = await broker.recoverConversation({ ...input, apply: true });
    assert.equal(recovered.applied, true);
    const after = await broker.getJob(job.jobId);
    assert.deepEqual(after.error, job.error);
    assert.deepEqual(after.owner, job.owner);
    assert.deepEqual(after.binding, job.binding);
    assert.deepEqual(after.cleanup.previousCleanup, job.cleanup);
    assert.equal(after.cleanup.status, "recovered");
    assert.match(await readFile(job.proof.events, "utf8"), /^\{"event":"original"\}/);
    const receipt = await broker.result({ jobId: job.jobId });
    assert.equal(receipt.complete, true);
    assert.equal(receipt.admissionEligible, true);
    const migrated = JSON.parse(await readFile(bindPath, "utf8"));
    assert.equal(migrated.recoveries[0].previousBinding.binderId, input.expectedBinderId);
    const retryInput = { ...input, expectedBinderId: broker.defaultBinderId, apply: true };
    await broker.recoverConversation(retryInput);
    assert.equal(JSON.parse(await readFile(bindPath, "utf8")).recoveries.length, 1);
    const successor = await broker.bindConversation({ hostConversationId: input.hostConversationId, binderId: broker.defaultBinderId,
      jobId: randomUUID(), workspace: job.workspace });
    assert.equal(successor.recoveries.length, 1);
    const successorBytes = await readFile(bindPath, "utf8");
    await assert.rejects(broker.recoverConversation(retryInput), /binding_changed_or_missing/);
    assert.equal(await readFile(bindPath, "utf8"), successorBytes);
  });

  test(`${lane}: carried recovery history cannot prevent recovery of an interrupted successor`, async () => {
    const { broker, job, input } = await fixture(lane);
    await broker.recoverConversation({ ...input, apply: true });
    const successor = await broker.bindConversation({ hostConversationId: input.hostConversationId,
      binderId: broker.defaultBinderId, jobId: randomUUID(), workspace: job.workspace });
    const runDir = path.join(broker.runsRoot, successor.jobId);
    await mkdir(runDir, { recursive: true });
    const sessionKey = `${lane}-acp:${successor.jobId}`;
    const nextJob = { ...job, jobId: successor.jobId, binding: successor, sessionKey, handle: { sessionKey },
      runDir, workers: job.workers.map(worker => ({ ...worker, launchId: randomUUID(), scope: { kind: "runtime-session", sessionKey } })),
      proof: { state: path.join(runDir, "STATE.md"), events: path.join(runDir, "events.jsonl"), proof: path.join(runDir, "PROOF.md") } };
    await writeFile(nextJob.proof.events, '{"event":"successor_interrupted"}\n');
    await broker.saveJob(nextJob);
    const result = await broker.recoverConversation({ jobId: successor.jobId, hostConversationId: input.hostConversationId,
      expectedBinderId: broker.defaultBinderId, apply: true });
    assert.equal(result.applied, true);
    assert.equal((await broker.result({ jobId: successor.jobId })).complete, true);
    assert.equal((await broker.getJob(job.jobId)).cleanup.status, "recovered");
  });

  test(`${lane}: proven terminal legacy cleanup migrates without invented worker metadata`, async () => {
    const { broker, job, input } = await fixture(lane);
    job.cleanup = { status: "completed", observed: "runtime_close_returned" };
    delete job.workers;
    await broker.saveJob(job);
    await broker.recoverConversation({ ...input, apply: true });
    assert.deepEqual((await broker.getJob(job.jobId)).cleanup, job.cleanup);
  });

  test(`${lane}: interrupted publication retains old binder and safely retries`, async () => {
    const { recoverConversation } = await import("../recovery.mjs");
    const { broker, job, bindPath, input, policy } = await fixture(lane);
    const before = await readFile(bindPath, "utf8");
    await assert.rejects(recoverConversation(broker, { ...input, apply: true }, policy.claimConversationBind,
      async () => { throw new Error("simulated interruption before binding publication"); }), /simulated interruption/);
    assert.equal(await readFile(bindPath, "utf8"), before);
    assert.equal((await broker.getJob(job.jobId)).cleanup.status, "recovered");
    await broker.recoverConversation({ ...input, apply: true });
    assert.equal((await broker.result({ jobId: job.jobId })).complete, true);
    assert.equal(JSON.parse(await readFile(bindPath, "utf8")).recoveries.length, 1);
  });

  test(`${lane}: interrupted worker remains fenced until observed exit, then retry succeeds`, async () => {
    const { broker, job, input } = await fixture(lane);
    let workerLive = true;
    broker.inspectProcess = async pid => pid === 600 && workerLive
      ? { status: "alive", startTime: "ps-utc-v1:2020-01-01T18:26:07.000Z" } : { status: "missing" };
    await assert.rejects(broker.recoverConversation({ ...input, apply: true }), /owner_or_worker_live/);
    assert.equal((await broker.getJob(job.jobId)).cleanup.status, "uncertain");
    workerLive = false;
    await broker.recoverConversation({ ...input, apply: true });
    assert.equal((await broker.result({ jobId: job.jobId })).complete, true);
  });

  for (const observedPid of [500, 600]) {
    for (const apply of [false, true]) {
      test(`${lane}: TZ-shifted legacy ${observedPid === 500 ? "owner" : "worker"} refuses recovery apply=${apply} without changing state`, async () => {
        const { broker, job, input, bindPath } = await fixture(lane);
        if (observedPid === 500) {
          job.owner.startTime = "Thu Oct  1 07:25:46 2026";
          await writeFile(path.join(broker.ownersRoot, `${job.owner.brokerId}.json`), JSON.stringify(job.owner));
        } else {
          job.workers[0].processStartTime = "Thu Oct  1 18:57:16 2026";
        }
        await broker.saveJob(job);
        broker.inspectProcess = async pid => pid === observedPid
          ? { status: "alive", startTime: observedPid === 500 ? "Thu Oct  1 04:25:46 2026" : "Thu Oct  1 15:57:16 2026" }
          : { status: "missing" };
        const jobPath = path.join(broker.jobsRoot, `${job.jobId}.json`);
        const before = await Promise.all([jobPath, bindPath, job.proof.events].map(p => readFile(p, "utf8")));
        await assert.rejects(broker.recoverConversation({ ...input, apply }), /ownership_unobservable/);
        assert.deepEqual(await Promise.all([jobPath, bindPath, job.proof.events].map(p => readFile(p, "utf8"))), before);
      });
    }
  }

  test(`${lane}: real comparable owner and worker reuse remains recoverable`, async () => {
    const { broker, job, input } = await fixture(lane);
    broker.inspectProcess = async () => ({ status: "alive", startTime: "ps-utc-v1:2026-10-01T23:32:44.000Z" });
    const receipt = await broker.recoverConversation({ ...input, apply: true });
    assert.equal(receipt.ownerObservation, "pid_reused");
    assert.equal(receipt.workerObservations[0].observation, "pid_reused");
    assert.equal(receipt.cleanupReady, true);
    assert.equal((await broker.getJob(job.jobId)).cleanup.status, "recovered");
  });

  test(`${lane}: a live canonical owner stays running across observation`, async () => {
    const { broker, job } = await fixture(lane);
    job.status = "running";
    delete job.error;
    job.owner.startTime = "ps-utc-v1:2026-10-01T11:25:46.000Z";
    await broker.saveJob(job);
    await writeFile(path.join(broker.ownersRoot, `${job.owner.brokerId}.json`), JSON.stringify(job.owner));
    broker.inspectProcess = async () => ({ status: "alive", startTime: job.owner.startTime });
    const jobPath = path.join(broker.jobsRoot, `${job.jobId}.json`);
    const before = await readFile(jobPath, "utf8");
    assert.equal((await broker.observeJob(job.jobId)).status, "running");
    assert.equal(await readFile(jobPath, "utf8"), before);
  });

  test(`${lane}: missing runtime close cannot claim cleanup`, async () => {
    const { broker, job } = await fixture(lane);
    await broker.closeRuntimeSession(job, job.handle);
    assert.equal(job.cleanup.status, "uncertain");
  });

  for (const failure of ["live-worker", "unknown-worker", "missing-workers", "foreign-binder", "lease-mismatch", "other-session", "live-owner", "active-job"]) {
    test(`${lane}: recovery refuses ${failure} without editing state`, async () => {
      const { broker, job, bind, bindPath, input } = await fixture(lane);
      if (failure === "live-worker" || failure === "unknown-worker") broker.inspectProcess = async pid => pid === 600
        ? failure === "live-worker" ? { status: "alive", startTime: "ps-utc-v1:2020-01-01T18:26:07.000Z" } : { status: "unknown" } : { status: "missing" };
      if (failure === "live-owner") broker.inspectProcess = async pid => pid === 500 ? { status: "alive", startTime: "ps-utc-v1:2020-01-01T02:34:23.000Z" } : { status: "missing" };
      if (failure === "missing-workers") delete job.workers;
      if (failure === "foreign-binder") { bind.binderId = "foreign-configured"; job.binding = bind; input.expectedBinderId = bind.binderId; await writeFile(bindPath, JSON.stringify(bind)); }
      if (failure === "lease-mismatch") await writeFile(path.join(broker.ownersRoot, `${job.owner.brokerId}.json`), JSON.stringify({ ...job.owner, startTime: "wrong" }));
      if (failure === "other-session") job.workers[0].scope.sessionKey = "ps-utc-v1:2020-01-01T03:17:42.000Z";
      if (failure === "active-job") broker.active.set(job.jobId, {});
      await broker.saveJob(job);
      const before = await readFile(bindPath, "utf8");
      const beforeJob = await readFile(path.join(broker.jobsRoot, `${job.jobId}.json`), "utf8");
      await assert.rejects(broker.recoverConversation({ ...input, apply: true }), { code: "ACP_RECOVERY_REFUSED" });
      assert.equal(await readFile(bindPath, "utf8"), before);
      assert.equal(await readFile(path.join(broker.jobsRoot, `${job.jobId}.json`), "utf8"), beforeJob);
    });
  }

  test(`${lane}: unsupported close succeeds only after every exact owned launch exits`, async () => {
    const { broker, job } = await fixture(lane);
    const tracker = createProcessLifecycleTracker();
    broker.processLifecycleTracker = tracker;
    broker.workerExitWaitMs = 0;
    const worker = job.workers[0];
    tracker.processLifecycle.onSpawned(worker);
    const foreign = { ...worker, launchId: "foreign-launch" };
    tracker.processLifecycle.onExit(foreign);
    broker.runtime = { close: async () => { throw Object.assign(new Error("Agent does not support session/close"), { code: "ACP_BACKEND_UNSUPPORTED_CONTROL" }); } };
    await broker.closeRuntimeSession(job, job.handle);
    assert.equal(job.cleanup.status, "uncertain");
    tracker.processLifecycle.onExit({ ...worker, exitCode: 0 });
    await broker.closeRuntimeSession(job, job.handle);
    assert.equal(job.cleanup.status, "completed");
    assert.equal(job.cleanup.backendSessionDiscard, "unsupported");
  });
}
