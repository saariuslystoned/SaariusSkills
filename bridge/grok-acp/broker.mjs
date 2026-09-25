import { accessSync, constants, statSync } from "node:fs";
import { access, appendFile, link, mkdir, open, readFile, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import { homedir } from "node:os";
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
  resolveLivePermissionMode,
} from "./host-policy.mjs";

const execFile = promisify(execFileCallback);

export const DEFAULT_GROK_COMMAND = "grok";
export const DEFAULT_GROK_ARGV = Object.freeze(["agent", "stdio"]);
export const DEFAULT_GROK_MODEL = "grok-4.7";
export const ACPX_GROK_AGENT = "grok-build";
export const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;
export const MAX_TIMEOUT_MS = 30 * 60 * 1000;
export const MAX_PROMPT_CHARS = 20_000;
export const MAX_STEER_CHARS = 8_000;

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
  return job?.cleanup?.status === "completed";
}

function isCanonicalComplete(job) {
  return isTerminalStatus(job?.status) && (
    isCleanupReady(job) || job?.error?.code === "BRIDGE_RESTARTED"
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

export function resolveRequestedGrokModel(requestedModel, availableModelIds) {
  if (availableModelIds.includes(requestedModel)) return requestedModel;
  throw new BridgeError(
    "MODEL_UNAVAILABLE",
    `Grok ACP did not advertise the required model ${requestedModel}`,
    { availableModelCount: availableModelIds.length, availableModelIds: availableModelIds.slice(0, 20) },
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
  if (!Number.isInteger(value) || value < 1_000 || value > MAX_TIMEOUT_MS) {
    throw new BridgeError(
      "INVALID_INPUT",
      `timeoutMs must be an integer between 1000 and ${MAX_TIMEOUT_MS}`,
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

function routeSummary(executable, model) {
  return {
    agent: "grok-build",
    transport: "acp",
    executable,
    argv: [executable, "agent", "stdio"],
    model,
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

function publicModel(model) {
  return {
    requestedModel: model.requestedModel,
    selectedModelId: model.selectedModelId,
    currentModelId: model.currentModelId,
    availableModelCount: model.availableModelIds.length,
    matchingModelIds: model.selectedModelId ? [model.selectedModelId] : [],
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

export function createDefaultRuntime({ stateRoot, grokExecutable, timeoutMs, processEnv = process.env }) {
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
    this.defaultHostConversationId = options.defaultHostConversationId ?? null;
    this.defaultBinderId = options.defaultBinderId ?? this.brokerId;
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
    this.model = options.model ?? DEFAULT_GROK_MODEL;
    this.defaultWorkspace = options.defaultWorkspace ?? process.cwd();
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
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
            timeoutMs: this.timeoutMs,
            processEnv: this.processEnv,
          })
        : createDefaultRuntime({
            stateRoot: this.stateRoot,
            grokExecutable: this.grokExecutable,
            timeoutMs: this.timeoutMs,
            processEnv: options.processEnv ?? process.env,
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
        message: "The owning broker is gone before this job reached a terminal result; resubmit explicitly.",
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

  async discover({ workspace } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace", {
      defaultValue: this.defaultWorkspace,
    });
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
      const models = await this.verifyModel(handle, targetWorkspace);
      return {
        ready: true,
        route: routeSummary(this.grokExecutable, this.model),
        executable,
        workspace: targetWorkspace,
        model: publicModel(models),
        session: publicHandle(handle),
        note: "Readiness opened and closed an ACP session without sending a model turn.",
      };
    } catch (error) {
      const failure = safeError(error, "READINESS_FAILED");
      return {
        ready: false,
        route: routeSummary(this.grokExecutable, this.model),
        executable,
        workspace: targetWorkspace,
        error: failure,
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

  async verifyModel(handle, workspace) {
    if (typeof this.runtime.getStatus !== "function") {
      throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not expose model status");
    }
    let status = await this.runtime.getStatus({ handle });
    let models = modelSnapshot(status);
    const selectedModelId = resolveRequestedGrokModel(this.model, models.availableModelIds);
    if (models.currentModelId !== selectedModelId && typeof this.runtime.setModel === "function") {
      await this.runtime.setModel({ handle, model: selectedModelId });
      status = await this.runtime.getStatus({ handle });
      models = modelSnapshot(status);
    }
    if (models.currentModelId !== selectedModelId) {
      throw new BridgeError(
        "MODEL_SELECTION_UNCONFIRMED",
        `Grok ACP did not confirm selected model ${selectedModelId}`,
        {
          requestedModel: this.model,
          currentModelId: models.currentModelId,
          availableModelIds: models.availableModelIds,
        },
      );
    }
    return { ...models, requestedModel: this.model, selectedModelId, workspace };
  }

  async delegate({ workspace, prompt, timeoutMs, hostConversationId, binderId } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace");
    const conversation = this.conversationIdentity({ hostConversationId, binderId });
    const taskPrompt = assertBoundedText(prompt, "prompt", MAX_PROMPT_CHARS);
    const boundedTimeout = timeoutMs === undefined ? this.timeoutMs : parseTimeout(timeoutMs);
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
      route: routeSummary(this.grokExecutable, this.model),
      workspace: targetWorkspace,
      timeoutMs: boundedTimeout,
      request: { promptSha256: hashText(taskPrompt), promptChars: taskPrompt.length },
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
      const models = await this.verifyModel(handle, targetWorkspace);
      job.route = routeSummary(this.grokExecutable, models.selectedModelId ?? this.model);
      job.model = models;
      job.handle = publicHandle(handle);
      job.status = "submitted";
      await this.persistAdmission(job, ADMISSION_STATE_STARTED);
      await this.recordEvent(job, "submitted", {
        promptSha256: job.request.promptSha256,
        workspace: targetWorkspace,
        hostConversationId: binding.hostConversationId,
        binderId: binding.binderId,
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
        job.model = await this.verifyModel(handle, job.workspace);
      }
      await this.saveJob(job);
      await this.recordEvent(job, "model_confirmed", {
        currentModelId: job.model.currentModelId,
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

  async closeRuntimeSession(job, handle) {
    job.cleanup = {
      status: "pending",
      observed: "runtime_close_started",
      at: this.now(),
    };
    await this.saveJob(job);
    if (!this.runtime?.close) {
      job.cleanup = { ...job.cleanup, status: "completed", observed: "no_runtime_close", at: this.now() };
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
    if (boundedWait > 0 && !isTerminalStatus(job.status)) {
      await this.waitForTerminal(jobId, boundedWait);
      job = await this.observeJob(jobId);
    }
    return {
      ...this.publicJob(job),
      taskComplete: isTerminalStatus(job.status),
      cleanupReady: isCleanupReady(job),
      complete: isTerminalStatus(job.status),
      waitExpired: !isTerminalStatus(job.status) && boundedWait > 0,
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
    // acpx 0.19.1 serializes startTurn calls for a session. Its mode: "steer"
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
      await rm(reclaimPath, { recursive: true, force: true });
    }
  }

  async tryAcquireLockReclaim(reclaimPath) {
    const uniqueReclaim = `${reclaimPath}.${randomUUID()}`;
    await mkdir(uniqueReclaim);
    await writeCompleteFile(
      path.join(uniqueReclaim, "owner.json"),
      `${JSON.stringify(this.ownerIdentity())}\n`,
    );
    try {
      await rename(uniqueReclaim, reclaimPath);
      return true;
    } catch {
      await rm(uniqueReclaim, { recursive: true, force: true });
    }
    try {
      const holder = JSON.parse(await readFile(path.join(reclaimPath, "owner.json"), "utf8"));
      const state = classifyOwnerIdentity(holder, await this.probeOwner(holder));
      if (state === "dead" || state === "reused") {
        await rm(reclaimPath, { recursive: true, force: true });
      }
    } catch {
      // Unreadable reclaim fence: do not delete indiscriminately.
    }
    return false;
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
      `Route: ${job.route.executable} agent stdio`,
      `Requested model: ${job.route.model}`,
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
      `Model: ${job.model?.selectedModelId ?? job.model?.currentModelId ?? job.route.model}`,
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
      jobId: job.jobId,
      status: job.status,
      route: job.route,
      workspace: job.workspace,
      createdAt: job.createdAt,
      updatedAt: job.updatedAt,
      startedAt: job.startedAt,
      timeoutMs: job.timeoutMs,
      model: job.model?.selectedModelId ?? job.model?.currentModelId ?? job.route.model,
      binding: job.binding,
      proof: job.proof,
    };
    if (job.status === "completed" || job.status === "cancelled") result.handoff = job.handoff;
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
      if (isTerminalStatus(job.status)) return;
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
