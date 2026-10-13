import { execFile as execFileCallback } from "node:child_process";
import { randomBytes } from "node:crypto";
import { appendFile, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { BridgeError, MAX_PROMPT_CHARS, redactSensitive } from "./broker.mjs";
import { appendEvent, buildView, createTranscript, isSessionId, loadSession, resolveSessionBaseUrl, saveSession, sessionUrl } from "./shed-sessions.mjs";
import { createRepoOwnerGuard, parseOptionalOwners, parseRepoOwners, REMOTE_ORIGIN_OWNERS_ENV, REMOTE_REPO_OWNERS_ENV } from "./repo-allowlist.mjs";

const execFile = promisify(execFileCallback);

// Remote-shed task runner. The remote endpoint exposes only these narrow
// operations (run / status / cancel); there is no general exec tool. Up to
// SAARIUS_ACP_REMOTE_MAX_CONCURRENT tasks (default 1) run at once, each in its
// own git worktree; over the cap a caller gets "busy" and queues or falls back.
// The bridge itself keeps no queue.
export const REMOTE_REPOS_ROOT_ENV = "SAARIUS_ACP_REMOTE_REPOS_ROOT";
export const MAX_CONCURRENT_ENV = "SAARIUS_ACP_REMOTE_MAX_CONCURRENT";
export const MAX_CONCURRENT_LIMIT = 16;
export const SHED_STATE_DIR_ENV = "SAARIUS_ACP_SHED_STATE_DIR";
export const BRANCH_PREFIX = "shed/";
// headBranch may only continue branches the shed (shed/<taskId>) or a Codex
// lane (codex/<name>) owns; never main/master/baseBranch or the repo default.
export const HEAD_BRANCH_PREFIXES = Object.freeze([BRANCH_PREFIX, "codex/"]);
const PROTECTED_BRANCHES = new Set(["main", "master", "head"]);
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

function assertNoSecrets(value, field) {
  if (SECRET_INPUT_PATTERN.test(value)) {
    throw new ShedTaskError("SECRET_REFUSED", `${field} looks like it contains a secret; remote tasks must never carry secrets`);
  }
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
  constructor({ broker, env = process.env, run = defaultRun, maxConcurrent, owners, originOwners, reposRoot, stateDir, guard, log, now = () => new Date(), sessionWaitMs = SESSION_WAIT_MS, sessionBaseUrl } = {}) {
    this.broker = broker;
    this.run = run;
    this.now = now;
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
    this.maxConcurrent = maxConcurrent !== undefined ? parseMaxConcurrent(maxConcurrent) : parseMaxConcurrent(env[MAX_CONCURRENT_ENV]);
    // taskId -> task for every task holding a slot (starting through finish).
    this.active = new Map();
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
    this.broker?.addEventObserver?.((jobId, event) => this.onAgentEvent(jobId, event));
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
    const transcript = this.transcripts.get(task.taskId);
    if (!transcript) return;
    appendEvent(transcript, event, this.now().toISOString());
    this.scheduleFlush(task);
  }

  bindJob(task, jobId) {
    this.jobTasks.set(jobId, task);
    const transcript = this.transcripts.get(task.taskId);
    for (const { event, at } of this.pendingEvents.get(jobId) ?? []) if (transcript) appendEvent(transcript, event, at);
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
    await saveSession(this.sessionsDir, task.sessionId, { sessionId: task.sessionId, task: this.publicTask(task), transcript });
  }

  // Read-only lookup for GET /s/<sessionId>[.json]. Returns null when unknown.
  async viewSession(sessionId) {
    if (!isSessionId(sessionId)) return null;
    for (const task of this.tasks.values()) {
      if (task.sessionId === sessionId && this.transcripts.has(task.taskId)) {
        return buildView({ sessionId, task: this.publicTask(task), transcript: this.transcripts.get(task.taskId) });
      }
    }
    const stored = await loadSession(this.sessionsDir, sessionId);
    if (!stored || stored.sessionId !== sessionId) return null;
    return buildView({ sessionId, task: stored.task, transcript: stored.transcript });
  }

  // Oldest running task id, kept for callers that read the single-task field.
  get activeTaskId() {
    return this.active.keys().next().value ?? null;
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

  async record(task, event) {
    task.updatedAt = this.now().toISOString();
    await writeFile(path.join(this.stateDir, "tasks", `${task.taskId}.json`), JSON.stringify(task, null, 2));
    // Audit line: who ran what, where. Never the task text or any secret.
    await this.log({
      at: task.updatedAt,
      event,
      taskId: task.taskId,
      caller: task.caller,
      requestedBy: task.requestedBy,
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
      repo: `${task.owner}/${task.repo}`,
      forge: task.forge,
      baseBranch: task.baseBranch,
      branch: task.branch,
      mode: task.headBranch ? "existing_branch" : "new_branch",
      requestedBy: task.requestedBy,
      createdAt: task.createdAt,
      updatedAt: task.updatedAt,
    };
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
    return out;
  }

  runningSummary(task) {
    return {
      taskId: task.taskId,
      status: task.status,
      repo: `${task.owner}/${task.repo}`,
      forge: task.forge,
      branch: task.branch,
      requestedBy: task.requestedBy,
      startedAt: task.createdAt,
      ...(task.sessionId ? { session_id: task.sessionId, session_url: sessionUrl(this.sessionBaseUrl, task.sessionId) } : {}),
    };
  }

  // status: "idle" (nothing running), "available" (running < cap), "busy" (at cap).
  shedState() {
    const running = this.active.size;
    const out = {
      status: running === 0 ? "idle" : running >= this.maxConcurrent ? "busy" : "available",
      running,
      maxConcurrent: this.maxConcurrent,
      tasks: [...this.active.values()].map((task) => this.runningSummary(task)),
    };
    if (running > 0) out.activeTaskId = this.activeTaskId;
    if (out.status === "busy") out.message = `The shed is at its concurrency cap (${running}/${this.maxConcurrent} tasks running); queue and retry later, or fall back.`;
    return out;
  }

  validate({ owner, repo, task, baseBranch, headBranch, forge, title, requested_by }) {
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
    if (typeof requested_by !== "string" || !LABEL_PATTERN.test(requested_by)) {
      throw new ShedTaskError("REQUESTED_BY_REQUIRED", "requested_by must name the bot that asked (letters, digits, _ . @ -)");
    }
    const safeTitle = typeof title === "string" && title.trim() ? title.trim().slice(0, TITLE_MAX) : undefined;
    assertNoSecrets(task, "task");
    if (safeTitle) assertNoSecrets(safeTitle, "title");
    return { owner: owner.toLowerCase(), repo, forge: safeForge, task, baseBranch: base, headBranch, title: safeTitle, requestedBy: requested_by };
  }

  async runTask(input, caller) {
    if (this.active.size >= this.maxConcurrent) return this.shedState();
    const request = this.validate(input ?? {});
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
    const task = {
      taskId,
      status: "starting",
      ...request,
      task: undefined,
      branch: request.headBranch ?? `${BRANCH_PREFIX}${taskId}`,
      caller: caller?.label ?? "unknown",
      createdAt: this.now().toISOString(),
      worktree: path.join(this.stateDir, "worktrees", taskId),
    };
    this.active.set(taskId, task);
    try {
      if (!(await stat(repoDir)).isDirectory()) throw new Error("not a directory");
    } catch {
      this.active.delete(taskId);
      return { status: "unavailable", reason: "REPO_NOT_ON_SHED", message: `${request.owner}/${request.repo} is not cloned under the shed repos root` };
    }
    this.tasks.set(taskId, task);
    this.transcripts.set(taskId, createTranscript({ prompt: request.task }));
    const started = this.start(task, request, repoDir);
    let timer;
    const stalled = new Promise((resolve) => {
      timer = setTimeout(() => resolve({ ...this.publicTask(task), sessionPending: true, message: "ACP session is still starting; read session_id / session_url from shed_task_status" }), this.sessionWaitMs);
    });
    try {
      return await Promise.race([started, stalled]);
    } finally {
      clearTimeout(timer);
    }
  }

  async start(task, request, repoDir) {
    const { taskId } = task;
    try {
      await this.record(task, "accepted");
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
      const submitted = await this.broker.delegate({
        workspace: task.worktree,
        prompt: `${SHED_INSTRUCTIONS}\n\nTask:\n${request.task}`,
        hostConversationId: taskId,
      });
      task.jobId = submitted.jobId;
      if (isSessionId(submitted.backendSessionId)) task.sessionId = submitted.backendSessionId;
      this.bindJob(task, submitted.jobId);
      if (isCancelled(task)) {
        // Cancel landed while delegate() was in flight: stop the job, keep cancelling.
        await this.broker.cancel({ jobId: task.jobId, reason: "cancelled by remote caller" }).catch(() => {});
        await this.record(task, "cancel_requested");
      } else {
        task.status = "running";
        await this.record(task, "running");
      }
    } catch (error) {
      if (isCancelled(task)) return this.cancelBeforeRun(task);
      const unavailable = /READINESS|OAUTH|RUNTIME|AUTH|SETUP/i.test(error?.code ?? "");
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
    let job;
    for (;;) {
      job = await this.broker.result({ jobId: task.jobId, waitMs: POLL_WAIT_MS });
      if (job.complete) break;
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
      await this.run("git", ["commit", "--quiet", "-m", title, "-m", `Remote-shed task ${task.taskId} requested by ${task.requestedBy}.`], { cwd });
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
    if (task.repoDir && task.worktree && task.startSha && !["pushed", "pr_opened"].includes(task.status)) {
      // Keep any unpushed agent commits reachable after the worktree goes away.
      try {
        const head = await this.run("git", ["rev-parse", "HEAD"], { cwd: task.worktree });
        if (head && head !== task.startSha) await this.run("git", ["update-ref", `refs/shed/keep/${task.taskId}`, head], { cwd: task.worktree });
      } catch {
        // best effort
      }
    }
    if (task.repoDir && task.worktree) {
      // Remove the worktree; the branch (and its PR) stay.
      await this.withRepoLock(task.repoDir, () =>
        this.run("git", ["worktree", "remove", "--force", task.worktree], { cwd: task.repoDir })
          .catch(() => rm(task.worktree, { recursive: true, force: true }))
          .then(() => this.run("git", ["worktree", "prune"], { cwd: task.repoDir }).catch(() => {})),
      ).catch(() => {});
    } else if (task.worktree) {
      await rm(task.worktree, { recursive: true, force: true }).catch(() => {});
    }
    this.active.delete(task.taskId);
    await this.record(task, event);
    clearTimeout(this.flushTimers.get(task.taskId));
    this.flushTimers.delete(task.taskId);
    await this.flushSession(task).catch(() => {});
    if (task.jobId) this.jobTasks.delete(task.jobId);
    this.transcripts.delete(task.taskId);
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
    if (task.jobId) await this.broker.cancel({ jobId: task.jobId, reason: "cancelled by remote caller" });
    return { ...this.publicTask(task), cancellationRequested: true };
  }
}
