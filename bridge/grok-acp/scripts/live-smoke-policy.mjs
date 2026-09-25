import { GrokAcpBroker } from "../broker.mjs";
import {
  BREAK_GLASS_PERMISSION_MODE,
  HostPolicyError,
  PERMISSION_MODE_ENV,
  resolveBinderId,
  resolveHostConversationId,
} from "../host-policy.mjs";

export function requireLiveSmokePermission(env = process.env) {
  const mode = typeof env?.[PERMISSION_MODE_ENV] === "string"
    ? env[PERMISSION_MODE_ENV].trim()
    : "";
  if (mode !== BREAK_GLASS_PERMISSION_MODE) {
    throw new HostPolicyError(
      "LIVE_SMOKE_PERMISSION_REQUIRED",
      `Live smoke requires explicit ${PERMISSION_MODE_ENV}=${BREAK_GLASS_PERMISSION_MODE} break-glass approval`,
      { required: BREAK_GLASS_PERMISSION_MODE },
    );
  }
  return { permissionMode: BREAK_GLASS_PERMISSION_MODE, breakGlass: true };
}

export function resolveLiveSmokeIdentity(env = process.env) {
  return {
    hostConversationId: resolveHostConversationId(undefined, env, "conv-grok-live-smoke"),
    binderId: resolveBinderId(undefined, env, "smoke-owner"),
  };
}

export function createLiveSmokeBroker(options = {}) {
  const processEnv = options.processEnv ?? process.env;
  requireLiveSmokePermission(processEnv);
  const identity = resolveLiveSmokeIdentity(processEnv);
  const broker = new GrokAcpBroker({
    ...options,
    processEnv,
    defaultHostConversationId: options.defaultHostConversationId ?? identity.hostConversationId,
    defaultBinderId: options.defaultBinderId ?? identity.binderId,
  });
  return { broker, ...identity };
}

export async function waitForCleanup(broker, jobId, { timeoutMs = 15_000, pollMs = 100 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (true) {
    let job;
    try {
      job = await broker.getJob(jobId);
    } catch (error) {
      return {
        ready: false,
        code: "CLEANUP_STATE_UNAVAILABLE",
        message: "Smoke could not observe the terminal job cleanup state.",
        error,
      };
    }
    const active = typeof broker.active?.has === "function" && broker.active.has(jobId);
    if (job.cleanup?.status === "completed" && !active) {
      return { ready: true, job };
    }
    if (job.cleanup?.status === "uncertain") {
      return {
        ready: false,
        code: "CLEANUP_UNCERTAIN",
        message: "Smoke will not rebind a conversation while terminal cleanup is uncertain.",
        job,
      };
    }
    if (Date.now() >= deadline) {
      return {
        ready: false,
        code: "CLEANUP_TIMEOUT",
        message: "Smoke timed out waiting for terminal cleanup before the next conversation turn.",
        job,
      };
    }
    await new Promise((resolve) => setTimeout(resolve, Math.min(pollMs, Math.max(1, deadline - Date.now()))));
  }
}
