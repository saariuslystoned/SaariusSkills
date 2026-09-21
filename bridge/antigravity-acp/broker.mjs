import { accessSync, constants } from "node:fs";
import { access, appendFile, link, mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import path from "node:path";
import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { createAcpRuntime, createAgentRegistry } from "acpx/runtime";
import {
  AUTH_MODE,
  BODY_KEYS,
  PROFILE_ENV,
  RUNTIME_PIN,
  authRepair,
  currentPlatformId,
  defaultGeminiHome,
  defaultRuntimeDir,
  defaultStateRoot,
  platformLaunch,
  presentForbiddenEnvNames,
  runtimeRepair,
  settingsPath,
} from "./contract.mjs";

export const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;
export const MAX_TIMEOUT_MS = 30 * 60 * 1000;
export const MAX_PROMPT_CHARS = 20_000;
export const MAX_STEER_CHARS = 8_000;

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "needs-input"]);
const JOB_ID_PATTERN = /^[0-9a-f-]{36}$/i;
const OWNER_ID_MAX_CHARS = 80;
const OWNER_HEARTBEAT_MS = 5_000;
const OWNER_OBSERVE_WAIT_SLICE_MS = 250;
const execFile = promisify(execFileCallback);

const BRIDGE_SYSTEM_PROMPT = [
  "You are official Google Antigravity ACP acting as a bounded implementation worker.",
  "Work only inside the explicitly supplied workspace.",
  "Do not access credentials, auth logs, .env files, private keys, or files outside that workspace.",
  "Do not push, deploy, send external messages, change accounts, spend money, or install global tools.",
  "Do not use API keys, Cloud projects, alternate accounts, paid credits, or overage fallback.",
  "Make only the requested bounded implementation change and run only relevant local checks.",
  "The parent agent owns decisions and independent review; do not broaden the task.",
  "If you need a fixed-choice answer or permission, stop; do not guess.",
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

export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.has(status);
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
  if (probe.status !== "alive" || typeof probe.startTime !== "string" || !probe.startTime.trim()) {
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

export function isCleanupObservedComplete(cleanup) {
  return cleanup?.status === "completed" || cleanup?.status === "recovered";
}

export function isCleanupReady(job) {
  if (!job) return false;
  if (isCleanupObservedComplete(job.cleanup)) return true;
  return isTerminalStatus(job.status) && !job.handle && !job.cleanup;
}

export function isCanonicalComplete(job) {
  return isTerminalStatus(job?.status) && isCleanupReady(job);
}

export function needsCleanupFence(job) {
  if (!job?.workspace || !isTerminalStatus(job.status)) return false;
  if (isCleanupObservedComplete(job.cleanup)) return false;
  return Boolean(job.handle || job.cleanup);
}

export function shouldRecoverCleanupFence(job, lease, probe) {
  if (!needsCleanupFence(job)) return false;
  if (!ownerIdentitiesMatch(job.owner, lease)) return false;
  const state = classifyOwnerIdentity(job.owner, probe);
  return state === "dead" || state === "reused";
}

function cleanupIdentity(job, handle) {
  return {
    jobId: job.jobId,
    workspace: job.workspace,
    owner: job.owner ? { ...job.owner } : undefined,
    handle: handle ? publicHandle(handle) : job.handle,
  };
}

export async function inspectProcessIdentity(pid, run = execFile) {
  if (!Number.isInteger(pid) || pid <= 0) return { status: "unknown" };
  try {
    process.kill(pid, 0);
  } catch (error) {
    if (error?.code === "ESRCH") return { status: "missing" };
    if (error?.code !== "EPERM") return { status: "unknown" };
  }
  try {
    const { stdout } = await run("ps", ["-p", String(pid), "-o", "lstart="], {
      encoding: "utf8",
      timeout: 2_000,
      maxBuffer: 4 * 1024,
      env: { LC_ALL: "C", PATH: process.env.PATH ?? "/usr/bin:/bin" },
    });
    const startTime = String(stdout ?? "").trim();
    return startTime ? { status: "alive", startTime } : { status: "unknown" };
  } catch {
    try {
      process.kill(pid, 0);
      return { status: "unknown" };
    } catch (error) {
      return error?.code === "ESRCH" ? { status: "missing" } : { status: "unknown" };
    }
  }
}

export function hashText(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function resolveRequestedAntigravityModel(requestedModel, availableModelIds) {
  if (typeof requestedModel !== "string" || requestedModel.trim().length === 0) {
    throw new BridgeError(
      "MODEL_REQUIRED",
      "model must be an exact advertised Antigravity ACP model id",
    );
  }
  if (requestedModel.includes("\u0000") || requestedModel !== requestedModel.trim()) {
    throw new BridgeError("MODEL_UNAVAILABLE", "model must be an exact advertised id with no wrapping whitespace");
  }
  const advertised = Array.isArray(availableModelIds) ? availableModelIds : [];
  const matches = advertised.filter((modelId) => modelId === requestedModel);
  if (matches.length === 0) {
    throw new BridgeError(
      "MODEL_UNAVAILABLE",
      `Antigravity ACP did not advertise the exact model ${requestedModel}`,
      {
        requestedModel,
        availableModelCount: advertised.length,
        availableModelIds: advertised.slice(0, 20),
      },
    );
  }
  if (matches.length !== 1) {
    throw new BridgeError(
      "MODEL_AMBIGUOUS",
      `Antigravity ACP advertised a duplicate exact id for ${requestedModel}`,
      { requestedModel, candidates: matches },
    );
  }
  return matches[0];
}

export function assertEffortUnsupported(effort) {
  if (effort !== undefined && effort !== null) {
    throw new BridgeError(
      "EFFORT_UNSUPPORTED",
      "ACP effort selection is unsupported until proved; pass an exact advertised model id instead of inferring effort from a label.",
    );
  }
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

export function isInteractionQuestion(request) {
  const raw = request?.raw ?? request;
  const candidates = [
    raw?.toolCall?.toolCallId,
    raw?.params?.toolCall?.toolCallId,
    raw?.toolCallId,
    request?.toolCallId,
    raw?.params?.toolCallId,
  ];
  return candidates.some((id) => typeof id === "string" && id.startsWith("interaction_"));
}

export function containsBodyKeys(value) {
  if (Array.isArray(value)) return value.some(containsBodyKeys);
  if (!value || typeof value !== "object") return false;
  return Object.entries(value).some(([key, nested]) => BODY_KEYS.includes(key) || containsBodyKeys(nested));
}

function resolveConfiguredStateRoot(env = process.env) {
  const configured = env.SAARIUS_ANTIGRAVITY_ACP_STATE_DIR?.trim();
  if (configured) return path.resolve(configured);
  const pluginData = env.PLUGIN_DATA?.trim();
  if (pluginData) return path.resolve(pluginData, "antigravity-acp");
  return defaultStateRoot();
}

function resolveConfiguredGeminiHome(env = process.env) {
  const scoped = env.SAARIUS_ANTIGRAVITY_ACP_GEMINI_HOME?.trim() || env.GEMINI_HOME?.trim();
  if (scoped) return path.resolve(scoped);
  return defaultGeminiHome();
}

function assertJobId(jobId) {
  if (typeof jobId !== "string" || !JOB_ID_PATTERN.test(jobId)) {
    throw new BridgeError("INVALID_JOB_ID", "jobId must be a UUID returned by antigravity_acp_delegate");
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
  const { rename } = await import("node:fs/promises");
  await rename(temporaryPath, filePath);
}

function whichOnPath(command, envPath = process.env.PATH ?? "") {
  if (!command || command.includes("/") || command.includes("\\")) return undefined;
  const parts = envPath.split(path.delimiter).filter(Boolean);
  for (const directory of parts) {
    const candidate = path.join(directory, command);
    try {
      accessSync(candidate, constants.X_OK);
      return candidate;
    } catch {
      // Keep searching PATH.
    }
  }
  return undefined;
}

function routeSummary(launch, model) {
  return {
    agent: "antigravity",
    transport: RUNTIME_PIN.id,
    runtime: RUNTIME_PIN,
    executable: launch?.command,
    argv: launch ? [launch.command, ...launch.args] : [],
    helper: launch?.helper,
    platformId: launch?.platformId,
    model: model ?? null,
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
    requestedModel: model.requestedModel ?? null,
    selectedModelId: model.selectedModelId ?? null,
    currentModelId: model.currentModelId,
    availableModelCount: model.availableModelIds.length,
    matchingModelIds: model.selectedModelId ? [model.selectedModelId] : [],
    effort: null,
    effortPolicy: "unsupported_until_acp_proof",
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
  if (interaction?.question) {
    return {
      status: "needs-input",
      error: {
        code: "INPUT_REQUIRED",
        message: "Antigravity ACP asked a fixed-choice interaction question; the bridge cancelled it and will not auto-answer.",
      },
      question: {
        state: "cancelled",
        humanRequired: true,
        outcome: "cancelled",
      },
    };
  }
  if (
    interaction?.permissionDenied ||
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
        message: "Antigravity ACP needs personal OAuth, permission, or an interactive answer; the bridge will not invent one.",
      },
    };
  }
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return {
      status: "failed",
      error: { code: "TIMEOUT", message: "Antigravity ACP exceeded the bounded job timeout." },
    };
  }
  return { status: "failed", error: safe };
}

function sanitizedAgentEnv(env, { geminiHome, helperPath }) {
  const child = {
    PATH: env.PATH ?? "",
    GEMINI_HOME: geminiHome,
    AGY_ACP_FORCE_FILE_STORAGE: "1",
  };
  if (env.HOME) child.HOME = env.HOME;
  if (env.TMPDIR) child.TMPDIR = env.TMPDIR;
  if (env.LANG) child.LANG = env.LANG;
  if (helperPath) child.ANTIGRAVITY_HARNESS_PATH = helperPath;
  return child;
}

export async function readAuthPolicyFile(geminiHome) {
  const filePath = settingsPath(geminiHome);
  try {
    const raw = await readFile(filePath, "utf8");
    const parsed = JSON.parse(raw);
    const authType = parsed?.auth?.type;
    const overageFlag = parsed?.useG1Credits;
    return {
      settingsPresent: true,
      authType: typeof authType === "string" ? authType : "missing",
      overageState:
        overageFlag === false ? "never" : overageFlag === true ? "enabled" : "unproven",
    };
  } catch (error) {
    if (error?.code === "ENOENT") {
      return { settingsPresent: false, authType: "missing", overageState: "unproven" };
    }
    return { settingsPresent: true, authType: "unreadable", overageState: "unproven" };
  }
}

export function createDefaultRuntime({
  stateRoot,
  launch,
  geminiHome,
  timeoutMs,
  processEnv = process.env,
}) {
  const registry = createAgentRegistry({
    overrides: { antigravity: [launch.command, ...launch.args] },
  });
  const sessions = new Map();
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
    agentProcessEnv: sanitizedAgentEnv(processEnv, {
      geminiHome,
      helperPath: launch.helper,
    }),
    // Match the Cursor ACP lane's bounded worker behavior: every tool request
    // is approved once for this exact delegated session. Fixed-choice questions
    // and elicitation remain fail-closed below; no permission is persisted as
    // allow-always and the bridge never forwards a reusable approval.
    permissionMode: "approve-all",
    nonInteractivePermissions: "fail",
    timeoutMs,
  });
  const shutdown = runtime.shutdown.bind(runtime);
  runtime.shutdown = async () => {
    try {
      await shutdown();
    } finally {
      sessions.clear();
    }
  };
  return runtime;
}

export class AntigravityAcpBroker {
  constructor(options = {}) {
    this.processEnv = options.processEnv ?? process.env;
    this.stateRoot = path.resolve(options.stateRoot ?? resolveConfiguredStateRoot(this.processEnv));
    this.jobsRoot = path.join(this.stateRoot, "jobs");
    this.runsRoot = path.join(this.stateRoot, "runs");
    this.ownersRoot = path.join(this.stateRoot, "owners");
    this.brokerId = options.brokerId ?? randomUUID();
    this.pid = Number.isInteger(options.pid) && options.pid > 0 ? options.pid : process.pid;
    this.startTime = typeof options.startTime === "string" && options.startTime.trim()
      ? options.startTime.trim()
      : null;
    this.inspectProcess = options.inspectProcess ?? inspectProcessIdentity;
    this.geminiHome = path.resolve(options.geminiHome ?? resolveConfiguredGeminiHome(this.processEnv));
    this.runtimeDir =
      options.runtimeDir ??
      this.processEnv.ANTIGRAVITY_ACP_RUNTIME_DIR?.trim() ??
      defaultRuntimeDir();
    this.runtimeServer = options.runtimeServer ?? this.processEnv.ANTIGRAVITY_ACP_SERVER?.trim();
    this.helperPath = options.helperPath ?? this.processEnv.ANTIGRAVITY_HARNESS_PATH?.trim();
    this.defaultWorkspace = options.defaultWorkspace ?? process.cwd();
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.idFactory = options.idFactory ?? randomUUID;
    this.now = options.now ?? (() => new Date().toISOString());
    this.which = options.which ?? ((command) => whichOnPath(command, this.processEnv.PATH));
    this.readAuthPolicy = options.readAuthPolicy ?? readAuthPolicyFile;
    this.runtime = options.runtime;
    this.runtimeFactory = options.runtimeFactory;
    this.active = new Map();
    this.changeWaiters = new Map();
    this.initPromise = null;
    this.heartbeatTimer = null;
  }

  ownerIdentity() {
    return { brokerId: this.brokerId, pid: this.pid, startTime: this.startTime };
  }

  async init() {
    if (!this.initPromise) {
      this.initPromise = (async () => {
        await mkdir(this.jobsRoot, { recursive: true, mode: 0o700 });
        await mkdir(this.runsRoot, { recursive: true, mode: 0o700 });
        await mkdir(this.ownersRoot, { recursive: true, mode: 0o700 });
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
    try {
      await this.recoverCleanupFenceIfEligible(await this.getJob(snapshot.jobId));
    } catch {
      // Missing or unreadable job state is not a reason to recover another job.
    }
  }

  async recoverOwnedJobIfEligible(snapshot) {
    if (!snapshot?.jobId || !JOB_ID_PATTERN.test(snapshot.jobId) || isTerminalStatus(snapshot.status)) return;
    const lease = await this.readOwnerLease(snapshot.owner?.brokerId);
    const probe = await this.probeOwner(snapshot.owner);
    if (!shouldRecoverOwnedJob(snapshot, lease, probe)) return;
    const job = await this.getJob(snapshot.jobId);
    if (!shouldRecoverOwnedJob(job, await this.readOwnerLease(job.owner?.brokerId), await this.probeOwner(job.owner))) return;
    const previousStatus = job.status;
    job.status = "failed";
    job.updatedAt = this.now();
    job.error = {
      code: "BRIDGE_RESTARTED",
      message: "The owning broker is gone before this job reached a terminal result; resubmit explicitly.",
    };
    if (needsCleanupFence(job) || job.handle) {
      job.cleanup = this.cleanupRecord(job, {
        status: "recovered",
        observed: "owner_gone",
      });
    }
    await this.saveJob(job);
    await this.recordEvent(job, "bridge_restarted", { previousStatus });
    this.notifyChange(job.jobId);
  }

  async recoverCleanupFenceIfEligible(snapshot) {
    if (!snapshot?.jobId || !JOB_ID_PATTERN.test(snapshot.jobId) || !needsCleanupFence(snapshot)) return;
    const lease = await this.readOwnerLease(snapshot.owner?.brokerId);
    const probe = await this.probeOwner(snapshot.owner);
    if (!shouldRecoverCleanupFence(snapshot, lease, probe)) return;
    const job = await this.getJob(snapshot.jobId);
    if (!shouldRecoverCleanupFence(
      job,
      await this.readOwnerLease(job.owner?.brokerId),
      await this.probeOwner(job.owner),
    )) return;
    const previousCleanup = job.cleanup?.status ?? "pending";
    job.cleanup = this.cleanupRecord(job, {
      status: "recovered",
      observed: "owner_gone",
    });
    job.updatedAt = this.now();
    await this.saveJob(job);
    await this.recordEvent(job, "cleanup_recovered", { previousCleanup, observed: "owner_gone" });
    this.notifyChange(job.jobId);
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
    if (!leasePath || !this.startTime) return;
    await atomicWrite(leasePath, `${JSON.stringify({
      schema: "saarius.antigravity-acp.owner.v1",
      ...this.ownerIdentity(),
      heartbeatAt: this.now(),
      released,
    }, null, 2)}\n`);
  }

  startOwnerHeartbeat() {
    if (this.heartbeatTimer) return;
    this.heartbeatTimer = setInterval(() => {
      void this.writeOwnerLease().catch(() => undefined);
    }, OWNER_HEARTBEAT_MS);
    this.heartbeatTimer.unref?.();
  }

  async observeJob(jobId) {
    let job = await this.getJob(jobId);
    if (!isTerminalStatus(job.status) && !this.active.has(jobId)) {
      await this.recoverOwnedJobIfEligible(job);
      job = await this.getJob(jobId);
    }
    if (needsCleanupFence(job) && !this.active.has(jobId)) {
      await this.recoverCleanupFenceIfEligible(job);
      job = await this.getJob(jobId);
    }
    return job;
  }

  cleanupRecord(job, { status, observed, message, handle } = {}) {
    return {
      status,
      observed,
      at: this.now(),
      ...cleanupIdentity(job, handle),
      ...(message ? { message } : {}),
    };
  }

  async recordCleanup(job, fields) {
    job.cleanup = this.cleanupRecord(job, fields);
    job.updatedAt = this.now();
    await this.saveJob(job);
    await this.recordEvent(job, `cleanup_${fields.status}`, {
      observed: fields.observed,
      message: fields.message,
      workspace: job.workspace,
      owner: job.owner,
    });
    this.notifyChange(job.jobId);
  }

  async closeRuntimeSession(job, handle) {
    if (isCleanupObservedComplete(job.cleanup)) return;
    if (!handle || !this.ensureRuntime()?.close) {
      await this.recordCleanup(job, {
        status: "completed",
        observed: "no_runtime_close",
        handle,
      });
      return;
    }
    await this.recordCleanup(job, {
      status: "pending",
      observed: "runtime_close_started",
      handle,
    });
    try {
      await this.ensureRuntime().close({
        handle,
        reason: `job ${job.status} terminal cleanup`,
        discardPersistentState: true,
      });
      await this.recordCleanup(job, {
        status: "completed",
        observed: "runtime_close_returned",
        handle,
      });
    } catch (error) {
      await this.recordCleanup(job, {
        status: "uncertain",
        observed: "runtime_close_failed",
        message: safeMessage(error?.message),
        handle,
      });
    }
  }

  async listJobSnapshots() {
    let names;
    try {
      names = await readdir(this.jobsRoot);
    } catch {
      return [];
    }
    const snapshots = [];
    for (const name of names) {
      if (!name.endsWith(".json")) continue;
      try {
        snapshots.push(JSON.parse(await readFile(path.join(this.jobsRoot, name), "utf8")));
      } catch {
        // Skip unreadable records; admission still fail-closes on a readable fence.
      }
    }
    return snapshots;
  }

  async findWorkspaceCleanupFence(workspace) {
    const resolved = path.resolve(workspace);
    for (const snapshot of await this.listJobSnapshots()) {
      if (path.resolve(snapshot.workspace ?? "") !== resolved) continue;
      if (!this.active.has(snapshot.jobId)) {
        await this.recoverCleanupFenceIfEligible(snapshot);
      }
      let job;
      try {
        job = await this.getJob(snapshot.jobId);
      } catch {
        continue;
      }
      if (needsCleanupFence(job)) return job;
    }
    return null;
  }

  async assertWorkspaceAdmissible(workspace) {
    const fence = await this.findWorkspaceCleanupFence(workspace);
    if (!fence) return;
    throw new BridgeError(
      "WORKSPACE_CLEANUP_PENDING",
      "A prior job in this workspace still has unresolved terminal cleanup; wait for observed cleanup or owner-controlled recovery before replacing the session.",
      {
        jobId: fence.jobId,
        workspace: fence.workspace,
        owner: fence.owner,
        cleanup: fence.cleanup,
        status: fence.status,
      },
    );
  }

  async close() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    try {
      await this.writeOwnerLease({ released: true });
    } catch {
      // Process identity remains the recovery source of truth.
    }
    for (const [jobId, active] of this.active) {
      try {
        await active.turn?.cancel({ reason: "bridge shutdown" });
      } catch {
        // Best effort. The runtime owns process cleanup.
      }
      this.active.delete(jobId);
    }
    await this.ensureRuntime()?.shutdown?.();
  }

  ensureRuntime() {
    if (this.runtime) return this.runtime;
    const launch = this.resolvedLaunch;
    if (!launch) return undefined;
    this.runtime = this.runtimeFactory
      ? this.runtimeFactory({
          stateRoot: this.stateRoot,
          launch,
          geminiHome: this.geminiHome,
          timeoutMs: this.timeoutMs,
          processEnv: this.processEnv,
        })
      : createDefaultRuntime({
          stateRoot: this.stateRoot,
          launch,
          geminiHome: this.geminiHome,
          timeoutMs: this.timeoutMs,
          processEnv: this.processEnv,
        });
    return this.runtime;
  }

  async resolveLaunch() {
    const platformId = currentPlatformId();
    const launch = platformLaunch(platformId);
    if (!launch) {
      throw new BridgeError(
        "PLATFORM_UNSUPPORTED",
        `No pinned antigravity-acp ${RUNTIME_PIN.version} launch shape for ${platformId}`,
        { platformId, repair: runtimeRepair(platformId) },
      );
    }
    const basename = path.basename(launch.runtimeCommand);
    let command;
    if (this.runtimeServer) {
      command = path.resolve(this.runtimeServer);
    } else if (this.runtimeDir) {
      command = path.resolve(this.runtimeDir, basename);
    } else {
      command = this.which(basename);
    }
    if (!command) {
      throw new BridgeError(
        "RUNTIME_MISSING",
        `Pinned antigravity-acp ${RUNTIME_PIN.version} runtime ${basename} is not installed`,
        { platformId, repair: runtimeRepair(platformId) },
      );
    }
    try {
      await access(command, constants.X_OK);
    } catch {
      throw new BridgeError(
        "RUNTIME_MISSING",
        `Antigravity ACP runtime is not executable: ${command}`,
        { platformId, repair: runtimeRepair(platformId) },
      );
    }
    const helperName = path.basename(launch.helper);
    let helper;
    if (this.helperPath) {
      helper = path.resolve(this.helperPath);
    } else {
      helper = path.join(path.dirname(command), helperName);
    }
    try {
      await access(helper, constants.X_OK);
    } catch {
      throw new BridgeError(
        "HELPER_MISSING",
        `Pinned helper ${helperName} is missing beside the ${RUNTIME_PIN.version} runtime`,
        { platformId, helper, repair: runtimeRepair(platformId) },
      );
    }
    this.resolvedLaunch = {
      platformId,
      command,
      args: [...launch.runtimeArgs],
      helper,
      archive: launch.archive,
    };
    return this.resolvedLaunch;
  }

  async diagnoseAuth() {
    const forbidden = presentForbiddenEnvNames(this.processEnv);
    const policy = await this.readAuthPolicy(this.geminiHome);
    const diagnosis = {
      mode: AUTH_MODE,
      profileEnv: PROFILE_ENV,
      profilePath: this.geminiHome,
      credentialSource: "runtime_owned",
      settingsPresent: policy.settingsPresent,
      settingsAuthType: policy.authType,
      accountState: "unproven",
      apiKeyPresent: forbidden.some((name) => /API_KEY/i.test(name)),
      cloudCredentialsPresent: forbidden.some((name) => !/API_KEY/i.test(name)),
      forbiddenEnvNames: forbidden,
      alternateAccount: false,
      interactiveLogin: false,
      overageState: policy.overageState,
      ultraAttribution: "unclaimed",
      repair: authRepair(this.geminiHome),
    };
    if (forbidden.length > 0) {
      throw new BridgeError(
        "AUTH_FALLBACK_FORBIDDEN",
        "API-key, Cloud, or alternate-credential environment variables are present; the bridge will not use them.",
        { ...diagnosis, accountState: "blocked" },
      );
    }
    if (policy.authType !== AUTH_MODE) {
      throw new BridgeError(
        "INPUT_REQUIRED",
        `Personal OAuth is not configured at ${settingsPath(this.geminiHome)}; complete runtime-owned sign-in in an interactive ACP client.`,
        { ...diagnosis, accountState: "needs-input" },
      );
    }
    if (policy.overageState !== "never" && policy.overageState !== "disabled") {
      throw new BridgeError(
        "OVERAGE_UNPROVEN",
        "AI-credit overage is not proven disabled/never; the bridge will not start a turn or invent entitlement evidence.",
        { ...diagnosis, accountState: "unproven" },
      );
    }
    return diagnosis;
  }

  async discover({ workspace, model, effort } = {}) {
    await this.init();
    assertEffortUnsupported(effort);
    const targetWorkspace = await requireDirectory(workspace, "workspace", {
      defaultValue: this.defaultWorkspace,
    });
    const platformId = currentPlatformId();
    const diagnosisBase = {
      ready: false,
      route: routeSummary({ platformId, command: null, args: [], helper: null }, model ?? null),
      workspace: targetWorkspace,
      pin: RUNTIME_PIN,
      effortPolicy: "unsupported_until_acp_proof",
      ultraAttribution: "unclaimed",
    };
    let launch;
    let auth;
    try {
      launch = await this.resolveLaunch();
      auth = await this.diagnoseAuth();
    } catch (error) {
      const failure = safeError(error, "READINESS_FAILED");
      return {
        ...diagnosisBase,
        route: routeSummary(launch ?? { platformId, command: null, args: [], helper: null }, model ?? null),
        auth: error?.details ?? undefined,
        error: failure,
        setup: {
          runtime: launch ? { present: true, command: launch.command, helper: launch.helper } : { present: false },
          repair: error?.details?.repair ?? runtimeRepair(platformId),
        },
      };
    }
    diagnosisBase.route = routeSummary(launch, model ?? null);
    diagnosisBase.auth = publicAuth(auth);
    const sessionKey = `antigravity-acp-probe:${this.idFactory()}`;
    let handle;
    try {
      const runtime = this.ensureRuntime();
      handle = await runtime.ensureSession({
        sessionKey,
        agent: "antigravity",
        mode: "oneshot",
        cwd: targetWorkspace,
      });
      const models = await this.verifyModel(handle, targetWorkspace, model);
      return {
        ready: true,
        route: routeSummary(launch, models.selectedModelId ?? model ?? null),
        workspace: targetWorkspace,
        pin: RUNTIME_PIN,
        auth: { ...publicAuth(auth), sessionOpened: true, accountState: "session-opened-unproven-entitlement" },
        model: publicModel(models),
        session: publicHandle(handle),
        effortPolicy: "unsupported_until_acp_proof",
        ultraAttribution: "unclaimed",
        note: "Readiness opened and closed an ACP session without sending a model turn. Session success is not Google AI Ultra quota proof.",
      };
    } catch (error) {
      const failure = classifyFailure(error, {});
      return {
        ...diagnosisBase,
        ready: false,
        error: failure.error,
        status: failure.status,
      };
    } finally {
      if (handle) {
        try {
          await this.ensureRuntime().close({
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

  async verifyModel(handle, workspace, requestedModel) {
    const runtime = this.ensureRuntime();
    if (typeof runtime.getStatus !== "function") {
      throw new BridgeError("MODEL_SELECTION_UNCONFIRMED", "Runtime did not expose model status");
    }
    let status = await runtime.getStatus({ handle });
    let models = modelSnapshot(status);
    if (requestedModel === undefined) {
      return { ...models, requestedModel: null, selectedModelId: null, workspace };
    }
    const selectedModelId = resolveRequestedAntigravityModel(requestedModel, models.availableModelIds);
    if (models.currentModelId !== selectedModelId && typeof runtime.setModel === "function") {
      await runtime.setModel({ handle, model: selectedModelId });
      status = await runtime.getStatus({ handle });
      models = modelSnapshot(status);
    }
    if (models.currentModelId !== selectedModelId) {
      throw new BridgeError(
        "MODEL_SELECTION_UNCONFIRMED",
        `Antigravity ACP did not confirm exact model ${selectedModelId}`,
        {
          requestedModel,
          currentModelId: models.currentModelId,
          availableModelIds: models.availableModelIds,
        },
      );
    }
    return { ...models, requestedModel, selectedModelId, workspace };
  }

  async delegate({ workspace, prompt, model, effort, timeoutMs } = {}) {
    await this.init();
    assertEffortUnsupported(effort);
    const targetWorkspace = await requireDirectory(workspace, "workspace");
    await this.assertWorkspaceAdmissible(targetWorkspace);
    const taskPrompt = assertBoundedText(prompt, "prompt", MAX_PROMPT_CHARS);
    const requestedModel = resolveRequestedAntigravityModel(model, [model]);
    const boundedTimeout = timeoutMs === undefined ? this.timeoutMs : parseTimeout(timeoutMs);
    const launch = await this.resolveLaunch();
    const auth = await this.diagnoseAuth();

    const jobId = this.idFactory();
    const runDir = path.join(this.runsRoot, jobId);
    const job = {
      schema: "saarius.antigravity-acp.job.v1",
      jobId,
      status: "submitted",
      createdAt: this.now(),
      updatedAt: this.now(),
      route: routeSummary(launch, requestedModel),
      workspace: targetWorkspace,
      timeoutMs: boundedTimeout,
      owner: this.ownerIdentity(),
      request: { promptSha256: hashText(taskPrompt), promptChars: taskPrompt.length },
      auth: publicAuth(auth),
      sessionKey: `antigravity-acp:${jobId}`,
      runDir,
      proof: {
        state: path.join(runDir, "STATE.md"),
        events: path.join(runDir, "events.jsonl"),
        proof: path.join(runDir, "PROOF.md"),
      },
    };
    await mkdir(runDir, { recursive: true, mode: 0o700 });
    await this.saveJob(job);
    await this.recordEvent(job, "submitted", {
      promptSha256: job.request.promptSha256,
      workspace: targetWorkspace,
      requestedModel,
    });

    const promise = Promise.resolve()
      .then(() => this.runJob(job, taskPrompt, requestedModel))
      .catch(() => undefined);
    this.active.set(jobId, { promise });
    return this.publicJob(job);
  }

  async runJob(job, taskPrompt, requestedModel) {
    let handle;
    let turn;
    const interaction = { permissionDenied: false, elicitation: false, question: false };
    let finalText = "";
    let eventCount = 0;
    let toolCallCount = 0;
    try {
      job.status = "running";
      job.startedAt = this.now();
      await this.saveAndRecord(job, "running", { workspace: job.workspace });
      const runtime = this.ensureRuntime();
      handle = await runtime.ensureSession({
        sessionKey: job.sessionKey,
        agent: "antigravity",
        mode: "persistent",
        cwd: job.workspace,
        sessionOptions: {
          systemPrompt: { append: BRIDGE_SYSTEM_PROMPT },
        },
      });
      job.handle = publicHandle(handle);
      const model = await this.verifyModel(handle, job.workspace, requestedModel);
      job.model = model;
      await this.saveJob(job);
      await this.recordEvent(job, "model_confirmed", {
        currentModelId: model.currentModelId,
        availableModelCount: model.availableModelIds.length,
      });

      turn = runtime.startTurn({
        handle,
        text: taskPrompt,
        mode: "prompt",
        requestId: job.jobId,
        timeoutMs: job.timeoutMs,
        onPermissionRequest: async (request) => {
          if (isInteractionQuestion(request)) {
            interaction.question = true;
            return { outcome: "cancel" };
          }
          return { outcome: "allow_once" };
        },
        onElicitation: async () => {
          interaction.elicitation = true;
          return { action: "cancel" };
        },
      });
      this.active.set(job.jobId, { promise: this.active.get(job.jobId)?.promise, handle, turn });
      await turn.promptStarted;
      await this.recordEvent(job, "prompt_started", { requestId: job.jobId });

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
      if (interaction.question) {
        job.status = "needs-input";
        job.error = {
          code: "INPUT_REQUIRED",
          message: "Antigravity ACP asked a fixed-choice interaction question; the bridge cancelled it and will not auto-answer.",
        };
        job.question = { state: "cancelled", humanRequired: true, outcome: "cancelled" };
        await this.saveAndRecord(job, "needs-input", { eventCount, toolCallCount, question: "cancelled" });
      } else if (interaction.permissionDenied || interaction.elicitation) {
        job.status = "needs-input";
        job.error = {
          code: "INPUT_REQUIRED",
          message: "Antigravity ACP required a permission or elicitation; the bridge cancelled it and will not auto-approve.",
        };
        await this.saveAndRecord(job, "needs-input", { eventCount, toolCallCount });
      } else if (result?.status === "completed") {
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
        job.handoff = "Antigravity ACP cancelled the active turn.";
        await this.saveAndRecord(job, "cancelled", { eventCount, toolCallCount });
      } else {
        const failure = classifyFailure(
          new BridgeError(
            result?.error?.code ?? "ACP_TURN_FAILED",
            result?.error?.message ?? "Antigravity ACP turn failed",
          ),
          interaction,
        );
        job.status = failure.status;
        job.error = failure.error;
        if (failure.question) job.question = failure.question;
        await this.saveAndRecord(job, failure.status, { eventCount, toolCallCount });
      }
    } catch (error) {
      const failure = classifyFailure(error, interaction);
      job.status = failure.status;
      job.error = failure.error;
      if (failure.question) job.question = failure.question;
      job.updatedAt = this.now();
      await this.saveAndRecord(job, failure.status, { eventCount, toolCallCount });
    } finally {
      if (handle && isTerminalStatus(job.status)) await this.closeRuntimeSession(job, handle);
      this.notifyChange(job.jobId);
      if (isTerminalStatus(job.status)) this.active.delete(job.jobId);
    }
    return this.publicJob(job);
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

  publicWaitResult(job, boundedWait = 0) {
    const taskComplete = isTerminalStatus(job.status);
    const cleanupReady = isCleanupReady(job);
    return {
      ...this.publicJob(job),
      taskComplete,
      cleanupReady,
      complete: taskComplete && cleanupReady,
      waitExpired: boundedWait > 0 && !(taskComplete && cleanupReady),
    };
  }

  async status({ jobId, waitMs } = {}) {
    const boundedWait = parseWait(waitMs, 10_000);
    let job = await this.observeJob(jobId);
    if (boundedWait > 0 && !isCanonicalComplete(job)) {
      await this.waitForChange(jobId, boundedWait);
      job = await this.observeJob(jobId);
    }
    return this.publicWaitResult(job, boundedWait);
  }

  async result({ jobId, waitMs } = {}) {
    const boundedWait = parseWait(waitMs, 300_000);
    let job = await this.observeJob(jobId);
    if (boundedWait > 0 && !isCanonicalComplete(job)) {
      await this.waitForTerminal(jobId, boundedWait);
      job = await this.observeJob(jobId);
    }
    return this.publicWaitResult(job, boundedWait);
  }

  async steer({ jobId, message } = {}) {
    assertBoundedText(message, "message", MAX_STEER_CHARS);
    const job = await this.observeJob(jobId);
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
    throw new BridgeError(
      "STEERING_UNSUPPORTED",
      "Active-turn steering is unproved for Antigravity ACP. Wait for the job's terminal result, then explicitly delegate a bounded follow-up.",
    );
  }

  async cancel({ jobId, reason } = {}) {
    const job = await this.observeJob(jobId);
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
    if (containsBodyKeys(job)) {
      throw new BridgeError("BODY_PERSISTENCE_FORBIDDEN", "Job state must not retain raw prompt, output, or question bodies");
    }
    job.updatedAt = job.updatedAt ?? this.now();
    await atomicWrite(path.join(this.jobsRoot, `${job.jobId}.json`), `${JSON.stringify(job, null, 2)}\n`);
    await this.writeState(job);
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
      `# Antigravity ACP job ${job.jobId}`,
      "",
      `Status: ${job.status}`,
      `Workspace: ${job.workspace}`,
      `Runtime: antigravity-acp ${RUNTIME_PIN.version}`,
      `Requested model: ${job.route.model ?? "unselected"}`,
      `Owner: ${job.owner?.brokerId ?? "unknown"}`,
      `Cleanup: ${job.cleanup?.status ?? "pending"}`,
      `Updated: ${job.updatedAt}`,
      "",
      "The request body is intentionally not persisted; only its SHA-256 and character count are recorded.",
    ];
    await atomicWrite(job.proof.state, `${lines.join("\n")}\n`);
  }

  async writeProof(job) {
    const lines = [
      `# Antigravity ACP job ${job.jobId}`,
      "",
      `Outcome: ${job.status}`,
      `Workspace: ${job.workspace}`,
      `Runtime: ${job.route.executable ?? "unresolved"}`,
      `Model: ${job.model?.selectedModelId ?? job.model?.currentModelId ?? job.route.model}`,
      `Prompt SHA-256: ${job.request.promptSha256}`,
      `Events observed: ${job.eventCount ?? 0}`,
      `Tool calls observed: ${job.toolCallCount ?? 0}`,
      `Cleanup: ${job.cleanup?.status ?? "unrecorded"}`,
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
      cleanup: job.cleanup,
      proof: job.proof,
    };
    if (job.status === "completed" || job.status === "cancelled") result.handoff = job.handoff;
    if (job.error) result.error = job.error;
    if (job.stopReason) result.stopReason = job.stopReason;
    if (job.cancelRequested) result.cancelRequested = true;
    if (job.question) result.question = job.question;
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
      if (isTerminalStatus(job.status) && job.cleanup?.status === "uncertain") return;
      const remaining = deadline - Date.now();
      if (remaining <= 0) return;
      await this.waitForChange(
        jobId,
        this.active.has(jobId) ? remaining : Math.min(remaining, OWNER_OBSERVE_WAIT_SLICE_MS),
      );
    }
  }

  notifyChange(jobId) {
    for (const resolve of this.changeWaiters.get(jobId) ?? []) resolve();
  }
}

function publicAuth(auth) {
  if (!auth) return undefined;
  return {
    mode: auth.mode,
    profileEnv: auth.profileEnv,
    credentialSource: auth.credentialSource,
    accountState: auth.accountState,
    settingsAuthType: auth.settingsAuthType,
    overageState: auth.overageState,
    apiKeyPresent: auth.apiKeyPresent,
    cloudCredentialsPresent: auth.cloudCredentialsPresent,
    alternateAccount: false,
    interactiveLogin: false,
    ultraAttribution: "unclaimed",
  };
}

function compactHandoff(value) {
  const safe = redactSensitive(value).trim();
  if (!safe) return "Antigravity ACP completed without a textual handoff.";
  return safe.length > 2_400 ? `…${safe.slice(-2_399)}` : safe;
}

function redactObject(value) {
  if (value === null || value === undefined) return value;
  if (typeof value === "string") return safeMessage(value, 500);
  if (Array.isArray(value)) return value.slice(0, 20).map(redactObject);
  if (typeof value !== "object") return value;
  const output = {};
  for (const [key, nested] of Object.entries(value).slice(0, 30)) {
    if (BODY_KEYS.includes(key) || /token|secret|password|credential|authorization|private/i.test(key)) {
      output[key] = "[redacted]";
    } else {
      output[key] = redactObject(nested);
    }
  }
  return output;
}
