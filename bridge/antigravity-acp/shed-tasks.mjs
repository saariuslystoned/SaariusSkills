import { execFile as execFileCallback } from "node:child_process";
import { randomBytes } from "node:crypto";
import { appendFile, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { BridgeError, MAX_PROMPT_CHARS, redactSensitive } from "./broker.mjs";
import { createRepoOwnerGuard, parseRepoOwners, REMOTE_REPO_OWNERS_ENV } from "./repo-allowlist.mjs";

const execFile = promisify(execFileCallback);

// Remote-shed task runner. The remote endpoint exposes only these narrow
// operations (run / status / cancel); there is no general exec tool. One task
// runs at a time on the shed; a second caller gets "busy" and can fall back.
export const REMOTE_REPOS_ROOT_ENV = "SAARIUS_ACP_REMOTE_REPOS_ROOT";
export const SHED_STATE_DIR_ENV = "SAARIUS_ACP_SHED_STATE_DIR";
export const BRANCH_PREFIX = "shed/";
const REPO_PATTERN = /^[A-Za-z0-9._-]{1,100}$/;
const BRANCH_PATTERN = /^(?!.*\.\.)(?!-)[A-Za-z0-9._/-]{1,100}$/;
const LABEL_PATTERN = /^[A-Za-z0-9_.@-]{1,64}$/;
const TITLE_MAX = 120;
const POLL_WAIT_MS = 30_000;
// Refuse token-shaped values in task input; callers must never pass secrets.
const SECRET_INPUT_PATTERN =
  /\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})\b|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----/i;

const SHED_INSTRUCTIONS = [
  "You are running on the owner's AI Shed through SaariusSkills remote-shed mode.",
  "Make the requested change in this repository working tree only.",
  "Do not commit, push, create branches, or open pull requests; the shed does that after you finish.",
  "Do not read, print, or write credentials, tokens, .env files, or private keys.",
  "Finish with a short plain-text summary of what you changed.",
].join("\n");

export class ShedTaskError extends BridgeError {}

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
  constructor({ broker, env = process.env, run = defaultRun, owners, reposRoot, stateDir, guard, log, now = () => new Date() } = {}) {
    this.broker = broker;
    this.run = run;
    this.now = now;
    this.owners = owners ? new Set([...owners].map((o) => o.toLowerCase())) : parseRepoOwners(env[REMOTE_REPO_OWNERS_ENV]);
    this.reposRoot = reposRoot ?? env[REMOTE_REPOS_ROOT_ENV]?.trim();
    if (!this.reposRoot || !path.isAbsolute(this.reposRoot)) {
      throw new ShedTaskError("REMOTE_REPOS_ROOT_REQUIRED", `${REMOTE_REPOS_ROOT_ENV} must be an absolute directory holding <owner>/<repo> clones`);
    }
    this.stateDir = stateDir ?? env[SHED_STATE_DIR_ENV]?.trim() ?? path.join(this.reposRoot, ".saarius-shed");
    this.guard = guard ?? createRepoOwnerGuard({ owners: this.owners });
    this.log = log ?? ((record) => appendFile(path.join(this.stateDir, "tasks.jsonl"), `${JSON.stringify(record)}\n`));
    this.tasks = new Map();
    this.activeTaskId = null;
  }

  async init() {
    await mkdir(path.join(this.stateDir, "worktrees"), { recursive: true });
    await mkdir(path.join(this.stateDir, "tasks"), { recursive: true });
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
      branch: task.branch,
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
      baseBranch: task.baseBranch,
      branch: task.branch,
      requestedBy: task.requestedBy,
      createdAt: task.createdAt,
      updatedAt: task.updatedAt,
    };
    if (task.prUrl) out.prUrl = task.prUrl;
    if (task.summary) out.summary = task.summary;
    if (task.error) out.error = task.error;
    return out;
  }

  shedState() {
    return this.activeTaskId
      ? { status: "busy", activeTaskId: this.activeTaskId, message: "The shed is running another task; try again later or fall back." }
      : { status: "idle" };
  }

  validate({ owner, repo, task, baseBranch, title, requested_by }) {
    if (typeof owner !== "string" || !this.owners.has(owner.toLowerCase())) {
      throw new ShedTaskError("REPO_OWNER_REFUSED", "owner is not on the shed's repo allowlist", { allowedOwners: [...this.owners] });
    }
    if (typeof repo !== "string" || !REPO_PATTERN.test(repo) || repo.startsWith(".")) {
      throw new ShedTaskError("REPO_INVALID", "repo must be a plain GitHub repository name");
    }
    if (typeof task !== "string" || !task.trim() || task.length > MAX_PROMPT_CHARS - SHED_INSTRUCTIONS.length - 200) {
      throw new ShedTaskError("TASK_INVALID", "task must be non-empty bounded text");
    }
    const base = baseBranch ?? "main";
    if (!BRANCH_PATTERN.test(base)) throw new ShedTaskError("BASE_BRANCH_INVALID", "baseBranch is not a safe branch name");
    if (typeof requested_by !== "string" || !LABEL_PATTERN.test(requested_by)) {
      throw new ShedTaskError("REQUESTED_BY_REQUIRED", "requested_by must name the bot that asked (letters, digits, _ . @ -)");
    }
    const safeTitle = typeof title === "string" && title.trim() ? title.trim().slice(0, TITLE_MAX) : undefined;
    assertNoSecrets(task, "task");
    if (safeTitle) assertNoSecrets(safeTitle, "title");
    return { owner: owner.toLowerCase(), repo, task, baseBranch: base, title: safeTitle, requestedBy: requested_by };
  }

  async runTask(input, caller) {
    if (this.activeTaskId) return this.shedState();
    const request = this.validate(input ?? {});
    const repoDir = path.join(this.reposRoot, request.owner, request.repo);
    try {
      if (!(await stat(repoDir)).isDirectory()) throw new Error("not a directory");
    } catch {
      return { status: "unavailable", reason: "REPO_NOT_ON_SHED", message: `${request.owner}/${request.repo} is not cloned under the shed repos root` };
    }
    const stamp = this.now().toISOString().replace(/[-:]/g, "").replace(/\..*$/, "");
    const taskId = `shed-${stamp}-${randomBytes(3).toString("hex")}`;
    const task = {
      taskId,
      status: "starting",
      ...request,
      task: undefined,
      branch: `${BRANCH_PREFIX}${taskId}`,
      caller: caller?.label ?? "unknown",
      createdAt: this.now().toISOString(),
      worktree: path.join(this.stateDir, "worktrees", taskId),
    };
    this.activeTaskId = taskId;
    this.tasks.set(taskId, task);
    try {
      await this.record(task, "accepted");
      await this.run("git", ["fetch", "--quiet", "origin", request.baseBranch], { cwd: repoDir });
      await this.run("git", ["worktree", "add", "--quiet", "-b", task.branch, task.worktree, `origin/${request.baseBranch}`], { cwd: repoDir });
      task.repoDir = repoDir;
      await this.guard(task.worktree);
      const submitted = await this.broker.delegate({
        workspace: task.worktree,
        prompt: `${SHED_INSTRUCTIONS}\n\nTask:\n${request.task}`,
        hostConversationId: taskId,
      });
      task.jobId = submitted.jobId;
      task.status = "running";
      await this.record(task, "running");
    } catch (error) {
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

  async watch(task) {
    let job;
    for (;;) {
      job = await this.broker.result({ jobId: task.jobId, waitMs: POLL_WAIT_MS });
      if (job.complete) break;
    }
    task.summary = clean(job.handoff);
    if (task.status === "cancelling" || job.status === "cancelled") {
      task.status = "cancelled";
      return this.finish(task, "cancelled");
    }
    if (job.status !== "completed") {
      task.status = "failed";
      task.error = { code: job.error?.code ?? "AGENT_FAILED", message: clean(job.error?.message ?? job.status, 300) };
      return this.finish(task, "failed");
    }
    const cwd = task.worktree;
    if (!(await this.run("git", ["status", "--porcelain"], { cwd }))) {
      task.status = "no_changes";
      return this.finish(task, "no_changes");
    }
    task.status = "opening_pr";
    await this.record(task, "opening_pr");
    const title = task.title ?? `Shed task ${task.taskId}`;
    await this.run("git", ["add", "-A"], { cwd });
    await this.run("git", ["commit", "--quiet", "-m", title, "-m", `Remote-shed task ${task.taskId} requested by ${task.requestedBy}.`], { cwd });
    // Plain push of a new branch; never --force.
    await this.run("git", ["push", "--quiet", "-u", "origin", task.branch], { cwd, timeoutMs: 300_000 });
    const body = [
      `Opened by SaariusSkills remote-shed task \`${task.taskId}\`.`,
      `Requested by: ${task.requestedBy} (Access caller: ${task.caller}).`,
      "",
      "Agent summary:",
      "",
      task.summary || "(none)",
    ].join("\n");
    task.prUrl = clean(await this.run("gh", ["pr", "create", "--draft", "--base", task.baseBranch, "--head", task.branch, "--title", title, "--body", body], { cwd, timeoutMs: 120_000 }), 300);
    task.status = "pr_opened";
    return this.finish(task, "pr_opened");
  }

  async finish(task, event) {
    if (task.repoDir && task.worktree) {
      // Remove the worktree; the branch (and its PR) stay.
      await this.run("git", ["worktree", "remove", "--force", task.worktree], { cwd: task.repoDir }).catch(() => rm(task.worktree, { recursive: true, force: true }));
    }
    if (this.activeTaskId === task.taskId) this.activeTaskId = null;
    await this.record(task, event);
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
    if (!task || taskId !== this.activeTaskId) {
      const known = task ?? (await this.load(taskId));
      return { ...this.publicTask(known), cancellationRequested: false };
    }
    task.status = "cancelling";
    await this.record(task, "cancel_requested");
    if (task.jobId) await this.broker.cancel({ jobId: task.jobId, reason: "cancelled by remote caller" });
    return { ...this.publicTask(task), cancellationRequested: true };
  }
}
