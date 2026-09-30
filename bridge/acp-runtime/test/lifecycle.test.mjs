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
    pid: 400, startTime: "new-owner", inspectProcess: async () => ({ status: "missing" }), ...options });
  await Promise.all([broker.bindingsRoot, broker.jobsRoot, broker.ownersRoot].map(p => mkdir(p, { recursive: true })));
  const jobId = randomUUID();
  const owner = { brokerId: randomUUID(), pid: 500, startTime: "old-owner" };
  const bind = { schema: "saarius.acp.conversation-bind.v1", hostConversationId: "real-conversation", binderId: owner.brokerId,
    jobId, workspace: root, boundAt: "original-time" };
  const runDir = path.join(broker.runsRoot, jobId);
  await mkdir(runDir, { recursive: true });
  const sessionKey = `${lane}-acp:${jobId}`;
  const job = { jobId, status: "failed", owner, binding: bind, sessionKey, workspace: root,
    route: { agent: lane === "grok" ? "grok-build" : lane, model: "fixture" }, request: { promptSha256: "fixture" },
    handle: { sessionKey }, admission: { state: "started" },
    cleanup: { status: "uncertain", observed: "runtime_close_failed", message: "original-error" },
    workers: [{ pid: 600, startedAt: "launch-time", processStartTime: "physical-start", launchId: randomUUID(), scope: { kind: "runtime-session", sessionKey } }],
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
    const second = new Broker({ stateRoot: broker.stateRoot, runtime: {}, processEnv: {}, pid: 401, startTime: "successor" });
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
      ? { status: "alive", startTime: "physical-start" } : { status: "missing" };
    await assert.rejects(broker.recoverConversation({ ...input, apply: true }), /owner_or_worker_live/);
    assert.equal((await broker.getJob(job.jobId)).cleanup.status, "uncertain");
    workerLive = false;
    await broker.recoverConversation({ ...input, apply: true });
    assert.equal((await broker.result({ jobId: job.jobId })).complete, true);
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
        ? failure === "live-worker" ? { status: "alive", startTime: "physical-start" } : { status: "unknown" } : { status: "missing" };
      if (failure === "live-owner") broker.inspectProcess = async pid => pid === 500 ? { status: "alive", startTime: "old-owner" } : { status: "missing" };
      if (failure === "missing-workers") delete job.workers;
      if (failure === "foreign-binder") { bind.binderId = "foreign-configured"; job.binding = bind; input.expectedBinderId = bind.binderId; await writeFile(bindPath, JSON.stringify(bind)); }
      if (failure === "lease-mismatch") await writeFile(path.join(broker.ownersRoot, `${job.owner.brokerId}.json`), JSON.stringify({ ...job.owner, startTime: "wrong" }));
      if (failure === "other-session") job.workers[0].scope.sessionKey = "successor";
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
