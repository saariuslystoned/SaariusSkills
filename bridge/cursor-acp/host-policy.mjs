import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
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
  const value = firstNonEmpty(explicit, env?.[HOST_CONVERSATION_ENV], fallback);
  if (!value) {
    throw new HostPolicyError(
      "HOST_CONVERSATION_REQUIRED",
      "Live ACP delegate requires one parent conversation id (hostConversationId or SAARIUS_ACP_HOST_CONVERSATION_ID)",
    );
  }
  return normalizeHostIdentity(value, "hostConversationId", "INVALID_HOST_CONVERSATION");
}

export function resolveBinderId(explicit, env = process.env, fallback) {
  const value = firstNonEmpty(explicit, env?.[BINDER_ENV], fallback, env?.USER, "local");
  return normalizeHostIdentity(value, "binderId", "INVALID_BINDER");
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
  if (existing.binderId === SYSTEM_BINDER_ID || existing.binderId === binderId) {
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

export async function claimConversationBind(bindingsRoot, record, { now, atomicWrite } = {}) {
  const existing = await loadConversationBind(bindingsRoot, record.hostConversationId);
  assertRebindAllowed(existing, record.binderId);
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
  const target = conversationBindPath(bindingsRoot, record.hostConversationId);
  if (atomicWrite) await atomicWrite(target, serialized);
  else await writeFile(target, serialized, { encoding: "utf8", mode: 0o600 });
  return next;
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
