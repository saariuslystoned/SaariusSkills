import { compareProcessStartTimes } from "./process-identity.mjs";
import path from "node:path";

export class RecoveryError extends Error {
  constructor(reason) {
    super(`ACP recovery refused: ${reason}`);
    this.code = "ACP_RECOVERY_REFUSED";
    this.details = { reason };
  }
}

const terminal = (job) => ["completed", "failed", "cancelled", "needs-input"].includes(job.status);
const cleaned = (job) => ["completed", "recovered"].includes(job.cleanup?.status);
const deny = (reason) => { throw new RecoveryError(reason); };

async function proveGone(broker, identity) {
  if (!identity || !Number.isInteger(identity.pid) || identity.pid <= 0 ||
      typeof identity.startTime !== "string" || !identity.startTime.trim()) deny("ownership_unobservable");
  const probe = await broker.inspectProcess(identity.pid);
  if (probe?.status === "missing") return "missing";
  if (probe?.status === "alive" && typeof probe.startTime === "string" && probe.startTime.trim()) {
    const comparison = compareProcessStartTimes(identity.startTime, probe.startTime);
    if (comparison === "different") return "pid_reused";
    if (comparison === "matching") deny("owner_or_worker_live");
  }
  deny("ownership_unobservable");
}

// This is observation-only cleanup recovery: never signal a PID, resume an old
// model session, or claim custody from another process. Hold the existing bind
// lock throughout validation/publication; new admission uses that same lock.
export async function recoverConversation(broker, input = {}, claimBind, atomicWrite) {
  const { jobId, hostConversationId, expectedBinderId, apply = false } = input;
  if (typeof apply !== "boolean" || !/^[0-9a-f-]{36}$/i.test(jobId ?? "") ||
      typeof expectedBinderId !== "string" || !expectedBinderId) deny("invalid_recovery_request");
  const current = broker.conversationIdentity({ hostConversationId });
  let receipt;
  await claimBind(broker.bindingsRoot, current, {
    owner: broker.ownerIdentity(), inspectOwner: (owner) => broker.probeOwner(owner), atomicWrite,
    recoverExisting: async (existing) => {
      if (!existing || existing.jobId !== jobId || existing.hostConversationId !== current.hostConversationId ||
          existing.binderId !== expectedBinderId) deny("binding_changed_or_missing");
      if (broker.active.has(jobId)) deny("job_active");
      const job = await broker.getJob(jobId);
      if (!terminal(job)) deny("job_nonterminal_observe_status_first");
      const previousRecovery = existing.recoveries?.at(-1);
      const originalBinder = previousRecovery?.jobId === jobId ? previousRecovery.fromBinderId : existing.binderId;
      if (job.binding?.jobId !== jobId || job.binding?.binderId !== originalBinder ||
          job.binding?.hostConversationId !== existing.hostConversationId ||
          job.workspace !== existing.workspace) deny("binding_job_mismatch");
      // Only the obsolete process-default binder can migrate. A configured foreign
      // binder stays foreign even if its broker is dead and its job is complete.
      if (existing.binderId !== current.binderId && existing.binderId !== job.owner?.brokerId) deny("foreign_binder");
      const lease = await broker.readOwnerLease(job.owner?.brokerId);
      if (!lease || lease.brokerId !== job.owner?.brokerId || lease.pid !== job.owner?.pid ||
          lease.startTime !== job.owner?.startTime) deny("owner_lease_mismatch");
      const ownerObservation = await proveGone(broker, job.owner);
      const workerObservations = [];
      if (!cleaned(job)) {
        if (!Array.isArray(job.workers) || job.workers.length === 0) deny("worker_ownership_unobservable");
        const agent = job.route?.agent === "grok-build" ? "grok" : job.route?.agent;
        if (!["antigravity", "cursor", "grok"].includes(agent)) deny("session_locator_mismatch");
        const expectedSession = `${agent}-acp:${jobId}`;
        if (job.sessionKey !== expectedSession || (job.handle && job.handle.sessionKey !== expectedSession)) deny("session_locator_mismatch");
        for (const worker of job.workers) {
          if (worker.scope?.kind !== "runtime-session" || worker.scope.sessionKey !== expectedSession ||
              typeof worker.launchId !== "string" || !worker.launchId ||
              typeof worker.startedAt !== "string" || !worker.startedAt) deny("worker_ownership_ambiguous");
          const observation = await proveGone(broker, { pid: worker.pid, startTime: worker.processStartTime });
          workerObservations.push({ pid: worker.pid, launchId: worker.launchId, observation });
        }
      }
      const recovery = {
        schema: "saarius.acp.recovery.v1", at: broker.now(), jobId,
        fromBinderId: existing.binderId, toBinderId: current.binderId,
        recoveredBy: broker.ownerIdentity(), ownerObservation, workerObservations,
        previousBinding: { ...existing, recoveries: undefined },
      };
      receipt = {
        jobId, hostConversationId: current.hostConversationId,
        fromBinderId: existing.binderId, toBinderId: current.binderId,
        cleanupReady: apply || cleaned(job),
        admissionEligible: apply || (cleaned(job) && existing.binderId === current.binderId),
        eligibleAfterApply: true,
        applied: apply, ownerObservation, workerObservations,
      };
      if (!apply || (existing.binderId === current.binderId && cleaned(job) && existing.recoveries?.at(-1)?.jobId === jobId)) return null;
      // Publishing cleanup before binding is safe on interruption: admission still
      // refuses the old binder. Retrying verifies the same exact binding/lease.
      if (!cleaned(job)) {
        const runDir = path.join(broker.runsRoot, jobId);
        if (job.runDir !== runDir || job.proof?.events !== path.join(runDir, "events.jsonl") ||
            job.proof?.state !== path.join(runDir, "STATE.md") || job.proof?.proof !== path.join(runDir, "PROOF.md")) deny("proof_locator_mismatch");
        job.cleanup = {
          status: "recovered", observed: "exact_recorded_workers_gone", at: broker.now(),
          previousCleanup: job.cleanup, recovery,
        };
        await broker.saveJob(job);
        await broker.recordEvent(job, "cleanup_recovered", { ownerObservation, workerObservations });
      }
      return { ...existing, binderId: current.binderId, recoveries: [...(existing.recoveries ?? []), recovery] };
    },
  });
  return receipt;
}
