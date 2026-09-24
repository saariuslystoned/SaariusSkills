import { createHash } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

export const LIVE_PERMISSION_MODE = "approve-reads";
export const BREAK_GLASS_PERMISSION_MODE = "approve-all";
export const LIVE_NON_INTERACTIVE_PERMISSIONS = "fail";
export const PERMISSION_MODE_ENV = "SAARIUS_ACP_PERMISSION_MODE";
export const HOST_CONVERSATION_ENV = "SAARIUS_ACP_HOST_CONVERSATION_ID";
export const BINDER_ENV = "SAARIUS_ACP_BINDER_ID";
export const SYSTEM_BINDER_ID = "system";
export const CONVERSATION_BIND_SCHEMA = "saarius.acp.conversation-bind.v1";
export const IDENTITY_MAX_CHARS = 120;
export const IDENTITY_PATTERN = /^[0-9A-Za-z_.:@-]+$/;

export class HostPolicyError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "HostPolicyError";
    this.code = code;
    this.details = details;
  }
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return undefined;
}

export function normalizeHostIdentity(value, field, code) {
  if (typeof value !== "string" || !value.trim()) {
    throw new HostPolicyError(code, `${field} is required`);
  }
  const normalized = value.trim();
  if (normalized.length > IDENTITY_MAX_CHARS || !IDENTITY_PATTERN.test(normalized)) {
    throw new HostPolicyError(code, `${field} must be a safe ${IDENTITY_MAX_CHARS}-character identity`);
  }
  if (normalized.includes("..")) {
    throw new HostPolicyError(code, `${field} must not contain path traversal`);
  }
  return normalized;
}

export function resolveLivePermissionMode(env = process.env) {
  const raw = firstNonEmpty(env?.[PERMISSION_MODE_ENV]);
  if (raw === BREAK_GLASS_PERMISSION_MODE) {
    return {
      permissionMode: BREAK_GLASS_PERMISSION_MODE,
      nonInteractivePermissions: LIVE_NON_INTERACTIVE_PERMISSIONS,
      breakGlass: true,
    };
  }
  if (raw && raw !== LIVE_PERMISSION_MODE) {
    throw new HostPolicyError(
      "INVALID_PERMISSION_MODE",
      `${PERMISSION_MODE_ENV} accepts ${LIVE_PERMISSION_MODE} or explicit break-glass ${BREAK_GLASS_PERMISSION_MODE}`,
      { value: raw },
    );
  }
  return {
    permissionMode: LIVE_PERMISSION_MODE,
    nonInteractivePermissions: LIVE_NON_INTERACTIVE_PERMISSIONS,
    breakGlass: false,
  };
}

export function resolveHostConversationId(explicit, env = process.env, fallback) {
  const requested = firstNonEmpty(explicit);
  const configured = firstNonEmpty(env?.[HOST_CONVERSATION_ENV], fallback);
  if (requested && configured) {
    const requestedId = normalizeHostIdentity(requested, "hostConversationId", "INVALID_HOST_CONVERSATION");
    const configuredId = normalizeHostIdentity(configured, "hostConversationId", "INVALID_HOST_CONVERSATION");
    if (requestedId !== configuredId) {
      throw new HostPolicyError(
        "HOST_CONVERSATION_NOT_HOST_CONTROLLED",
        "The request hostConversationId must match the host-controlled conversation identity",
        { hostConversationId: requestedId, hostConfiguredConversationId: configuredId },
      );
    }
    return configuredId;
  }
  const value = requested ?? configured;
  if (!value) {
    throw new HostPolicyError(
      "HOST_CONVERSATION_REQUIRED",
      "Live ACP delegate requires one parent conversation id (hostConversationId or SAARIUS_ACP_HOST_CONVERSATION_ID)",
    );
  }
  return normalizeHostIdentity(value, "hostConversationId", "INVALID_HOST_CONVERSATION");
}

export function resolveBinderId(explicit, env = process.env, fallback) {
  const hostValue = firstNonEmpty(env?.[BINDER_ENV], fallback, env?.USER, "local");
  const hostBinderId = normalizeHostIdentity(hostValue, "binderId", "INVALID_BINDER");
  const requested = firstNonEmpty(explicit);
  if (requested) {
    const requestedBinderId = normalizeHostIdentity(requested, "binderId", "INVALID_BINDER");
    if (requestedBinderId !== hostBinderId) {
      throw new HostPolicyError(
        "BINDER_ID_NOT_HOST_CONTROLLED",
        "The request binderId must match the host-controlled binder identity",
        { binderId: requestedBinderId, hostBinderId },
      );
    }
  }
  return hostBinderId;
}

export function resolveConversationIdentity(input = {}, env = process.env, defaults = {}) {
  return {
    hostConversationId: resolveHostConversationId(
      input.hostConversationId,
      env,
      defaults.defaultHostConversationId,
    ),
    binderId: resolveBinderId(input.binderId, env, defaults.defaultBinderId),
  };
}

export function canRebindConversation(existing, binderId) {
  if (!existing) return { ok: true, reason: "unbound" };
  if (existing.binderId === binderId) {
    return { ok: true, reason: "owner" };
  }
  return {
    ok: false,
    reason: "foreign_binder",
    boundBy: existing.binderId,
  };
}

export function assertRebindAllowed(existing, binderId) {
  const decision = canRebindConversation(existing, binderId);
  if (decision.ok) return decision;
  throw new HostPolicyError(
    "CONVERSATION_REBIND_FORBIDDEN",
    `Only ${existing.binderId} can rebind this conversation.`,
    {
      hostConversationId: existing.hostConversationId,
      boundBy: existing.binderId,
      binderId,
    },
  );
}

export function conversationBindFilename(conversationId) {
  return `${createHash("sha256").update(conversationId, "utf8").digest("hex")}.json`;
}

export function conversationBindPath(bindingsRoot, conversationId) {
  return path.join(bindingsRoot, conversationBindFilename(conversationId));
}

export async function loadConversationBind(bindingsRoot, conversationId) {
  try {
    const raw = JSON.parse(await readFile(conversationBindPath(bindingsRoot, conversationId), "utf8"));
    if (raw?.schema !== CONVERSATION_BIND_SCHEMA) return null;
    return raw;
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw new HostPolicyError("CONVERSATION_BIND_INVALID", "conversation bind could not be read");
  }
}

function isCompleteLockOwner(owner) {
  return Boolean(
    owner &&
      typeof owner.brokerId === "string" &&
      owner.brokerId.length > 0 &&
      owner.brokerId.length <= IDENTITY_MAX_CHARS &&
      IDENTITY_PATTERN.test(owner.brokerId) &&
      Number.isInteger(owner.pid) &&
      owner.pid > 0 &&
      typeof owner.startTime === "string" &&
      owner.startTime.trim().length > 0,
  );
}

function lockOwnersMatch(left, right) {
  return isCompleteLockOwner(left) && isCompleteLockOwner(right) &&
    left.brokerId === right.brokerId &&
    left.pid === right.pid &&
    left.startTime === right.startTime;
}

async function inspectConversationLock(lockPath) {
  try {
    const raw = await readFile(path.join(lockPath, "owner.json"), "utf8");
    try {
      const owner = JSON.parse(raw);
      return isCompleteLockOwner(owner)
        ? { status: "readable", owner }
        : { status: "unreadable" };
    } catch {
      return { status: "unreadable" };
    }
  } catch (error) {
    if (error?.code === "ENOENT") return { status: "unknown" };
    return { status: "unknown" };
  }
}

async function tryAcquireConversationReclaim(reclaimPath, owner, inspectOwner) {
  if (!isCompleteLockOwner(owner) || typeof inspectOwner !== "function") return false;
  try {
    await mkdir(reclaimPath, { mode: 0o700 });
    await writeFile(path.join(reclaimPath, "owner.json"), `${JSON.stringify(owner)}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    return true;
  } catch (error) {
    if (error?.code === "EEXIST") return { recoveryRequired: true };
    throw error;
  }
}

async function reclaimDeadConversationLock(lockPath, reclaimPath, owner, inspectOwner) {
  const fence = await tryAcquireConversationReclaim(reclaimPath, owner, inspectOwner);
  if (fence?.recoveryRequired) return fence;
  if (!fence) return false;
  try {
    const observed = await inspectConversationLock(lockPath);
    if (observed.status !== "readable") return false;
    let probe;
    try {
      probe = await inspectOwner(observed.owner);
    } catch {
      return false;
    }
    const provenDead = probe?.status === "missing" ||
      (probe?.status === "alive" && probe.startTime !== observed.owner.startTime);
    if (!provenDead) return false;

    const current = await inspectConversationLock(lockPath);
    if (current.status !== "readable" || !lockOwnersMatch(current.owner, observed.owner)) return false;
    let confirmed;
    try {
      confirmed = await inspectOwner(current.owner);
    } catch {
      return false;
    }
    const stillDead = confirmed?.status === "missing" ||
      (confirmed?.status === "alive" && confirmed.startTime !== current.owner.startTime);
    if (!stillDead) return false;
    await rm(lockPath, { recursive: true, force: true });
    return true;
  } finally {
    await rm(reclaimPath, { recursive: true, force: true });
  }
}

export async function claimConversationBind(
  bindingsRoot,
  record,
  { now, atomicWrite, inspectExisting, owner, inspectOwner } = {},
) {
  const target = conversationBindPath(bindingsRoot, record.hostConversationId);
  const lockPath = `${target}.lock`;
  const reclaimPath = `${lockPath}.reclaim`;
  let acquired = false;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await mkdir(lockPath, { mode: 0o700 });
      acquired = true;
      if (owner) {
        await writeFile(path.join(lockPath, "owner.json"), `${JSON.stringify(owner)}\n`, {
          encoding: "utf8",
          mode: 0o600,
        });
      }
      break;
    } catch (error) {
      if (acquired) {
        await rm(lockPath, { recursive: true, force: true });
        throw error;
      }
      if (error?.code !== "EEXIST") throw error;
      const reclaim = await reclaimDeadConversationLock(lockPath, reclaimPath, owner, inspectOwner);
      if (reclaim?.recoveryRequired) {
        throw new HostPolicyError(
          "CONVERSATION_BIND_RECOVERY_REQUIRED",
          "Conversation lock recovery is already fenced by another or interrupted reclaimer; owner recovery is required",
          { hostConversationId: record.hostConversationId, reclaimPath },
        );
      }
      if (!reclaim) {
        throw new HostPolicyError(
          "CONVERSATION_BIND_BUSY",
          "The conversation binding is being claimed by another worker; retry after its claim completes",
          { hostConversationId: record.hostConversationId },
        );
      }
    }
  }
  if (!acquired) {
    throw new HostPolicyError(
      "CONVERSATION_BIND_BUSY",
      "The conversation binding is being claimed by another worker; retry after its claim completes",
      { hostConversationId: record.hostConversationId },
    );
  }
  try {
    const existing = await loadConversationBind(bindingsRoot, record.hostConversationId);
    assertRebindAllowed(existing, record.binderId);
    if (existing && typeof inspectExisting === "function") {
      const decision = await inspectExisting(existing);
      if (!decision?.ok) {
        throw new HostPolicyError(
          "CONVERSATION_REBIND_UNSAFE",
          "The previous conversation worker is still active or its cleanup is not proven complete",
          {
            hostConversationId: record.hostConversationId,
            jobId: existing.jobId,
            workspace: existing.workspace,
            reason: decision?.reason ?? "unknown",
          },
        );
      }
    }
    const next = {
      schema: CONVERSATION_BIND_SCHEMA,
      hostConversationId: record.hostConversationId,
      binderId: record.binderId,
      jobId: record.jobId,
      workspace: record.workspace,
      boundAt: typeof now === "function" ? now() : new Date().toISOString(),
      replacedJobId: existing?.jobId,
    };
    const serialized = `${JSON.stringify(next, null, 2)}\n`;
    if (atomicWrite) await atomicWrite(target, serialized);
    else await writeFile(target, serialized, { encoding: "utf8", mode: 0o600 });
    return next;
  } finally {
    await rm(lockPath, { recursive: true, force: true });
  }
}

export function isReadinessRed(report) {
  return !report?.ready;
}

export function refuseUnlessReady(report) {
  if (report?.ready) return report;
  const code = report?.error?.code ?? "READINESS_FAILED";
  const message = report?.error?.message ?? "ACP delegate refused because readiness is red.";
  throw new HostPolicyError(code, message, {
    readiness: {
      ready: false,
      status: report?.status,
      error: report?.error,
    },
  });
}

export function livePermissionDecision(request, { isInteractionQuestion } = {}) {
  if (typeof isInteractionQuestion === "function" && isInteractionQuestion(request)) {
    return { outcome: "cancel", reason: "interaction_question" };
  }
  return { defer: true, reason: "approve_reads_fail" };
}

export function permissionPromptUnavailableError(message) {
  const error = new Error(message);
  error.name = "PermissionPromptUnavailableError";
  error.code = "PERMISSION_PROMPT_UNAVAILABLE";
  return error;
}

export function isPermissionPromptUnavailable(error) {
  if (!error || typeof error !== "object") return false;
  if (error.code === "PERMISSION_PROMPT_UNAVAILABLE") return true;
  if (error.name === "PermissionPromptUnavailableError") return true;
  return /permission prompt unavailable/i.test(String(error.message ?? ""));
}
