import { defaultBinderIdForStateRoot, createProcessLifecycleTracker, isUnsupportedBackendSessionClose,
  publicWorkerIdentity, captureJobWorkers, lifecycleReceipt, brokerProcessLifecycle } from "../acp-runtime/lifecycle.mjs";
import { recoverConversation } from "../acp-runtime/recovery.mjs";
import { constants } from "node:fs";
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

export const DEFAULT_CURSOR_EXECUTABLE = "/Users/bobbybones/.local/bin/cursor-agent";
// Plugin alias for base gpt-5.6-luna plus effort medium. Not a live ACP model id.
export const DEFAULT_CURSOR_MODEL = "gpt-5.6-luna-medium";
export const PREFERRED_DEFAULT_MODEL_BASE = "gpt-5.6-luna";
export const PREFERRED_DEFAULT_EFFORT = "medium";
const EFFORT_KEYS = ["effort", "reasoning_effort", "reasoning"];
const EFFORT_TOKEN = /^[a-z][a-z0-9]{0,15}$/;
const LEGACY_GROK_SELECTOR = /^cursor-grok-4\.6-(low|medium|high|xhigh)$/;
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

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "needs-input"]);
const JOB_ID_PATTERN = /^[0-9a-f-]{36}$/i;
const OWNER_ID_MAX_CHARS = 80;
const JOB_LOCK_TIMEOUT_MS = 5_000;
const JOB_LOCK_RETRY_MS = 15;
const OWNER_HEARTBEAT_MS = 5_000;
const OWNER_OBSERVE_WAIT_SLICE_MS = 250;

const BRIDGE_SYSTEM_PROMPT = [
  "You are Cursor ACP acting as a bounded implementation worker.",
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
  return probe.startTime === owner.startTime ? "live" : "reused";
}

export function shouldRecoverOwnedJob(job, lease, probe) {
  if (!job || isTerminalStatus(job.status)) return false;
  if (!ownerIdentitiesMatch(job.owner, lease)) return false;
  const state = classifyOwnerIdentity(job.owner, probe);
  return state === "dead" || state === "reused";
}

export async function inspectProcessIdentity(pid, exec = execFile) {
  if (!Number.isInteger(pid) || pid <= 0) return { status: "unknown" };
  try {
    process.kill(pid, 0);
  } catch (error) {
    if (error?.code === "ESRCH") return { status: "missing" };
    if (error?.code !== "EPERM") return { status: "unknown" };
  }
  try {
    const { stdout } = await exec("ps", ["-p", String(pid), "-o", "lstart="], {
      encoding: "utf8",
      timeout: 2_000,
      maxBuffer: 4 * 1024,
      env: { LC_ALL: "C", PATH: process.env.PATH ?? "/usr/bin:/bin" },
    });
    const startTime = String(stdout ?? "").trim();
    if (!startTime) return { status: "unknown" };
    return { status: "alive", startTime };
  } catch {
    try {
      process.kill(pid, 0);
      return { status: "unknown" };
    } catch (error) {
      if (error?.code === "ESRCH") return { status: "missing" };
      return { status: "unknown" };
    }
  }
}

export function hashText(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function isOmittedCursorModel(requestedModel) {
  return requestedModel === undefined || requestedModel === null;
}

export function isOmittedCursorEffort(requestedEffort) {
  return requestedEffort === undefined || requestedEffort === null;
}

export function parseCursorModelId(modelId) {
  if (typeof modelId !== "string") {
    return { baseModelId: "", parameters: new Map(), rawParameters: "", duplicateKeys: [] };
  }
  const bracketIndex = modelId.indexOf("[");
  if (bracketIndex === -1 || !modelId.endsWith("]")) {
    return { baseModelId: modelId, parameters: new Map(), rawParameters: "", duplicateKeys: [] };
  }
  const baseModelId = modelId.slice(0, bracketIndex);
  const rawParameters = modelId.slice(bracketIndex + 1, -1);
  const parameters = new Map();
  const duplicateKeys = [];
  if (rawParameters.trim().length > 0) {
    for (const part of rawParameters.split(",")) {
      if (part.trim().length === 0) continue;
      const eq = part.indexOf("=");
      const key = (eq === -1 ? part : part.slice(0, eq)).trim();
      const value = eq === -1 ? "" : part.slice(eq + 1).trim();
      if (!key) continue;
      if (parameters.has(key)) duplicateKeys.push(key);
      parameters.set(key, value);
    }
  }
  return { baseModelId, parameters, rawParameters, duplicateKeys };
}

export function effortFieldsFromModelId(modelId) {
  const parsed = parseCursorModelId(modelId);
  return EFFORT_KEYS.filter((key) => parsed.parameters.has(key)).map((key) => ({
    key,
    value: parsed.parameters.get(key),
  }));
}

export function extractEffortFromModelId(modelId) {
  const fields = effortFieldsFromModelId(modelId);
  if (fields.length === 0) return null;
  const values = new Set(fields.map((field) => field.value));
  if (values.size !== 1) return null;
  const parsed = parseCursorModelId(modelId);
  if (parsed.duplicateKeys.some((key) => EFFORT_KEYS.includes(key))) return null;
  return fields[0].value;
}

export function assertCoherentAdvertisedEffort(modelId) {
  const parsed = parseCursorModelId(modelId);
  const fields = effortFieldsFromModelId(modelId);
  const duplicateEffortKeys = parsed.duplicateKeys.filter((key) => EFFORT_KEYS.includes(key));
  if (duplicateEffortKeys.length > 0) {
    throw new BridgeError(
      "EFFORT_UNSUPPORTED",
      `Advertised model ${modelId} repeats effort fields`,
      { modelId, duplicateEffortKeys },
    );
  }
  if (fields.length === 0) return null;
  const values = [...new Set(fields.map((field) => field.value))];
  if (values.length !== 1 || !EFFORT_TOKEN.test(values[0])) {
    throw new BridgeError(
      "EFFORT_UNSUPPORTED",
      `Advertised model ${modelId} has conflicting or malformed effort fields`,
      { modelId, effortFields: fields },
    );
  }
  return values[0];
}

export function parseDocumentedCursorSelector(requestedModel) {
  if (requestedModel === DEFAULT_CURSOR_MODEL) {
    return {
      kind: "plugin-default",
      alias: DEFAULT_CURSOR_MODEL,
      base: PREFERRED_DEFAULT_MODEL_BASE,
      effort: PREFERRED_DEFAULT_EFFORT,
    };
  }
  const legacy = LEGACY_GROK_SELECTOR.exec(requestedModel);
  if (!legacy) return null;
  return {
    kind: "legacy-grok-selector",
    alias: requestedModel,
    base: "grok-4.6",
    effort: legacy[1],
    fast: "true",
  };
}

export function parseModelSlug(requestedModel) {
  const documented = parseDocumentedCursorSelector(requestedModel);
  if (!documented) return null;
  return { base: documented.base, effort: documented.effort, kind: documented.kind };
}

function advertisedModelIds(availableModelIds) {
  return Array.isArray(availableModelIds) ? availableModelIds.filter((modelId) => typeof modelId === "string") : [];
}

function assertCleanRequestedModel(requestedModel) {
  if (typeof requestedModel !== "string" || requestedModel.trim().length === 0) {
    throw new BridgeError(
      "MODEL_REQUIRED",
      "model must be an exact advertised Cursor ACP model id, a base model plus effort, or a documented plugin alias",
    );
  }
  if (requestedModel.includes("\u0000") || requestedModel !== requestedModel.trim() || requestedModel.length > 300) {
    throw new BridgeError(
      "MODEL_UNAVAILABLE",
      "model must be an exact advertised id or documented selector with no wrapping whitespace",
    );
  }
}

function assertCleanRequestedEffort(requestedEffort) {
  if (isOmittedCursorEffort(requestedEffort)) return;
  if (typeof requestedEffort !== "string" || !EFFORT_TOKEN.test(requestedEffort)) {
    throw new BridgeError(
      "EFFORT_UNSUPPORTED",
      "effort must be one lowercase token with no wrapping whitespace or extra fields",
    );
  }
}

function legacyGrokBase(modelId) {
  const base = parseCursorModelId(modelId).baseModelId;
  return base === "grok-4.6" || base === "cursor-grok-4.6" ? "grok-4.6" : null;
}

export function preferredDefaultAdvertised(availableModelIds) {
  try {
    resolveRequestedCursorModel(DEFAULT_CURSOR_MODEL, advertisedModelIds(availableModelIds));
    return true;
  } catch {
    return false;
  }
}

export function resolvePreferredDefaultCursorModel(availableModelIds) {
  const advertised = advertisedModelIds(availableModelIds);
  try {
    return resolveRequestedCursorModel(DEFAULT_CURSOR_MODEL, advertised);
  } catch (error) {
    if (error instanceof BridgeError && error.code === "EFFORT_UNSUPPORTED") {
      throw new BridgeError(
        "EFFORT_UNSUPPORTED",
        `plugin default alias ${DEFAULT_CURSOR_MODEL} requires effort ${PREFERRED_DEFAULT_EFFORT} on ${PREFERRED_DEFAULT_MODEL_BASE}, which is not advertised`,
        {
          ...(error.details ?? {}),
          preferredDefaultAlias: DEFAULT_CURSOR_MODEL,
          preferredDefaultModelId: null,
          preferredDefaultBase: PREFERRED_DEFAULT_MODEL_BASE,
          preferredDefaultEffort: PREFERRED_DEFAULT_EFFORT,
        },
      );
    }
    if (error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE") {
      throw new BridgeError(
        "MODEL_REQUIRED",
        `plugin default alias ${DEFAULT_CURSOR_MODEL} (base ${PREFERRED_DEFAULT_MODEL_BASE}, effort ${PREFERRED_DEFAULT_EFFORT}) is not advertised; pass an exact advertised model id`,
        {
          preferredDefaultAlias: DEFAULT_CURSOR_MODEL,
          preferredDefaultModelId: null,
          preferredDefaultBase: PREFERRED_DEFAULT_MODEL_BASE,
          preferredDefaultEffort: PREFERRED_DEFAULT_EFFORT,
          availableModelCount: advertised.length,
          availableModelIds: advertised,
        },
      );
    }
    throw error;
  }
}

export function pluginDefaultSelectionPolicy() {
  return {
    kind: "plugin-default",
    alias: DEFAULT_CURSOR_MODEL,
    baseModel: PREFERRED_DEFAULT_MODEL_BASE,
    effort: PREFERRED_DEFAULT_EFFORT,
    liveModelId: null,
  };
}

export function resolveCursorModelChoice(requestedModel, availableModelIds, requestedEffort) {
  const omittedModel = isOmittedCursorModel(requestedModel);
  const omittedEffort = isOmittedCursorEffort(requestedEffort);

  if (omittedModel && omittedEffort) {
    const selectedModelId = resolvePreferredDefaultCursorModel(availableModelIds);
    const selectedEffort = extractEffortFromModelId(selectedModelId) ?? PREFERRED_DEFAULT_EFFORT;
    return {
      selectedModelId,
      selectedEffort,
      selectionPolicy: pluginDefaultSelectionPolicy(),
    };
  }

  const modelToResolve = omittedModel ? PREFERRED_DEFAULT_MODEL_BASE : requestedModel;
  const selectedModelId = resolveRequestedCursorModel(modelToResolve, availableModelIds, requestedEffort);
  const selectedEffort = extractEffortFromModelId(selectedModelId) ?? requestedEffort ?? null;
  return {
    selectedModelId,
    selectedEffort,
    selectionPolicy: {
      kind: "explicit",
      requestedModel: omittedModel ? null : requestedModel,
      requestedEffort: omittedEffort ? null : requestedEffort,
      baseModel: omittedModel ? PREFERRED_DEFAULT_MODEL_BASE : null,
      effort: omittedEffort ? null : requestedEffort,
    },
  };
}

export function resolveRequestedCursorModel(requestedModel, availableModelIds, requestedEffort) {
  const advertised = advertisedModelIds(availableModelIds);
  assertCleanRequestedModel(requestedModel);
  assertCleanRequestedEffort(requestedEffort);

  const exact = advertised.filter((modelId) => modelId === requestedModel);
  if (exact.length > 1) {
    throw new BridgeError(
      "MODEL_AMBIGUOUS",
      `Cursor ACP advertised duplicate exact ids for ${requestedModel}`,
      { requestedModel, matches: exact.length },
    );
  }
  if (exact.length === 1) {
    const actualEffort = assertCoherentAdvertisedEffort(requestedModel);
    if (!isOmittedCursorEffort(requestedEffort) && actualEffort !== requestedEffort) {
      throw new BridgeError(
        "EFFORT_UNSUPPORTED",
        `Advertised model ${requestedModel} has effort '${actualEffort}', which does not match requested effort '${requestedEffort}'`,
        { requestedModel, requestedEffort, actualEffort },
      );
    }
    return requestedModel;
  }

  const documented = parseDocumentedCursorSelector(requestedModel);
  let targetBase = requestedModel;
  let targetEffort = isOmittedCursorEffort(requestedEffort) ? null : requestedEffort;
  let requireFast = null;
  if (documented) {
    if (!isOmittedCursorEffort(requestedEffort) && requestedEffort !== documented.effort) {
      throw new BridgeError(
        "EFFORT_UNSUPPORTED",
        `Model selector '${requestedModel}' specifies effort '${documented.effort}', which conflicts with requested effort '${requestedEffort}'`,
        { requestedModel, selectorEffort: documented.effort, requestedEffort },
      );
    }
    targetBase = documented.base;
    targetEffort = documented.effort;
    requireFast = documented.fast ?? null;
  }

  const malformed = [];
  const candidates = [];
  for (const modelId of advertised) {
    const parsed = parseCursorModelId(modelId);
    const base = documented?.kind === "legacy-grok-selector" ? legacyGrokBase(modelId) : parsed.baseModelId;
    if (base !== targetBase) continue;
    let effort;
    try {
      effort = assertCoherentAdvertisedEffort(modelId);
    } catch {
      malformed.push(modelId);
      continue;
    }
    if (targetEffort !== null && effort !== targetEffort) continue;
    if (requireFast !== null && parsed.parameters.get("fast") !== requireFast) continue;
    candidates.push(modelId);
  }

  if (candidates.length > 1) {
    throw new BridgeError(
      "MODEL_AMBIGUOUS",
      `Cursor ACP advertised multiple candidates for ${requestedModel}`,
      { requestedModel, targetBase, targetEffort, candidates },
    );
  }
  if (candidates.length === 1) return candidates[0];

  const baseCandidates = advertised.filter((modelId) => {
    const parsed = parseCursorModelId(modelId);
    const base = documented?.kind === "legacy-grok-selector" ? legacyGrokBase(modelId) : parsed.baseModelId;
    return base === targetBase;
  });
  if (targetEffort !== null && (baseCandidates.length > 0 || malformed.length > 0)) {
    const availableEfforts = [];
    for (const modelId of baseCandidates) {
      try {
        const effort = assertCoherentAdvertisedEffort(modelId);
        if (effort) availableEfforts.push(effort);
      } catch {
        // Already recorded as malformed when it was a candidate base.
      }
    }
    throw new BridgeError(
      "EFFORT_UNSUPPORTED",
      `Cursor ACP does not advertise effort '${targetEffort}' for model '${targetBase}'. Advertised: ${availableEfforts.join(", ") || "none"}`,
      {
        requestedModel,
        targetBase,
        targetEffort,
        availableEfforts,
        malformedModelIds: malformed,
        availableModelIds: advertised,
      },
    );
  }

  throw new BridgeError(
    "MODEL_UNAVAILABLE",
    `Cursor ACP did not advertise the required model ${requestedModel}`,
    {
      requestedModel,
      targetEffort,
      availableModelCount: advertised.length,
      availableModelIds: advertised,
    },
  );
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
  const configured = process.env.SAARIUS_CURSOR_ACP_STATE_DIR?.trim();
  if (configured) return path.resolve(configured);
  const pluginData = process.env.PLUGIN_DATA?.trim();
  if (pluginData) return path.resolve(pluginData, "cursor-acp");
  return path.join(homedir(), ".local", "state", "saarius-skills", "cursor-acp-delegation");
}

function assertJobId(jobId) {
  if (typeof jobId !== "string" || !JOB_ID_PATTERN.test(jobId)) {
    throw new BridgeError("INVALID_JOB_ID", "jobId must be a UUID returned by cursor_acp_delegate");
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

function routeSummary(executable, model, effort = null) {
  return {
    agent: "cursor",
    transport: "acp",
    executable,
    argv: [executable, "acp"],
    model,
    ...(effort ? { effort } : {}),
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

function safeAdvertisedModels(model) {
  const availableModelIds = Array.isArray(model?.availableModelIds)
    ? model.availableModelIds.filter((modelId) => typeof modelId === "string")
    : [];
  const availableModels = (Array.isArray(model?.availableModels) ? model.availableModels : [])
    .map((entry) => {
      if (!entry || typeof entry !== "object" || typeof entry.modelId !== "string") return null;
      return typeof entry.name === "string" ? { modelId: entry.modelId, name: entry.name } : { modelId: entry.modelId };
    })
    .filter(Boolean);
  return { availableModelIds, availableModels };
}

export function assertAdvertisedSelectedModel(models, selectedModelId, selectedEffort) {
  const availableModelIds = Array.isArray(models?.availableModelIds) ? models.availableModelIds : [];
  const matches = availableModelIds.filter((id) => id === selectedModelId);
  if (matches.length === 0) {
    throw new BridgeError(
      "MODEL_SELECTION_UNCONFIRMED",
      `Cursor ACP does not advertise selected model ${selectedModelId}`,
      {
        selectedModelId,
        selectedEffort,
        currentModelId: models?.currentModelId ?? null,
      },
    );
  }
  if (matches.length > 1) {
    throw new BridgeError(
      "MODEL_SELECTION_UNCONFIRMED",
      `Cursor ACP advertises ambiguous entries for selected model ${selectedModelId}`,
      {
        selectedModelId,
        selectedEffort,
        currentModelId: models?.currentModelId ?? null,
        matchCount: matches.length,
      },
    );
  }
  let advertisedEffort = null;
  try {
    advertisedEffort = assertCoherentAdvertisedEffort(selectedModelId);
  } catch (error) {
    throw new BridgeError(
      "MODEL_SELECTION_UNCONFIRMED",
      `Cursor ACP selected model ${selectedModelId} has conflicting or malformed effort fields`,
      {
        selectedModelId,
        selectedEffort,
        currentModelId: models?.currentModelId ?? null,
        cause: safeMessage(error?.message),
      },
    );
  }
  if (selectedEffort !== null && advertisedEffort !== selectedEffort) {
    throw new BridgeError(
      "MODEL_SELECTION_UNCONFIRMED",
      `Cursor ACP selected model ${selectedModelId} effort '${advertisedEffort}' does not match stored effort '${selectedEffort}'`,
      {
        selectedModelId,
        selectedEffort,
        currentModelId: models?.currentModelId ?? null,
        advertisedEffort,
      },
    );
  }
}

export async function confirmExactCursorModel(
  runtime,
  handle,
  selectedModelId,
  selectedEffort,
  { allowSelection = false } = {},
) {
  if (typeof runtime?.getStatus !== "function") {
    throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not expose model status");
  }
  let models;
  try {
    models = modelSnapshot(await runtime.getStatus({ handle }));
  } catch (error) {
    if (error instanceof BridgeError) throw error;
    throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not return model status", {
      cause: safeMessage(error?.message),
    });
  }
  try {
    assertAdvertisedSelectedModel(models, selectedModelId, selectedEffort);
    if (models.currentModelId !== selectedModelId) {
      if (!allowSelection) {
        throw new BridgeError(
          "MODEL_SELECTION_UNCONFIRMED",
          `Cursor ACP current model ${models.currentModelId ?? "unknown"} does not match selected model ${selectedModelId}`,
          {
            selectedModelId,
            selectedEffort,
            currentModelId: models.currentModelId ?? null,
          },
        );
      }
      if (typeof runtime.setModel === "function") {
        await runtime.setModel({ handle, model: selectedModelId });
        models = modelSnapshot(await runtime.getStatus({ handle }));
        assertAdvertisedSelectedModel(models, selectedModelId, selectedEffort);
      }
    }
    let currentEffort = null;
    if (typeof models.currentModelId === "string") {
      try {
        currentEffort = assertCoherentAdvertisedEffort(models.currentModelId);
      } catch (error) {
        throw new BridgeError(
          "MODEL_SELECTION_UNCONFIRMED",
          `Cursor ACP current model ${models.currentModelId} has conflicting or malformed effort fields`,
          {
            selectedModelId,
            selectedEffort,
            currentModelId: models.currentModelId,
            cause: safeMessage(error?.message),
          },
        );
      }
    }
    if (models.currentModelId !== selectedModelId || (selectedEffort !== null && currentEffort !== selectedEffort)) {
      throw new BridgeError(
        "MODEL_SELECTION_UNCONFIRMED",
        `Cursor ACP did not confirm persisted model ${selectedModelId}`,
        {
          selectedModelId,
          selectedEffort,
          currentModelId: models.currentModelId ?? null,
          currentEffort,
        },
      );
    }
    return models;
  } catch (error) {
    throw attachCatalog(error, models);
  }
}

function attachCatalog(error, models) {
  const safe = safeAdvertisedModels(models);
  const bridgeError = error instanceof BridgeError
    ? error
    : new BridgeError("MODEL_SELECTION_UNCONFIRMED", safeMessage(error?.message ?? error));
  bridgeError.details = {
    ...(bridgeError.details ?? {}),
    currentModelId: models?.currentModelId ?? null,
    availableModelIds: safe.availableModelIds,
    availableModels: safe.availableModels,
  };
  return bridgeError;
}

function resolvedDefaultModelId(availableModelIds) {
  if (!preferredDefaultAdvertised(availableModelIds)) return null;
  try {
    return resolvePreferredDefaultCursorModel(availableModelIds);
  } catch {
    return null;
  }
}

function currentEffortOrNull(modelId) {
  if (typeof modelId !== "string" || modelId.length === 0) return null;
  try {
    return assertCoherentAdvertisedEffort(modelId);
  } catch {
    return null;
  }
}

function publicModel(model) {
  const safe = safeAdvertisedModels(model);
  const preferredDefaultModelId = resolvedDefaultModelId(safe.availableModelIds);
  return {
    requestedModel: model.requestedModel ?? null,
    requestedEffort: model.requestedEffort ?? null,
    selectionPolicy: model.selectionPolicy ?? null,
    selectedModelId: model.selectedModelId ?? null,
    selectedEffort: model.selectedEffort ?? null,
    currentModelId: model.currentModelId ?? null,
    currentEffort: currentEffortOrNull(model.currentModelId),
    preferredDefaultAlias: DEFAULT_CURSOR_MODEL,
    preferredDefaultPolicy: pluginDefaultSelectionPolicy(),
    preferredDefaultModelId,
    preferredDefaultAvailable: preferredDefaultModelId !== null,
    availableModelIds: safe.availableModelIds,
    availableModels: safe.availableModels,
    availableModelCount: safe.availableModelIds.length,
    matchingModelIds: model.selectedModelId ? [model.selectedModelId] : [],
    effort: model.selectedEffort ?? null,
    effortPolicy: "unambiguous_advertised_selection",
  };
}

function publicSelection(job) {
  return {
    requestedModel: job.request?.model ?? null,
    requestedEffort: job.request?.effort ?? null,
    selectionPolicy: job.request?.selectionPolicy ?? null,
    selectedModelId: job.model?.selectedModelId ?? null,
    selectedEffort: job.model?.selectedEffort ?? null,
    currentModelId: job.model?.currentModelId ?? null,
    currentEffort: currentEffortOrNull(job.model?.currentModelId),
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
  if (safe.code === "CURSOR_TRANSPORT_UNAVAILABLE") {
    return { status: "failed", error: { ...safe, source: error.source ?? "runtime-error" } };
  }
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
        message: "Cursor ACP needs an interactive login, permission, or elicitation response.",
      },
    };
  }
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return {
      status: "failed",
      error: { code: "TIMEOUT", message: "Cursor ACP exceeded the bounded job timeout." },
    };
  }
  return { status: "failed", error: safe };
}

// Cursor 2026.08.11 catches this HTTP/2 error in processPrompt, emits an
// agent-message chunk, then returns end_turn. This is a narrow compatibility
// signature, not a general prose classifier or an authenticated provider signal.
function cursorOutputFailure(text, inFence) {
  if (inFence) return null;
  const value = String(text ?? "");
  const suffix = /(?:^|\n\n)Error: RetriableError: \[unavailable\] PING timed out\s*$/;
  if (!suffix.test(value)) return null;
  const error = new BridgeError("CURSOR_TRANSPORT_UNAVAILABLE", "Cursor's HTTP/2 transport reported PING timed out; partial work requires parent review.");
  error.source = "cursor-output-signature";
  return error;
}

function trackOutputFence(state, text) {
  const lines = `${state.line}${text}`.split("\n");
  state.line = lines.pop().slice(0, 256);
  for (const line of lines) {
    const match = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (!match) continue;
    const token = match[1];
    if (!state.fence) state.fence = token;
    else if (token[0] === state.fence[0] && token.length >= state.fence.length && !match[2].trim()) state.fence = null;
  }
}

function validateFallbackModels(models, selection) {
  if (models === undefined) return [];
  if (!Array.isArray(models) || models.length > 2 || models.some(model => typeof model !== "string")) {
    throw new BridgeError("INVALID_FALLBACK_MODELS", "fallbackModels must contain at most two advertised Cursor model selectors.");
  }
  if (models.length && selection.selectionPolicy.kind !== "plugin-default") {
    throw new BridgeError("FALLBACK_PINNED", "Explicit model or effort selections remain strict; omit both to configure default-model fallbacks.");
  }
  for (const model of models) assertCleanRequestedModel(model);
  return models;
}

function fallbackDecision(job, now) {
  const policy = job.fallbackPolicy;
  if (!policy) return null;
  const remainingMs = Math.max(0, Math.min(job.timeoutMs, Date.parse(policy.deadlineAt) - Date.parse(now)));
  const nextModel = policy.models[policy.index + 1] ?? null;
  let reason = "parent_review_required";
  if (!isTerminalStatus(job.status)) reason = "turn_active";
  else if (!isCleanupReady(job)) reason = "cleanup_unproven";
  else if (job.status !== "failed" || job.error?.code !== "CURSOR_TRANSPORT_UNAVAILABLE") reason = "failure_ineligible";
  else if (remainingMs < MIN_TIMEOUT_MS) reason = "deadline_exhausted";
  else if (!nextModel) reason = "exhausted";
  return { ...policy, nextModel, remainingMs, eligible: reason === "parent_review_required", reason };
}

export function createDefaultRuntime({ stateRoot, cursorExecutable, timeoutMs = RUNTIME_CONTROL_TIMEOUT_MS, processEnv = process.env, processLifecycle }) {
  const registry = createAgentRegistry({
    overrides: { cursor: [cursorExecutable, "acp"] },
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

export class CursorAcpBroker {
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
    this.cursorExecutable = path.resolve(
      options.cursorExecutable ??
        process.env.CURSOR_AGENT_EXECUTABLE ??
        DEFAULT_CURSOR_EXECUTABLE,
    );
    this.model = options.model ?? DEFAULT_CURSOR_MODEL;
    this.effort = options.effort ?? null;
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
            cursorExecutable: this.cursorExecutable,
            model: this.model,
            timeoutMs: this.runtimeControlTimeoutMs,
            processEnv: this.processEnv,
            processLifecycle: brokerProcessLifecycle(this),
          })
        : createDefaultRuntime({
            stateRoot: this.stateRoot,
            cursorExecutable: this.cursorExecutable,
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

  async bindConversation({ hostConversationId, binderId, jobId, workspace, retryOf }) {
    try {
      return await claimConversationBind(
        this.bindingsRoot,
        { hostConversationId, binderId, jobId, workspace, ...(retryOf ? { expectedJobId: retryOf } : {}) },
        {
          now: this.now,
          atomicWrite,
          owner: this.ownerIdentity(),
          inspectOwner: (owner) => this.inspectProcess(owner.pid),
          inspectExisting: (existing) => inspectConversationRebind(this, existing),
        },
      );
    } catch (error) {
      if (retryOf && error?.code === "CONVERSATION_BIND_CHANGED") {
        throw new BridgeError("FALLBACK_SOURCE_CHANGED", "The fallback source is no longer the current conversation job.");
      }
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
      schema: "saarius.cursor-acp.owner.v1",
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
      await access(this.cursorExecutable, constants.X_OK);
    } catch {
      throw new BridgeError(
        "EXECUTABLE_MISSING",
        `Cursor executable is not executable: ${this.cursorExecutable}`,
      );
    }
    try {
      const version = await this.execFile(this.cursorExecutable, ["--version"], {
        cwd: this.stateRoot,
        timeout: 5_000,
        maxBuffer: 128 * 1024,
        encoding: "utf8",
      });
      await this.execFile(this.cursorExecutable, ["acp", "--help"], {
        cwd: this.stateRoot,
        timeout: 5_000,
        maxBuffer: 128 * 1024,
        encoding: "utf8",
      });
      return {
        executable: this.cursorExecutable,
        version: safeMessage(version?.stdout ?? version?.stderr ?? "unknown", 160),
        acpHelp: true,
      };
    } catch (error) {
      throw new BridgeError("ACP_UNAVAILABLE", "Cursor ACP preflight failed", {
        cause: safeMessage(error?.message),
      });
    }
  }

  selectionInput(model, effort) {
    const requestedModel = model ?? (this.model !== DEFAULT_CURSOR_MODEL ? this.model : null);
    const requestedEffort = effort ?? this.effort ?? null;
    const omittedModel = isOmittedCursorModel(requestedModel);
    const omittedEffort = isOmittedCursorEffort(requestedEffort);
    const selectionPolicy = omittedModel && omittedEffort
      ? pluginDefaultSelectionPolicy()
      : {
          kind: "explicit",
          requestedModel: omittedModel ? null : requestedModel,
          requestedEffort: omittedEffort ? null : requestedEffort,
          baseModel: omittedModel ? PREFERRED_DEFAULT_MODEL_BASE : null,
          effort: omittedEffort ? null : requestedEffort,
        };
    return {
      requestedModel: omittedModel ? null : requestedModel,
      requestedEffort: omittedEffort ? null : requestedEffort,
      selectionPolicy,
    };
  }

  async discover({ workspace, model, effort } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace", {
      defaultValue: this.defaultWorkspace,
    });
    const executable = await this.checkExecutable();
    const permission = describeLivePermissionMode(this.processEnv);
    const selection = this.selectionInput(model, effort);
    const sessionKey = `cursor-acp-probe:${this.idFactory()}`;
    let handle;
    try {
      handle = await this.runtime.ensureSession({
        sessionKey,
        agent: "cursor",
        mode: "oneshot",
        cwd: targetWorkspace,
      });
      const models = await this.verifyModel(handle, targetWorkspace, selection);
      return {
        ready: true,
        catalogReady: true,
        selectionReady: true,
        route: routeSummary(this.cursorExecutable, models.selectedModelId, models.selectedEffort),
        executable,
        workspace: targetWorkspace,
        permission,
        model: publicModel(models),
        session: publicHandle(handle),
        note: "Readiness opened and closed an ACP session without sending a model turn.",
      };
    } catch (error) {
      const failure = safeError(error, "READINESS_FAILED");
      const catalogIds = Array.isArray(error?.details?.availableModelIds) ? error.details.availableModelIds : null;
      const modelReport = catalogIds
        ? publicModel({
            availableModelIds: catalogIds,
            availableModels: error.details.availableModels,
            currentModelId: error.details.currentModelId ?? null,
            requestedModel: selection.requestedModel,
            requestedEffort: selection.requestedEffort,
            selectionPolicy: selection.selectionPolicy,
            selectedModelId: null,
            selectedEffort: null,
          })
        : undefined;
      return {
        ready: false,
        catalogReady: Boolean(catalogIds),
        selectionReady: false,
        route: routeSummary(this.cursorExecutable, null, selection.requestedEffort),
        executable,
        workspace: targetWorkspace,
        permission,
        ...(modelReport ? { model: modelReport } : {}),
        error: failure,
        note: "Readiness did not send a model turn.",
      };
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

  async verifyModel(handle, workspace, selection) {
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
    let resolved;
    try {
      resolved = resolveCursorModelChoice(
        selection.requestedModel,
        models.availableModelIds,
        selection.requestedEffort,
      );
    } catch (error) {
      throw attachCatalog(error, models);
    }
    models = await confirmExactCursorModel(
      this.runtime,
      handle,
      resolved.selectedModelId,
      resolved.selectedEffort,
      { allowSelection: true },
    );
    return {
      ...models,
      requestedModel: selection.requestedModel,
      requestedEffort: selection.requestedEffort,
      selectionPolicy: selection.selectionPolicy,
      selectedModelId: resolved.selectedModelId,
      selectedEffort: resolved.selectedEffort,
      workspace,
    };
  }

  async confirmPersistedSelection(handle, job, { allowSelection = false } = {}) {
    const selectedModelId = job.model?.selectedModelId;
    const selectedEffort = job.model?.selectedEffort ?? null;
    if (typeof selectedModelId !== "string" || selectedModelId.length === 0) {
      throw new BridgeError(
        "MODEL_SELECTION_UNCONFIRMED",
        "Cursor ACP job is missing its persisted resolved model",
        {
          requestedModel: job.request?.model ?? null,
          requestedEffort: job.request?.effort ?? null,
        },
      );
    }
    try {
      const models = await confirmExactCursorModel(
        this.runtime,
        handle,
        selectedModelId,
        selectedEffort,
        { allowSelection },
      );
      job.model = {
        ...job.model,
        selectedModelId,
        selectedEffort,
        currentModelId: models.currentModelId,
        availableModelIds: models.availableModelIds,
        availableModels: models.availableModels,
      };
      return job.model;
    } catch (error) {
      if (job.model && error?.details?.currentModelId !== undefined) {
        job.model = {
          ...job.model,
          currentModelId: error.details.currentModelId,
          ...(Array.isArray(error.details.availableModelIds)
            ? { availableModelIds: error.details.availableModelIds }
            : {}),
          ...(Array.isArray(error.details.availableModels)
            ? { availableModels: error.details.availableModels }
            : {}),
        };
      }
      throw error;
    }
  }

  async delegate({
    workspace,
    prompt,
    model,
    effort,
    timeoutMs,
    hostConversationId,
    binderId,
    fallbackModels,
    retryOf,
    partialWorkReviewed,
  } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace");
    const conversation = this.conversationIdentity({ hostConversationId, binderId });
    const taskPrompt = assertBoundedText(prompt, "prompt", MAX_PROMPT_CHARS);
    let boundedTimeout = timeoutMs === undefined ? this.timeoutMs : parseTimeout(timeoutMs);
    let selection = this.selectionInput(model, effort);
    let fallbackPolicy;
    let configuredFallbackModels = [];
    if (retryOf !== undefined) {
      if ([model, effort, timeoutMs, fallbackModels].some(value => value !== undefined)) {
        throw new BridgeError("FALLBACK_OVERRIDE_FORBIDDEN", "A fallback continuation inherits its resolved chain and original deadline; model, effort, timeoutMs and fallbackModels cannot override it.");
      }
      if (selection.selectionPolicy.kind !== "plugin-default") {
        throw new BridgeError("FALLBACK_PINNED", "A current server model/effort pin cannot enter configured fallback.");
      }
      if (partialWorkReviewed !== true) {
        throw new BridgeError("FALLBACK_REVIEW_REQUIRED", "Inspect partial source, process and proof state; submit a bounded continuation with partialWorkReviewed: true.");
      }
      const source = await this.observeJob(retryOf);
      if (source.workspace !== targetWorkspace || source.binding?.hostConversationId !== conversation.hostConversationId ||
          source.binding?.binderId !== conversation.binderId || source.route.executable !== this.cursorExecutable ||
          source.permission?.permissionMode !== describeLivePermissionMode(this.processEnv).permissionMode) {
        throw new BridgeError("FALLBACK_SCOPE_CHANGED", "Fallback must retain the exact workspace, conversation, binder, executable and permission policy.");
      }
      const decision = fallbackDecision(source, this.now());
      if (!decision?.eligible) {
        throw new BridgeError(decision?.reason === "exhausted" ? "FALLBACK_EXHAUSTED" : "FALLBACK_INELIGIBLE", "The source job does not admit a fallback continuation.", { reason: decision?.reason ?? "not_configured" });
      }
      boundedTimeout = decision.remainingMs;
      selection = this.selectionInput(decision.nextModel, null);
      selection.selectionPolicy = { kind: "configured-fallback", rootJobId: decision.rootJobId, retryOf };
      fallbackPolicy = { ...source.fallbackPolicy, index: source.fallbackPolicy.index + 1, retryOf, partialWorkReviewed: true };
    } else {
      if (partialWorkReviewed !== undefined) throw new BridgeError("INVALID_INPUT", "partialWorkReviewed requires retryOf.");
      configuredFallbackModels = validateFallbackModels(fallbackModels, selection);
    }
    try {
      await this.checkExecutable();
    } catch (error) {
      throw toBridgeError(error);
    }

    const jobId = this.idFactory();
    const sessionKey = `cursor-acp:${jobId}`;
    const runDir = path.join(this.runsRoot, jobId);
    const job = {
      schema: "saarius.cursor-acp.job.v1",
      jobId,
      status: "admitted",
      createdAt: this.now(),
      updatedAt: this.now(),
      route: routeSummary(this.cursorExecutable, null, selection.requestedEffort),
      workspace: targetWorkspace,
      timeoutMs: boundedTimeout,
      ...(fallbackPolicy ? { fallbackPolicy } : {}),
      request: {
        promptSha256: hashText(taskPrompt),
        promptChars: taskPrompt.length,
        model: selection.requestedModel,
        effort: selection.requestedEffort,
        selectionPolicy: selection.selectionPolicy,
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
        retryOf,
      });
      const binding = await this.bindConversation({
        ...conversation,
        jobId,
        workspace: targetWorkspace,
        retryOf,
      });
      job.binding = binding;
      await this.persistAdmission(job, ADMISSION_STATE_BOUND);
      await this.persistAdmission(job, ADMISSION_STATE_STARTING);
      handle = await this.runtime.ensureSession({
        sessionKey,
        agent: "cursor",
        mode: "persistent",
        cwd: targetWorkspace,
        sessionOptions: {
          systemPrompt: { append: BRIDGE_SYSTEM_PROMPT },
        },
      });
      const models = await this.verifyModel(handle, targetWorkspace, selection);
      if (configuredFallbackModels.length) {
        const chain = [models.selectedModelId, ...configuredFallbackModels.map(model => resolveRequestedCursorModel(model, models.availableModelIds))];
        if (new Set(chain).size !== chain.length) throw new BridgeError("FALLBACK_DUPLICATE", "Fallback candidates must resolve to distinct advertised model IDs, including the primary.");
        job.fallbackPolicy = { mode: "parent-reviewed", rootJobId: jobId, retryOf: null, models: chain, index: 0, deadlineAt: new Date(Date.parse(job.createdAt) + boundedTimeout).toISOString() };
      }
      job.route = routeSummary(this.cursorExecutable, models.selectedModelId, models.selectedEffort);
      job.model = models;
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
        selectedModelId: models.selectedModelId,
        selectedEffort: models.selectedEffort,
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
    const hasPreparedHandle = Boolean(prepared && prepared.handle);
    let handle = prepared.handle;
    let turn;
    const interaction = { permission: false, elicitation: false, permissionDenied: false };
    let finalText = "";
    let streamFailure;
    const outputFence = { fence: null, line: "" };
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
          agent: "cursor",
          mode: "persistent",
          cwd: job.workspace,
          sessionOptions: {
            systemPrompt: { append: BRIDGE_SYSTEM_PROMPT },
          },
        });
        job.handle = publicHandle(handle);
        await captureJobWorkers(this, job, handle);
      }
      await this.confirmPersistedSelection(handle, job, { allowSelection: !hasPreparedHandle });
      await this.saveJob(job);
      await this.recordEvent(job, "model_confirmed", {
        selectedModelId: job.model.selectedModelId,
        selectedEffort: job.model.selectedEffort,
        currentModelId: job.model.currentModelId,
        requestedModel: job.request?.model ?? null,
        requestedEffort: job.request?.effort ?? null,
        selectionPolicy: job.request?.selectionPolicy ?? null,
      });

      if (job.fallbackPolicy) {
        const remainingMs = Math.min(job.timeoutMs, Date.parse(job.fallbackPolicy.deadlineAt) - Date.parse(this.now()));
        if (remainingMs < MIN_TIMEOUT_MS) throw new BridgeError("FALLBACK_DEADLINE_EXHAUSTED", "The original fallback-chain deadline expired before prompt submission.");
        job.timeoutMs = remainingMs;
        await this.saveJob(job);
      }

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
        if (event?.type === "error") {
          streamFailure = new BridgeError(event.code ?? "ACP_TURN_FAILED", event.message ?? "Cursor ACP stream reported an error.");
        }
        if (event?.type === "tool_call") toolCallCount += 1;
        if (event?.type === "text_delta" && event.stream !== "thought") {
          trackOutputFence(outputFence, String(event.text ?? ""));
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
      const outputFailure = result?.status === "completed" ? cursorOutputFailure(finalText, outputFence.fence) : null;
      if (result?.status === "completed" && !streamFailure && !outputFailure) {
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
        job.handoff = "Cursor ACP cancelled the active turn.";
        await this.saveAndRecord(job, "cancelled", { eventCount, toolCallCount });
      } else {
        const failure = classifyFailure(
          streamFailure ?? outputFailure ?? new BridgeError(
            result?.error?.code ?? "ACP_TURN_FAILED",
            result?.error?.message ?? "Cursor ACP turn failed",
          ),
          interaction,
        );
        job.status = failure.status;
        job.error = failure.error;
        if (finalText) job.handoff = compactHandoff(finalText);
        if (result?.stopReason) job.stopReason = safeMessage(result.stopReason, 120);
        await this.saveAndRecord(job, failure.status, { eventCount, toolCallCount });
      }
    } catch (error) {
      if (job.model && error?.details?.currentModelId !== undefined) {
        job.model = {
          ...job.model,
          currentModelId: error.details.currentModelId,
          ...(Array.isArray(error.details.availableModelIds)
            ? { availableModelIds: error.details.availableModelIds }
            : {}),
          ...(Array.isArray(error.details.availableModels)
            ? { availableModels: error.details.availableModels }
            : {}),
        };
      }
      const failure = classifyFailure(error, interaction);
      job.status = failure.status;
      job.error = failure.error;
      if (finalText) job.handoff = compactHandoff(finalText);
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
    // acpx 0.19.3 serializes startTurn calls for a session. Its mode: "steer"
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
      model: job.model?.selectedModelId ?? null,
      modelSelection: publicSelection(job),
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
      `# Cursor ACP job ${job.jobId}`,
      "",
      `Status: ${job.status}`,
      `Workspace: ${job.workspace}`,
      `Route: ${job.route.executable} acp`,
      `Requested model: ${job.request?.model ?? "omitted"}`,
      `Requested effort: ${job.request?.effort ?? "omitted"}`,
      `Selection policy: ${job.request?.selectionPolicy?.kind ?? "unknown"}${job.request?.selectionPolicy?.alias ? ` ${job.request.selectionPolicy.alias}` : ""}`,
      `Selected model: ${job.model?.selectedModelId ?? "unresolved"}`,
      `Selected effort: ${job.model?.selectedEffort ?? "none"}`,
      `Current model: ${job.model?.currentModelId ?? "unconfirmed"}`,
      `Owner: ${job.owner?.brokerId ?? "unknown"}`,
      `Updated: ${job.updatedAt}`,
      "",
      "The request body is intentionally not persisted; only its SHA-256 and character count are recorded.",
    ];
    await atomicWrite(job.proof.state, `${lines.join("\n")}\n`);
  }

  async writeProof(job) {
    const lines = [
      `# Cursor ACP job ${job.jobId}`,
      "",
      `Outcome: ${job.status}`,
      `Error code: ${job.error?.code ?? "none"}`,
      `Workspace: ${job.workspace}`,
      `Executable: ${job.route.executable}`,
      `Selected model: ${job.model?.selectedModelId ?? "unresolved"}`,
      `Selected effort: ${job.model?.selectedEffort ?? "none"}`,
      `Requested model: ${job.request?.model ?? "omitted"}`,
      `Requested effort: ${job.request?.effort ?? "omitted"}`,
      `Selection policy: ${job.request?.selectionPolicy?.kind ?? "unknown"}${job.request?.selectionPolicy?.alias ? ` ${job.request.selectionPolicy.alias}` : ""}`,
      `Current model: ${job.model?.currentModelId ?? "unconfirmed"}`,
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
      model: job.model?.selectedModelId ?? null,
      modelSelection: publicSelection(job),
      binding: job.binding,
      proof: job.proof,
    };
    if (job.handoff) result.handoff = job.handoff;
    if (job.fallbackPolicy) result.fallback = fallbackDecision(job, this.now());
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
  if (!safe) return "Cursor ACP completed without a textual handoff.";
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
