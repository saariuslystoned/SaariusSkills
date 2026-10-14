import { execFile as execFileCallback } from "node:child_process";
import { randomBytes } from "node:crypto";
import { appendFile, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { BridgeError, MAX_PROMPT_CHARS, redactSensitive, formatAge, summarizeToolCall } from "./broker.mjs";
import { appendEvent, buildView, createTranscript, isSessionId, loadSession, normalizeHarness, resolveSessionBaseUrl, saveSession, sessionUrl } from "./shed-sessions.mjs";
import { createRepoOwnerGuard, parseOptionalOwners, parseRepoOwners, REMOTE_ORIGIN_OWNERS_ENV, REMOTE_REPO_OWNERS_ENV } from "./repo-allowlist.mjs";

const execFile = promisify(execFileCallback);

// Remote-shed task runner. The remote endpoint exposes only these narrow
// operations (run / status / cancel / steer / result); there is no general exec tool.
// Lane caps are counted per harness (default 5 for antigravity and 5 for muse);
// each task runs in its own git worktree. Over a harness cap a caller gets
// "busy" naming the full harness and queues or falls back.
// The bridge itself keeps no queue.
export const REMOTE_REPOS_ROOT_ENV = "SAARIUS_ACP_REMOTE_REPOS_ROOT";
export const MAX_CONCURRENT_ENV = "SAARIUS_ACP_REMOTE_MAX_CONCURRENT";
export const MAX_CONCURRENT_LIMIT = 16;
export const DEFAULT_HARNESS_CONCURRENCY = 5;
export const SHED_HARNESSES = Object.freeze(["antigravity", "muse"]);
export const DEFAULT_SHED_HARNESS = "antigravity";
export const DEFAULT_ANTIGRAVITY_MODEL = "gemini-4-argon-medium";
export const SHED_ANTIGRAVITY_MODEL_ENV = "SHED_ANTIGRAVITY_MODEL";
export const DEFAULT_ANTIGRAVITY_ADVERTISED_MODELS = Object.freeze([
  DEFAULT_ANTIGRAVITY_MODEL,
  "gemini-3.8-flash-high",
  "gemini-3.1-pro",
  "gemini-3-flash",
]);
export const DEFAULT_MUSE_ADVERTISED_MODELS = Object.freeze([
  "claude-sonnet-4-6",
  "claude-opus-4-6",
  "gpt-5.4",
  "gemini-3.1-pro",
  "fixture-a",
  "fixture-b",
  "fixture-c",
  "fixture-fast",
]);
export const DEFAULT_ADVERTISED_MODELS = Object.freeze({
  antigravity: DEFAULT_ANTIGRAVITY_ADVERTISED_MODELS,
  muse: DEFAULT_MUSE_ADVERTISED_MODELS,
});
export const STEER_MAX = 8_000;
export const SHED_STATE_DIR_ENV = "SAARIUS_ACP_SHED_STATE_DIR";
export const SAARIUS_ACP_HARNESS_ENV = "SAARIUS_ACP_HARNESS";
export const BRANCH_PREFIX = "shed/";
// headBranch may only continue branches the shed (shed/<taskId>) or a Codex
// lane (codex/<name>) owns; never main/master/baseBranch or the repo default.
export const HEAD_BRANCH_PREFIXES = Object.freeze([BRANCH_PREFIX, "codex/"]);
const PROTECTED_BRANCHES = new Set(["main", "master", "head"]);
const TERMINAL_TASK_STATUSES = new Set([
  "pr_opened",
  "pushed",
  "no_changes",
  "cancelled",
  "failed",
  "unavailable",
]);
const isCancelled = (task) => task.status === "cancelling" || task.status === "cancelled";
export const FORGES = Object.freeze(["github", "origin"]);
const REPO_PATTERN = /^[A-Za-z0-9._-]{1,100}$/;
const BRANCH_PATTERN = /^(?!.*\.\.)(?!-)[A-Za-z0-9._/-]{1,100}$/;
const LABEL_PATTERN = /^[A-Za-z0-9_.@-]{1,64}$/;
const TITLE_MAX = 120;
const POLL_WAIT_MS = 30_000;
// shed_task_run waits this long for ACP session/new so its first response can
// carry session_id / session_url; past it the ids appear in shed_task_status.
export const SESSION_WAIT_MS = 10_000;
const MAX_PENDING_EVENTS = 500;
// Refuse token-shaped values in task input; callers must never pass secrets.
const SECRET_INPUT_PATTERN =
  /\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})\b|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----/i;

const SHED_INSTRUCTIONS = [
  "You are running on the owner's AI Shed through SaariusSkills remote-shed mode.",
  "Make the requested change in this repository working tree only.",
  "You may create local commits (including merges) if the task needs them, but never push, force-push, rewrite published history, switch branches, or open pull requests; the shed pushes after you finish.",
  "Do not read, print, or write credentials, tokens, .env files, or private keys.",
  "Finish with a short plain-text summary of what you changed.",
].join("\n");

// Shed commits keep the owner as author (repo git config). The Muse harness is
// credited through a Co-authored-by trailer only when MUSE_COAUTHOR is set to a
// GitHub-recognized identity (e.g. "Muse <12345+muse-bot@users.noreply.github.com>"
// or "12345+muse-bot@users.noreply.github.com"); unset/empty adds no trailer.
export const SHED_COMMIT_AUTHOR = "saariuslystoned <159389674+saariuslystoned@users.noreply.github.com>";
export const MUSE_COAUTHOR_ENV = "MUSE_COAUTHOR";
const MUSE_TRAILER_PATTERN = /^[ \t]*Co-authored-by:[ \t]*Muse\b/im;

function parseMuseCoAuthor(envOrIdentity = process.env) {
  const rawValue = typeof envOrIdentity === "string"
    ? envOrIdentity
    : (envOrIdentity?.[MUSE_COAUTHOR_ENV] ?? envOrIdentity?.coAuthor ?? "");
  const cleaned = typeof rawValue === "string"
    ? rawValue.replace(/[\r\n]+/g, " ").replace(/^[ \t]*Co-authored-by:[ \t]*/i, "").trim()
    : "";
  if (!cleaned) return null;
  const angleMatch = cleaned.match(/^([^<>]*?)<([^<>\s]+@[^<>\s]+)>$/);
  if (angleMatch) {
    const name = angleMatch[1].trim() || "Muse";
    const email = angleMatch[2].trim();
    return { name, email };
  }
  const plainEmail = cleaned.replace(/^[<]+|[>]+$/g, "").trim();
  if (/^[^\s<>@]+@[^\s<>@]+$/.test(plainEmail)) {
    return { name: "Muse", email: plainEmail };
  }
  return null;
}

export function museCoAuthorTrailer(model, env = process.env) {
  const identity = parseMuseCoAuthor(env);
  if (!identity) return "";
  const id = typeof model === "string" ? model.trim().replace(/[\r\n<>]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 120) : "";
  return id
    ? `Co-authored-by: ${identity.name} (${id}) <${identity.email}>`
    : `Co-authored-by: ${identity.name} <${identity.email}>`;
}

function hasExistingMuseTrailer(text, identity) {
  if (MUSE_TRAILER_PATTERN.test(text)) return true;
  if (!identity) return false;
  const emailLower = `<${identity.email.toLowerCase()}>`;
  const nameLower = identity.name.toLowerCase();
  return text.split(/\r?\n/).some((line) => {
    if (!/^[ \t]*Co-authored-by:/i.test(line)) return false;
    const lower = line.toLowerCase();
    return lower.includes(emailLower) || lower.includes(nameLower);
  });
}

export function appendCoAuthorTrailer(message, { harness, model, env = process.env, coAuthor } = {}) {
  const text = String(message ?? "");
  const h = typeof harness === "string" ? harness.trim().toLowerCase() : "";
  if (h !== "muse" && h !== "muse-acp") return text;
  const identity = parseMuseCoAuthor(coAuthor ?? env);
  if (!identity) return text;
  if (hasExistingMuseTrailer(text, identity)) return text;
  const trailer = museCoAuthorTrailer(model, coAuthor ?? env);
  return text.trim() ? `${text.replace(/\s+$/, "")}\n\n${trailer}` : trailer;
}

function coAuthorPromptNote(harness, model, env = process.env) {
  const h = typeof harness === "string" ? harness.trim().toLowerCase() : "";
  if (h !== "muse" && h !== "muse-acp") return "";
  const identity = parseMuseCoAuthor(env);
  if (!identity) return "";
  const trailer = typeof model === "string" && model.trim()
    ? museCoAuthorTrailer(model, env)
    : `Co-authored-by: ${identity.name} (<your exact model id>) <${identity.email}>`;
  return `\nIf you create git commits, end each commit message with this trailer line: ${trailer}`;
}

export class ShedTaskError extends BridgeError {}

export function parseMaxConcurrent(value) {
  if (value === undefined || value === null || String(value).trim() === "") return 1;
  const text = String(value).trim();
  const n = Number(text);
  if (!/^[0-9]+$/.test(text) || !Number.isInteger(n) || n < 1 || n > MAX_CONCURRENT_LIMIT) {
    throw new ShedTaskError("MAX_CONCURRENT_INVALID", `${MAX_CONCURRENT_ENV} must be an integer from 1 to ${MAX_CONCURRENT_LIMIT}`);
  }
  return n;
}

export function resolveAntigravityModel({ antigravityModel, model } = {}, env = process.env) {
  const explicit = antigravityModel ?? model;
  if (typeof explicit === "string" && explicit.trim()) return explicit.trim();
  const fromEnv = env?.[SHED_ANTIGRAVITY_MODEL_ENV] ?? env?.SAARIUS_ACP_ANTIGRAVITY_MODEL;
  if (typeof fromEnv === "string" && fromEnv.trim()) return fromEnv.trim();
  return DEFAULT_ANTIGRAVITY_MODEL;
}

export function resolveHarnessCaps(maxConcurrent, env = process.env) {
  let antigravity = DEFAULT_HARNESS_CONCURRENCY;
  let muse = DEFAULT_HARNESS_CONCURRENCY;

  if (typeof maxConcurrent === "number") {
    const cap = parseMaxConcurrent(maxConcurrent);
    antigravity = cap;
    muse = cap;
  } else if (typeof maxConcurrent === "object" && maxConcurrent !== null) {
    if (maxConcurrent.antigravity !== undefined) antigravity = parseMaxConcurrent(maxConcurrent.antigravity);
    if (maxConcurrent.muse !== undefined) muse = parseMaxConcurrent(maxConcurrent.muse);
  } else if (env[MAX_CONCURRENT_ENV] !== undefined && env[MAX_CONCURRENT_ENV] !== null && String(env[MAX_CONCURRENT_ENV]).trim() !== "") {
    const cap = parseMaxConcurrent(env[MAX_CONCURRENT_ENV]);
    antigravity = cap;
    muse = cap;
  }

  if (env.SAARIUS_ACP_REMOTE_MAX_CONCURRENT_ANTIGRAVITY !== undefined && String(env.SAARIUS_ACP_REMOTE_MAX_CONCURRENT_ANTIGRAVITY).trim() !== "") {
    antigravity = parseMaxConcurrent(env.SAARIUS_ACP_REMOTE_MAX_CONCURRENT_ANTIGRAVITY);
  }
  if (env.SAARIUS_ACP_REMOTE_MAX_CONCURRENT_MUSE !== undefined && String(env.SAARIUS_ACP_REMOTE_MAX_CONCURRENT_MUSE).trim() !== "") {
    muse = parseMaxConcurrent(env.SAARIUS_ACP_REMOTE_MAX_CONCURRENT_MUSE);
  }

  return { antigravity, muse };
}

function assertNoSecrets(value, field) {
  if (SECRET_INPUT_PATTERN.test(value)) {
    throw new ShedTaskError("SECRET_REFUSED", `${field} looks like it contains a secret; remote tasks must never carry secrets`);
  }
}

function assertCaller(caller) {
  if (
    !caller ||
    typeof caller !== "object" ||
    typeof caller.label !== "string" ||
    !LABEL_PATTERN.test(caller.label.trim())
  ) {
    throw new ShedTaskError("ACCESS_DENIED", "Valid Access caller identity is required");
  }
  return { ...caller, label: caller.label.trim() };
}

function validateRequestedBy(requested_by) {
  if (typeof requested_by !== "string" || !LABEL_PATTERN.test(requested_by)) {
    throw new ShedTaskError("REQUESTED_BY_REQUIRED", "requested_by must name the bot that asked (letters, digits, _ . @ -)");
  }
  return requested_by;
}

const clean = (value, max = 2_400) => {
  const safe = redactSensitive(String(value ?? "")).trim();
  return safe.length > max ? `${safe.slice(0, max - 1)}…` : safe;
};

async function defaultRun(command, args, { cwd, timeoutMs = 120_000 } = {}) {
  const { stdout } = await execFile(command, args, {
    cwd,
    timeout: timeoutMs,
    maxBuffer: 1024 * 1024,
    env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GH_PROMPT_DISABLED: "1" },
  });
  return stdout.trim();
}

export class ShedTaskRunner {
  constructor({
    broker,
    brokers,
    env = process.env,
    run = defaultRun,
    maxConcurrent,
    owners,
    originOwners,
    reposRoot,
    stateDir,
    guard,
    log,
    now = () => new Date(),
    sessionWaitMs = SESSION_WAIT_MS,
    sessionBaseUrl,
    harness,
    antigravityModel,
    model,
    advertisedModels,
  } = {}) {
    this.env = env;
    this.antigravityModel = resolveAntigravityModel({ antigravityModel, model }, env);
    this.model = this.antigravityModel;
    this.advertisedModels = advertisedModels ?? null;
    this.broker = broker;
    this.brokers = new Map();
    if (brokers) {
      if (brokers instanceof Map) {
        for (const [k, v] of brokers.entries()) this.brokers.set(normalizeHarness(k), v);
      } else {
        for (const [k, v] of Object.entries(brokers)) this.brokers.set(normalizeHarness(k), v);
      }
    }
    if (broker) {
      const h = normalizeHarness(broker.harness ?? broker.agent ?? "antigravity");
      if (!this.brokers.has(h)) this.brokers.set(h, broker);
      if (!this.brokers.has("antigravity")) this.brokers.set("antigravity", broker);
    }
    this.unsubscribers = [];
    this.run = run;
    this.now = now;
    this.harness = normalizeHarness(harness ?? env[SAARIUS_ACP_HARNESS_ENV] ?? env.SAARIUS_ACP_HARNESS ?? broker?.harness ?? broker?.agent ?? "antigravity");
    this.owners = owners ? new Set([...owners].map((o) => o.toLowerCase())) : parseRepoOwners(env[REMOTE_REPO_OWNERS_ENV]);
    this.originOwners = originOwners ? new Set([...originOwners].map((o) => o.toLowerCase())) : parseOptionalOwners(env[REMOTE_ORIGIN_OWNERS_ENV], REMOTE_ORIGIN_OWNERS_ENV);
    this.reposRoot = reposRoot ?? env[REMOTE_REPOS_ROOT_ENV]?.trim();
    if (!this.reposRoot || !path.isAbsolute(this.reposRoot)) {
      throw new ShedTaskError("REMOTE_REPOS_ROOT_REQUIRED", `${REMOTE_REPOS_ROOT_ENV} must be an absolute directory holding <owner>/<repo> clones`);
    }
    this.stateDir = stateDir ?? env[SHED_STATE_DIR_ENV]?.trim() ?? path.join(this.reposRoot, ".saarius-shed");
    this.guard = guard ?? createRepoOwnerGuard({ owners: this.owners, originOwners: this.originOwners });
    this.log = log ?? ((record) => appendFile(path.join(this.stateDir, "tasks.jsonl"), `${JSON.stringify(record)}\n`));
    this.tasks = new Map();
    this.maxConcurrent = resolveHarnessCaps(maxConcurrent, env);
    // taskId -> task for every task holding a slot (starting through finish).
    this.active = new Map();
    this.idleWaiters = new Set();
    this.taskWaiters = new Map();
    // Per-clone promise chain so fetch / worktree add / remove on one repo never race on git locks.
    this.repoLocks = new Map();
    // Session viewer: redacted transcripts keyed by taskId, persisted under
    // <stateDir>/sessions/<sessionId>.json. Never part of tasks/*.json.
    this.sessionWaitMs = sessionWaitMs;
    this.sessionBaseUrl = sessionBaseUrl ?? resolveSessionBaseUrl(env);
    this.sessionsDir = path.join(this.stateDir, "sessions");
    this.transcripts = new Map();
    this.jobTasks = new Map();
    this.pendingEvents = new Map();
    this.flushTimers = new Map();
    this.taskBrokers = new Map();
    for (const b of this.brokers.values()) {
      this.wireBrokerEvents(b);
    }
  }

  wireBrokerEvents(broker) {
    if (broker && typeof broker.addEventObserver === "function") {
      const unsub = broker.addEventObserver((jobId, event) => this.onAgentEvent(jobId, event));
      if (typeof unsub === "function") this.unsubscribers.push(unsub);
    }
  }

  async getBroker(harness) {
    const h = normalizeHarness(harness ?? this.harness);
    let broker = this.brokers.get(h);
    if (!broker && h === "muse") {
      try {
        const { MuseAcpBroker } = await import("../muse-acp/broker.mjs");
        broker = await new MuseAcpBroker().init();
        this.brokers.set("muse", broker);
        this.wireBrokerEvents(broker);
      } catch (err) {
        throw new ShedTaskError("BROKER_UNAVAILABLE", `Muse broker could not be initialized: ${err.message}`);
      }
    }
    if (!broker && h === "antigravity") {
      broker = this.broker;
    }
    if (!broker) {
      throw new ShedTaskError("BROKER_UNAVAILABLE", `No broker available for harness "${harness}"`);
    }
    return broker;
  }

  async getAdvertisedModels(harness, broker) {
    const h = normalizeHarness(harness ?? this.harness);
    const normalize = (list) =>
      [...new Set([...list].filter((m) => typeof m === "string" && m.trim()).map((m) => m.trim()))];
    if (Array.isArray(this.advertisedModels) || this.advertisedModels instanceof Set) {
      return normalize(this.advertisedModels);
    }
    if (
      this.advertisedModels &&
      typeof this.advertisedModels === "object" &&
      (Array.isArray(this.advertisedModels[h]) || this.advertisedModels[h] instanceof Set)
    ) {
      return normalize(this.advertisedModels[h]);
    }
    if (typeof broker?.getAdvertisedModels === "function") {
      const dynamic = await broker.getAdvertisedModels();
      if (Array.isArray(dynamic) || dynamic instanceof Set) return normalize(dynamic);
    }
    if (typeof broker?.listModels === "function") {
      const dynamic = await broker.listModels();
      if (Array.isArray(dynamic) || dynamic instanceof Set) return normalize(dynamic);
    }
    if (Array.isArray(broker?.advertisedModels) || broker?.advertisedModels instanceof Set) {
      return normalize(broker.advertisedModels);
    }
    if (Array.isArray(broker?.availableModelIds) || broker?.availableModelIds instanceof Set) {
      return normalize(broker.availableModelIds);
    }
    if (Array.isArray(broker?.models?.availableModelIds)) {
      return normalize(broker.models.availableModelIds);
    }
    if (Array.isArray(broker?.models)) {
      return normalize(broker.models);
    }
    if (typeof broker?.verifyModel === "function") {
      return null;
    }
    const defaults = [...(DEFAULT_ADVERTISED_MODELS[h] ?? [])];
    if (h === "antigravity" && this.antigravityModel) {
      defaults.push(this.antigravityModel);
    }
    return normalize(defaults);
  }

  applyToolLatestEvent(task, event, at) {
    const toolInfo = summarizeToolCall(event);
    const isFinished = event.status === "completed" || event.status === "failed" || event.status === "error";
    task.latestEvent = {
      event: isFinished ? "tool_call_finished" : "tool_call_started",
      tool: toolInfo.tool,
      // Completion updates often carry only rawOutput; keep the started
      // call's command summary instead of overwriting it with an empty one.
      summary: toolInfo.summary || task.latestEvent?.summary || "",
      status: event.status,
      timestamp: at,
      at,
    };
    task.updatedAt = at;
  }

  onAgentEvent(jobId, event) {
    const task = this.jobTasks.get(jobId);
    if (!task) {
      // Event raced ahead of delegate() returning; hold a bounded buffer.
      const pending = this.pendingEvents.get(jobId) ?? [];
      if (pending.length < MAX_PENDING_EVENTS) pending.push({ event, at: this.now().toISOString() });
      this.pendingEvents.set(jobId, pending);
      return;
    }
    const at = this.now().toISOString();
    if (event?.type === "job_event") {
      task.latestEvent = {
        event: event.event,
        timestamp: event.timestamp || at,
        at: event.timestamp || at,
        ...event.details,
      };
      task.updatedAt = task.latestEvent.timestamp;
    } else if (event?.type === "tool_call") {
      this.applyToolLatestEvent(task, event, at);
    }
    const transcript = this.transcripts.get(task.taskId);
    if (!transcript) return;
    appendEvent(transcript, event, at);
    this.scheduleFlush(task);
  }

  bindJob(task, jobId) {
    task.jobId = jobId;
    this.jobTasks.set(jobId, task);
    const transcript = this.transcripts.get(task.taskId);
    for (const { event, at } of this.pendingEvents.get(jobId) ?? []) {
      if (event?.type === "job_event") {
        task.latestEvent = {
          event: event.event,
          timestamp: event.timestamp || at,
          at: event.timestamp || at,
          ...event.details,
        };
        task.updatedAt = task.latestEvent.timestamp;
      } else if (event?.type === "tool_call") {
        this.applyToolLatestEvent(task, event, at);
      }
      if (transcript) appendEvent(transcript, event, at);
    }
    this.pendingEvents.delete(jobId);
  }

  scheduleFlush(task) {
    if (!task.sessionId || this.flushTimers.has(task.taskId)) return;
    const timer = setTimeout(() => {
      this.flushTimers.delete(task.taskId);
      void this.flushSession(task).catch(() => {});
    }, 1_000);
    timer.unref?.();
    this.flushTimers.set(task.taskId, timer);
  }

  async flushSession(task) {
    if (!isSessionId(task.sessionId)) return;
    const transcript = this.transcripts.get(task.taskId);
    if (!transcript) return;
    const harness = normalizeHarness(task.harness ?? this.harness);
    await saveSession(this.sessionsDir, task.sessionId, { sessionId: task.sessionId, harness, task: this.publicTask(task), transcript });
  }

  async viewSession(sessionId) {
    if (!isSessionId(sessionId)) return null;
    for (const task of this.tasks.values()) {
      if (task.sessionId === sessionId && this.transcripts.has(task.taskId)) {
        return buildView({ sessionId, harness: task.harness ?? this.harness, task: this.publicTask(task), transcript: this.transcripts.get(task.taskId) });
      }
    }
    const stored = await loadSession(this.sessionsDir, sessionId);
    if (!stored || stored.sessionId !== sessionId) return null;
    return buildView({ sessionId, harness: stored.harness ?? stored.task?.harness, task: stored.task, transcript: stored.transcript });
  }

  // Oldest running task id, kept for callers that read the single-task field.
  get activeTaskId() {
    return this.active.keys().next().value ?? null;
  }

  activeTaskIdForHarness(harness) {
    const h = harness ? normalizeHarness(harness) : undefined;
    for (const [taskId, task] of this.active.entries()) {
      if (!h || (task.harness ?? this.harness) === h) return taskId;
    }
    return null;
  }

  maxConcurrentFor(harness) {
    const h = normalizeHarness(harness ?? this.harness);
    return this.maxConcurrent[h] ?? DEFAULT_HARNESS_CONCURRENCY;
  }

  activeCountForHarness(harness) {
    const h = normalizeHarness(harness ?? this.harness);
    let count = 0;
    for (const task of this.active.values()) {
      if ((task.harness ?? this.harness) === h) count += 1;
    }
    return count;
  }

  withRepoLock(repoDir, fn) {
    const prev = this.repoLocks.get(repoDir) ?? Promise.resolve();
    const next = prev.catch(() => {}).then(fn);
    const tail = next.catch(() => {});
    this.repoLocks.set(repoDir, tail);
    tail.then(() => { if (this.repoLocks.get(repoDir) === tail) this.repoLocks.delete(repoDir); });
    return next;
  }

  branchKey(task) {
    return `${task.forge}:${task.owner}/${task.repo}#${task.branch}`.toLowerCase();
  }

  async init() {
    await mkdir(path.join(this.stateDir, "worktrees"), { recursive: true });
    await mkdir(path.join(this.stateDir, "tasks"), { recursive: true });
    await mkdir(this.sessionsDir, { recursive: true, mode: 0o700 });
    return this;
  }

  async record(task, event, details = {}) {
    task.updatedAt = this.now().toISOString();
    task.latestEvent = {
      event,
      timestamp: task.updatedAt,
      at: task.updatedAt,
      ...details,
    };
    await writeFile(path.join(this.stateDir, "tasks", `${task.taskId}.json`), JSON.stringify(task, null, 2));
    // Audit line: who ran what, where. Never the task text or any secret.
    await this.log({
      at: task.updatedAt,
      event,
      taskId: task.taskId,
      caller: task.caller,
      requestedBy: task.requestedBy,
      harness: task.harness ?? this.harness,
      model: task.model ?? null,
      repo: `${task.owner}/${task.repo}`,
      forge: task.forge,
      branch: task.branch,
      headSha: task.headSha ?? null,
      status: task.status,
      prUrl: task.prUrl ?? null,
      errorCode: task.error?.code ?? null,
    });
  }

  publicTask(task) {
    const out = {
      taskId: task.taskId,
      status: task.status,
      harness: task.harness ?? this.harness,
      repo: `${task.owner}/${task.repo}`,
      forge: task.forge,
      baseBranch: task.baseBranch,
      branch: task.branch,
      mode: task.headBranch ? "existing_branch" : "new_branch",
      requestedBy: task.requestedBy,
      createdAt: task.createdAt,
      updatedAt: task.updatedAt,
    };
    if (task.model) out.model = task.model;
    if (task.startSha) out.startSha = task.startSha;
    if (task.headSha) out.headSha = task.headSha;
    if (task.commitsAhead !== undefined) out.commitsAhead = task.commitsAhead;
    if (task.prUrl) out.prUrl = task.prUrl;
    if (task.sessionId) {
      out.session_id = task.sessionId;
      out.session_url = sessionUrl(this.sessionBaseUrl, task.sessionId);
    }
    if (task.summary) out.summary = task.summary;
    if (task.error) out.error = task.error;
    if (task.latestEvent) {
      out.latestEvent = task.latestEvent;
      const at = task.latestEvent.timestamp ?? task.latestEvent.at;
      const atMs = at ? new Date(at).getTime() : null;
      if (atMs && Number.isFinite(atMs)) {
        const ageMs = Math.max(0, this.now().getTime() - atMs);
        out.latestEventAgeMs = ageMs;
        out.latestEventAge = formatAge(ageMs);
      }
    }
    return out;
  }

  runningSummary(task) {
    const summary = {
      taskId: task.taskId,
      status: task.status,
      harness: task.harness ?? this.harness,
      ...(task.model ? { model: task.model } : {}),
      repo: `${task.owner}/${task.repo}`,
      forge: task.forge,
      branch: task.branch,
      requestedBy: task.requestedBy,
      startedAt: task.createdAt,
      ...(task.sessionId ? { session_id: task.sessionId, session_url: sessionUrl(this.sessionBaseUrl, task.sessionId) } : {}),
    };
    if (task.latestEvent) {
      summary.latestEvent = task.latestEvent;
      const at = task.latestEvent.timestamp ?? task.latestEvent.at;
      const atMs = at ? new Date(at).getTime() : null;
      if (atMs && Number.isFinite(atMs)) {
        const ageMs = Math.max(0, this.now().getTime() - atMs);
        summary.latestEventAgeMs = ageMs;
        summary.latestEventAge = formatAge(ageMs);
      }
    }
    return summary;
  }

  // status: "idle" (nothing running), "available" (running < cap), "busy" (at cap).
  shedState(targetHarness) {
    if (targetHarness) {
      const h = normalizeHarness(targetHarness);
      const harnessTasks = [...this.active.values()]
        .filter((t) => (t.harness ?? this.harness) === h)
        .map((t) => this.runningSummary(t));
      const running = harnessTasks.length;
      const maxConcurrent = this.maxConcurrentFor(h);
      const out = {
        status: running === 0 ? "idle" : running >= maxConcurrent ? "busy" : "available",
        harness: h,
        running,
        maxConcurrent,
        tasks: harnessTasks,
      };
      const activeId = this.activeTaskIdForHarness(h);
      if (activeId) out.activeTaskId = activeId;
      if (out.status === "busy") {
        out.message = `The shed is at its concurrency cap for ${h} (${running}/${maxConcurrent} tasks running); queue and retry later, or fall back.`;
      }
      return out;
    }

    const running = this.active.size;
    const defaultCap = this.maxConcurrentFor(this.harness);
    const defaultRunning = this.activeCountForHarness(this.harness);
    const out = {
      status: running === 0 ? "idle" : defaultRunning >= defaultCap ? "busy" : "available",
      running,
      maxConcurrent: defaultCap,
      tasks: [...this.active.values()].map((task) => this.runningSummary(task)),
    };
    if (running > 0) out.activeTaskId = this.activeTaskId;
    if (out.status === "busy") {
      out.message = `The shed is at its concurrency cap (${running}/${defaultCap} tasks running); queue and retry later, or fall back.`;
    }
    return out;
  }

  validate({ owner, repo, task, baseBranch, headBranch, forge, title, requested_by, harness, model }) {
    const safeForge = forge ?? "github";
    if (!FORGES.includes(safeForge)) throw new ShedTaskError("FORGE_INVALID", "forge must be github or origin");
    const allowedOwners = safeForge === "origin" ? this.originOwners : this.owners;
    if (typeof owner !== "string" || !allowedOwners.has(owner.toLowerCase())) {
      throw new ShedTaskError("REPO_OWNER_REFUSED", `owner is not on the shed's ${safeForge} repo allowlist`, { allowedOwners: [...allowedOwners] });
    }
    if (typeof repo !== "string" || !REPO_PATTERN.test(repo) || repo.startsWith(".")) {
      throw new ShedTaskError("REPO_INVALID", "repo must be a plain GitHub repository name");
    }
    if (typeof task !== "string" || !task.trim() || task.length > MAX_PROMPT_CHARS - SHED_INSTRUCTIONS.length - 200) {
      throw new ShedTaskError("TASK_INVALID", "task must be non-empty bounded text");
    }
    const base = baseBranch ?? "main";
    if (!BRANCH_PATTERN.test(base)) throw new ShedTaskError("BASE_BRANCH_INVALID", "baseBranch is not a safe branch name");
    if (headBranch !== undefined && (
      typeof headBranch !== "string"
      || !BRANCH_PATTERN.test(headBranch)
      || headBranch.toLowerCase() === base.toLowerCase()
      || PROTECTED_BRANCHES.has(headBranch.toLowerCase())
      || !HEAD_BRANCH_PREFIXES.some((prefix) => headBranch.startsWith(prefix) && headBranch.length > prefix.length)
    )) {
      throw new ShedTaskError("HEAD_BRANCH_INVALID", `headBranch must be an existing shed-owned branch (${HEAD_BRANCH_PREFIXES.join(", ")}) different from baseBranch, main, master, and the repo default branch`);
    }
    validateRequestedBy(requested_by);
    const rawHarness = harness === undefined || harness === null ? DEFAULT_SHED_HARNESS : harness;
    if (typeof rawHarness !== "string" || !SHED_HARNESSES.includes(rawHarness.trim().toLowerCase())) {
      throw new ShedTaskError("HARNESS_INVALID", `harness must be one of: ${SHED_HARNESSES.join(", ")}`);
    }
    const safeHarness = rawHarness.trim().toLowerCase();
    const safeTitle = typeof title === "string" && title.trim() ? title.trim().slice(0, TITLE_MAX) : undefined;
    let safeModel;
    if (model !== undefined) {
      if (
        typeof model !== "string" ||
        !model.trim() ||
        model !== model.trim() ||
        model.length > 120 ||
        model.includes("\u0000")
      ) {
        throw new ShedTaskError("MODEL_INVALID", "model must be a non-empty model ID string (max 120 chars)");
      }
      assertNoSecrets(model, "model");
      safeModel = model;
    }
    assertNoSecrets(task, "task");
    if (safeTitle) assertNoSecrets(safeTitle, "title");
    return {
      owner: owner.toLowerCase(),
      repo,
      forge: safeForge,
      task,
      baseBranch: base,
      headBranch,
      title: safeTitle,
      requestedBy: requested_by,
      harness: safeHarness,
      ...(safeModel ? { model: safeModel } : {}),
    };
  }

  validateSteer({ taskId, instruction, requested_by } = {}) {
    const safeRequestedBy = validateRequestedBy(requested_by);
    if (typeof taskId !== "string" || !taskId.trim()) {
      throw new ShedTaskError("TASK_NOT_FOUND", "unknown task");
    }
    if (
      typeof instruction !== "string" ||
      !instruction.trim() ||
      instruction.length > STEER_MAX ||
      instruction.includes("\u0000")
    ) {
      throw new ShedTaskError(
        "INSTRUCTION_INVALID",
        `instruction must be a non-empty string up to ${STEER_MAX} characters`,
      );
    }
    assertNoSecrets(instruction, "instruction");
    return {
      taskId: taskId.trim(),
      instruction: instruction.trim(),
      requestedBy: safeRequestedBy,
    };
  }

  async runTask(input, caller) {
    const verifiedCaller = assertCaller(caller);
    const request = this.validate(input ?? {});
    const harness = request.harness;
    if (request.model !== undefined) {
      const brokerForValidation = this.brokers.get(harness) ?? (harness === "antigravity" ? this.broker : undefined);
      const advertised = await this.getAdvertisedModels(harness, brokerForValidation);
      if (Array.isArray(advertised) && !advertised.includes(request.model)) {
        throw new ShedTaskError(
          "MODEL_INVALID",
          `Unknown model "${request.model}": not advertised by harness "${harness}" (advertised: ${advertised.join(", ") || "none"})`,
          { harness, model: request.model, advertisedModels: advertised },
        );
      }
    }
    const runningForHarness = this.activeCountForHarness(harness);
    const capForHarness = this.maxConcurrentFor(harness);
    if (runningForHarness >= capForHarness) return this.shedState(harness);

    const repoDir = path.join(this.reposRoot, request.owner, request.repo);
    // Everything below up to the slot reservation is synchronous, so two
    // concurrent calls can never both take the last slot or the same branch.
    if (request.headBranch) {
      const key = this.branchKey({ ...request, branch: request.headBranch });
      const holder = [...this.active.values()].find((t) => this.branchKey(t) === key);
      if (holder) {
        throw new ShedTaskError(
          "BRANCH_BUSY",
          `${request.owner}/${request.repo} branch ${request.headBranch} already has a running shed task (${holder.taskId}); wait for it to finish or cancel it`,
          { taskId: holder.taskId, branch: request.headBranch },
        );
      }
    }
    const stamp = this.now().toISOString().replace(/[-:]/g, "").replace(/\..*$/, "");
    const taskId = `shed-${stamp}-${randomBytes(3).toString("hex")}`;
    const chosenModel = request.model ?? (request.harness === "antigravity" ? this.antigravityModel : undefined);
    const task = {
      taskId,
      status: "starting",
      harness: request.harness,
      ...request,
      ...(chosenModel ? { model: chosenModel } : {}),
      task: undefined,
      branch: request.headBranch ?? `${BRANCH_PREFIX}${taskId}`,
      mode: request.headBranch ? "existing_branch" : "new_branch",
      caller: verifiedCaller.label,
      createdAt: this.now().toISOString(),
      worktree: path.join(this.stateDir, "worktrees", taskId),
    };
    this.active.set(taskId, task);
    try {
      if (!(await stat(repoDir)).isDirectory()) throw new Error("not a directory");
    } catch {
      this.releaseActive(taskId, task);
      return { status: "unavailable", reason: "REPO_NOT_ON_SHED", message: `${request.owner}/${request.repo} is not cloned under the shed repos root` };
    }

    this.tasks.set(taskId, task);
    const transcript = createTranscript({ prompt: request.task });
    this.transcripts.set(taskId, transcript);

    const started = new Promise((resolve, reject) => {
      let timer;
      timer = setTimeout(() => resolve({ ...this.publicTask(task), sessionPending: true, message: "ACP session is still starting; read session_id / session_url from shed_task_status" }), this.sessionWaitMs);
      this.start(task, request, repoDir).then(
        (v) => {
          clearTimeout(timer);
          resolve(v);
        },
        (err) => {
          clearTimeout(timer);
          reject(err);
        },
      );
    });

    return started;
  }

  async start(task, request, repoDir) {
    const { taskId } = task;
    let broker;
    try {
      await this.record(task, "accepted");
      broker = await this.getBroker(task.harness);
      this.taskBrokers.set(taskId, broker);
      if (request.model !== undefined) {
        const advertised = await this.getAdvertisedModels(task.harness, broker);
        if (Array.isArray(advertised) && !advertised.includes(request.model)) {
          throw new ShedTaskError(
            "MODEL_INVALID",
            `Unknown model "${request.model}": not advertised by harness "${task.harness}" (advertised: ${advertised.join(", ") || "none"})`,
            { harness: task.harness, model: request.model, advertisedModels: advertised },
          );
        }
      }
      const startRef = request.headBranch ?? request.baseBranch;
      // Each task gets its own worktree under <stateDir>/worktrees/<taskId>.
      await this.withRepoLock(repoDir, async () => {
        if (isCancelled(task)) return;
        if (request.headBranch) await this.refuseDefaultBranch(request.headBranch, repoDir);
        await this.run("git", ["fetch", "--quiet", "origin", `+refs/heads/${startRef}:refs/remotes/origin/${startRef}`], { cwd: repoDir, timeoutMs: 300_000 });
        task.startSha = await this.run("git", ["rev-parse", "--verify", `refs/remotes/origin/${startRef}^{commit}`], { cwd: repoDir });
        if (request.headBranch) {
          // Existing PR branch: detached checkout at the remote head; pushed back fast-forward only.
          await this.run("git", ["worktree", "add", "--quiet", "--detach", task.worktree, task.startSha], { cwd: repoDir });
        } else {
          await this.run("git", ["worktree", "add", "--quiet", "-b", task.branch, task.worktree, task.startSha], { cwd: repoDir });
        }
        task.repoDir = repoDir;
      });
      // A cancel that arrived while waiting for the repo lock (or during
      // setup) ends the task here; never delegate a cancelled task.
      if (isCancelled(task)) return this.cancelBeforeRun(task);
      await this.guard(task.worktree);
      if (isCancelled(task)) return this.cancelBeforeRun(task);
      const submitted = await broker.delegate({
        workspace: task.worktree,
        prompt: `${SHED_INSTRUCTIONS}${coAuthorPromptNote(task.harness ?? request.harness, task.model ?? request.model, this.env)}\n\nTask:\n${request.task}`,
        hostConversationId: taskId,
        ...(task.model ? { model: task.model } : {}),
      });
      task.jobId = submitted.jobId;
      if (isSessionId(submitted.backendSessionId)) task.sessionId = submitted.backendSessionId;
      this.bindJob(task, submitted.jobId);
      if (isCancelled(task)) {
        // Cancel landed while delegate() was in flight: stop the job, keep cancelling.
        await broker.cancel({ jobId: task.jobId, reason: "cancelled by remote caller" }).catch(() => {});
        await this.record(task, "cancel_requested");
      } else {
        task.status = "running";
        await this.record(task, "running");
      }
    } catch (error) {
      if (isCancelled(task)) return this.cancelBeforeRun(task);
      if (/^(MODEL_UNAVAILABLE|INVALID_MODEL|MODEL_REQUIRED|MODEL_AMBIGUOUS|MODEL_INVALID)$/i.test(error?.code ?? "")) {
        await this.finish(task, "start_failed");
        this.tasks.delete(taskId);
        throw new ShedTaskError(
          "MODEL_INVALID",
          clean(error?.message || `Model is not advertised by harness ${task.harness}`, 300),
          error?.details ?? { harness: task.harness, model: request.model },
        );
      }
      const unavailable = /READINESS|OAUTH|RUNTIME|AUTH|SETUP|BROKER_UNAVAILABLE/i.test(error?.code ?? "");
      task.status = unavailable ? "unavailable" : "failed";
      task.error = { code: error?.code ?? "TASK_START_FAILED", message: clean(error?.message, 300) };
      await this.finish(task, "start_failed");
      return unavailable
        ? { status: "unavailable", reason: task.error.code, taskId, message: task.error.message }
        : this.publicTask(task);
    }
    this.watch(task).catch(async (error) => {
      task.status = "failed";
      task.error = { code: error?.code ?? "TASK_FAILED", message: clean(error?.message, 300) };
      await this.finish(task, "failed");
    });
    return this.publicTask(task);
  }

  async cancelBeforeRun(task) {
    task.status = "cancelled";
    await this.finish(task, "cancelled");
    return this.publicTask(task);
  }

  // Refuse a headBranch that is the remote's default branch (e.g. "develop").
  async refuseDefaultBranch(headBranch, repoDir) {
    let defaultBranch = "";
    try {
      const out = await this.run("git", ["ls-remote", "--symref", "origin", "HEAD"], { cwd: repoDir, timeoutMs: 120_000 });
      defaultBranch = out.match(/^ref:\s*refs\/heads\/(\S+)\s+HEAD/m)?.[1] ?? "";
    } catch {
      defaultBranch = "";
    }
    if (!defaultBranch) {
      try {
        defaultBranch = (await this.run("git", ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], { cwd: repoDir })).replace(/^origin\//, "");
      } catch {
        defaultBranch = "";
      }
    }
    if (defaultBranch && defaultBranch.toLowerCase() === headBranch.toLowerCase()) {
      throw new ShedTaskError("HEAD_BRANCH_INVALID", "headBranch must not be the repository default branch");
    }
  }

  async watch(task) {
    const broker = this.taskBrokers.get(task.taskId) ?? (await this.getBroker(task.harness));
    let job;
    for (;;) {
      job = await broker.result({ jobId: task.jobId, waitMs: POLL_WAIT_MS });
      if (job.complete || (job.taskComplete && (!broker?.active?.has?.(task.jobId) || job.cleanup?.status === "uncertain"))) break;
    }
    if (!task.model && job?.model?.selectedModelId) {
      task.model = job.model.selectedModelId;
    }
    task.summary = clean(job.handoff);
    const transcript = this.transcripts.get(task.taskId);
    if (transcript) transcript.result = String(job.handoff ?? "").slice(0, 20_000) || null;
    if (task.status === "cancelling" || job.status === "cancelled") {
      task.status = "cancelled";
      return this.finish(task, "cancelled");
    }
    if (job.status !== "completed") {
      task.status = "failed";
      task.error = { code: job.error?.code ?? "AGENT_FAILED", message: clean(job.error?.message ?? job.status, 300) };
      return this.finish(task, "failed");
    }
    if (isCancelled(task)) {
      task.status = "cancelled";
      return this.finish(task, "cancelled");
    }
    const cwd = task.worktree;
    const title = task.title ?? `Shed task ${task.taskId}`;
    if (await this.run("git", ["status", "--porcelain"], { cwd })) {
      await this.run("git", ["add", "-A"], { cwd });
      const body = appendCoAuthorTrailer(`Remote-shed task ${task.taskId} requested by ${task.requestedBy}.`, { harness: task.harness ?? this.harness, model: task.model, env: this.env });
      await this.run("git", ["commit", "--quiet", "-m", title, "-m", body], { cwd });
    }
    // Count commits ahead of the start point, so agent-made commits (git am,
    // merges) are pushed too, not only a dirty worktree.
    task.commitsAhead = Number.parseInt(await this.run("git", ["rev-list", "--count", `${task.startSha}..HEAD`], { cwd }), 10) || 0;
    if (task.commitsAhead === 0) {
      task.status = "no_changes";
      return this.finish(task, "no_changes");
    }
    task.headSha = await this.run("git", ["rev-parse", "HEAD"], { cwd });
    // Last gate before anything leaves the shed.
    if (isCancelled(task)) {
      task.status = "cancelled";
      return this.finish(task, "cancelled");
    }
    task.status = "pushing";
    await this.record(task, "pushing");
    if (task.headBranch) return this.pushExisting(task, cwd);
    // Plain push of a new branch; never --force.
    await this.run("git", ["push", "--quiet", "-u", "origin", `HEAD:refs/heads/${task.branch}`], { cwd, timeoutMs: 300_000 });
    task.status = "opening_pr";
    await this.record(task, "opening_pr");
    const body = [
      `Opened by SaariusSkills remote-shed task \`${task.taskId}\`.`,
      `Requested by: ${task.requestedBy} (Access caller: ${task.caller}).`,
      "",
      "Agent summary:",
      "",
      task.summary || "(none)",
    ].join("\n");
    const prOut = task.forge === "origin"
      ? await this.run("origin", ["pr", "create", "--repo", `${task.owner}/${task.repo}`, "--draft", "--base", task.baseBranch, "--head", task.branch, "--title", title, "--body", body], { cwd, timeoutMs: 120_000 })
      : await this.run("gh", ["pr", "create", "--draft", "--base", task.baseBranch, "--head", task.branch, "--title", title, "--body", body], { cwd, timeoutMs: 120_000 });
    task.prUrl = clean(prOut.match(/https?:\/\/\S+/)?.[0] ?? prOut, 300);
    task.status = "pr_opened";
    return this.finish(task, "pr_opened");
  }

  // Existing PR head branch: fast-forward push only. If the remote branch
  // moved since the task started, fail clearly; never force.
  async pushExisting(task, cwd) {
    const moved = (remoteSha) => {
      task.status = "failed";
      task.error = {
        code: "REMOTE_BRANCH_MOVED",
        message: clean(`origin/${task.branch} moved since the task started (was ${task.startSha}${remoteSha ? `, now ${remoteSha}` : ""}); nothing was pushed. Local result kept at refs/shed/keep/${task.taskId}.`, 400),
      };
      return this.finish(task, "remote_moved");
    };
    let remoteSha = "";
    try {
      const line = await this.run("git", ["ls-remote", "--heads", "origin", `refs/heads/${task.branch}`], { cwd, timeoutMs: 120_000 });
      remoteSha = line.split(/\s+/)[0] ?? "";
    } catch {
      remoteSha = "";
    }
    if (remoteSha !== task.startSha) return moved(remoteSha);
    try {
      await this.run("git", ["push", "--quiet", "origin", `HEAD:refs/heads/${task.branch}`], { cwd, timeoutMs: 300_000 });
    } catch (error) {
      if (/non-fast-forward|fetch first|rejected|stale info/i.test(String(error?.stderr ?? error?.message ?? ""))) return moved("");
      throw error;
    }
    if (task.forge === "github") {
      task.prUrl = clean(await this.run("gh", ["pr", "view", task.branch, "--json", "url", "--jq", ".url"], { cwd, timeoutMs: 60_000 }).catch(() => ""), 300) || undefined;
    }
    task.status = "pushed";
    return this.finish(task, "pushed");
  }

  async finish(task, event) {
    task.finishedAt = this.now().toISOString();
    let hasUncommitted = false;
    if (task.repoDir && task.worktree && !["pushed", "pr_opened"].includes(task.status)) {
      try {
        const dirty = await this.run("git", ["status", "--porcelain"], { cwd: task.worktree });
        if (dirty && dirty.trim().length > 0) {
          try {
            await this.run("git", ["add", "-A"], { cwd: task.worktree });
            await this.run("git", [
              "commit",
              "--quiet",
              "--no-verify",
              "-m",
              appendCoAuthorTrailer(`Rescue uncommitted changes for task ${task.taskId}`, { harness: task.harness ?? this.harness, model: task.model, env: this.env }),
            ], { cwd: task.worktree });
          } catch {
            hasUncommitted = true;
          }
        }
      } catch {
        hasUncommitted = true;
      }
      if (task.startSha) {
        // Keep any unpushed agent commits reachable after the worktree goes away.
        try {
          const head = await this.run("git", ["rev-parse", "HEAD"], { cwd: task.worktree });
          if (head && head !== task.startSha) {
            await this.run("git", ["update-ref", `refs/shed/keep/${task.taskId}`, head], { cwd: task.worktree });
          }
        } catch {
          // best effort
        }
      }
    }
    if (task.repoDir && task.worktree) {
      if (!hasUncommitted) {
        // Remove the worktree; the branch (and its PR) stay.
        await this.withRepoLock(task.repoDir, () =>
          this.run("git", ["worktree", "remove", "--force", task.worktree], { cwd: task.repoDir })
            .catch(() => rm(task.worktree, { recursive: true, force: true }))
            .then(() => this.run("git", ["worktree", "prune"], { cwd: task.repoDir }).catch(() => {})),
        ).catch(() => {});
      }
    } else if (task.worktree) {
      if (!hasUncommitted) {
        await rm(task.worktree, { recursive: true, force: true }).catch(() => {});
      }
    }
    try {
      await this.record(task, event);
    } finally {
      clearTimeout(this.flushTimers.get(task.taskId));
      this.flushTimers.delete(task.taskId);
      await this.flushSession(task).catch(() => {});
      if (task.jobId) this.jobTasks.delete(task.jobId);
      this.transcripts.delete(task.taskId);
      this.taskBrokers.delete(task.taskId);
      this.releaseActive(task.taskId, task);
    }
    return this.publicTask(task);
  }

  releaseActive(taskId, task) {
    this.active.delete(taskId);
    this.taskBrokers.delete(taskId);
    const waiters = this.taskWaiters.get(taskId);
    if (waiters) {
      this.taskWaiters.delete(taskId);
      for (const resolve of waiters) resolve(this.status({ taskId }));
    }
    if (this.active.size === 0 && this.idleWaiters.size > 0) {
      const idle = [...this.idleWaiters];
      this.idleWaiters.clear();
      for (const resolve of idle) resolve();
    }
  }

  async whenTask(taskId) {
    if (!this.active.has(taskId)) return this.status({ taskId });
    return new Promise((resolve) => {
      let waiters = this.taskWaiters.get(taskId);
      if (!waiters) {
        waiters = new Set();
        this.taskWaiters.set(taskId, waiters);
      }
      waiters.add(resolve);
    });
  }

  whenIdle() {
    if (this.active.size === 0) return Promise.resolve();
    return new Promise((resolve) => {
      this.idleWaiters.add(resolve);
    });
  }

  async status({ taskId } = {}) {
    if (!taskId) return this.shedState();
    const task = this.tasks.get(taskId) ?? (await this.load(taskId));
    return this.publicTask(task);
  }

  async load(taskId) {
    if (!/^shed-[0-9TZ]+-[a-f0-9]{6}$/.test(String(taskId))) throw new ShedTaskError("TASK_NOT_FOUND", "unknown task");
    try {
      return JSON.parse(await readFile(path.join(this.stateDir, "tasks", `${taskId}.json`), "utf8"));
    } catch {
      throw new ShedTaskError("TASK_NOT_FOUND", "unknown task");
    }
  }

  async cancel({ taskId } = {}) {
    const task = this.tasks.get(taskId);
    if (!task || !this.active.has(taskId)) {
      const known = task ?? (await this.load(taskId));
      return { ...this.publicTask(known), cancellationRequested: false };
    }
    task.status = "cancelling";
    await this.record(task, "cancel_requested");
    if (task.jobId) {
      const broker = this.taskBrokers.get(task.taskId) ?? (await this.getBroker(task.harness));
      await broker.cancel({ jobId: task.jobId, reason: "cancelled by remote caller" }).catch(() => {});
    }
    return { ...this.publicTask(task), cancellationRequested: true };
  }

  async steer(input = {}, caller) {
    assertCaller(caller);
    const { taskId, instruction, requestedBy } = this.validateSteer(input);
    const task = this.tasks.get(taskId) ?? (await this.load(taskId));
    if (!this.active.has(taskId) || task.status !== "running" || !task.jobId) {
      throw new ShedTaskError(
        "TASK_NOT_RUNNING",
        `Task ${taskId} is not running (current state: ${task.status}); only running tasks can be steered`,
        { taskId, status: task.status },
      );
    }
    const broker = this.taskBrokers.get(taskId) ?? (await this.getBroker(task.harness));
    if (typeof broker?.steer === "function") {
      try {
        await broker.steer({
          jobId: task.jobId,
          sessionId: task.sessionId,
          instruction,
          message: instruction,
          requestedBy,
        });
      } catch (error) {
        if (error?.code === "STEERING_UNSUPPORTED") {
          await this.steerViaRuntime(broker, task, instruction);
        } else {
          throw error;
        }
      }
    } else if (typeof broker?.steerSession === "function") {
      await broker.steerSession({
        jobId: task.jobId,
        sessionId: task.sessionId,
        instruction,
        message: instruction,
        requestedBy,
      });
    } else {
      await this.steerViaRuntime(broker, task, instruction);
    }
    const transcript = this.transcripts.get(taskId);
    if (transcript) {
      appendEvent(transcript, { type: "status", tag: "steered", text: instruction }, this.now().toISOString());
      this.scheduleFlush(task);
    }
    await this.record(task, "steered");
    return {
      ...this.publicTask(task),
      steered: true,
      requestedBy,
    };
  }

  async steerViaRuntime(broker, task, instruction) {
    const active = broker?.active?.get?.(task.jobId);
    const runtime =
      broker?.runtime ?? (typeof broker?.ensureRuntime === "function" ? broker.ensureRuntime() : null);
    if (active?.handle && typeof runtime?.startTurn === "function") {
      const turn = runtime.startTurn({
        handle: active.handle,
        text: instruction,
        mode: "steer",
        requestId: `${task.jobId}:steer:${Date.now()}`,
        timeoutMs: 120_000,
      });
      if (turn?.promptStarted) await turn.promptStarted;
      return;
    }
    throw new ShedTaskError(
      "STEER_UNAVAILABLE",
      `Unable to steer running task ${task.taskId}: active ACP session does not expose a steer handler`,
      { taskId: task.taskId },
    );
  }

  async result({ taskId } = {}, caller) {
    assertCaller(caller);
    if (typeof taskId !== "string" || !taskId.trim()) {
      throw new ShedTaskError("TASK_NOT_FOUND", "unknown task");
    }
    const trimmedId = taskId.trim();
    const inMem = this.tasks.get(trimmedId);
    if (this.active.has(trimmedId) || (inMem && !TERMINAL_TASK_STATUSES.has(inMem.status))) {
      const currentStatus = inMem?.status ?? "running";
      throw new ShedTaskError(
        "TASK_NOT_FINISHED",
        `Task ${trimmedId} is still ${currentStatus} (not finished); wait for completion before calling shed_task_result`,
        { taskId: trimmedId, status: currentStatus },
      );
    }
    const record = await this.load(trimmedId);
    if (!TERMINAL_TASK_STATUSES.has(record.status)) {
      throw new ShedTaskError(
        "TASK_NOT_FINISHED",
        `Task ${trimmedId} is still ${record.status} (not finished); wait for completion before calling shed_task_result`,
        { taskId: trimmedId, status: record.status },
      );
    }
    const sessionId = record.sessionId ?? record.session_id ?? null;
    const link = record.session_url ?? (sessionId ? sessionUrl(this.sessionBaseUrl, sessionId) ?? null : null);
    const summary = typeof record.summary === "string" ? clean(record.summary) : null;
    const harness = record.harness ?? this.harness;
    const model = record.model ?? (harness === "antigravity" ? this.antigravityModel : null);
    return {
      taskId: record.taskId,
      status: record.status,
      summary,
      prUrl: record.prUrl ?? null,
      headSha: record.headSha ?? null,
      harness,
      model,
      session_id: sessionId,
      session_url: link,
      sessionUrl: link,
      repo: record.repo ?? (record.owner && record.repo ? `${record.owner}/${record.repo}` : undefined),
      forge: record.forge,
      branch: record.branch,
      baseBranch: record.baseBranch,
      ...(record.headBranch ? { headBranch: record.headBranch } : {}),
      ...(record.commitsAhead !== undefined ? { commitsAhead: record.commitsAhead } : {}),
      ...(record.startSha ? { startSha: record.startSha } : {}),
      ...(record.error ? { error: record.error } : {}),
      requestedBy: record.requestedBy,
      createdAt: record.createdAt,
      updatedAt: record.updatedAt,
      ...(record.finishedAt ? { finishedAt: record.finishedAt } : {}),
    };
  }
}
