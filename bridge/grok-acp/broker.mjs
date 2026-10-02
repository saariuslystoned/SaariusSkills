import { inspectProcessIdentity, compareProcessStartTimes } from "../acp-runtime/process-identity.mjs";
export { inspectProcessIdentity } from "../acp-runtime/process-identity.mjs";
import { createProcessLifecycleTracker, isUnsupportedBackendSessionClose,
  publicWorkerIdentity, captureJobWorkers, lifecycleReceipt, brokerProcessLifecycle } from "../acp-runtime/lifecycle.mjs";
import { recoverConversation } from "../acp-runtime/recovery.mjs";
import { accessSync, constants, statSync } from "node:fs";
import { access, appendFile, link, lstat, mkdir, open, readFile, readdir, readlink, rename, rm, stat, symlink, writeFile } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import { homedir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import path from "node:path";
import { promisify } from "node:util";
import { execFile as execFileCallback } from "node:child_process";
import {
  createAcpRuntime,
  createAgentRegistry,
} from "acpx/runtime";
import {
  ADMISSION_STATE_BOUND,
  ADMISSION_STATE_RELEASED,
  ADMISSION_STATE_STARTING,
  ADMISSION_STATE_STARTED,
  ADMISSION_STATE_UNSTARTED,
  HostPolicyError,
  claimConversationBind,
  classifyConversationAdmission,
  decideConversationRebind,
  isPermissionPromptUnavailable,
  livePermissionDecision,
  permissionPromptUnavailableError,
  resolveConversationIdentity,
  describeLivePermissionMode,
  resolveLivePermissionMode,
} from "./host-policy.mjs";

const execFile = promisify(execFileCallback);

export const DEFAULT_GROK_COMMAND = "grok";
export const DEFAULT_GROK_ARGV = Object.freeze(["agent", "stdio"]);
export const DEFAULT_GROK_MODEL = "grok-4.7";
// Omitted model prefers the advertised default, then these alternatives in order.
// A caller-supplied fallbackModels list replaces this pair; an empty list disables alternatives.
export const DEFAULT_GROK_FALLBACK_MODELS = Object.freeze(["grok-4.6", "grok-4.5"]);
export const MAX_GROK_FALLBACK_MODELS = 2;
// Pin reasoning effort for delegated jobs so a user's interactive CLI default
// (for example `xhigh` in ~/.grok/config.toml) does not leak into bounded work.
export const DEFAULT_GROK_REASONING_EFFORT = "high";
export const GROK_REASONING_EFFORTS = Object.freeze(["low", "medium", "high", "xhigh"]);
// `grok agent stdio` ignores the --reasoning-effort CLI flag; the effort is an
// ACP session config option (id "reasoning_effort", category "thought_level").
const REASONING_OPTION_ID = "reasoning_effort";
export const ACPX_GROK_AGENT = "grok-build";
export const MIN_TIMEOUT_MS = 1_000;
export const DEFAULT_TIMEOUT_MS = 3_600_000;
export const MAX_TIMEOUT_MS = 14_400_000;
// ACpx constructor timeout covers session connect/close, not the job turn.
// Keep it at the previous 10-minute control-plane budget.
export const RUNTIME_CONTROL_TIMEOUT_MS = 10 * 60 * 1000;
export const MAX_PROMPT_CHARS = 20_000;
export const MAX_STEER_CHARS = 8_000;

export function timeoutMsZod(z) {
  return z.number().int().min(MIN_TIMEOUT_MS).max(MAX_TIMEOUT_MS).optional();
}

export function grokModelZod(z) {
  return z.string().min(1).optional();
}

export function grokFallbackModelsZod(z) {
  return z.array(z.string().min(1)).max(MAX_GROK_FALLBACK_MODELS).optional();
}

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "needs-input"]);
const JOB_ID_PATTERN = /^[0-9a-f-]{36}$/i;
const OWNER_ID_MAX_CHARS = 80;
const JOB_LOCK_TIMEOUT_MS = 5_000;
const JOB_LOCK_RETRY_MS = 15;
const OWNER_HEARTBEAT_MS = 5_000;
const OWNER_OBSERVE_WAIT_SLICE_MS = 250;

const BRIDGE_SYSTEM_PROMPT = [
  "You are Grok ACP acting as a bounded implementation worker.",
  "Work only inside the explicitly supplied workspace.",
  "Do not access credentials, auth logs, .env files, private keys, or files outside that workspace.",
  "Do not push, deploy, send external messages, change accounts, spend money, or install global tools.",
  "Make only the requested bounded implementation change and run only relevant local checks.",
  "The parent agent owns decisions and independent review; do not broaden the task.",
  "Finish with a concise handoff naming changed files, commit SHA if one exists, tests/proof run, and remaining risks.",
].join(" ");

export class BridgeError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "BridgeError";
    this.code = code;
    this.details = details;
  }
}

export function toBridgeError(error) {
  if (error instanceof BridgeError) return error;
  if (error instanceof HostPolicyError) {
    return new BridgeError(error.code, error.message, error.details);
  }
  return error;
}

export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.has(status);
}

function isCleanupReady(job) {
  return ["completed", "recovered"].includes(job?.cleanup?.status);
}

function isCanonicalComplete(job) {
  return isTerminalStatus(job?.status) && (
    isCleanupReady(job)
  );
}

async function inspectConversationRebind(broker, existing) {
  const isActive = broker.active.has(existing.jobId);
  let job;
  try {
    job = await broker.getJob(existing.jobId);
  } catch {
    return decideConversationRebind({
      classification: { kind: "unreadable" },
      isActive,
    });
  }
  return decideConversationRebind({
    classification: classifyConversationAdmission(job),
    isActive,
    ownerState: classifyOwnerIdentity(job.owner, await broker.probeOwner(job.owner)),
    jobTerminal: isTerminalStatus(job.status),
    cleanupComplete: isCleanupReady(job),
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isSqliteBusy(error) {
  return error?.code === "ERR_SQLITE_BUSY" ||
    (error?.code === "ERR_SQLITE_ERROR" && /database is locked/i.test(error?.message ?? ""));
}

function isSafeOwnerId(brokerId) {
  return typeof brokerId === "string" &&
    brokerId.length > 0 &&
    brokerId.length <= OWNER_ID_MAX_CHARS &&
    /^[0-9A-Za-z_-]+$/.test(brokerId);
}

export function isCompleteOwnerIdentity(owner) {
  return Boolean(
    owner &&
      isSafeOwnerId(owner.brokerId) &&
      Number.isInteger(owner.pid) &&
      owner.pid > 0 &&
      typeof owner.startTime === "string" &&
      owner.startTime.trim().length > 0,
  );
}

export function ownerIdentitiesMatch(left, right) {
  if (!isCompleteOwnerIdentity(left) || !isCompleteOwnerIdentity(right)) return false;
  return left.brokerId === right.brokerId &&
    left.pid === right.pid &&
    left.startTime === right.startTime;
}

export function classifyOwnerIdentity(owner, probe) {
  if (!isCompleteOwnerIdentity(owner)) return "unknown";
  if (!probe || probe.status === "error" || probe.status === "unknown") return "unknown";
  if (probe.status === "missing") return "dead";
  if (probe.status !== "alive") return "unknown";
  if (typeof probe.startTime !== "string" || probe.startTime.trim().length === 0) {
    return "unknown";
  }
  const comparison = compareProcessStartTimes(owner.startTime, probe.startTime);
  return comparison === "matching" ? "live" : comparison === "different" ? "reused" : "unknown";
}

export function shouldRecoverOwnedJob(job, lease, probe) {
  if (!job || isTerminalStatus(job.status)) return false;
  if (!ownerIdentitiesMatch(job.owner, lease)) return false;
  const state = classifyOwnerIdentity(job.owner, probe);
  return state === "dead" || state === "reused";
}


export function hashText(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function defaultBinderIdForStateRoot(stateRoot) {
  return `state-${hashText(path.resolve(stateRoot)).slice(0, 32)}`;
}

function hasNonEmptyEnvironmentValue(env, key) {
  return typeof env?.[key] === "string" && env[key].trim().length > 0;
}

function assertNoAmbientGrokApiKey(processEnv) {
  if (hasNonEmptyEnvironmentValue(processEnv, "XAI_API_KEY") ||
      hasNonEmptyEnvironmentValue(process.env, "XAI_API_KEY")) {
    throw new BridgeError(
      "AMBIENT_API_KEY_BLOCKED",
      "Grok ACP requires local login; ambient XAI_API_KEY is not permitted",
    );
  }
}

function isExecutableRegularFile(candidate) {
  try {
    const info = statSync(candidate);
    if (!info.isFile()) return false;
    accessSync(candidate, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

export function resolveGrokExecutable({ grokExecutable, env = process.env } = {}) {
  const configured = (grokExecutable ?? env.GROK_EXECUTABLE ?? "").trim();
  if (configured) return path.resolve(configured);
  const command = process.platform === "win32" ? "grok.exe" : DEFAULT_GROK_COMMAND;
  for (const dir of (env.PATH ?? "").split(path.delimiter)) {
    if (!dir) continue;
    const candidate = path.join(dir, command);
    if (isExecutableRegularFile(candidate)) return candidate;
  }
  return DEFAULT_GROK_COMMAND;
}

function advertisedGrokModelIds(availableModelIds) {
  if (!Array.isArray(availableModelIds)) return [];
  return availableModelIds.filter((modelId) => typeof modelId === "string");
}

function freezeSelectionPolicy(policy) {
  if (policy.kind === "explicit") {
    return Object.freeze({ kind: "explicit", model: policy.model });
  }
  return Object.freeze({
    kind: "default",
    preferred: policy.preferred,
    alternatives: Object.freeze([...policy.alternatives]),
  });
}

export function assertExactGrokModelId(value, label = "model") {
  if (typeof value !== "string" || value.length === 0 || value.length > 200 || value !== value.trim() || value.includes("\0")) {
    throw new BridgeError("INVALID_MODEL", `${label} must be a nonempty exact Grok model id`);
  }
  return value;
}

export function resolveRequestedGrokModel(requestedModel, availableModelIds) {
  const advertised = advertisedGrokModelIds(availableModelIds);
  if (advertised.includes(requestedModel)) return requestedModel;
  throw new BridgeError(
    "MODEL_UNAVAILABLE",
    `Grok ACP did not advertise the required model ${requestedModel}`,
    { availableModelCount: advertised.length, availableModelIds: advertised },
  );
}

export function validateGrokFallbackModels(fallbackModels) {
  if (!Array.isArray(fallbackModels) || fallbackModels.length > MAX_GROK_FALLBACK_MODELS) {
    throw new BridgeError(
      "INVALID_FALLBACK_MODELS",
      "fallbackModels must be an array of at most two exact Grok model ids",
    );
  }
  const ids = [];
  for (const [index, value] of fallbackModels.entries()) {
    try {
      ids.push(assertExactGrokModelId(value, `fallbackModels[${index}]`));
    } catch (error) {
      if (error instanceof BridgeError && error.code === "INVALID_MODEL") {
        throw new BridgeError("INVALID_FALLBACK_MODELS", error.message);
      }
      throw error;
    }
  }
  if (new Set(ids).size !== ids.length || ids.includes(DEFAULT_GROK_MODEL)) {
    throw new BridgeError(
      "INVALID_FALLBACK_MODELS",
      "fallbackModels must be unique exact ids and must not repeat the default grok-4.7",
    );
  }
  return ids;
}

// Explicit model is strict. Omitted model uses grok-4.7, then the active alternatives.
// An explicit constructor pin stays strict until a per-job model or fallbackModels is supplied.
export function resolveGrokSelectionPolicy({
  requestedModel,
  fallbackModels,
  constructorModel,
  constructorPinned = false,
} = {}) {
  if (requestedModel === null || fallbackModels === null) {
    throw new BridgeError("INVALID_MODEL", "model and fallbackModels must be omitted or valid; null is not a selection");
  }
  const explicit = requestedModel !== undefined;
  const hasFallbacks = fallbackModels !== undefined;
  if (explicit && hasFallbacks) {
    throw new BridgeError(
      "FALLBACK_PINNED",
      "Explicit model stays exact; omit model to configure fallbackModels",
    );
  }
  if (explicit) {
    return freezeSelectionPolicy({ kind: "explicit", model: assertExactGrokModelId(requestedModel) });
  }
  if (hasFallbacks) {
    return freezeSelectionPolicy({
      kind: "default",
      preferred: DEFAULT_GROK_MODEL,
      alternatives: validateGrokFallbackModels(fallbackModels),
    });
  }
  if (constructorPinned) {
    return freezeSelectionPolicy({
      kind: "explicit",
      model: assertExactGrokModelId(constructorModel, "constructor model"),
    });
  }
  return freezeSelectionPolicy({
    kind: "default",
    preferred: DEFAULT_GROK_MODEL,
    alternatives: [...DEFAULT_GROK_FALLBACK_MODELS],
  });
}

export function resolveGrokModelChoice(policy, availableModelIds) {
  const advertised = advertisedGrokModelIds(availableModelIds);
  if (policy?.kind === "explicit") {
    const selectedModelId = resolveRequestedGrokModel(policy.model, advertised);
    return {
      selectedModelId,
      requestedModel: policy.model,
      selectionPolicy: policy,
      usedDefaultAlternative: false,
    };
  }
  const preferred = policy?.preferred ?? DEFAULT_GROK_MODEL;
  const alternatives = Array.isArray(policy?.alternatives) ? policy.alternatives : [...DEFAULT_GROK_FALLBACK_MODELS];
  const chain = [preferred, ...alternatives];
  const selectedModelId = chain.find((modelId) => advertised.includes(modelId));
  if (!selectedModelId) {
    throw new BridgeError(
      "MODEL_UNAVAILABLE",
      `Grok ACP did not advertise any allowed model (${chain.join(", ")})`,
      {
        availableModelCount: advertised.length,
        availableModelIds: advertised,
        requestedModel: null,
        selectionPolicy: policy ?? null,
      },
    );
  }
  return {
    selectedModelId,
    requestedModel: null,
    selectionPolicy: policy,
    usedDefaultAlternative: selectedModelId !== preferred,
  };
}

export function redactSensitive(value) {
  let text = String(value ?? "");
  text = text.replace(
    /-----BEGIN [^-]+ PRIVATE KEY-----[\s\S]*?-----END [^-]+ PRIVATE KEY-----/gi,
    "[redacted private key]",
  );
  text = text.replace(
    /\b(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret)\b\s*[:=]\s*Bearer\s+[A-Za-z0-9._~+/=-]+/gi,
    "$1=[redacted]",
  );
  text = text.replace(
    /\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|authorization)\b\s*[:=]\s*[^\s,;]+/gi,
    "$1=[redacted]",
  );
  text = text.replace(
    /\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,})\b/g,
    "[redacted token]",
  );
  text = text.replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]");
  return text;
}

export function safeMessage(value, maxChars = 320) {
  const text = redactSensitive(value).replace(/\s+/g, " ").trim();
  return text.length > maxChars ? `${text.slice(0, maxChars - 1)}…` : text;
}

function defaultStateRoot() {
  const configured = process.env.SAARIUS_GROK_ACP_STATE_DIR?.trim();
  if (configured) return path.resolve(configured);
  const pluginData = process.env.PLUGIN_DATA?.trim();
  if (pluginData) return path.resolve(pluginData, "grok-acp");
  return path.join(homedir(), ".local", "state", "saarius-skills", "grok-acp-delegation");
}

function assertJobId(jobId) {
  if (typeof jobId !== "string" || !JOB_ID_PATTERN.test(jobId)) {
    throw new BridgeError("INVALID_JOB_ID", "jobId must be a UUID returned by grok_acp_delegate");
  }
}

function assertBoundedText(value, field, maxChars) {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new BridgeError("INVALID_INPUT", `${field} must be a non-empty string`);
  }
  if (value.includes("\u0000")) {
    throw new BridgeError("INVALID_INPUT", `${field} contains an invalid NUL character`);
  }
  if (value.length > maxChars) {
    throw new BridgeError("INVALID_INPUT", `${field} exceeds the ${maxChars}-character limit`);
  }
  return value.trim();
}

function parseTimeout(value) {
  if (value === undefined) return DEFAULT_TIMEOUT_MS;
  if (!Number.isInteger(value) || value < MIN_TIMEOUT_MS || value > MAX_TIMEOUT_MS) {
    throw new BridgeError(
      "INVALID_INPUT",
      `timeoutMs must be an integer between ${MIN_TIMEOUT_MS} and ${MAX_TIMEOUT_MS}`,
    );
  }
  return value;
}

function parseWait(value, max = 300_000) {
  if (value === undefined) return 0;
  if (!Number.isInteger(value) || value < 0 || value > max) {
    throw new BridgeError("INVALID_INPUT", `waitMs must be an integer between 0 and ${max}`);
  }
  return value;
}

async function requireDirectory(value, field, { defaultValue } = {}) {
  const candidate = value === undefined ? defaultValue : value;
  if (typeof candidate !== "string" || !path.isAbsolute(candidate)) {
    throw new BridgeError("INVALID_WORKSPACE", `${field} must be an absolute directory path`);
  }
  const resolved = path.resolve(candidate);
  let info;
  try {
    info = await stat(resolved);
  } catch (error) {
    throw new BridgeError("WORKSPACE_UNAVAILABLE", `${field} is not accessible`, {
      cause: safeMessage(error?.message),
    });
  }
  if (!info.isDirectory()) {
    throw new BridgeError("INVALID_WORKSPACE", `${field} must name a directory`);
  }
  return resolved;
}

async function atomicWrite(filePath, contents) {
  const temporaryPath = `${filePath}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporaryPath, contents, { encoding: "utf8", mode: 0o600 });
  await rename(temporaryPath, filePath);
}

async function writeCompleteFile(filePath, contents) {
  const handle = await open(filePath, "w", 0o600);
  try {
    await handle.writeFile(contents, { encoding: "utf8" });
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function removeDetachedReclaim(detachedPath) {
  await rm(detachedPath, { recursive: true, force: true });
}

async function removeDetachedReclaimGeneration(reclaimPath, detachedPath) {
  let targetPath;
  try {
    targetPath = await readlink(detachedPath);
  } catch {
    // A legacy directory fence has no generation target to validate.
    await removeDetachedReclaim(detachedPath);
    return;
  }
  const resolvedTarget = path.resolve(path.dirname(detachedPath), targetPath);
  const reclaimPrefix = `${path.resolve(reclaimPath)}.`;
  const token = resolvedTarget.startsWith(reclaimPrefix) ? resolvedTarget.slice(reclaimPrefix.length) : null;
  let permitted = false;
  if (token && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(token)) {
    try {
      const stats = await lstat(resolvedTarget);
      if (stats.isDirectory() && !stats.isSymbolicLink()) {
        const owner = JSON.parse(await readFile(path.join(resolvedTarget, "owner.json"), "utf8"));
        permitted = owner?.reclaimToken === token;
      }
    } catch {
      // Preserve unrecognized, malformed, or missing generation targets.
    }
  }
  await removeDetachedReclaim(detachedPath);
  if (permitted) await rm(resolvedTarget, { recursive: true, force: true });
}

async function inspectReclaimTarget(reclaimPath) {
  let targetPath;
  try {
    targetPath = await readlink(reclaimPath);
  } catch (error) {
    if (error?.code === "EINVAL" || error?.code === "ENOENT") return null;
    throw error;
  }
  const resolvedTarget = path.resolve(path.dirname(reclaimPath), targetPath);
  try {
    await lstat(resolvedTarget);
    return { exists: true, path: resolvedTarget };
  } catch (error) {
    if (error?.code === "ENOENT") return { exists: false, path: resolvedTarget };
    throw error;
  }
}

async function inspectLockFile(lockPath) {
  try {
    const raw = await readFile(lockPath, "utf8");
    try {
      const holder = JSON.parse(raw);
      if (!holder || typeof holder !== "object") return { status: "unreadable" };
      return { status: "readable", holder };
    } catch {
      return { status: "unreadable" };
    }
  } catch (error) {
    if (error?.code === "ENOENT") return { status: "missing" };
    return { status: "unreadable" };
  }
}

function lockHoldersMatch(left, right) {
  if (!left || !right) return false;
  if (typeof left.token === "string" && left.token && left.token === right.token) return true;
  return left.brokerId === right.brokerId &&
    left.pid === right.pid &&
    left.startTime === right.startTime;
}

async function releaseOwnedLockFile(lockPath, token) {
  try {
    const inspection = await inspectLockFile(lockPath);
    if (inspection.status === "readable" && inspection.holder?.token === token) {
      await rm(lockPath, { force: true });
    }
  } catch {
    // Fail-safe: never delete a lock we cannot prove we still own.
  }
}

// SAARIUS_GROK_ACP_REASONING_EFFORT: one of GROK_REASONING_EFFORTS, or
// "inherit" to omit the flag and use the Grok CLI's own configured default.
export function resolveReasoningEffort(env = process.env) {
  const value = env.SAARIUS_GROK_ACP_REASONING_EFFORT?.trim().toLowerCase();
  if (!value) return DEFAULT_GROK_REASONING_EFFORT;
  if (value === "inherit") return null;
  if (!GROK_REASONING_EFFORTS.includes(value)) {
    throw new BridgeError(
      "INVALID_CONFIG",
      `SAARIUS_GROK_ACP_REASONING_EFFORT must be one of ${GROK_REASONING_EFFORTS.join(", ")} or inherit`,
    );
  }
  return value;
}

function routeSummary(executable, model, reasoningEffort, selection = null) {
  return {
    agent: "grok-build",
    transport: "acp",
    executable,
    argv: [executable, "agent", "stdio"],
    model,
    reasoningEffort: reasoningEffort ?? "inherited",
    requestedModel: selection?.requestedModel ?? null,
    selectionPolicy: selection?.selectionPolicy ?? null,
    usedDefaultAlternative: Boolean(selection?.usedDefaultAlternative),
  };
}

function publicHandle(handle) {
  return {
    sessionKey: handle?.sessionKey,
    backend: handle?.backend,
    runtimeSessionName: handle?.runtimeSessionName,
    cwd: handle?.cwd,
    acpxRecordId: handle?.acpxRecordId,
    backendSessionId: handle?.backendSessionId,
    agentSessionId: handle?.agentSessionId,
  };
}

function modelSnapshot(status) {
  const models = status?.models ?? {};
  return {
    currentModelId: models.currentModelId,
    availableModelIds: Array.isArray(models.availableModelIds) ? models.availableModelIds : [],
    availableModels: Array.isArray(models.availableModels) ? models.availableModels : undefined,
  };
}

function reasoningOption(status) {
  const options = status?.details?.configOptions;
  if (!Array.isArray(options)) return undefined;
  return options.find((o) => o?.id === REASONING_OPTION_ID) ?? options.find((o) => o?.category === "thought_level");
}

function reasoningEffortFromStatus(status, requested) {
  const option = reasoningOption(status);
  const available = Array.isArray(option?.options) ? option.options.map((o) => o?.value).filter(Boolean) : [];
  if (!requested) {
    return { requested: "inherit", current: option?.currentValue ?? null, available };
  }
  if (!option) {
    throw new BridgeError(
      "REASONING_EFFORT_UNSUPPORTED",
      "Grok ACP did not advertise a reasoning_effort option; set SAARIUS_GROK_ACP_REASONING_EFFORT=inherit to use the CLI default",
    );
  }
  if (!available.includes(requested)) {
    throw new BridgeError("REASONING_EFFORT_UNAVAILABLE", `Grok ACP does not offer reasoning effort ${requested}`, {
      requested,
      available,
    });
  }
  if (option.currentValue !== requested) {
    throw new BridgeError("REASONING_EFFORT_UNCONFIRMED", `Grok ACP did not confirm reasoning effort ${requested}`, {
      requested,
      current: option.currentValue ?? null,
    });
  }
  return { requested, current: option.currentValue, available };
}

function publicModel(model) {
  const availableModelIds = advertisedGrokModelIds(model?.availableModelIds);
  const availableModels = Array.isArray(model?.availableModels) ? model.availableModels : [];
  return {
    reasoningEffort: model?.reasoningEffort,
    requestedModel: model?.requestedModel ?? null,
    selectionPolicy: model?.selectionPolicy ?? null,
    selectedModelId: model?.selectedModelId ?? null,
    usedDefaultAlternative: Boolean(model?.usedDefaultAlternative),
    currentModelId: model?.currentModelId ?? null,
    availableModelIds,
    availableModels,
    availableModelCount: availableModelIds.length,
    matchingModelIds: model?.selectedModelId ? [model.selectedModelId] : [],
  };
}

function selectionRouteModel(policy) {
  return policy?.kind === "explicit" ? policy.model : policy?.preferred ?? DEFAULT_GROK_MODEL;
}

function selectionText(job) {
  const policy = job.modelBinding?.selectionPolicy ?? job.request?.selectionPolicy;
  if (policy?.kind === "explicit") return `explicit ${policy.model}`;
  if (policy?.kind === "default") {
    const alternatives = policy.alternatives?.length ? policy.alternatives.join(", ") : "(none)";
    return `default ${policy.preferred}, then ${alternatives}`;
  }
  return "unspecified";
}

function alternativeText(job) {
  if (!job.modelBinding) return "unselected";
  return job.modelBinding.usedDefaultAlternative ? "selected" : "not used";
}

function selectionReceipt(policy, choice = null) {
  return {
    requestedModel: choice?.requestedModel ?? (policy?.kind === "explicit" ? policy.model : null),
    selectionPolicy: choice?.selectionPolicy ?? policy ?? null,
    usedDefaultAlternative: Boolean(choice?.usedDefaultAlternative),
  };
}

function safeError(error, fallbackCode = "BRIDGE_ERROR") {
  if (error instanceof BridgeError) {
    return {
      code: error.code,
      message: safeMessage(error.message),
      details: error.details && Object.keys(error.details).length ? error.details : undefined,
    };
  }
  return {
    code: typeof error?.code === "string" ? error.code : fallbackCode,
    message: safeMessage(error?.message ?? error),
  };
}

function classifyFailure(error, interaction) {
  const safe = safeError(error);
  const lower = `${safe.code} ${safe.message}`.toLowerCase();
  if (interaction?.permissionDenied || isPermissionPromptUnavailable(error) || safe.code === "PERMISSION_PROMPT_UNAVAILABLE") {
    return {
      status: "failed",
      error: {
        code: "PERMISSION_PROMPT_UNAVAILABLE",
        message: "Live MCP approve-reads failed a write or exec that would prompt. approve-all is an explicit break-glass, not the default.",
      },
    };
  }
  if (
    interaction?.elicitation ||
    lower.includes("elicitation") ||
    lower.includes("login") ||
    lower.includes("authenticate") ||
    lower.includes("authentication") ||
    lower.includes("permission") ||
    lower.includes("approval")
  ) {
    return {
      status: "needs-input",
      error: {
        code: "INPUT_REQUIRED",
        message: "Grok ACP needs an interactive login, permission, or elicitation response.",
      },
    };
  }
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return {
      status: "failed",
      error: { code: "TIMEOUT", message: "Grok ACP exceeded the bounded job timeout." },
    };
  }
  return { status: "failed", error: safe };
}

export function createDefaultRuntime({
  stateRoot,
  grokExecutable,
  timeoutMs = RUNTIME_CONTROL_TIMEOUT_MS,
  processEnv = process.env,
  processLifecycle,
}) {
  assertNoAmbientGrokApiKey(processEnv);
  const registry = createAgentRegistry({
    overrides: { "grok-build": [grokExecutable, "agent", "stdio"] },
  });
  // acpx session records contain full conversation messages. Keep those
  // internal records ephemeral; only the broker's bounded control proof is
  // durable. Restart never resumes a previous model session. In-flight jobs
  // are failed closed only when their exact owner identity is demonstrably
  // gone: missing/dead, or proven PID reuse after complete matching job and
  // lease identities plus a definite process start-time mismatch. The same
  // contract is applied by status/result observations of a nonterminal job;
  // there is no generic periodic recovery service.
  const sessions = new Map();
  const permission = resolveLivePermissionMode(processEnv);
  const runtime = createAcpRuntime({
    cwd: stateRoot,
    sessionStore: {
      async load(id) {
        const record = sessions.get(id);
        return record === undefined ? undefined : structuredClone(record);
      },
      async save(record) {
        sessions.set(record.acpxRecordId, structuredClone(record));
      },
    },
    agentRegistry: registry,
    // Live MCP copies OpenClaw's ACP-host default: approve-reads + fail.
    // approve-all is an explicit SAARIUS_ACP_PERMISSION_MODE break-glass.
    // One-path allow_once stays on the candidate Puppet controller, not here.
    permissionMode: permission.permissionMode,
    nonInteractivePermissions: permission.nonInteractivePermissions,
    agentProcessEnv: { XAI_API_KEY: "" },
    timeoutMs,
    processLifecycle,
  });
  const shutdown = runtime.shutdown.bind(runtime);
  runtime.shutdown = async () => {
    try { await shutdown(); }
    finally { sessions.clear(); }
  };
  return runtime;
}

export class GrokAcpBroker {
  constructor(options = {}) {
    this.stateRoot = path.resolve(options.stateRoot ?? defaultStateRoot());
    this.jobsRoot = path.join(this.stateRoot, "jobs");
    this.runsRoot = path.join(this.stateRoot, "runs");
    this.ownersRoot = path.join(this.stateRoot, "owners");
    this.bindingsRoot = path.join(this.stateRoot, "bindings");
    this.processEnv = options.processEnv ?? process.env;
    this.brokerId = options.brokerId ?? randomUUID();
    this.processLifecycleTracker = options.processLifecycleTracker ?? createProcessLifecycleTracker();
    this.workerExitWaitMs = options.workerExitWaitMs ?? 10_000;
    this.defaultHostConversationId = options.defaultHostConversationId ?? null;
    this.defaultBinderId = options.defaultBinderId ?? defaultBinderIdForStateRoot(this.stateRoot);
    this.pid = Number.isInteger(options.pid) && options.pid > 0 ? options.pid : process.pid;
    this.startTime = typeof options.startTime === "string" && options.startTime.trim()
      ? options.startTime.trim()
      : null;
    this.inspectProcess = options.inspectProcess ?? inspectProcessIdentity;
    this.onJobLockPrepared = options.onJobLockPrepared ?? null;
    this.onAdmissionBoundary = options.onAdmissionBoundary;
    this.grokExecutable = resolveGrokExecutable({
      grokExecutable: options.grokExecutable,
      env: this.processEnv,
    });
    // An explicit constructor model is a strict pin. Omitting it keeps the
    // advertised grok-4.7, then grok-4.6, then grok-4.5 policy. Per-job model
    // or fallbackModels can override the pin; jobs never write this.model.
    this.modelPinned = options.model !== undefined && options.model !== null;
    this.model = this.modelPinned ? options.model : DEFAULT_GROK_MODEL;
    this.reasoningEffort = options.reasoningEffort !== undefined
      ? options.reasoningEffort
      : resolveReasoningEffort(this.processEnv);
    this.defaultWorkspace = options.defaultWorkspace ?? process.cwd();
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.runtimeControlTimeoutMs = options.runtimeControlTimeoutMs ?? RUNTIME_CONTROL_TIMEOUT_MS;
    this.execFile = options.execFile ?? execFile;
    this.idFactory = options.idFactory ?? randomUUID;
    this.now = options.now ?? (() => new Date().toISOString());
    this.runtime =
      options.runtime ??
      (options.runtimeFactory
        ? options.runtimeFactory({
            stateRoot: this.stateRoot,
            grokExecutable: this.grokExecutable,
            model: this.model,
            reasoningEffort: this.reasoningEffort,
            timeoutMs: this.runtimeControlTimeoutMs,
            processEnv: this.processEnv,
            processLifecycle: brokerProcessLifecycle(this),
          })
        : createDefaultRuntime({
            stateRoot: this.stateRoot,
            grokExecutable: this.grokExecutable,
            timeoutMs: this.runtimeControlTimeoutMs,
            processEnv: options.processEnv ?? process.env,
            processLifecycle: brokerProcessLifecycle(this),
          }));
    this.active = new Map();
    this.changeWaiters = new Map();
    this.initPromise = null;
    this.heartbeatTimer = null;
  }

  ownerIdentity() {
    return {
      brokerId: this.brokerId,
      pid: this.pid,
      startTime: this.startTime,
    };
  }

  conversationIdentity(input = {}) {
    try {
      return resolveConversationIdentity(input, this.processEnv, {
        defaultHostConversationId: this.defaultHostConversationId,
        defaultBinderId: this.defaultBinderId,
      });
    } catch (error) {
      throw toBridgeError(error);
    }
  }

  async bindConversation({ hostConversationId, binderId, jobId, workspace }) {
    try {
      return await claimConversationBind(
        this.bindingsRoot,
        { hostConversationId, binderId, jobId, workspace },
        {
          now: this.now,
          atomicWrite,
          owner: this.ownerIdentity(),
          inspectOwner: (owner) => this.inspectProcess(owner.pid),
          inspectExisting: (existing) => inspectConversationRebind(this, existing),
        },
      );
    } catch (error) {
      if (
        error?.code === "CONVERSATION_REBIND_UNSAFE" &&
        error.details?.reason === "previous_job_cleanup_unproven" &&
        error.details?.workspace === workspace
      ) {
        throw new BridgeError(
          "WORKSPACE_CLEANUP_PENDING",
          "A prior job in this workspace still has unresolved terminal cleanup; wait for observed cleanup or owner-controlled recovery before replacing the session.",
          error.details,
        );
      }
      throw toBridgeError(error);
    }
  }

  async closeAdmissionHandle(handle, reason) {
    if (!handle || !this.runtime?.close) return;
    try {
      await this.runtime.close({
        handle,
        reason,
        discardPersistentState: true,
      });
    } catch {
      // Admission failures must not hide the readiness refusal.
    }
  }

  async persistAdmission(job, state) {
    job.admission = {
      ...(job.admission ?? {}),
      state,
    };
    await this.saveJob(job);
    if (typeof this.onAdmissionBoundary === "function") {
      await this.onAdmissionBoundary(state, job);
    }
  }

  async confirmAdmissionWorkerReleased(handle, reason, startupAttempted = false) {
    if (!handle) return !startupAttempted;
    if (typeof this.runtime?.close !== "function") return false;
    try {
      await this.runtime.close({
        handle,
        reason,
        discardPersistentState: true,
      });
      return true;
    } catch {
      return false;
    }
  }

  async releaseAdmission(job, handle, cause) {
    const startupAttempted = [ADMISSION_STATE_STARTING, ADMISSION_STATE_STARTED]
      .includes(job?.admission?.state);
    const released = await this.confirmAdmissionWorkerReleased(
      handle,
      "delegate admission failed",
      startupAttempted,
    );
    if (!job?.jobId) return;
    let current;
    try {
      current = await this.getJob(job.jobId);
    } catch {
      return;
    }
    current.error = {
      code: cause?.code ?? "ADMISSION_FAILED",
      message: safeMessage(cause?.message ?? "ACP admission failed before the job became runnable"),
    };
    if (!released) {
      await this.saveJob(current).catch(() => undefined);
      return;
    }
    current.status = "failed";
    current.admission = {
      ...(current.admission ?? job.admission ?? {}),
      state: ADMISSION_STATE_RELEASED,
      releasedAt: this.now(),
    };
    current.cleanup = {
      status: "completed",
      observed: handle ? "admission_handle_closed" : "admission_unstarted",
    };
    delete current.handle;
    try {
      await this.saveJob(current);
      if (current.proof?.events) {
        await this.recordEvent(current, "admission_released", {
          observed: current.cleanup.observed,
        });
      }
    } catch {
      // Leave the already-durable job/bind records for the next owner probe.
    }
  }

  async init() {
    if (!this.initPromise) {
      this.initPromise = (async () => {
        await mkdir(this.jobsRoot, { recursive: true, mode: 0o700 });
        await mkdir(this.runsRoot, { recursive: true, mode: 0o700 });
        await mkdir(this.ownersRoot, { recursive: true, mode: 0o700 });
        await mkdir(this.bindingsRoot, { recursive: true, mode: 0o700 });
        if (this.startTime == null) {
          const self = await this.inspectProcess(this.pid);
          if (self.status === "alive" && self.startTime) this.startTime = self.startTime;
        }
        await this.writeOwnerLease();
        this.startOwnerHeartbeat();
        await this.recoverStaleJobs();
        return this;
      })().catch((error) => {
        this.initPromise = null;
        throw error;
      });
    }
    return this.initPromise;
  }

  async recoverStaleJobs() {
    let names;
    try {
      names = await readdir(this.jobsRoot);
    } catch {
      return;
    }
    for (const name of names) {
      if (!name.endsWith(".json")) continue;
      await this.recoverJobFile(name);
    }
  }

  async recoverJobFile(name) {
    let snapshot;
    try {
      snapshot = JSON.parse(await readFile(path.join(this.jobsRoot, name), "utf8"));
    } catch {
      return;
    }
    await this.recoverOwnedJobIfEligible(snapshot);
  }

  async recoverObservedJob(jobId) {
    const snapshot = await this.readJobRecord(jobId);
    if (!snapshot) return;
    await this.recoverOwnedJobIfEligible(snapshot);
  }

  async recoverOwnedJobIfEligible(snapshot) {
    if (!snapshot?.jobId || !JOB_ID_PATTERN.test(snapshot.jobId)) return;
    if (isTerminalStatus(snapshot.status)) return;
    const lease = await this.readOwnerLease(snapshot.owner?.brokerId);
    const probe = await this.probeOwner(snapshot.owner);
    if (!shouldRecoverOwnedJob(snapshot, lease, probe)) return;
    await this.withJobLock(snapshot.jobId, async () => {
      const job = await this.readJobRecord(snapshot.jobId);
      if (!job || isTerminalStatus(job.status)) return;
      const confirmedLease = await this.readOwnerLease(job.owner?.brokerId);
      const confirmed = await this.probeOwner(job.owner);
      if (!shouldRecoverOwnedJob(job, confirmedLease, confirmed)) return;
      const previousStatus = job.status;
      job.status = "failed";
      job.updatedAt = this.now();
      job.error = {
        code: "BRIDGE_RESTARTED",
        message: "The owning broker is gone; task interrupted. Worker cleanup is unproven. Inspect exact ownership before explicit recovery and retry.",
      };
      await this.writeJobRecord(job);
      if (job.proof?.events) await this.recordEvent(job, "bridge_restarted", { previousStatus });
      this.notifyChange(job.jobId);
    }, { skipOnTimeout: true });
  }

  async probeOwner(owner) {
    if (!isCompleteOwnerIdentity(owner)) return { status: "unknown" };
    return this.inspectProcess(owner.pid);
  }

  ownerLeasePath(brokerId) {
    if (!isSafeOwnerId(brokerId)) return null;
    return path.join(this.ownersRoot, `${brokerId}.json`);
  }

  async readOwnerLease(brokerId) {
    const leasePath = this.ownerLeasePath(brokerId);
    if (!leasePath) return null;
    try {
      const lease = JSON.parse(await readFile(leasePath, "utf8"));
      return isCompleteOwnerIdentity(lease) ? lease : null;
    } catch {
      return null;
    }
  }

  async writeOwnerLease({ released = false } = {}) {
    const leasePath = this.ownerLeasePath(this.brokerId);
    if (!leasePath) return;
    await mkdir(this.ownersRoot, { recursive: true, mode: 0o700 });
    const record = {
      schema: "saarius.grok-acp.owner.v1",
      ...this.ownerIdentity(),
      heartbeatAt: this.now(),
      released,
    };
    await atomicWrite(leasePath, `${JSON.stringify(record, null, 2)}\n`);
  }

  startOwnerHeartbeat() {
    if (this.heartbeatTimer) return;
    this.heartbeatTimer = setInterval(() => {
      void this.writeOwnerLease().catch(() => undefined);
    }, OWNER_HEARTBEAT_MS);
    this.heartbeatTimer.unref?.();
  }

  async close() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    try {
      await this.writeOwnerLease({ released: true });
    } catch {
      // Best effort. Process identity remains the recovery source of truth.
    }
    for (const [jobId, active] of this.active) {
      try {
        await active.turn?.cancel({ reason: "bridge shutdown" });
      } catch {
        // Best effort. The runtime owns process cleanup.
      }
      this.active.delete(jobId);
    }
    await this.runtime.shutdown?.();
  }

  async checkExecutable() {
    try {
      await access(this.grokExecutable, constants.X_OK);
    } catch {
      throw new BridgeError(
        "EXECUTABLE_MISSING",
        `Grok executable is not executable: ${this.grokExecutable}`,
      );
    }
    try {
      const version = await this.execFile(this.grokExecutable, ["--version"], {
        cwd: this.stateRoot,
        timeout: 5_000,
        maxBuffer: 128 * 1024,
        encoding: "utf8",
      });
      await this.execFile(this.grokExecutable, ["agent", "stdio", "--help"], {
        cwd: this.stateRoot,
        timeout: 5_000,
        maxBuffer: 128 * 1024,
        encoding: "utf8",
      });
      return {
        executable: this.grokExecutable,
        version: safeMessage(version?.stdout ?? version?.stderr ?? "unknown", 160),
        acpHelp: true,
      };
    } catch (error) {
      throw new BridgeError("ACP_UNAVAILABLE", "Grok ACP preflight failed", {
        cause: safeMessage(error?.message),
      });
    }
  }

  selectionPolicy({ model, fallbackModels } = {}) {
    return resolveGrokSelectionPolicy({
      requestedModel: model,
      fallbackModels,
      constructorModel: this.model,
      constructorPinned: this.modelPinned,
    });
  }

  readinessFailure(error, policy, executable, workspace, permission) {
    const failure = safeError(error, "READINESS_FAILED");
    const details = failure.details ?? {};
    const catalogIds = Array.isArray(details.availableModelIds) ? details.availableModelIds : null;
    const modelReport = catalogIds
      ? publicModel({
          availableModelIds: catalogIds,
          availableModels: details.availableModels,
          currentModelId: details.currentModelId ?? null,
          requestedModel: policy?.kind === "explicit" ? policy.model : null,
          selectionPolicy: policy ?? details.selectionPolicy ?? null,
          selectedModelId: null,
          usedDefaultAlternative: false,
        })
      : undefined;
    return {
      ready: false,
      catalogReady: Boolean(catalogIds),
      selectionReady: false,
      route: routeSummary(
        this.grokExecutable,
        selectionRouteModel(policy),
        this.reasoningEffort,
        selectionReceipt(policy),
      ),
      executable,
      workspace,
      permission,
      ...(modelReport ? { model: modelReport } : {}),
      error: failure,
      note: "Readiness did not send a model turn.",
    };
  }

  async discover({ workspace, model, fallbackModels } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace", {
      defaultValue: this.defaultWorkspace,
    });
    const permission = describeLivePermissionMode(this.processEnv);
    let policy;
    try {
      policy = this.selectionPolicy({ model, fallbackModels });
    } catch (error) {
      return this.readinessFailure(error, null, undefined, targetWorkspace, permission);
    }
    const executable = await this.checkExecutable();
    const sessionKey = `grok-acp-probe:${this.idFactory()}`;
    let handle;
    try {
      handle = await this.runtime.ensureSession({
        sessionKey,
        agent: "grok-build",
        mode: "oneshot",
        cwd: targetWorkspace,
      });
      const models = await this.verifyModel(handle, targetWorkspace, policy);
      return {
        ready: true,
        catalogReady: true,
        selectionReady: true,
        route: routeSummary(this.grokExecutable, models.selectedModelId, this.reasoningEffort, models),
        executable,
        workspace: targetWorkspace,
        permission,
        model: publicModel(models),
        session: publicHandle(handle),
        note: "Readiness opened and closed an ACP session without sending a model turn.",
      };
    } catch (error) {
      return this.readinessFailure(error, policy, executable, targetWorkspace, permission);
    } finally {
      if (handle) {
        try {
          await this.runtime.close({
            handle,
            reason: "readiness probe complete",
            discardPersistentState: true,
          });
        } catch {
          // A readiness failure must not hide the primary diagnostic.
        }
      }
    }
  }

  async confirmExactModel(handle, selectedModelId, snapshot) {
    let models = snapshot ?? modelSnapshot(await this.runtime.getStatus({ handle }));
    const advertised = advertisedGrokModelIds(models.availableModelIds);
    const catalog = {
      requestedModel: selectedModelId,
      selectedModelId,
      currentModelId: models.currentModelId ?? null,
      availableModelIds: advertised,
      availableModels: Array.isArray(models.availableModels) ? models.availableModels : [],
      renegotiated: false,
    };
    if (!advertised.includes(selectedModelId)) {
      throw new BridgeError(
        "MODEL_UNAVAILABLE",
        `Grok ACP did not advertise the required model ${selectedModelId}`,
        catalog,
      );
    }
    if (models.currentModelId !== selectedModelId) {
      if (typeof this.runtime.setModel !== "function") {
        throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime cannot set the selected Grok model", catalog);
      }
      await this.runtime.setModel({ handle, model: selectedModelId });
      models = modelSnapshot(await this.runtime.getStatus({ handle }));
      catalog.currentModelId = models.currentModelId ?? null;
      catalog.availableModelIds = advertisedGrokModelIds(models.availableModelIds);
      catalog.availableModels = Array.isArray(models.availableModels) ? models.availableModels : [];
    }
    if (models.currentModelId !== selectedModelId || !catalog.availableModelIds.includes(selectedModelId)) {
      throw new BridgeError(
        "MODEL_SELECTION_UNCONFIRMED",
        `Grok ACP did not confirm selected model ${selectedModelId}`,
        catalog,
      );
    }
    return models;
  }

  async verifyModel(handle, workspace, policy = this.selectionPolicy()) {
    if (typeof this.runtime.getStatus !== "function") {
      throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not expose model status");
    }
    let models;
    try {
      models = modelSnapshot(await this.runtime.getStatus({ handle }));
    } catch (error) {
      if (error instanceof BridgeError) throw error;
      throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not return model status", {
        cause: safeMessage(error?.message),
      });
    }
    let choice;
    try {
      choice = resolveGrokModelChoice(policy, models.availableModelIds);
    } catch (error) {
      if (error instanceof BridgeError) {
        error.details = {
          ...error.details,
          currentModelId: models.currentModelId ?? null,
          availableModelIds: advertisedGrokModelIds(models.availableModelIds),
          availableModels: Array.isArray(models.availableModels) ? models.availableModels : [],
        };
      }
      throw error;
    }
    const confirmed = await this.confirmExactModel(handle, choice.selectedModelId, models);
    let reasoningEffort;
    try {
      reasoningEffort = await this.applyReasoningEffort(handle);
    } catch (error) {
      if (error instanceof BridgeError && !Array.isArray(error.details?.availableModelIds)) {
        error.details = {
          ...(error.details ?? {}),
          availableModelIds: advertisedGrokModelIds(confirmed.availableModelIds),
          availableModels: Array.isArray(confirmed.availableModels) ? confirmed.availableModels : [],
          currentModelId: confirmed.currentModelId ?? null,
        };
      }
      throw error;
    }
    return {
      ...confirmed,
      requestedModel: choice.requestedModel,
      selectedModelId: choice.selectedModelId,
      selectionPolicy: choice.selectionPolicy,
      usedDefaultAlternative: choice.usedDefaultAlternative,
      workspace,
      reasoningEffort,
    };
  }

  bindModelChoice(job, models) {
    job.modelBinding = Object.freeze({
      requestedModel: models.requestedModel ?? null,
      selectedModelId: models.selectedModelId,
      selectionPolicy: models.selectionPolicy,
      usedDefaultAlternative: Boolean(models.usedDefaultAlternative),
    });
    job.model = models;
    job.request.selectedModelId = models.selectedModelId;
    job.request.usedDefaultAlternative = job.modelBinding.usedDefaultAlternative;
  }

  async recheckBoundModel(handle, job) {
    const bound = job.modelBinding;
    if (typeof bound?.selectedModelId !== "string" || bound.selectedModelId.length === 0) {
      throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Job has no bound Grok model", { renegotiated: false });
    }
    const models = await this.confirmExactModel(handle, bound.selectedModelId);
    try {
      await this.applyReasoningEffort(handle);
    } catch (error) {
      if (error instanceof BridgeError && !Array.isArray(error.details?.availableModelIds)) {
        error.details = {
          ...(error.details ?? {}),
          availableModelIds: advertisedGrokModelIds(models.availableModelIds),
          availableModels: Array.isArray(models.availableModels) ? models.availableModels : [],
          currentModelId: models.currentModelId ?? null,
        };
      }
      throw error;
    }
    const coherent = await this.inspectPrePromptInvariant(handle, bound.selectedModelId);
    job.model = {
      ...job.model,
      currentModelId: coherent.currentModelId,
      availableModelIds: coherent.availableModelIds,
      availableModels: coherent.availableModels,
      requestedModel: bound.requestedModel,
      selectedModelId: bound.selectedModelId,
      selectionPolicy: bound.selectionPolicy,
      usedDefaultAlternative: bound.usedDefaultAlternative,
      reasoningEffort: coherent.reasoningEffort,
    };
    return coherent;
  }

  async inspectPrePromptInvariant(handle, selectedModelId) {
    if (typeof this.runtime.getStatus !== "function") {
      throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not expose model status");
    }
    let status;
    try {
      status = await this.runtime.getStatus({ handle });
    } catch (error) {
      if (error instanceof BridgeError) throw error;
      throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not return model status", {
        cause: safeMessage(error?.message),
      });
    }
    const models = modelSnapshot(status);
    const advertised = advertisedGrokModelIds(models.availableModelIds);
    const catalog = {
      requestedModel: selectedModelId,
      selectedModelId,
      currentModelId: models.currentModelId ?? null,
      availableModelIds: advertised,
      availableModels: Array.isArray(models.availableModels) ? models.availableModels : [],
      renegotiated: false,
    };
    if (!advertised.includes(selectedModelId)) {
      throw new BridgeError(
        "MODEL_UNAVAILABLE",
        `Grok ACP did not advertise the required model ${selectedModelId}`,
        catalog,
      );
    }
    if (models.currentModelId !== selectedModelId) {
      throw new BridgeError(
        "MODEL_SELECTION_UNCONFIRMED",
        `Grok ACP did not confirm selected model ${selectedModelId}`,
        catalog,
      );
    }
    let reasoningEffort;
    try {
      reasoningEffort = reasoningEffortFromStatus(status, this.reasoningEffort);
    } catch (error) {
      if (error instanceof BridgeError && !Array.isArray(error.details?.availableModelIds)) {
        error.details = {
          ...(error.details ?? {}),
          availableModelIds: advertised,
          availableModels: catalog.availableModels,
          currentModelId: catalog.currentModelId,
        };
      }
      throw error;
    }
    return { ...models, availableModelIds: advertised, reasoningEffort };
  }

  async applyReasoningEffort(handle) {
    let status = await this.runtime.getStatus({ handle });
    let option = reasoningOption(status);
    if (!this.reasoningEffort) {
      return reasoningEffortFromStatus(status, null);
    }
    const available = Array.isArray(option?.options) ? option.options.map((o) => o?.value).filter(Boolean) : [];
    if (!option) {
      throw new BridgeError(
        "REASONING_EFFORT_UNSUPPORTED",
        "Grok ACP did not advertise a reasoning_effort option; set SAARIUS_GROK_ACP_REASONING_EFFORT=inherit to use the CLI default",
      );
    }
    if (!available.includes(this.reasoningEffort)) {
      throw new BridgeError("REASONING_EFFORT_UNAVAILABLE", `Grok ACP does not offer reasoning effort ${this.reasoningEffort}`, {
        requested: this.reasoningEffort,
        available,
      });
    }
    if (option.currentValue !== this.reasoningEffort) {
      if (typeof this.runtime.setConfigOption !== "function") {
        throw new BridgeError("REASONING_EFFORT_UNCONFIRMED", "Runtime cannot set ACP session config options");
      }
      await this.runtime.setConfigOption({ handle, key: option.id, value: this.reasoningEffort });
      status = await this.runtime.getStatus({ handle });
    }
    return reasoningEffortFromStatus(status, this.reasoningEffort);
  }

  async delegate({ workspace, prompt, timeoutMs, hostConversationId, binderId, model, fallbackModels } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace");
    const policy = this.selectionPolicy({ model, fallbackModels });
    const conversation = this.conversationIdentity({ hostConversationId, binderId });
    const taskPrompt = assertBoundedText(prompt, "prompt", MAX_PROMPT_CHARS);
    const boundedTimeout = timeoutMs === undefined ? this.timeoutMs : parseTimeout(timeoutMs);
    const requestedSelection = selectionReceipt(policy);
    try {
      await this.checkExecutable();
    } catch (error) {
      throw toBridgeError(error);
    }

    const jobId = this.idFactory();
    const sessionKey = `grok-acp:${jobId}`;
    const runDir = path.join(this.runsRoot, jobId);
    const job = {
      schema: "saarius.grok-acp.job.v1",
      jobId,
      status: "admitted",
      createdAt: this.now(),
      updatedAt: this.now(),
      route: routeSummary(this.grokExecutable, selectionRouteModel(policy), this.reasoningEffort, requestedSelection),
      workspace: targetWorkspace,
      timeoutMs: boundedTimeout,
      request: {
        promptSha256: hashText(taskPrompt),
        promptChars: taskPrompt.length,
        requestedModel: requestedSelection.requestedModel,
        fallbackModels: policy.kind === "default" ? [...policy.alternatives] : null,
        selectionPolicy: policy,
      },
      // Issue #92: the submission receipt carries the resolved permission
      // policy so a cockpit sees approve-reads before the first write fails.
      permission: describeLivePermissionMode(this.processEnv),
      owner: this.ownerIdentity(),
      admission: {
        state: ADMISSION_STATE_UNSTARTED,
        hostConversationId: conversation.hostConversationId,
        binderId: conversation.binderId,
      },
      sessionKey,
      runDir,
      proof: {
        state: path.join(runDir, "STATE.md"),
        events: path.join(runDir, "events.jsonl"),
        proof: path.join(runDir, "PROOF.md"),
      },
    };
    await mkdir(runDir, { recursive: true, mode: 0o700 });
    let handle;
    try {
      await this.persistAdmission(job, ADMISSION_STATE_UNSTARTED);
      await this.recordEvent(job, "admitted", {
        hostConversationId: conversation.hostConversationId,
        binderId: conversation.binderId,
        workspace: targetWorkspace,
      });
      const binding = await this.bindConversation({
        ...conversation,
        jobId,
        workspace: targetWorkspace,
      });
      job.binding = binding;
      await this.persistAdmission(job, ADMISSION_STATE_BOUND);
      await this.persistAdmission(job, ADMISSION_STATE_STARTING);
      handle = await this.runtime.ensureSession({
        sessionKey,
        agent: "grok-build",
        mode: "persistent",
        cwd: targetWorkspace,
        sessionOptions: {
          systemPrompt: { append: BRIDGE_SYSTEM_PROMPT },
        },
      });
      const models = await this.verifyModel(handle, targetWorkspace, policy);
      this.bindModelChoice(job, models);
      job.route = routeSummary(this.grokExecutable, models.selectedModelId, this.reasoningEffort, models);
      job.handle = publicHandle(handle);
      await captureJobWorkers(this, job, handle);
      job.status = "submitted";
      await this.persistAdmission(job, ADMISSION_STATE_STARTED);
      await this.recordEvent(job, "submitted", {
        promptSha256: job.request.promptSha256,
        permissionMode: job.permission.permissionMode,
        workspace: targetWorkspace,
        hostConversationId: binding.hostConversationId,
        binderId: binding.binderId,
        selectedModelId: job.modelBinding.selectedModelId,
        usedDefaultAlternative: job.modelBinding.usedDefaultAlternative,
      });
      const promise = Promise.resolve()
        .then(() => this.runJob(job, taskPrompt, { handle }))
        .catch(() => undefined);
      this.active.set(jobId, { promise, handle });
      return this.publicJob(job);
    } catch (error) {
      await this.releaseAdmission(job, handle, error);
      throw toBridgeError(error);
    }
  }

  async runJob(job, taskPrompt, prepared = {}) {
    let handle = prepared.handle;
    let turn;
    const interaction = { permission: false, elicitation: false, permissionDenied: false };
    let finalText = "";
    let eventCount = 0;
    let toolCallCount = 0;
    try {
      job.status = "running";
      job.startedAt = this.now();
      await this.saveAndRecord(job, "running", { workspace: job.workspace });
      if (!handle) {
        await this.persistAdmission(job, ADMISSION_STATE_STARTING);
        handle = await this.runtime.ensureSession({
          sessionKey: job.sessionKey,
          agent: "grok-build",
          mode: "persistent",
          cwd: job.workspace,
          sessionOptions: {
            systemPrompt: { append: BRIDGE_SYSTEM_PROMPT },
          },
        });
        job.handle = publicHandle(handle);
        await captureJobWorkers(this, job, handle);
      }
      await this.recheckBoundModel(handle, job);
      await this.saveJob(job);
      await this.recordEvent(job, "model_confirmed", {
        selectedModelId: job.modelBinding.selectedModelId,
        currentModelId: job.model.currentModelId,
        usedDefaultAlternative: job.modelBinding.usedDefaultAlternative,
        availableModelIds: job.model.availableModelIds,
      });

      turn = this.runtime.startTurn({
        handle,
        text: taskPrompt,
        mode: "prompt",
        requestId: jobIdFrom(job),
        timeoutMs: job.timeoutMs,
        onPermissionRequest: async (request) => {
          const decision = livePermissionDecision(request);
          if (decision.outcome === "cancel") {
            interaction.permission = true;
            return { outcome: "cancel" };
          }
          // Returning undefined delegates the non-interaction decision to the
          // pinned runtime's configured approve-reads/approve-all policy.
          // The bridge must not turn a runtime-managed permission result into
          // a synthetic prompt-unavailable failure.
          return undefined;
        },
        onElicitation: async () => {
          interaction.elicitation = true;
          return { action: "cancel" };
        },
      });
      this.active.set(job.jobId, { promise: this.active.get(job.jobId)?.promise, handle, turn });
      await turn.promptStarted;
      await this.recordEvent(job, "prompt_started", { requestId: jobIdFrom(job) });

      const eventsPromise = this.consumeEvents(turn.events, async (event) => {
        eventCount += 1;
        if (event?.type === "tool_call") toolCallCount += 1;
        if (event?.type === "text_delta" && event.stream !== "thought") {
          finalText = `${finalText}${String(event.text ?? "")}`.slice(-12_000);
        }
        if (event?.type === "status") {
          job.lastEventTag = event.tag;
        }
      });
      const result = await turn.result;
      await eventsPromise;
      job.eventCount = eventCount;
      job.toolCallCount = toolCallCount;
      job.updatedAt = this.now();
      if (result?.status === "completed") {
        job.status = "completed";
        job.handoff = compactHandoff(finalText);
        job.stopReason = safeMessage(result.stopReason ?? "completed", 120);
        await this.saveAndRecord(job, "completed", {
          stopReason: job.stopReason,
          eventCount,
          toolCallCount,
        });
      } else if (result?.status === "cancelled") {
        job.status = "cancelled";
        job.handoff = "Grok ACP cancelled the active turn.";
        await this.saveAndRecord(job, "cancelled", { eventCount, toolCallCount });
      } else {
        const failure = classifyFailure(
          new BridgeError(
            result?.error?.code ?? "ACP_TURN_FAILED",
            result?.error?.message ?? "Grok ACP turn failed",
          ),
          interaction,
        );
        job.status = failure.status;
        job.error = failure.error;
        await this.saveAndRecord(job, failure.status, { eventCount, toolCallCount });
      }
    } catch (error) {
      const failure = classifyFailure(error, interaction);
      job.status = failure.status;
      job.error = failure.error;
      job.updatedAt = this.now();
      await this.saveAndRecord(job, failure.status, {
        eventCount,
        toolCallCount,
      });
    } finally {
      if (handle && isTerminalStatus(job.status)) await this.closeRuntimeSession(job, handle);
      this.notifyChange(job.jobId);
      if (isTerminalStatus(job.status)) this.active.delete(job.jobId);
    }
    return this.publicJob(job);
  }

  async recoverConversation(input) {
    return recoverConversation(this, input, claimConversationBind, atomicWrite);
  }

  async closeRuntimeSession(job, handle) {
    job.cleanup = {
      status: "pending",
      observed: "runtime_close_started",
      at: this.now(),
    };
    await this.saveJob(job);
    if (!this.runtime?.close) {
      job.cleanup = { ...job.cleanup, status: "uncertain", observed: "runtime_close_unavailable", at: this.now() };
      await this.saveJob(job);
      return;
    }
    try {
      await this.runtime.close({
        handle,
        reason: `job ${job.status} terminal cleanup`,
        discardPersistentState: true,
      });
      job.cleanup = { ...job.cleanup, status: "completed", observed: "runtime_close_returned", at: this.now() };
    } catch (error) {
      const proof = isUnsupportedBackendSessionClose(error)
        ? await this.processLifecycleTracker.waitForOwnedExit(handle?.sessionKey, { timeoutMs: this.workerExitWaitMs })
        : null;
      if (proof?.status === "exited") {
        job.cleanup = {
          ...job.cleanup, status: "completed",
          observed: "local_worker_terminated_backend_session_discard_unsupported",
          backendSessionDiscard: "unsupported",
          workers: proof.exits.map(publicWorkerIdentity), at: this.now(),
        };
        await this.saveJob(job);
        return;
      }
      job.cleanup = {
        ...job.cleanup,
        status: "uncertain",
        observed: "runtime_close_failed",
        message: safeMessage(error?.message),
        at: this.now(),
      };
    }
    await this.saveJob(job);
  }

  async consumeEvents(events, onEvent) {
    try {
      for await (const event of events) await onEvent(event);
    } catch (error) {
      throw new BridgeError("ACP_EVENT_STREAM_FAILED", safeMessage(error?.message));
    }
  }

  async getJob(jobId) {
    assertJobId(jobId);
    try {
      const raw = await readFile(path.join(this.jobsRoot, `${jobId}.json`), "utf8");
      return JSON.parse(raw);
    } catch (error) {
      if (error?.code === "ENOENT") throw new BridgeError("JOB_NOT_FOUND", `Unknown job ${jobId}`);
      throw new BridgeError("JOB_STATE_INVALID", "Job state could not be read");
    }
  }

  async status({ jobId, waitMs } = {}) {
    const boundedWait = parseWait(waitMs, 10_000);
    let job = await this.observeJob(jobId);
    if (boundedWait > 0 && !isTerminalStatus(job.status)) {
      await this.waitForChange(jobId, boundedWait);
      job = await this.observeJob(jobId);
    }
    return this.publicJob(job);
  }

  async result({ jobId, waitMs } = {}) {
    const boundedWait = parseWait(waitMs, 300_000);
    let job = await this.observeJob(jobId);
    if (boundedWait > 0 && !isCanonicalComplete(job)) {
      await this.waitForTerminal(jobId, boundedWait);
      job = await this.observeJob(jobId);
    }
    return {
      ...this.publicJob(job),
      taskComplete: isTerminalStatus(job.status),
      cleanupReady: isCleanupReady(job),
      complete: isCanonicalComplete(job),
      waitExpired: !isCanonicalComplete(job) && boundedWait > 0,
    };
  }

  async observeJob(jobId) {
    const job = await this.getJob(jobId);
    if (isTerminalStatus(job.status) || this.active.has(jobId)) return job;
    await this.recoverObservedJob(jobId);
    return this.getJob(jobId);
  }

  async steer({ jobId, message } = {}) {
    assertBoundedText(message, "message", MAX_STEER_CHARS);
    const job = await this.getJob(jobId);
    if (job.status !== "running") {
      throw new BridgeError("JOB_NOT_RUNNING", `Job ${jobId} is ${job.status}; steering is unavailable`);
    }
    const active = this.active.get(jobId);
    if (!active?.handle || !active.turn) {
      throw new BridgeError(
        "JOB_NOT_ACTIVE",
        "The bridge has no active ACP turn for this job; resubmit explicitly instead of replacing the session",
      );
    }
    // acpx 0.19.4 serializes startTurn calls for a session. Its mode: "steer"
    // therefore queues a new model turn rather than steering the active one.
    // Launching it here would outlive the original job's result/cancel owner.
    throw new BridgeError(
      "STEERING_UNSUPPORTED",
      "The pinned ACP runtime cannot steer an active turn. Wait for the job's terminal result, then explicitly delegate a bounded follow-up.",
    );
  }

  async cancel({ jobId, reason } = {}) {
    const job = await this.getJob(jobId);
    if (isTerminalStatus(job.status)) return { ...this.publicJob(job), cancellationRequested: false };
    const active = this.active.get(jobId);
    if (!active?.handle || !active.turn) {
      throw new BridgeError(
        "JOB_NOT_ACTIVE",
        "The bridge has no active ACP turn for this job; cancellation is fail-closed",
      );
    }
    const safeReason = reason ? safeMessage(reason, 200) : "cancelled by parent agent";
    job.cancelRequested = true;
    job.cancelReason = safeReason;
    await this.saveAndRecord(job, "cancel_requested", { reason: safeReason });
    await active.turn.cancel({ reason: safeReason });
    return {
      jobId,
      status: "cancellation-requested",
      route: job.route,
      model: job.model?.selectedModelId ?? job.model?.currentModelId ?? job.route.model,
    };
  }

  async saveJob(job) {
    if (job.owner?.brokerId === this.brokerId) await captureJobWorkers(this, job, job.handle);
    await this.withJobLock(job.jobId, async () => {
      await this.writeJobRecord(job);
    });
  }

  async readJobRecord(jobId) {
    try {
      return JSON.parse(await readFile(path.join(this.jobsRoot, `${jobId}.json`), "utf8"));
    } catch (error) {
      if (error?.code === "ENOENT") return null;
      throw new BridgeError("JOB_STATE_INVALID", "Job state could not be read");
    }
  }

  async writeJobRecord(job) {
    if (!job.owner) job.owner = this.ownerIdentity();
    job.updatedAt = job.updatedAt ?? this.now();
    await atomicWrite(path.join(this.jobsRoot, `${job.jobId}.json`), `${JSON.stringify(job, null, 2)}\n`);
    if (job.proof?.state) {
      await mkdir(path.dirname(job.proof.state), { recursive: true, mode: 0o700 });
      await this.writeState(job);
    }
  }

  jobLockPath(jobId) {
    return path.join(this.jobsRoot, `${jobId}.json.lock`);
  }

  async withJobLock(jobId, fn, { timeoutMs = JOB_LOCK_TIMEOUT_MS, skipOnTimeout = false } = {}) {
    const lockPath = this.jobLockPath(jobId);
    const reclaimPath = `${lockPath}.reclaim`;
    const deadline = Date.now() + timeoutMs;
    let token;
    let uniquePath;
    while (true) {
      token = randomUUID();
      uniquePath = `${lockPath}.${token}`;
      const payload = `${JSON.stringify({ ...this.ownerIdentity(), token })}\n`;
      await writeCompleteFile(uniquePath, payload);
      if (this.onJobLockPrepared) {
        await this.onJobLockPrepared({ jobId, lockPath, uniquePath, token, payload });
      }
      try {
        await link(uniquePath, lockPath);
      } catch (error) {
        await rm(uniquePath, { force: true });
        uniquePath = null;
        if (error?.code !== "EEXIST") throw error;
        if (Date.now() >= deadline) {
          if (skipOnTimeout) return undefined;
          throw new BridgeError("JOB_LOCK_TIMEOUT", `Timed out locking job ${jobId}`);
        }
        const inspection = await inspectLockFile(lockPath);
        if (inspection.status === "missing") continue;
        if (inspection.status === "unreadable") {
          await this.reclaimJobLock(lockPath, reclaimPath, { observed: null, unreadable: true });
          continue;
        }
        const holderState = classifyOwnerIdentity(inspection.holder, await this.probeOwner(inspection.holder));
        if (holderState === "dead" || holderState === "reused") {
          await this.reclaimJobLock(lockPath, reclaimPath, { observed: inspection.holder, unreadable: false });
          continue;
        }
        await sleep(JOB_LOCK_RETRY_MS);
        continue;
      }
      if (await this.hasOtherLiveLockHolder(lockPath, token)) {
        await releaseOwnedLockFile(lockPath, token);
        await rm(uniquePath, { force: true });
        uniquePath = null;
        if (Date.now() >= deadline) {
          if (skipOnTimeout) return undefined;
          throw new BridgeError("JOB_LOCK_TIMEOUT", `Timed out locking job ${jobId}`);
        }
        await sleep(JOB_LOCK_RETRY_MS);
        continue;
      }
      break;
    }
    try {
      return await fn();
    } finally {
      if (uniquePath) await rm(uniquePath, { force: true });
      await releaseOwnedLockFile(lockPath, token);
    }
  }

  async reclaimJobLock(lockPath, reclaimPath, { observed, unreadable }) {
    const acquired = await this.tryAcquireLockReclaim(reclaimPath);
    if (!acquired) {
      await sleep(JOB_LOCK_RETRY_MS);
      return;
    }
    try {
      const current = await inspectLockFile(lockPath);
      if (unreadable) {
        if (current.status === "unreadable") await rm(lockPath, { force: true });
        return;
      }
      if (current.status !== "readable" || !lockHoldersMatch(current.holder, observed)) return;
      const holderState = classifyOwnerIdentity(current.holder, await this.probeOwner(current.holder));
      if (holderState === "dead" || holderState === "reused") {
        await rm(lockPath, { force: true });
      }
    } finally {
      await this.releaseLockReclaim(reclaimPath, acquired);
    }
  }

  async tryAcquireLockReclaim(reclaimPath) {
    const mutex = this.acquireLockReclaimMutex(reclaimPath);
    if (!mutex) return null;
    try {
      return await this.tryAcquireLockReclaimWithMutex(reclaimPath);
    } finally {
      this.releaseLockReclaimMutex(mutex);
    }
  }

  acquireLockReclaimMutex(reclaimPath) {
    const mutexPath = `${reclaimPath}.mutex.sqlite`;
    let database;
    try {
      database = new DatabaseSync(mutexPath);
      database.exec("PRAGMA busy_timeout = 0");
      database.exec("CREATE TABLE IF NOT EXISTS reclaim_mutex (id INTEGER PRIMARY KEY CHECK (id = 1))");
      database.exec("BEGIN IMMEDIATE");
      return database;
    } catch (error) {
      database?.close();
      if (isSqliteBusy(error)) return null;
      throw error;
    }
  }

  async waitForLockReclaimMutex(reclaimPath) {
    while (true) {
      const mutex = this.acquireLockReclaimMutex(reclaimPath);
      if (mutex) return mutex;
      await sleep(JOB_LOCK_RETRY_MS);
    }
  }

  releaseLockReclaimMutex(database) {
    try {
      database.exec("ROLLBACK");
    } finally {
      database.close();
    }
  }

  async tryAcquireLockReclaimWithMutex(reclaimPath) {
    const token = randomUUID();
    const uniqueReclaim = `${reclaimPath}.${token}`;
    let keepGeneration = false;
    try {
      await mkdir(uniqueReclaim);
        await writeCompleteFile(
          path.join(uniqueReclaim, "owner.json"),
          `${JSON.stringify({ ...this.ownerIdentity(), reclaimToken: token })}\n`,
        );
        try {
          await symlink(uniqueReclaim, reclaimPath, "dir");
          keepGeneration = true;
          return { token, uniquePath: uniqueReclaim };
        } catch {
          await rm(uniqueReclaim, { recursive: true, force: true });
        }
        let holder;
        let state;
        try {
          holder = JSON.parse(await readFile(path.join(reclaimPath, "owner.json"), "utf8"));
          state = classifyOwnerIdentity(holder, await this.probeOwner(holder));
        } catch {
          // Unreadable reclaim fences are fail-closed. Only a symlink whose
          // generation target is genuinely absent may be cleaned up here.
          try {
            const target = await inspectReclaimTarget(reclaimPath);
            if (target?.exists === false) {
              const detachedPath = `${reclaimPath}.stale.${randomUUID()}`;
              await rename(reclaimPath, detachedPath);
              await rm(detachedPath, { recursive: true, force: true });
            }
          } catch (error) {
            if (error?.code !== "ENOENT") throw error;
          }
          return null;
        }
        if (state === "dead" || state === "reused") {
          const detachedPath = `${reclaimPath}.stale.${randomUUID()}`;
          try {
            await rename(reclaimPath, detachedPath);
          } catch (error) {
            if (error?.code === "ENOENT") return null;
            throw error;
          }
          await removeDetachedReclaimGeneration(reclaimPath, detachedPath);
        }
        return null;
    } finally {
      if (!keepGeneration) await rm(uniqueReclaim, { recursive: true, force: true });
    }
  }

  async releaseLockReclaim(reclaimPath, fence) {
    if (!fence || typeof fence !== "object" || !fence.uniquePath) return;
    const mutex = await this.waitForLockReclaimMutex(reclaimPath);
    try {
      await rm(fence.uniquePath, { recursive: true, force: true });
    } finally {
      this.releaseLockReclaimMutex(mutex);
    }
  }

  async hasOtherLiveLockHolder(lockPath, token) {
    const directory = path.dirname(lockPath);
    const prefix = `${path.basename(lockPath)}.`;
    let names;
    try {
      names = await readdir(directory);
    } catch {
      return false;
    }
    for (const name of names) {
      if (!name.startsWith(prefix)) continue;
      if (name.endsWith(".tmp") || name.endsWith(".reclaim") || name.includes(".reclaim.")) continue;
      const suffix = name.slice(prefix.length);
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(suffix)) continue;
      if (suffix === token) continue;
      try {
        const holder = JSON.parse(await readFile(path.join(directory, name), "utf8"));
        const state = classifyOwnerIdentity(holder, await this.probeOwner(holder));
        if (state === "live" || state === "unknown") return true;
      } catch {
        // Unreadable unique tickets are not treated as live holders.
      }
    }
    return false;
  }

  async saveAndRecord(job, status, details = {}) {
    job.status = status;
    job.updatedAt = this.now();
    await this.saveJob(job);
    await this.recordEvent(job, status, details);
    this.notifyChange(job.jobId);
  }

  async recordEvent(job, event, details = {}) {
    const entry = {
      timestamp: this.now(),
      event,
      jobId: job.jobId,
      details: redactObject(details),
    };
    await appendFile(job.proof.events, `${JSON.stringify(entry)}\n`, { encoding: "utf8", mode: 0o600 });
    await writeFile(path.join(job.runDir, "heartbeat"), `${entry.timestamp}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
    if (isTerminalStatus(job.status)) await this.writeProof(job);
  }

  async writeState(job) {
    const lines = [
      `# Grok ACP job ${job.jobId}`,
      "",
      `Status: ${job.status}`,
      `Workspace: ${job.workspace}`,
      `Route: ${(job.route.argv ?? [job.route.executable, "agent", "stdio"]).join(" ")}`,
      `Requested model: ${job.modelBinding?.requestedModel ?? job.request?.requestedModel ?? "omitted"}`,
      `Selection: ${selectionText(job)}`,
      `Selected model: ${job.modelBinding?.selectedModelId ?? job.model?.selectedModelId ?? "unselected"}`,
      `Default alternative: ${alternativeText(job)}`,
      `Owner: ${job.owner?.brokerId ?? "unknown"}`,
      `Updated: ${job.updatedAt}`,
      "",
      "The request body is intentionally not persisted; only its SHA-256 and character count are recorded.",
    ];
    await atomicWrite(job.proof.state, `${lines.join("\n")}\n`);
  }

  async writeProof(job) {
    const lines = [
      `# Grok ACP job ${job.jobId}`,
      "",
      `Outcome: ${job.status}`,
      `Workspace: ${job.workspace}`,
      `Executable: ${job.route.executable}`,
      `Model: ${job.modelBinding?.selectedModelId ?? job.model?.selectedModelId ?? job.model?.currentModelId ?? job.route.model}`,
      `Selection: ${selectionText(job)}`,
      `Default alternative: ${alternativeText(job)}`,
      `Prompt SHA-256: ${job.request.promptSha256}`,
      `Events observed: ${job.eventCount ?? 0}`,
      `Tool calls observed: ${job.toolCallCount ?? 0}`,
      "",
      "## Bounded handoff",
      "",
      job.handoff ?? job.error?.message ?? "No handoff was produced.",
    ];
    await atomicWrite(job.proof.proof, `${lines.join("\n")}\n`);
  }

  publicJob(job) {
    const result = {
      ...lifecycleReceipt(job, { terminal: isTerminalStatus(job.status), cleanupReady: isCleanupReady(job), active: this.active.has(job.jobId) }),
      jobId: job.jobId,
      status: job.status,
      route: job.route,
      workspace: job.workspace,
      createdAt: job.createdAt,
      updatedAt: job.updatedAt,
      startedAt: job.startedAt,
      timeoutMs: job.timeoutMs,
      model: job.modelBinding?.selectedModelId ?? job.model?.selectedModelId ?? job.model?.currentModelId ?? job.route.model,
      ...(job.modelBinding ? {
        modelSelection: {
          requestedModel: job.modelBinding.requestedModel,
          selectionPolicy: job.modelBinding.selectionPolicy,
          selectedModelId: job.modelBinding.selectedModelId,
          usedDefaultAlternative: job.modelBinding.usedDefaultAlternative,
          currentModelId: job.model?.currentModelId ?? null,
        },
      } : {}),
      binding: job.binding,
      proof: job.proof,
    };
    if (job.status === "completed" || job.status === "cancelled") result.handoff = job.handoff;
    if (job.permission) result.permission = job.permission;
    if (job.error) result.error = job.error;
    if (job.stopReason) result.stopReason = job.stopReason;
    if (job.cleanup) result.cleanup = job.cleanup;
    if (job.cancelRequested) result.cancelRequested = true;
    return result;
  }

  async waitForChange(jobId, waitMs) {
    const current = this.changeWaiters.get(jobId) ?? new Set();
    this.changeWaiters.set(jobId, current);
    await new Promise((resolve) => {
      const timer = setTimeout(() => {
        current.delete(notify);
        resolve();
      }, waitMs);
      const notify = () => {
        clearTimeout(timer);
        current.delete(notify);
        resolve();
      };
      current.add(notify);
    });
    if (current.size === 0) this.changeWaiters.delete(jobId);
  }

  async waitForTerminal(jobId, waitMs) {
    const deadline = Date.now() + waitMs;
    while (Date.now() < deadline) {
      const job = await this.observeJob(jobId);
      if (isCanonicalComplete(job)) return;
      if (isTerminalStatus(job.status) && (!this.active.has(jobId) || job.cleanup?.status === "uncertain")) return;
      const remaining = deadline - Date.now();
      if (remaining <= 0) return;
      const slice = this.active.has(jobId)
        ? remaining
        : Math.min(remaining, OWNER_OBSERVE_WAIT_SLICE_MS);
      await this.waitForChange(jobId, slice);
    }
  }

  notifyChange(jobId) {
    for (const resolve of this.changeWaiters.get(jobId) ?? []) resolve();
  }
}

function jobIdFrom(job) {
  return job.jobId;
}

function compactHandoff(value) {
  const safe = redactSensitive(value).trim();
  if (!safe) return "Grok ACP completed without a textual handoff.";
  const bounded = safe.length > 2_400 ? `…${safe.slice(-2_399)}` : safe;
  return bounded;
}

function redactObject(value) {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") return safeMessage(value, 500);
  if (Array.isArray(value)) return value.slice(0, 20).map(redactObject);
  if (typeof value !== "object") return value;
  const output = {};
  for (const [key, nested] of Object.entries(value).slice(0, 30)) {
    if (/token|secret|password|credential|authorization|private/i.test(key)) {
      output[key] = "[redacted]";
    } else {
      output[key] = redactObject(nested);
    }
  }
  return output;
}
