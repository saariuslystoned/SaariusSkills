import { constants } from "node:fs";
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

const execFile = promisify(execFileCallback);

export const DEFAULT_CURSOR_EXECUTABLE = "/Users/bobbybones/.local/bin/cursor-agent";
export const DEFAULT_CURSOR_MODEL = "cursor-grok-4.6-high";
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

export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.has(status);
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

export function resolveRequestedCursorModel(requestedModel, availableModelIds) {
  if (availableModelIds.includes(requestedModel)) return requestedModel;
  const match = /^cursor-grok-4\.6-(low|medium|high|xhigh)$/.exec(requestedModel);
  if (!match) {
    throw new BridgeError(
      "MODEL_UNAVAILABLE",
      `Cursor ACP did not advertise the required model ${requestedModel}`,
      { availableModelCount: availableModelIds.length, availableModelIds: availableModelIds.slice(0, 20) },
    );
  }
  const effort = match[1];
  const candidates = availableModelIds.filter((modelId) => {
    if (!/^(?:cursor-)?grok-4\.6\[/.test(modelId)) return false;
    const parameters = modelId.slice(modelId.indexOf("[") + 1, -1).split(",");
    const values = new Map(
      parameters.map((parameter) => {
        const [key, value] = parameter.split("=", 2);
        return [key?.trim(), value?.trim()];
      }),
    );
    return values.get("effort") === effort && values.get("fast") === "true";
  });
  if (candidates.length !== 1) {
    throw new BridgeError(
      candidates.length === 0 ? "MODEL_UNAVAILABLE" : "MODEL_AMBIGUOUS",
      candidates.length === 0
        ? `Cursor ACP did not advertise a unique ${requestedModel} model`
        : `Cursor ACP advertised multiple candidates for ${requestedModel}`,
      {
        requestedModel,
        availableModelCount: availableModelIds.length,
        availableModelIds: availableModelIds.slice(0, 20),
        candidates,
      },
    );
  }
  return candidates[0];
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
    agent: "cursor",
    transport: "acp",
    executable,
    argv: [executable, "acp"],
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

export function createDefaultRuntime({ stateRoot, cursorExecutable, timeoutMs }) {
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
    permissionMode: "approve-all",
    nonInteractivePermissions: "fail",
    timeoutMs,
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
    this.brokerId = options.brokerId ?? randomUUID();
    this.pid = Number.isInteger(options.pid) && options.pid > 0 ? options.pid : process.pid;
    this.startTime = typeof options.startTime === "string" && options.startTime.trim()
      ? options.startTime.trim()
      : null;
    this.inspectProcess = options.inspectProcess ?? inspectProcessIdentity;
    this.onJobLockPrepared = options.onJobLockPrepared ?? null;
    this.cursorExecutable = path.resolve(
      options.cursorExecutable ??
        process.env.CURSOR_AGENT_EXECUTABLE ??
        DEFAULT_CURSOR_EXECUTABLE,
    );
    this.model = options.model ?? DEFAULT_CURSOR_MODEL;
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
            cursorExecutable: this.cursorExecutable,
            model: this.model,
            timeoutMs: this.timeoutMs,
          })
        : createDefaultRuntime({
            stateRoot: this.stateRoot,
            cursorExecutable: this.cursorExecutable,
            timeoutMs: this.timeoutMs,
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

  async discover({ workspace } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace", {
      defaultValue: this.defaultWorkspace,
    });
    const executable = await this.checkExecutable();
    const sessionKey = `cursor-acp-probe:${this.idFactory()}`;
    let handle;
    try {
      handle = await this.runtime.ensureSession({
        sessionKey,
        agent: "cursor",
        mode: "oneshot",
        cwd: targetWorkspace,
      });
      const models = await this.verifyModel(handle, targetWorkspace);
      return {
        ready: true,
        route: routeSummary(this.cursorExecutable, this.model),
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
        route: routeSummary(this.cursorExecutable, this.model),
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
    const selectedModelId = resolveRequestedCursorModel(this.model, models.availableModelIds);
    if (models.currentModelId !== selectedModelId && typeof this.runtime.setModel === "function") {
      await this.runtime.setModel({ handle, model: selectedModelId });
      status = await this.runtime.getStatus({ handle });
      models = modelSnapshot(status);
    }
    if (models.currentModelId !== selectedModelId) {
      throw new BridgeError(
        "MODEL_SELECTION_UNCONFIRMED",
        `Cursor ACP did not confirm selected model ${selectedModelId}`,
        {
          requestedModel: this.model,
          currentModelId: models.currentModelId,
          availableModelIds: models.availableModelIds,
        },
      );
    }
    return { ...models, requestedModel: this.model, selectedModelId, workspace };
  }

  async delegate({ workspace, prompt, timeoutMs } = {}) {
    await this.init();
    const targetWorkspace = await requireDirectory(workspace, "workspace");
    const taskPrompt = assertBoundedText(prompt, "prompt", MAX_PROMPT_CHARS);
    const boundedTimeout = timeoutMs === undefined ? this.timeoutMs : parseTimeout(timeoutMs);
    await this.checkExecutable();

    const jobId = this.idFactory();
    const runDir = path.join(this.runsRoot, jobId);
    const job = {
      schema: "saarius.cursor-acp.job.v1",
      jobId,
      status: "submitted",
      createdAt: this.now(),
      updatedAt: this.now(),
      route: routeSummary(this.cursorExecutable, this.model),
      workspace: targetWorkspace,
      timeoutMs: boundedTimeout,
      request: { promptSha256: hashText(taskPrompt), promptChars: taskPrompt.length },
      owner: this.ownerIdentity(),
      sessionKey: `cursor-acp:${jobId}`,
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
    });

    const promise = Promise.resolve()
      .then(() => this.runJob(job, taskPrompt))
      .catch(() => undefined);
    this.active.set(jobId, { promise });
    return this.publicJob(job);
  }

  async runJob(job, taskPrompt) {
    let handle;
    let turn;
    const interaction = { permission: false, elicitation: false };
    let finalText = "";
    let eventCount = 0;
    let toolCallCount = 0;
    try {
      job.status = "running";
      job.startedAt = this.now();
      await this.saveAndRecord(job, "running", { workspace: job.workspace });
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
      const model = await this.verifyModel(handle, job.workspace);
      job.model = model;
      await this.saveJob(job);
      await this.recordEvent(job, "model_confirmed", {
        currentModelId: model.currentModelId,
        availableModelIds: model.availableModelIds,
      });

      turn = this.runtime.startTurn({
        handle,
        text: taskPrompt,
        mode: "prompt",
        requestId: jobIdFrom(job),
        timeoutMs: job.timeoutMs,
        onPermissionRequest: async () => {
          interaction.permission = true;
          return { outcome: "allow_once" };
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
        job.handoff = "Cursor ACP cancelled the active turn.";
        await this.saveAndRecord(job, "cancelled", { eventCount, toolCallCount });
      } else {
        const failure = classifyFailure(
          new BridgeError(
            result?.error?.code ?? "ACP_TURN_FAILED",
            result?.error?.message ?? "Cursor ACP turn failed",
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
      if (handle && job.status === "failed" && this.runtime.close) {
        try {
          await this.runtime.close({ handle, reason: "job failed", discardPersistentState: false });
        } catch {
          // Preserve the primary job result; runtime cleanup is best effort.
        }
      }
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
    // acpx 0.19.0 serializes startTurn calls for a session. Its mode: "steer"
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
      `# Cursor ACP job ${job.jobId}`,
      "",
      `Status: ${job.status}`,
      `Workspace: ${job.workspace}`,
      `Route: ${job.route.executable} acp`,
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
      `# Cursor ACP job ${job.jobId}`,
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
      proof: job.proof,
    };
    if (job.status === "completed" || job.status === "cancelled") result.handoff = job.handoff;
    if (job.error) result.error = job.error;
    if (job.stopReason) result.stopReason = job.stopReason;
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
