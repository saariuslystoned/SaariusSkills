import { createHash } from "node:crypto";
import path from "node:path";

// Logical host ownership survives a process restart. Physical broker custody does not.
// Match the existing Grok state-root namespace; explicit host binders still win.
export function defaultBinderIdForStateRoot(stateRoot) {
  return `state-${createHash("sha256").update(path.resolve(stateRoot), "utf8").digest("hex").slice(0, 32)}`;
}

export const WORKER_EXIT_WAIT_MS = 10_000;

export function isUnsupportedBackendSessionClose(error) {
  if (!error || typeof error !== "object") return false;
  if (error.code !== "ACP_BACKEND_UNSUPPORTED_CONTROL") return false;
  return /session\/close/i.test(String(error.message ?? ""));
}

export function launchScopesMatch(left, right) {
  if (!left || !right || left.kind !== right.kind) return false;
  if (left.kind === "runtime-session") return left.sessionKey === right.sessionKey;
  if (left.kind === "runtime-probe") return left.agent === right.agent;
  return left.kind === "client";
}

export function processIdentitiesMatch(left, right) {
  if (!left || !right) return false;
  if (!Number.isInteger(left.pid) || left.pid <= 0 || left.pid !== right.pid) return false;
  if (typeof left.startedAt !== "string" || !left.startedAt || left.startedAt !== right.startedAt) {
    return false;
  }
  if (typeof left.launchId !== "string" || !left.launchId || left.launchId !== right.launchId) {
    return false;
  }
  return launchScopesMatch(left.scope, right.scope);
}

export function isOwnedSessionProcess(process, sessionKey) {
  return Boolean(
    process &&
      typeof sessionKey === "string" &&
      sessionKey &&
      process.scope?.kind === "runtime-session" &&
      process.scope.sessionKey === sessionKey,
  );
}

export function publicWorkerIdentity(process) {
  if (!process) return undefined;
  return {
    pid: process.pid,
    startedAt: process.startedAt,
    launchId: process.launchId,
    scope: process.scope,
    ...(process.signal !== undefined ? { signal: process.signal } : {}),
    ...(process.exitCode !== undefined ? { exitCode: process.exitCode } : {}),
  };
}

export function createProcessLifecycleTracker() {
  const spawned = [];
  const exits = [];
  const waiters = new Set();
  const physicalStartTimes = new Map();

  function notify() {
    for (const wake of waiters) wake();
  }

  function ownedSpawned(sessionKey) {
    return spawned.filter((process) => isOwnedSessionProcess(process, sessionKey));
  }

  function matchingExit(started) {
    return exits.find((exit) => processIdentitiesMatch(started, exit));
  }

  function snapshotOwned(sessionKey) {
    const started = ownedSpawned(sessionKey);
    const observed = started.map(matchingExit).filter(Boolean);
    return { started, exits: observed };
  }

  return {
    processLifecycle: {
      onSpawned(process) {
        spawned.push(process);
        notify();
      },
      onExit(exit) {
        exits.push(exit);
        notify();
      },
    },
    spawned,
    exits,
    physicalStartTimes,
    ownedSpawned,
    matchingExit,
    snapshotOwned,
    async waitForOwnedExit(sessionKey, { timeoutMs = WORKER_EXIT_WAIT_MS } = {}) {
      const deadline = Date.now() + timeoutMs;
      while (true) {
        const snapshot = snapshotOwned(sessionKey);
        if (snapshot.started.length > 0 && snapshot.exits.length === snapshot.started.length) {
          return { status: "exited", ...snapshot };
        }
        const remaining = deadline - Date.now();
        if (remaining <= 0) {
          return { status: snapshot.started.length > 0 ? "pending" : "none", ...snapshot };
        }
        await new Promise((resolve) => {
          let settled = false;
          const done = () => {
            if (settled) return;
            settled = true;
            waiters.delete(done);
            clearTimeout(timer);
            resolve();
          };
          const timer = setTimeout(done, Math.min(50, remaining));
          waiters.add(done);
        });
      }
    },
  };
}


export async function captureJobWorkers(broker, job, handle) {
  const workers = broker.processLifecycleTracker.snapshotOwned(handle?.sessionKey ?? job.sessionKey).started;
  if (workers.length === 0) return;
  job.workers = await Promise.all(workers.map(async (worker) => {
    const key = JSON.stringify([worker.launchId, worker.pid, worker.startedAt]);
    let startTime = broker.processLifecycleTracker.physicalStartTimes.get(key)
      ?? job.workers?.find(prior => processIdentitiesMatch(prior, worker))?.processStartTime;
    if (!startTime) {
      const probe = await broker.inspectProcess(worker.pid);
      if (probe.status === "alive" && probe.startTime) {
        startTime = probe.startTime;
        broker.processLifecycleTracker.physicalStartTimes.set(key, startTime);
      }
    }
    return {
      ...publicWorkerIdentity(worker),
      ...(startTime ? { processStartTime: startTime } : {}),
    };
  }));
}

export function lifecycleReceipt(job, { terminal, cleanupReady, active = false } = {}) {
  const taskComplete = terminal;
  const admissionEligible = taskComplete && cleanupReady && !active;
  return {
    taskComplete, cleanupReady, complete: taskComplete && cleanupReady,
    admissionEligible,
    remediation: admissionEligible ? "none" : taskComplete
      ? "inspect_exact_owned_worker_then_explicit_recovery" : "wait_for_task_and_cleanup",
  };
}

export function brokerProcessLifecycle(broker) {
  return {
    ...broker.processLifecycleTracker.processLifecycle,
    async onSpawned(worker) {
      broker.processLifecycleTracker.processLifecycle.onSpawned(worker);
      if (worker.scope?.kind !== "runtime-session") return;
      if (!/^(antigravity|cursor|grok)-acp:[0-9a-f-]{36}$/i.test(worker.scope.sessionKey ?? "")) return;
      const jobId = worker.scope.sessionKey.split(":").at(-1);
      if (!/^[0-9a-f-]{36}$/i.test(jobId ?? "")) return;
      const job = await broker.getJob(jobId);
      if (job.sessionKey !== worker.scope.sessionKey) throw new Error("Worker session ownership mismatch");
      await captureJobWorkers(broker, job, { sessionKey: job.sessionKey });
      await broker.saveJob(job);
    },
  };
}
