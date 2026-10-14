import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { generateKeyPairSync, sign } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { request } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { createAccessAuthenticator, parseRemoteCallers, resolveAccessConfig } from "../access-auth.mjs";
import { resolveHttpConfig, resolveTransport, startRemoteShedHost } from "../http-host.mjs";
import { createRepoOwnerGuard, githubOwnerFromRemote, originOwnerFromRemote, parseRepoOwners } from "../repo-allowlist.mjs";
import {
  DEFAULT_ANTIGRAVITY_ADVERTISED_MODELS,
  DEFAULT_ANTIGRAVITY_MODEL,
  DEFAULT_MUSE_ADVERTISED_MODELS,
  SHED_ANTIGRAVITY_MODEL_ENV,
  MUSE_COAUTHOR_ENV,
  SHED_COMMIT_AUTHOR,
  STEER_MAX,
  appendCoAuthorTrailer,
  museCoAuthorTrailer,
  parseMaxConcurrent,
  ShedTaskRunner,
} from "../shed-tasks.mjs";
import { createShedMcpServer, SHED_TOOL_NAMES } from "../shed-tools.mjs";

const OWNERS = "saariuslystoned,saari-co,dinkuskit";
const TEAM = "sm0ky.cloudflareaccess.com";
const AUD = "a".repeat(64);
const CLIENT_ID = "acprunner0001.access";
const ACCESS_ENV = {
  SAARIUS_ACP_ACCESS_TEAM_DOMAIN: TEAM,
  SAARIUS_ACP_ACCESS_AUD: AUD,
  SAARIUS_ACP_REMOTE_CALLERS: `${CLIENT_ID}=acp-runner`,
};

const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const JWKS = { keys: [{ ...publicKey.export({ format: "jwk" }), kid: "k1", alg: "RS256" }] };
const other = generateKeyPairSync("rsa", { modulusLength: 2048 });

function jwt(claims = {}, { key = privateKey, kid = "k1" } = {}) {
  const enc = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const head = enc({ alg: "RS256", kid, typ: "JWT" });
  const body = enc({ iss: `https://${TEAM}`, aud: [AUD], exp: now + 300, iat: now, common_name: CLIENT_ID, ...claims });
  return `${head}.${body}.${sign("RSA-SHA256", Buffer.from(`${head}.${body}`), key).toString("base64url")}`;
}

const authenticator = () => createAccessAuthenticator({ env: ACCESS_ENV, fetchJwks: async () => JWKS });

function repo(remote) {
  const dir = realpathSync(mkdtempSync(path.join(tmpdir(), "shed-repo-")));
  execFileSync("git", ["init", "-q"], { cwd: dir });
  if (remote) execFileSync("git", ["remote", "add", "origin", remote], { cwd: dir });
  return dir;
}

function fakeBroker({ delegateError, jobStatus = "completed", backendSessionId = "11111111-2222-3333-4444-555555555555", advertisedModels } = {}) {
  const calls = [];
  let release;
  const done = new Promise((resolve) => { release = resolve; });
  return {
    calls,
    ...(advertisedModels ? { advertisedModels } : {}),
    finish: () => release(),
    async delegate(input) {
      calls.push({ name: "delegate", input });
      if (delegateError) throw delegateError;
      return { jobId: "job-1", ...(backendSessionId ? { backendSessionId } : {}) };
    },
    async result(input) {
      calls.push({ name: "result", input });
      await done;
      return { complete: true, status: jobStatus, handoff: "Changed README. token ghp_abcdefghijklmnop" };
    },
    async cancel(input) {
      calls.push({ name: "cancel", input });
      release();
      return { status: "cancellation-requested" };
    },
    async steer(input) {
      calls.push({ name: "steer", input });
      return { steered: true };
    },
  };
}

const START = "a".repeat(40);
const HEAD = "b".repeat(40);
function shedFixture(brokerOptions, { changes = " M README.md", ahead, remoteHead = START, pushError, broker: customBroker, brokers: customBrokers, env: extraEnv = {}, symrefHead = "", runnerOptions = {} } = {}) {
  const reposRoot = realpathSync(mkdtempSync(path.join(tmpdir(), "shed-root-")));
  mkdirSync(path.join(reposRoot, "saari-co", "site"), { recursive: true });
  mkdirSync(path.join(reposRoot, "smoky", "motors"), { recursive: true });
  let committed = false;
  const commands = [];
  const logs = [];
  const broker = customBroker ?? (customBrokers ? undefined : fakeBroker(brokerOptions));
  const runner = new ShedTaskRunner({
    broker,
    brokers: customBrokers,
    env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS, SAARIUS_ACP_REMOTE_REPOS_ROOT: reposRoot, SAARIUS_ACP_REMOTE_ORIGIN_OWNERS: "smoky", SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "1", ...extraEnv },
    guard: async () => {},
    log: async (record) => logs.push(record),
    run: async (command, args) => {
      commands.push([command, ...args]);
      if (args[0] === "status") return changes;
      if (args[0] === "commit") committed = true;
      if (args[0] === "rev-parse") return args[1] === "--verify" ? START : HEAD;
      if (args[0] === "rev-list") return String(ahead ?? (committed ? 1 : 0));
      if (args[0] === "ls-remote" && args[1] === "--symref") return symrefHead ? `ref: refs/heads/${symrefHead}\tHEAD\n${START}\tHEAD` : "";
      if (args[0] === "ls-remote") return `${remoteHead}\trefs/heads/x`;
      if (args[0] === "push" && pushError) throw pushError;
      if (command === "origin") return "Created change https://origin.cursor.com/smoky/motors/pull/3";
      if (command === "gh") return "https://github.com/saari-co/site/pull/7";
      return "";
    },
    ...runnerOptions,
  });
  return { runner, broker, commands, logs, reposRoot };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 50));
const TEST_MUSE_COAUTHOR = "Muse <123456+muse-bot@users.noreply.github.com>";

test("muse co-author trailer requires MUSE_COAUTHOR, includes model id when known, and keeps the shed author identity", () => {
  assert.equal(MUSE_COAUTHOR_ENV, "MUSE_COAUTHOR");
  assert.equal(SHED_COMMIT_AUTHOR, "saariuslystoned <159389674+saariuslystoned@users.noreply.github.com>");
  assert.equal(museCoAuthorTrailer("claude-sonnet-4-6", {}), "");
  assert.equal(museCoAuthorTrailer("claude-sonnet-4-6", { MUSE_COAUTHOR: "   " }), "");
  assert.equal(
    museCoAuthorTrailer("claude-sonnet-4-6", { MUSE_COAUTHOR: TEST_MUSE_COAUTHOR }),
    "Co-authored-by: Muse (claude-sonnet-4-6) <123456+muse-bot@users.noreply.github.com>",
  );
  assert.equal(
    museCoAuthorTrailer(undefined, { MUSE_COAUTHOR: TEST_MUSE_COAUTHOR }),
    "Co-authored-by: Muse <123456+muse-bot@users.noreply.github.com>",
  );
  assert.equal(
    museCoAuthorTrailer("gpt-5.4", { MUSE_COAUTHOR: "123456+muse-bot@users.noreply.github.com" }),
    "Co-authored-by: Muse (gpt-5.4) <123456+muse-bot@users.noreply.github.com>",
  );
});

test("co-author trailer is omitted when MUSE_COAUTHOR is unset and appended once without duplication when set", () => {
  const base = "Fix typo\n\nRemote-shed task shed-x requested by acp-runner.";
  assert.equal(appendCoAuthorTrailer(base, { harness: "muse", model: "claude-sonnet-4-6", env: {} }), base);
  assert.equal(appendCoAuthorTrailer(base, { harness: "muse", model: "claude-sonnet-4-6", env: { MUSE_COAUTHOR: "" } }), base);

  const env = { MUSE_COAUTHOR: TEST_MUSE_COAUTHOR };
  const once = appendCoAuthorTrailer(base, { harness: "muse", model: "claude-sonnet-4-6", env });
  assert.match(once, /\n\nCo-authored-by: Muse \(claude-sonnet-4-6\) <123456\+muse-bot@users\.noreply\.github\.com>$/);
  assert.equal(appendCoAuthorTrailer(once, { harness: "muse", model: "claude-sonnet-4-6", env }), once);
  const agentAdded = "Fix typo\n\nCo-authored-by: Muse (claude-sonnet-4-6) <123456+muse-bot@users.noreply.github.com>";
  assert.equal(appendCoAuthorTrailer(agentAdded, { harness: "muse", model: "gpt-5.4", env }), agentAdded);
  assert.equal((once.match(/Co-authored-by: Muse/g) ?? []).length, 1);

  const noModel = appendCoAuthorTrailer(base, { harness: "muse", env });
  assert.match(noModel, /\n\nCo-authored-by: Muse <123456\+muse-bot@users\.noreply\.github\.com>$/);
  assert.equal(appendCoAuthorTrailer(noModel, { harness: "muse", env }), noModel);
});

test("other harnesses get no co-author trailer even when MUSE_COAUTHOR is set", () => {
  const msg = "Fix typo";
  const env = { MUSE_COAUTHOR: TEST_MUSE_COAUTHOR };
  assert.equal(appendCoAuthorTrailer(msg, { harness: "antigravity", model: "gemini-3.1-pro", env }), msg);
  assert.equal(appendCoAuthorTrailer(msg, { harness: "cursor", model: "x", env }), msg);
  assert.equal(appendCoAuthorTrailer(msg, { harness: undefined, model: "x", env }), msg);
});

const RUN = { owner: "saari-co", repo: "site", task: "Fix the README typo", requested_by: "acp-runner" };
const CALLER = { label: "acp-runner", clientId: CLIENT_ID };

test("transport selection defaults to stdio and refuses hop in http mode", () => {
  assert.equal(resolveTransport({ argv: [], env: {} }), "stdio");
  assert.equal(resolveTransport({ argv: ["--transport", "http"], env: {} }), "http");
  assert.throws(() => resolveTransport({ argv: ["--transport", "tcp"], env: {} }), { code: "TRANSPORT_INVALID" });
  assert.throws(
    () => resolveTransport({ argv: ["--transport", "http"], env: { SAARIUS_ACP_HOP_ARGV: '["ssh","cp-1"]' } }),
    { code: "HTTP_HOP_REFUSED" },
  );
});

test("http host binds loopback only", () => {
  assert.throws(() => resolveHttpConfig({ SAARIUS_ACP_HTTP_HOST: "0.0.0.0" }), { code: "HTTP_BIND_REFUSED" });
  const config = resolveHttpConfig({ SAARIUS_ACP_HTTP_PUBLIC_HOST: "Shed.sm0ky.dev" });
  assert.equal(config.host, "127.0.0.1");
  assert.deepEqual(config.publicHosts, ["shed.sm0ky.dev"]);
});

test("Access config requires team, AUD, and at least one caller", () => {
  assert.throws(() => resolveAccessConfig({}), { code: "ACCESS_TEAM_DOMAIN_REQUIRED" });
  assert.throws(() => resolveAccessConfig({ SAARIUS_ACP_ACCESS_TEAM_DOMAIN: TEAM }), { code: "ACCESS_AUD_REQUIRED" });
  assert.throws(() => parseRemoteCallers(""), { code: "REMOTE_CALLERS_REQUIRED" });
  assert.throws(() => parseRemoteCallers("nolabel"), { code: "REMOTE_CALLERS_INVALID" });
  assert.equal(resolveAccessConfig(ACCESS_ENV).callers.get(CLIENT_ID), "acp-runner");
});

test("Access JWT verification accepts the known service token and refuses everything else", async () => {
  const auth = authenticator();
  assert.deepEqual(await auth({ "cf-access-jwt-assertion": jwt() }), { label: "acp-runner", clientId: CLIENT_ID });
  const refused = async (headers, reason) => {
    await assert.rejects(auth(headers), (error) => error.code === "ACCESS_DENIED" && error.details.reason === reason);
  };
  await refused({}, "missing");
  await refused({ "cf-access-jwt-assertion": "x.y" }, "malformed");
  await refused({ "cf-access-jwt-assertion": jwt({}, { key: other.privateKey }) }, "signature");
  await refused({ "cf-access-jwt-assertion": jwt({}, { kid: "nope" }) }, "unknown_key");
  await refused({ "cf-access-jwt-assertion": jwt({ aud: ["b".repeat(64)] }) }, "audience");
  await refused({ "cf-access-jwt-assertion": jwt({ iss: "https://evil.cloudflareaccess.com" }) }, "issuer");
  await refused({ "cf-access-jwt-assertion": jwt({ exp: 1 }) }, "expired");
  await refused({ "cf-access-jwt-assertion": jwt({ common_name: "someone-else.access" }) }, "unknown_caller");
});

test("remote endpoint requires Access and exposes only the narrow task tools", async () => {
  assert.deepEqual(SHED_TOOL_NAMES, [
    "shed_task_run",
    "shed_task_status",
    "shed_task_cancel",
    "shed_task_steer",
    "shed_task_result",
  ]);
  const { runner } = shedFixture();
  await runner.init();
  const host = await startRemoteShedHost({
    env: { SAARIUS_ACP_HTTP_PORT: "0" },
    bridge: "antigravity-acp",
    authenticate: authenticator(),
    createServer: (caller) => createShedMcpServer(runner, caller),
    log: () => {},
  });
  try {
    const url = new URL(`http://127.0.0.1:${host.port}/mcp`);
    const init = { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "t", version: "0" } } };
    const headers = { "content-type": "application/json", accept: "application/json, text/event-stream" };
    assert.equal((await fetch(url, { method: "POST", headers, body: JSON.stringify(init) })).status, 401);
    assert.equal((await fetch(url, { method: "POST", headers: { ...headers, "cf-access-jwt-assertion": jwt({ common_name: "x".repeat(12) }) }, body: JSON.stringify(init) })).status, 401);
    const wrongHost = await new Promise((resolve, reject) => {
      const req = request({ host: "127.0.0.1", port: host.port, path: "/mcp", method: "POST", headers: { ...headers, host: "evil.example", "cf-access-jwt-assertion": jwt() } }, (res) => {
        res.resume();
        resolve(res.statusCode);
      });
      req.once("error", reject);
      req.end(JSON.stringify(init));
    });
    assert.equal(wrongHost, 403);

    const client = new Client({ name: "acp-runner", version: "0" });
    await client.connect(new StreamableHTTPClientTransport(url, { requestInit: { headers: { "cf-access-jwt-assertion": jwt() } } }));
    const { tools } = await client.listTools();
    assert.deepEqual(tools.map((tool) => tool.name).sort(), [...SHED_TOOL_NAMES].sort());
    assert.ok(!tools.some((tool) => /exec|shell|command|antigravity_acp_/i.test(tool.name)));
    const idle = await client.callTool({ name: "shed_task_status", arguments: {} });
    assert.equal(JSON.parse(idle.content[0].text).status, "idle");
    await client.close();
  } finally {
    await host.close();
  }
});

test("a task runs on a new branch and ends in a draft PR; audit log names caller and requested_by only", async () => {
  const { runner, broker, commands, logs } = shedFixture();
  await runner.init();
  const started = await runner.runTask(RUN, CALLER);
  assert.equal(started.status, "running");
  assert.match(started.branch, /^shed\/shed-/);
  const busy = await runner.runTask({ ...RUN, task: "another" }, CALLER);
  assert.equal(busy.status, "busy");
  assert.equal(busy.activeTaskId, started.taskId);
  broker.finish();
  await settle();
  const final = await runner.status({ taskId: started.taskId });
  assert.equal(final.status, "pr_opened");
  assert.equal(final.prUrl, "https://github.com/saari-co/site/pull/7");
  assert.doesNotMatch(final.summary, /ghp_abcdefghijklmnop/);
  const delegate = broker.calls.find((call) => call.name === "delegate").input;
  assert.equal(delegate.hostConversationId, started.taskId);
  assert.match(delegate.prompt, /never push, force-push/);
  const flat = commands.map((c) => c.join(" "));
  assert.ok(flat.some((c) => c.startsWith(`git worktree add --quiet -b ${started.branch}`)));
  assert.ok(flat.some((c) => c === `git push --quiet -u origin HEAD:refs/heads/${started.branch}`));
  assert.ok(flat.some((c) => c.startsWith("gh pr create --draft --base main")));
  assert.ok(!flat.some((c) => /--force(?!\s+\S*worktrees)|merge/.test(c.replace(/git worktree remove --force \S+/, ""))));
  assert.ok(logs.every((line) => line.caller === "acp-runner" && line.requestedBy === "acp-runner"));
  assert.ok(!JSON.stringify(logs).includes("README typo"));
  // The task is pr_opened before async cleanup clears the active slot; poll
  // briefly instead of assuming cleanup finished within settle().
  let shedStatus = (await runner.status({})).status;
  for (let attempt = 0; attempt < 100 && shedStatus !== "idle"; attempt += 1) {
    await settle();
    shedStatus = (await runner.status({})).status;
  }
  assert.equal(shedStatus, "idle");
});

test("terminal tool updates preserve the started command summary in latestEvent", async () => {
  const { runner } = shedFixture();
  await runner.init();
  const started = {
    type: "job_event",
    event: "tool_call_started",
    timestamp: "2026-10-14T00:00:00.000Z",
    details: { toolCallId: "call-1", tool: "Bash", summary: "echo hi" },
  };
  const completedRaw = {
    type: "tool_call",
    toolCallId: "call-1",
    title: "Bash",
    status: "completed",
    rawOutput: { exitCode: 0, output: "ok" },
  };
  const task = { taskId: "task-summary-1" };
  runner.jobTasks.set("job-summary-1", task);
  runner.onAgentEvent("job-summary-1", started);
  runner.onAgentEvent("job-summary-1", completedRaw);
  assert.equal(task.latestEvent.event, "tool_call_finished");
  assert.equal(task.latestEvent.summary, "echo hi", "completion without rawInput must keep the started summary");

  const pendingTask = { taskId: "task-summary-2" };
  runner.pendingEvents.set("job-summary-2", [
    { event: started, at: "2026-10-14T00:00:00.000Z" },
    { event: completedRaw, at: "2026-10-14T00:00:01.000Z" },
  ]);
  runner.bindJob(pendingTask, "job-summary-2");
  assert.equal(pendingTask.latestEvent.event, "tool_call_finished");
  assert.equal(pendingTask.latestEvent.summary, "echo hi");
});

test("input validation: allowlist, requested_by, secrets, and unavailable repos", async () => {
  const { runner } = shedFixture();
  await runner.init();
  await assert.rejects(runner.runTask({ ...RUN, owner: "someone-else" }, CALLER), { code: "REPO_OWNER_REFUSED" });
  await assert.rejects(runner.runTask({ ...RUN, repo: "../x" }, CALLER), { code: "REPO_INVALID" });
  await assert.rejects(runner.runTask({ ...RUN, requested_by: undefined }, CALLER), { code: "REQUESTED_BY_REQUIRED" });
  await assert.rejects(runner.runTask({ ...RUN, task: "use ghp_abcdefghijklmnopqrst to push" }, CALLER), { code: "SECRET_REFUSED" });
  await assert.rejects(runner.runTask({ ...RUN, baseBranch: "--upload-pack=x" }, CALLER), { code: "BASE_BRANCH_INVALID" });
  const missing = await runner.runTask({ ...RUN, owner: "dinkuskit", repo: "not-cloned" }, CALLER);
  assert.equal(missing.status, "unavailable");
  assert.equal(missing.reason, "REPO_NOT_ON_SHED");
  assert.equal((await runner.status({})).status, "idle");
});

test("Antigravity not ready returns unavailable and frees the shed", async () => {
  const error = Object.assign(new Error("readiness is red"), { code: "READINESS_RED" });
  const { runner } = shedFixture({ delegateError: error });
  await runner.init();
  const out = await runner.runTask(RUN, CALLER);
  assert.equal(out.status, "unavailable");
  assert.equal((await runner.status({})).status, "idle");
});

test("cancel stops the task without a PR", async () => {
  const { runner, commands } = shedFixture({ jobStatus: "cancelled" });
  await runner.init();
  const started = await runner.runTask(RUN, CALLER);
  const cancelled = await runner.cancel({ taskId: started.taskId });
  assert.equal(cancelled.cancellationRequested, true);
  await settle();
  assert.equal((await runner.status({ taskId: started.taskId })).status, "cancelled");
  assert.ok(!commands.some((c) => c[0] === "gh"));
});

test("repo owner guard checks every remote and the repo root", async () => {
  assert.deepEqual([...parseRepoOwners(OWNERS)], ["saariuslystoned", "saari-co", "dinkuskit"]);
  assert.equal(githubOwnerFromRemote("git@github.com:Saari-Co/site.git"), "saari-co");
  assert.equal(githubOwnerFromRemote("https://github.com.evil.test/saari-co/x.git"), null);
  const guard = createRepoOwnerGuard({ env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS } });
  const allowed = repo("git@github.com:saari-co/site.git");
  await guard(allowed);
  await assert.rejects(guard(repo("https://github.com/someone-else/site.git")), { code: "REMOTE_REPO_OWNER_REFUSED" });
  await assert.rejects(guard(repo()), { code: "REMOTE_REPO_OWNER_REFUSED" });
  mkdirSync(path.join(allowed, "sub"));
  await assert.rejects(guard(path.join(allowed, "sub")), { code: "REMOTE_WORKSPACE_NOT_REPO_ROOT" });
});

const noForce = (flat) => !flat.some((c) => /--force|\+refs\/heads\/\S+:refs\/heads|push .*\+/.test(c.replace(/git worktree remove --force \S+/, "").replace(/git fetch --quiet origin \+refs\/heads\/\S+:refs\/remotes\/\S+/, "")));

test("agent-made commits on a clean worktree count as changes and are pushed (git am / merge)", async () => {
  const { runner, broker, commands } = shedFixture({}, { changes: "", ahead: 2 });
  await runner.init();
  const started = await runner.runTask(RUN, CALLER);
  broker.finish();
  await settle();
  const final = await runner.status({ taskId: started.taskId });
  assert.equal(final.status, "pr_opened");
  assert.equal(final.commitsAhead, 2);
  assert.equal(final.headSha, HEAD);
  const flat = commands.map((c) => c.join(" "));
  assert.ok(!flat.some((c) => c.startsWith("git commit")));
  assert.ok(flat.some((c) => c === `git rev-list --count ${START}..HEAD`));
  assert.ok(flat.some((c) => c === `git push --quiet -u origin HEAD:refs/heads/${started.branch}`));
  assert.ok(noForce(flat));
});

test("clean worktree with zero commits ahead is no_changes and pushes nothing", async () => {
  const { runner, broker, commands } = shedFixture({}, { changes: "", ahead: 0 });
  await runner.init();
  const started = await runner.runTask(RUN, CALLER);
  broker.finish();
  await settle();
  assert.equal((await runner.status({ taskId: started.taskId })).status, "no_changes");
  assert.ok(!commands.some((c) => c[1] === "push"));
});

test("headBranch continues an existing PR branch with a plain fast-forward push", async () => {
  const { runner, broker, commands } = shedFixture();
  await runner.init();
  const started = await runner.runTask({ ...RUN, headBranch: "shed/shed-20261011T211640-ee8eab" }, CALLER);
  assert.equal(started.branch, "shed/shed-20261011T211640-ee8eab");
  assert.equal(started.mode, "existing_branch");
  broker.finish();
  await settle();
  const final = await runner.status({ taskId: started.taskId });
  assert.equal(final.status, "pushed");
  assert.equal(final.prUrl, "https://github.com/saari-co/site/pull/7");
  const flat = commands.map((c) => c.join(" "));
  assert.ok(flat.some((c) => c.startsWith(`git worktree add --quiet --detach`) && c.endsWith(START)));
  assert.ok(flat.some((c) => c === "git push --quiet origin HEAD:refs/heads/shed/shed-20261011T211640-ee8eab"));
  assert.ok(!flat.some((c) => c.startsWith("gh pr create")));
  assert.ok(noForce(flat));
});

test("headBranch fails clearly and never pushes when the remote moved", async () => {
  const { runner, broker, commands } = shedFixture({}, { remoteHead: "c".repeat(40) });
  await runner.init();
  const started = await runner.runTask({ ...RUN, headBranch: "codex/x" }, CALLER);
  broker.finish();
  await settle();
  const final = await runner.status({ taskId: started.taskId });
  assert.equal(final.status, "failed");
  assert.equal(final.error.code, "REMOTE_BRANCH_MOVED");
  assert.ok(!commands.some((c) => c[1] === "push"));
  assert.ok(commands.some((c) => c[1] === "update-ref" && c[2] === `refs/shed/keep/${started.taskId}`));
});

test("headBranch maps a rejected non-fast-forward push to REMOTE_BRANCH_MOVED", async () => {
  const pushError = Object.assign(new Error("push failed"), { stderr: "! [rejected] HEAD -> x (non-fast-forward)" });
  const { runner, broker } = shedFixture({}, { pushError });
  await runner.init();
  const started = await runner.runTask({ ...RUN, headBranch: "codex/x" }, CALLER);
  broker.finish();
  await settle();
  assert.equal((await runner.status({ taskId: started.taskId })).error.code, "REMOTE_BRANCH_MOVED");
});

test("headBranch validation", async () => {
  const { runner } = shedFixture();
  await runner.init();
  await assert.rejects(runner.runTask({ ...RUN, headBranch: "--force" }, CALLER), { code: "HEAD_BRANCH_INVALID" });
  await assert.rejects(runner.runTask({ ...RUN, headBranch: "main" }, CALLER), { code: "HEAD_BRANCH_INVALID" });
  // Only shed-owned prefixes; never main/master/baseBranch, even if "safe".
  for (const headBranch of ["master", "MAIN", "develop", "feature/x", "release/1.0", "shed/", "codex/", "mainline"]) {
    await assert.rejects(runner.runTask({ ...RUN, headBranch }, CALLER), { code: "HEAD_BRANCH_INVALID" }, headBranch);
  }
  await assert.rejects(runner.runTask({ ...RUN, baseBranch: "codex/base", headBranch: "codex/base" }, CALLER), { code: "HEAD_BRANCH_INVALID" });
  assert.equal((await runner.status({})).status, "idle");
});

test("headBranch that is the repo default branch is refused before any worktree or push", async () => {
  const { runner, commands } = shedFixture({}, { symrefHead: "codex/trunk" });
  await runner.init();
  const out = await runner.runTask({ ...RUN, headBranch: "codex/trunk" }, CALLER);
  assert.equal(out.status, "failed");
  assert.equal(out.error.code, "HEAD_BRANCH_INVALID");
  assert.ok(!commands.some((c) => c[1] === "worktree" && c[2] === "add"));
  assert.ok(!commands.some((c) => c[1] === "push"));
  assert.equal((await runner.status({})).status, "idle");
});

test("a task cancelled while waiting for the repo lock never delegates, pushes, or opens a PR", async () => {
  const { runner, broker, commands, reposRoot } = shedFixture({}, { runnerOptions: { sessionWaitMs: 20 } });
  await runner.init();
  let releaseLock;
  const held = runner.withRepoLock(path.join(reposRoot, "saari-co", "site"), () => new Promise((resolve) => { releaseLock = resolve; }));
  const started = await runner.runTask(RUN, CALLER);
  assert.equal(started.sessionPending, true);
  const cancelled = await runner.cancel({ taskId: started.taskId });
  assert.equal(cancelled.cancellationRequested, true);
  releaseLock();
  await held;
  await settle();
  const final = await runner.status({ taskId: started.taskId });
  assert.equal(final.status, "cancelled");
  assert.ok(!broker.calls.some((c) => c.name === "delegate"));
  assert.ok(!commands.some((c) => c[1] === "push" || c[1] === "fetch" || c[0] === "gh"));
  assert.equal((await runner.status({})).status, "idle");
});

test("a cancel that lands while delegate() is in flight cancels the job and is never set back to running", async () => {
  let releaseDelegate;
  const base = fakeBroker();
  const broker = {
    ...base,
    calls: base.calls,
    async delegate(input) {
      base.calls.push({ name: "delegate", input });
      await new Promise((resolve) => { releaseDelegate = resolve; });
      return { jobId: "job-1" };
    },
  };
  const { runner, commands } = shedFixture({}, { broker, runnerOptions: { sessionWaitMs: 20 } });
  await runner.init();
  const started = await runner.runTask(RUN, CALLER);
  await settle();
  await runner.cancel({ taskId: started.taskId });
  releaseDelegate();
  await settle();
  const final = await runner.status({ taskId: started.taskId });
  assert.equal(final.status, "cancelled");
  assert.ok(broker.calls.some((c) => c.name === "cancel"));
  assert.ok(!commands.some((c) => c[1] === "push" || c[0] === "gh"));
});

test("Origin forge: separate owner allowlist and origin pr create", async () => {
  const { runner, broker, commands } = shedFixture();
  await runner.init();
  await assert.rejects(runner.runTask({ ...RUN, owner: "smoky", repo: "motors" }, CALLER), { code: "REPO_OWNER_REFUSED" });
  await assert.rejects(runner.runTask({ ...RUN, forge: "origin" }, CALLER), { code: "REPO_OWNER_REFUSED" });
  await assert.rejects(runner.runTask({ ...RUN, forge: "gitlab" }, CALLER), { code: "FORGE_INVALID" });
  const started = await runner.runTask({ ...RUN, owner: "smoky", repo: "motors", forge: "origin" }, CALLER);
  broker.finish();
  await settle();
  const final = await runner.status({ taskId: started.taskId });
  assert.equal(final.status, "pr_opened");
  assert.equal(final.prUrl, "https://origin.cursor.com/smoky/motors/pull/3");
  assert.ok(commands.some((c) => c[0] === "origin" && c.includes("--draft") && c.includes("smoky/motors")));
  assert.equal(originOwnerFromRemote("https://origin.cursor.com/smoky/smokymotors.git"), "smoky");
  assert.equal(originOwnerFromRemote("https://origin.cursor.com.evil.test/smoky/x.git"), null);
  const guard = createRepoOwnerGuard({ env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS, SAARIUS_ACP_REMOTE_ORIGIN_OWNERS: "smoky" } });
  await guard(repo("https://origin.cursor.com/smoky/smokymotors.git"));
  await assert.rejects(guard(repo("https://origin.cursor.com/other/x.git")), { code: "REMOTE_REPO_OWNER_REFUSED" });
  const githubOnly = createRepoOwnerGuard({ env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS } });
  await assert.rejects(githubOnly(repo("https://origin.cursor.com/smoky/smokymotors.git")), { code: "REMOTE_REPO_OWNER_REFUSED" });
});

// Broker with one independently released job per delegate call.
function multiBroker({ onDelegate, advertisedModels } = {}) {
  const jobs = new Map();
  const steers = [];
  let n = 0;
  return {
    jobs,
    steers,
    ...(advertisedModels ? { advertisedModels } : {}),
    async delegate(input) {
      const jobId = `job-${++n}`;
      let release;
      const done = new Promise((resolve) => { release = resolve; });
      jobs.set(jobId, { input, release, done });
      if (onDelegate) await onDelegate(input);
      return { jobId };
    },
    async result({ jobId }) {
      const status = await jobs.get(jobId).done;
      return { complete: true, status: status ?? "completed", handoff: "done" };
    },
    async cancel({ jobId }) {
      jobs.get(jobId).release("cancelled");
      return { status: "cancellation-requested" };
    },
    async steer(input) {
      steers.push(input);
      return { steered: true };
    },
    finish(jobId, status) { jobs.get(jobId).release(status); },
  };
}

test("max concurrent parses from env with default 1 and refuses junk", () => {
  assert.equal(parseMaxConcurrent(undefined), 1);
  assert.equal(parseMaxConcurrent(""), 1);
  assert.equal(parseMaxConcurrent("5"), 5);
  for (const bad of ["0", "-1", "1.5", "abc", "17"]) assert.throws(() => parseMaxConcurrent(bad), { code: "MAX_CONCURRENT_INVALID" });
});

test("up to the cap tasks run at once; over the cap returns busy with the running list; status lists all; cancel by id", async () => {
  const broker = multiBroker();
  const { runner } = shedFixture(undefined, { broker, env: { SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "3" } });
  await runner.init();
  assert.deepEqual(await runner.status({}), { status: "idle", running: 0, maxConcurrent: 3, tasks: [] });
  // Fire all at once: the slot check must be race-free.
  const results = await Promise.all([1, 2, 3, 4].map((i) => runner.runTask({ ...RUN, task: `t${i}`, requested_by: `bot${i}` }, CALLER)));
  const started = results.filter((r) => r.status === "running");
  const busy = results.filter((r) => r.status === "busy");
  assert.equal(started.length, 3);
  assert.equal(busy.length, 1);
  assert.equal(busy[0].running, 3);
  assert.equal(busy[0].maxConcurrent, 3);
  assert.match(busy[0].message, /3\/3/);
  assert.equal(new Set(started.map((t) => t.taskId)).size, 3);
  const workspaces = [...broker.jobs.values()].map((j) => j.input.workspace);
  assert.equal(new Set(workspaces).size, 3);
  const state = await runner.status({});
  assert.equal(state.status, "busy");
  assert.deepEqual(state.tasks.map((t) => t.taskId).sort(), started.map((t) => t.taskId).sort());
  for (const t of state.tasks) {
    assert.equal(t.repo, "saari-co/site");
    assert.match(t.branch, /^shed\/shed-/);
    assert.match(t.requestedBy, /^bot\d$/);
    assert.ok(t.startedAt);
  }
  const cancelled = await runner.cancel({ taskId: started[1].taskId });
  assert.equal(cancelled.cancellationRequested, true);
  await runner.whenTask(started[1].taskId);
  assert.equal((await runner.status({ taskId: started[1].taskId })).status, "cancelled");
  const after = await runner.status({});
  assert.equal(after.status, "available");
  assert.equal(after.running, 2);
  const again = await runner.runTask({ ...RUN, task: "t5" }, CALLER);
  assert.equal(again.status, "running");
  for (const id of broker.jobs.keys()) broker.finish(id);
  await runner.whenIdle();
  assert.equal((await runner.status({})).status, "idle");
});

test("a second task on the same repo+headBranch is refused while the first runs", async () => {
  const broker = multiBroker();
  const { runner } = shedFixture(undefined, { broker, env: { SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "5" } });
  await runner.init();
  const first = await runner.runTask({ ...RUN, headBranch: "codex/x" }, CALLER);
  assert.equal(first.status, "running");
  await assert.rejects(
    runner.runTask({ ...RUN, task: "other", headBranch: "codex/x" }, CALLER),
    (error) => error.code === "BRANCH_BUSY" && error.details.taskId === first.taskId,
  );
  const otherBranch = await runner.runTask({ ...RUN, headBranch: "codex/y" }, CALLER);
  assert.equal(otherBranch.status, "running");
  const otherRepo = await runner.runTask({ ...RUN, owner: "smoky", repo: "motors", forge: "origin", headBranch: "codex/x" }, CALLER);
  assert.equal(otherRepo.status, "running");
  for (const id of broker.jobs.keys()) broker.finish(id, "cancelled");
  await runner.whenIdle();
  const freed = await runner.runTask({ ...RUN, task: "later", headBranch: "codex/x" }, CALLER);
  assert.equal(freed.status, "running");
  for (const id of broker.jobs.keys()) broker.finish(id, "cancelled");
  await runner.whenIdle();
});

test("real git: concurrent tasks get isolated worktrees, push their own branches, and clean up", async () => {
  const sh = (args, cwd) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
  const base = realpathSync(mkdtempSync(path.join(tmpdir(), "shed-git-")));
  const origin = path.join(base, "origin.git");
  sh(["init", "-q", "--bare", "-b", "main", origin], base);
  const seed = path.join(base, "seed");
  sh(["clone", "-q", origin, seed], base);
  sh(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], seed);
  sh(["push", "-q", "origin", "HEAD:refs/heads/main"], seed);
  const reposRoot = path.join(base, "repos");
  const clone = path.join(reposRoot, "saari-co", "site");
  mkdirSync(path.dirname(clone), { recursive: true });
  sh(["clone", "-q", origin, clone], base);
  sh(["config", "user.email", "shed@test"], clone);
  sh(["config", "user.name", "shed"], clone);
  const broker = multiBroker({
    onDelegate: async ({ workspace, hostConversationId }) => writeFileSync(path.join(workspace, `${hostConversationId}.txt`), "x\n"),
  });
  const prs = [];
  const runner = new ShedTaskRunner({
    broker,
    env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS, SAARIUS_ACP_REMOTE_REPOS_ROOT: reposRoot, SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "5" },
    guard: async () => {},
    log: async () => {},
    run: async (command, args, { cwd } = {}) => {
      if (command !== "git") { prs.push(args); return `https://example.invalid/pull/${prs.length}`; }
      return sh(args, cwd);
    },
  });
  await runner.init();
  const started = await Promise.all([1, 2, 3, 4, 5].map((i) => runner.runTask({ ...RUN, task: `t${i}` }, CALLER)));
  assert.ok(started.every((t) => t.status === "running"), JSON.stringify(started));
  assert.equal(sh(["worktree", "list", "--porcelain"], clone).split("\n").filter((l) => l.startsWith("worktree ")).length, 6);
  for (const id of broker.jobs.keys()) broker.finish(id);
  await runner.whenIdle();
  for (const t of started) {
    const final = await runner.status({ taskId: t.taskId });
    assert.equal(final.status, "pr_opened", JSON.stringify(final));
    const files = sh(["ls-tree", "--name-only", `refs/heads/${t.branch}`], origin).split("\n");
    assert.deepEqual(files, [`${t.taskId}.txt`]);
  }
  assert.equal(prs.length, 5);
  assert.equal(sh(["worktree", "list", "--porcelain"], clone).split("\n").filter((l) => l.startsWith("worktree ")).length, 1);
  assert.deepEqual(readdirSync(path.join(reposRoot, ".saarius-shed", "worktrees")), []);
  assert.ok(!existsSync(path.join(reposRoot, ".saarius-shed", "worktrees", started[0].taskId)));
});


test("whenIdle and whenTask provide explicit completion signals", async () => {
  const broker = multiBroker();
  const { runner } = shedFixture(undefined, { broker, env: { SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "2" } });
  await runner.init();
  await runner.whenIdle();
  const t1 = await runner.runTask({ ...RUN, task: "one" }, CALLER);
  const t2 = await runner.runTask({ ...RUN, task: "two" }, CALLER);
  assert.equal(t1.status, "running");
  assert.equal(t2.status, "running");

  let t1Done = false;
  const t1Promise = runner.whenTask(t1.taskId).then((res) => {
    t1Done = true;
    return res;
  });

  const firstJobId = broker.jobs.keys().next().value;
  broker.finish(firstJobId);
  const t1Result = await t1Promise;
  assert.equal(t1Done, true);
  assert.equal(t1Result.taskId, t1.taskId);
  assert.equal(t1Result.status, "pr_opened");
  assert.equal((await runner.status({})).status, "available");

  const t1Immediate = await runner.whenTask(t1.taskId);
  assert.equal(t1Immediate.status, "pr_opened");

  for (const id of broker.jobs.keys()) broker.finish(id);
  await runner.whenIdle();
  assert.deepEqual(await runner.status({}), { status: "idle", running: 0, maxConcurrent: 2, tasks: [] });
});

test("harness validation: refuses unknown harness with HARNESS_INVALID and defaults to antigravity", async () => {
  const broker = multiBroker();
  const { runner } = shedFixture(undefined, { broker });
  await runner.init();

  for (const bad of ["unknown", "codex", "claude", "", "   "]) {
    await assert.rejects(
      runner.runTask({ ...RUN, harness: bad }, CALLER),
      (err) => err.code === "HARNESS_INVALID" && /antigravity, muse/.test(err.message),
    );
  }

  // Missing or undefined defaults to antigravity
  const defaultTask = await runner.runTask(RUN, CALLER);
  assert.equal(defaultTask.status, "running");
  assert.equal(defaultTask.harness, "antigravity");
  broker.finish(broker.jobs.keys().next().value);
  await runner.whenIdle();
});

test("routing per harness: antigravity and muse route to their respective brokers and store harness", async () => {
  const antiBroker = multiBroker();
  antiBroker.harness = "antigravity";
  const museBroker = multiBroker();
  museBroker.harness = "muse";

  const { runner } = shedFixture(undefined, {
    brokers: { antigravity: antiBroker, muse: museBroker },
    env: { SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "5" },
  });
  await runner.init();

  const antiTask = await runner.runTask({ ...RUN, harness: "antigravity", task: "anti task" }, CALLER);
  assert.equal(antiTask.status, "running");
  assert.equal(antiTask.harness, "antigravity");
  assert.equal(antiBroker.jobs.size, 1);
  assert.equal(museBroker.jobs.size, 0);

  const museTask = await runner.runTask({ ...RUN, harness: "muse", task: "muse task" }, CALLER);
  assert.equal(museTask.status, "running");
  assert.equal(museTask.harness, "muse");
  assert.equal(antiBroker.jobs.size, 1);
  assert.equal(museBroker.jobs.size, 1);

  const antiStatus = await runner.status({ taskId: antiTask.taskId });
  assert.equal(antiStatus.harness, "antigravity");

  const museStatus = await runner.status({ taskId: museTask.taskId });
  assert.equal(museStatus.harness, "muse");

  // Clean up
  for (const id of antiBroker.jobs.keys()) antiBroker.finish(id);
  for (const id of museBroker.jobs.keys()) museBroker.finish(id);
  await runner.whenIdle();
});

test("shed commit carries the Muse trailer only when MUSE_COAUTHOR is set for muse tasks; antigravity commits stay unchanged", async () => {
  // 1. When MUSE_COAUTHOR is unset, Muse tasks get no co-author trailer
  const unsetMuseBroker = multiBroker();
  unsetMuseBroker.harness = "muse";
  const { runner: unsetRunner, commands: unsetCommands } = shedFixture(undefined, {
    brokers: { muse: unsetMuseBroker },
    env: { MUSE_COAUTHOR: "" },
  });
  await unsetRunner.init();
  const unsetTask = await unsetRunner.runTask({ ...RUN, harness: "muse", model: "claude-sonnet-4-6", task: "muse unset task" }, CALLER);
  unsetMuseBroker.finish(unsetMuseBroker.jobs.keys().next().value);
  await unsetRunner.whenIdle();
  assert.equal((await unsetRunner.status({ taskId: unsetTask.taskId })).status, "pr_opened");
  const unsetCommit = unsetCommands.find((c) => c[0] === "git" && c[1] === "commit");
  assert.ok(unsetCommit, "shed should create a commit for the muse task");
  assert.ok(!unsetCommit.join(" ").includes("Co-authored-by:"), unsetCommit.join(" "));
  assert.ok(!([...unsetMuseBroker.jobs.values()][0].input.prompt).includes("Co-authored-by:"));

  // 2. When MUSE_COAUTHOR is set, Muse tasks include the trailer and Antigravity tasks stay unchanged
  const antiBroker = multiBroker();
  antiBroker.harness = "antigravity";
  const museBroker = multiBroker();
  museBroker.harness = "muse";
  const { runner, commands } = shedFixture(undefined, {
    brokers: { antigravity: antiBroker, muse: museBroker },
    env: { MUSE_COAUTHOR: TEST_MUSE_COAUTHOR },
  });
  await runner.init();

  const museTask = await runner.runTask({ ...RUN, harness: "muse", model: "claude-sonnet-4-6", task: "muse commit task" }, CALLER);
  museBroker.finish(museBroker.jobs.keys().next().value);
  await runner.whenIdle();
  assert.equal((await runner.status({ taskId: museTask.taskId })).status, "pr_opened");
  const museCommit = commands.find((c) => c[0] === "git" && c[1] === "commit");
  assert.ok(museCommit, "shed should create a commit for the muse task");
  const museFlat = museCommit.join(" ");
  assert.ok(museFlat.includes("Co-authored-by: Muse (claude-sonnet-4-6) <123456+muse-bot@users.noreply.github.com>"), museFlat);
  assert.equal((museFlat.match(/Co-authored-by: Muse/g) ?? []).length, 1);
  assert.ok(!museCommit.some((arg) => String(arg).startsWith("--author")), "commit author must stay the shed git identity");
  const museDelegate = [...museBroker.jobs.values()][0].input;
  assert.ok(museDelegate.prompt.includes("Co-authored-by: Muse (claude-sonnet-4-6) <123456+muse-bot@users.noreply.github.com>"), museDelegate.prompt);

  const before = commands.length;
  const antiTask = await runner.runTask({ ...RUN, harness: "antigravity", task: "anti commit task" }, CALLER);
  antiBroker.finish(antiBroker.jobs.keys().next().value);
  await runner.whenIdle();
  assert.equal((await runner.status({ taskId: antiTask.taskId })).status, "pr_opened");
  const antiCommit = commands.slice(before).find((c) => c[0] === "git" && c[1] === "commit");
  assert.ok(antiCommit, "shed should create a commit for the antigravity task");
  assert.ok(!antiCommit.join(" ").includes("Co-authored-by:"), antiCommit.join(" "));
  const antiDelegate = [...antiBroker.jobs.values()][0].input;
  assert.ok(!antiDelegate.prompt.includes("Co-authored-by:"), antiDelegate.prompt);
});

test("independent lane caps: 5 antigravity running still lets muse start; 6th is busy naming harness", async () => {
  const antiBroker = multiBroker();
  antiBroker.harness = "antigravity";
  const museBroker = multiBroker();
  museBroker.harness = "muse";

  // Default concurrency: 5 for antigravity and 5 for muse (omit SAARIUS_ACP_REMOTE_MAX_CONCURRENT)
  const reposRoot = realpathSync(mkdtempSync(path.join(tmpdir(), "shed-caps-")));
  mkdirSync(path.join(reposRoot, "saari-co", "site"), { recursive: true });

  const runner = new ShedTaskRunner({
    brokers: { antigravity: antiBroker, muse: museBroker },
    env: {
      SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS,
      SAARIUS_ACP_REMOTE_REPOS_ROOT: reposRoot,
    },
    guard: async () => {},
    log: async () => {},
    run: async (command, args) => {
      if (args[0] === "rev-parse") return START;
      return "";
    },
  });
  await runner.init();

  assert.equal(runner.maxConcurrentFor("antigravity"), 5);
  assert.equal(runner.maxConcurrentFor("muse"), 5);

  // Start 5 antigravity tasks
  const antiTasks = await Promise.all(
    [1, 2, 3, 4, 5].map((i) => runner.runTask({ ...RUN, harness: "antigravity", task: `anti-${i}` }, CALLER)),
  );
  assert.ok(antiTasks.every((t) => t.status === "running"), "all 5 antigravity tasks should be running");
  assert.equal(runner.activeCountForHarness("antigravity"), 5);
  assert.equal(runner.activeCountForHarness("muse"), 0);

  // 6th antigravity task should return busy naming antigravity
  const antiBusy = await runner.runTask({ ...RUN, harness: "antigravity", task: "anti-6" }, CALLER);
  assert.equal(antiBusy.status, "busy");
  assert.equal(antiBusy.harness, "antigravity");
  assert.equal(antiBusy.running, 5);
  assert.equal(antiBusy.maxConcurrent, 5);
  assert.match(antiBusy.message, /antigravity/);

  // 5 antigravity running STILL lets a muse task start
  const museTask = await runner.runTask({ ...RUN, harness: "muse", task: "muse-1" }, CALLER);
  assert.equal(museTask.status, "running");
  assert.equal(museTask.harness, "muse");
  assert.equal(runner.activeCountForHarness("muse"), 1);

  // Fill remaining 4 muse slots (total 5 muse)
  const moreMuse = await Promise.all(
    [2, 3, 4, 5].map((i) => runner.runTask({ ...RUN, harness: "muse", task: `muse-${i}` }, CALLER)),
  );
  assert.ok(moreMuse.every((t) => t.status === "running"));
  assert.equal(runner.activeCountForHarness("muse"), 5);

  // 6th muse task should return busy naming muse
  const museBusy = await runner.runTask({ ...RUN, harness: "muse", task: "muse-6" }, CALLER);
  assert.equal(museBusy.status, "busy");
  assert.equal(museBusy.harness, "muse");
  assert.equal(museBusy.running, 5);
  assert.equal(museBusy.maxConcurrent, 5);
  assert.match(museBusy.message, /muse/);

  // Clean up
  for (const id of antiBroker.jobs.keys()) antiBroker.finish(id);
  for (const id of museBroker.jobs.keys()) museBroker.finish(id);
  await runner.whenIdle();
});

test("shed_task_run tool input schema exposes headBranch, harness, and model, and steer/result tools are registered", () => {
  const fakeRunner = { runTask: () => {}, status: () => {}, cancel: () => {}, steer: () => {}, result: () => {} };
  const server = createShedMcpServer(fakeRunner, { label: "test" });
  const tool = server._registeredTools["shed_task_run"];
  assert.ok(tool, "shed_task_run tool must be registered");
  const shape = tool.inputSchema.shape;
  assert.ok(shape.headBranch, "headBranch must be present in input schema");
  assert.ok(shape.harness, "harness must be present in input schema");
  assert.ok(shape.model, "model must be present in input schema");
  assert.deepEqual(shape.harness.unwrap().options, ["antigravity", "muse"]);

  const steerTool = server._registeredTools["shed_task_steer"];
  assert.ok(steerTool, "shed_task_steer tool must be registered");
  assert.ok(steerTool.inputSchema.shape.taskId);
  assert.ok(steerTool.inputSchema.shape.instruction);
  assert.ok(steerTool.inputSchema.shape.requested_by);

  const resultTool = server._registeredTools["shed_task_result"];
  assert.ok(resultTool, "shed_task_result tool must be registered");
  assert.ok(resultTool.inputSchema.shape.taskId);
});

test("circular-JSON crash fix: start() keeps broker off task record; map entry removed after finish", async () => {
  const broker = fakeBroker();
  broker.timer = setTimeout(() => {}, 60_000);
  broker.circularRef = broker;

  const { runner, reposRoot } = shedFixture(undefined, { broker });
  await runner.init();

  try {
    const started = await runner.runTask(RUN, CALLER);
    assert.equal(started.status, "running");
    assert.ok(started.taskId);

    assert.equal(runner.taskBrokers.get(started.taskId), broker);
    const inMemoryTask = runner.tasks.get(started.taskId);
    assert.equal(inMemoryTask.broker, undefined);

    const taskRecordPath = path.join(reposRoot, ".saarius-shed", "tasks", `${started.taskId}.json`);
    const writtenJson = readFileSync(taskRecordPath, "utf8");
    const parsed = JSON.parse(writtenJson);
    assert.equal(parsed.broker, undefined);
    assert.equal(parsed.taskId, started.taskId);
    assert.equal(parsed.status, "running");

    broker.finish();
    await runner.whenIdle();

    assert.equal(runner.taskBrokers.has(started.taskId), false);

    const finalParsed = JSON.parse(readFileSync(taskRecordPath, "utf8"));
    assert.equal(finalParsed.broker, undefined);
    assert.equal(finalParsed.status, "pr_opened");
  } finally {
    clearTimeout(broker.timer);
  }
});

test("model selection: default used when unset, sent to broker, and recorded", async () => {
  assert.equal(DEFAULT_ANTIGRAVITY_MODEL, "gemini-4-argon-medium");
  const { runner, broker, reposRoot } = shedFixture();
  await runner.init();

  const started = await runner.runTask(RUN, CALLER);
  assert.equal(started.status, "running");
  assert.equal(started.model, DEFAULT_ANTIGRAVITY_MODEL);

  const delegateCall = broker.calls.find((c) => c.name === "delegate");
  assert.ok(delegateCall, "delegate should be called");
  assert.equal(delegateCall.input.model, DEFAULT_ANTIGRAVITY_MODEL);

  const status = await runner.status({ taskId: started.taskId });
  assert.equal(status.model, DEFAULT_ANTIGRAVITY_MODEL);

  const taskRecordPath = path.join(reposRoot, ".saarius-shed", "tasks", `${started.taskId}.json`);
  const record = JSON.parse(readFileSync(taskRecordPath, "utf8"));
  assert.equal(record.model, DEFAULT_ANTIGRAVITY_MODEL);

  broker.finish();
  await runner.whenIdle();
});

test("model selection: env and config overrides win, request override wins, model persisted in record", async () => {
  const envModel = "test-env-model-override";
  const { runner: envRunner, broker: envBroker, reposRoot: envRoot } = shedFixture(undefined, {
    env: { [SHED_ANTIGRAVITY_MODEL_ENV]: envModel },
  });
  await envRunner.init();
  const envStarted = await envRunner.runTask(RUN, CALLER);
  assert.equal(envStarted.model, envModel);
  assert.equal(envBroker.calls.find((c) => c.name === "delegate")?.input.model, envModel);
  const envRecord = JSON.parse(readFileSync(path.join(envRoot, ".saarius-shed", "tasks", `${envStarted.taskId}.json`), "utf8"));
  assert.equal(envRecord.model, envModel);
  envBroker.finish();
  await envRunner.whenIdle();

  const configModel = "test-config-model-override";
  const { runner: configRunner, broker: configBroker, reposRoot: configRoot } = shedFixture(undefined, {
    env: { [SHED_ANTIGRAVITY_MODEL_ENV]: "should-be-shadowed" },
    runnerOptions: { antigravityModel: configModel },
  });
  await configRunner.init();
  const configStarted = await configRunner.runTask(RUN, CALLER);
  assert.equal(configStarted.model, configModel);
  assert.equal(configBroker.calls.find((c) => c.name === "delegate")?.input.model, configModel);
  const configRecord = JSON.parse(readFileSync(path.join(configRoot, ".saarius-shed", "tasks", `${configStarted.taskId}.json`), "utf8"));
  assert.equal(configRecord.model, configModel);

  configBroker.finish();
  await configRunner.whenIdle();

  // 3. Request-level override wins over runner config
  const requestModel = "test-request-model-override";
  const { runner: reqRunner, broker: reqBroker, reposRoot: reqRoot } = shedFixture(undefined, {
    runnerOptions: { antigravityModel: configModel, advertisedModels: { antigravity: [configModel, requestModel] } },
  });
  await reqRunner.init();
  const reqStarted = await reqRunner.runTask({ ...RUN, model: requestModel }, CALLER);
  assert.equal(reqStarted.model, requestModel);
  assert.equal(reqBroker.calls.find((c) => c.name === "delegate")?.input.model, requestModel);
  const reqRecord = JSON.parse(readFileSync(path.join(reqRoot, ".saarius-shed", "tasks", `${reqStarted.taskId}.json`), "utf8"));
  assert.equal(reqRecord.model, requestModel);
  reqBroker.finish();
  await reqRunner.whenIdle();
});

test("runTask propagates rejections from start() instead of resolving with an error value", async () => {
  const { runner, broker } = shedFixture();
  await runner.init();

  const originalStart = runner.start.bind(runner);
  runner.start = async (task) => {
    runner.releaseActive(task.taskId, task);
    throw new Error("start failed explicitly");
  };

  await assert.rejects(runner.runTask(RUN, CALLER), /start failed explicitly/);

  runner.start = originalStart;
  const normal = await runner.runTask(RUN, CALLER);
  assert.equal(normal.status, "running");
  broker.finish();
  await runner.whenIdle();
});

test("shed_task_run validates model against each harness's advertised models and rejects unknown models", async () => {
  const antiBroker = multiBroker({ advertisedModels: ["gemini-4-argon-medium", "gemini-3.8-flash-high"] });
  antiBroker.harness = "antigravity";
  const museBroker = multiBroker({ advertisedModels: ["claude-sonnet-4-6", "gpt-5.4"] });
  museBroker.harness = "muse";

  const { runner } = shedFixture(undefined, {
    brokers: { antigravity: antiBroker, muse: museBroker },
    env: { SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "5" },
  });
  await runner.init();

  // Rejects unknown model for antigravity
  await assert.rejects(
    runner.runTask({ ...RUN, harness: "antigravity", model: "claude-sonnet-4-6" }, CALLER),
    (err) =>
      err.code === "MODEL_INVALID" &&
      /not advertised by harness "antigravity"/.test(err.message) &&
      err.details?.harness === "antigravity",
  );

  // Rejects unknown model for muse
  await assert.rejects(
    runner.runTask({ ...RUN, harness: "muse", model: "gemini-4-argon-medium" }, CALLER),
    (err) =>
      err.code === "MODEL_INVALID" &&
      /not advertised by harness "muse"/.test(err.message) &&
      err.details?.harness === "muse",
  );

  // Rejects empty/whitespace/secret model strings
  for (const badModel of ["", "   ", " gemini-4-argon-medium ", "x".repeat(121)]) {
    await assert.rejects(
      runner.runTask({ ...RUN, model: badModel }, CALLER),
      (err) => err.code === "MODEL_INVALID",
    );
  }
  await assert.rejects(
    runner.runTask({ ...RUN, model: "ghp_abcdefghijklmnopqrstuv" }, CALLER),
    (err) => err.code === "SECRET_REFUSED",
  );

  // Accepts advertised models for each harness
  assert.ok(DEFAULT_ANTIGRAVITY_ADVERTISED_MODELS.includes("gemini-3.8-flash-high"));
  assert.ok(DEFAULT_MUSE_ADVERTISED_MODELS.includes("claude-sonnet-4-6"));
  const antiStarted = await runner.runTask({ ...RUN, harness: "antigravity", model: "gemini-3.8-flash-high" }, CALLER);
  assert.equal(antiStarted.status, "running");
  assert.equal(antiStarted.model, "gemini-3.8-flash-high");

  const museStarted = await runner.runTask({ ...RUN, harness: "muse", model: "claude-sonnet-4-6" }, CALLER);
  assert.equal(museStarted.status, "running");
  assert.equal(museStarted.model, "claude-sonnet-4-6");

  for (const id of antiBroker.jobs.keys()) antiBroker.finish(id);
  for (const id of museBroker.jobs.keys()) museBroker.finish(id);
  await runner.whenIdle();
});

test("shed_task_steer sends follow-up instruction to a running task and validates caller, requested_by, secrets, and state", async () => {
  const { runner, broker, logs } = shedFixture();
  await runner.init();

  // Auth refusal on runTask, steer, and result when Access caller is missing or invalid
  for (const badCaller of [undefined, null, {}, { label: "" }, { label: "invalid caller!" }]) {
    await assert.rejects(runner.runTask(RUN, badCaller), { code: "ACCESS_DENIED" });
    await assert.rejects(
      runner.steer({ taskId: "shed-20261014T000000-abcdef", instruction: "Continue", requested_by: "acp-runner" }, badCaller),
      { code: "ACCESS_DENIED" },
    );
    await assert.rejects(runner.result({ taskId: "shed-20261014T000000-abcdef" }, badCaller), { code: "ACCESS_DENIED" });
  }

  // Unknown taskId -> TASK_NOT_FOUND
  await assert.rejects(
    runner.steer({ taskId: "shed-20261014T000000-deadbe", instruction: "Check tests", requested_by: "acp-runner" }, CALLER),
    { code: "TASK_NOT_FOUND" },
  );
  await assert.rejects(
    runner.steer({ taskId: "not-a-task-id", instruction: "Check tests", requested_by: "acp-runner" }, CALLER),
    { code: "TASK_NOT_FOUND" },
  );

  // Start a task
  const started = await runner.runTask(RUN, CALLER);
  assert.equal(started.status, "running");

  // Validate requested_by
  for (const badReqBy of [undefined, null, "", "   ", "bad space", "bad/slash"]) {
    await assert.rejects(
      runner.steer({ taskId: started.taskId, instruction: "Focus on unit tests", requested_by: badReqBy }, CALLER),
      { code: "REQUESTED_BY_REQUIRED" },
    );
  }

  // Validate instruction (non-empty, length cap, string types, null bytes)
  for (const badInstruction of [undefined, null, 123, "", "   ", "a\u0000b", "x".repeat(STEER_MAX + 1)]) {
    await assert.rejects(
      runner.steer({ taskId: started.taskId, instruction: badInstruction, requested_by: "acp-runner" }, CALLER),
      { code: "INSTRUCTION_INVALID" },
    );
  }

  // Secret scanner on instruction -> reject with SECRET_REFUSED
  for (const secretInstruction of [
    "Use token ghp_abcdefghijklmnopqrstuv to authenticate",
    "Here is key sk-1234567890abcdefghij",
    "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9",
    "-----BEGIN RSA PRIVATE KEY-----",
  ]) {
    await assert.rejects(
      runner.steer({ taskId: started.taskId, instruction: secretInstruction, requested_by: "acp-runner" }, CALLER),
      { code: "SECRET_REFUSED" },
    );
  }
  assert.equal(broker.calls.filter((c) => c.name === "steer").length, 0);

  // Success path: steers running task
  const steered = await runner.steer(
    { taskId: started.taskId, instruction: "Also update the unit tests", requested_by: "bot-steerer" },
    CALLER,
  );
  assert.equal(steered.steered, true);
  assert.equal(steered.taskId, started.taskId);
  assert.equal(steered.status, "running");
  assert.equal(steered.requestedBy, "bot-steerer");

  const steerCall = broker.calls.find((c) => c.name === "steer");
  assert.ok(steerCall, "broker.steer should have been called");
  assert.equal(steerCall.input.jobId, "job-1");
  assert.equal(steerCall.input.sessionId, "11111111-2222-3333-4444-555555555555");
  assert.equal(steerCall.input.instruction, "Also update the unit tests");
  assert.equal(steerCall.input.requestedBy, "bot-steerer");
  assert.ok(logs.some((l) => l.event === "steered" && l.taskId === started.taskId));
  assert.ok(!JSON.stringify(logs).includes("Also update the unit tests"));

  // Finish task, then verify steer refuses finished task with TASK_NOT_RUNNING
  broker.finish();
  await runner.whenIdle();
  await assert.rejects(
    runner.steer({ taskId: started.taskId, instruction: "Too late", requested_by: "acp-runner" }, CALLER),
    (err) => err.code === "TASK_NOT_RUNNING" && /pr_opened/.test(err.message),
  );
});

test("shed_task_steer refuses cancelled and failed tasks with TASK_NOT_RUNNING and supports runtime fallback", async () => {
  // 1. Cancelled task refusal
  const { runner: cancelRunner } = shedFixture({ jobStatus: "cancelled" });
  await cancelRunner.init();
  const cTask = await cancelRunner.runTask(RUN, CALLER);
  await cancelRunner.cancel({ taskId: cTask.taskId });
  await cancelRunner.whenIdle();
  await assert.rejects(
    cancelRunner.steer({ taskId: cTask.taskId, instruction: "After cancel", requested_by: "acp-runner" }, CALLER),
    (err) => err.code === "TASK_NOT_RUNNING" && /cancelled/.test(err.message),
  );

  // 2. Failed task refusal
  const { runner: failRunner, broker: failBroker } = shedFixture({ jobStatus: "failed" });
  await failRunner.init();
  const fTask = await failRunner.runTask(RUN, CALLER);
  failBroker.finish();
  await failRunner.whenIdle();
  await assert.rejects(
    failRunner.steer({ taskId: fTask.taskId, instruction: "After fail", requested_by: "acp-runner" }, CALLER),
    (err) => err.code === "TASK_NOT_RUNNING" && /failed/.test(err.message),
  );

  // 3. Fallback to runtime.startTurn when broker.steer throws STEERING_UNSUPPORTED
  const turnCalls = [];
  const baseBroker = fakeBroker();
  const runtimeBroker = {
    ...baseBroker,
    active: new Map([["job-1", { handle: { sessionId: "sess-1" } }]]),
    runtime: {
      startTurn(args) {
        turnCalls.push(args);
        return { promptStarted: Promise.resolve() };
      },
    },
    async steer() {
      const err = new Error("not supported");
      err.code = "STEERING_UNSUPPORTED";
      throw err;
    },
  };
  const { runner: rtRunner } = shedFixture(undefined, { broker: runtimeBroker });
  await rtRunner.init();
  const rtTask = await rtRunner.runTask(RUN, CALLER);
  const steered = await rtRunner.steer({ taskId: rtTask.taskId, instruction: "Fallback steer", requested_by: "acp-runner" }, CALLER);
  assert.equal(steered.steered, true);
  assert.equal(turnCalls.length, 1);
  assert.equal(turnCalls[0].text, "Fallback steer");
  assert.equal(turnCalls[0].mode, "steer");
  baseBroker.finish();
  await rtRunner.whenIdle();
});

test("shed_task_result returns redacted summary, PR url, head sha, harness, model, and session link from finished task record", async () => {
  const { runner, broker, reposRoot } = shedFixture(
    { backendSessionId: "11111111-2222-3333-4444-555555555555" },
    { runnerOptions: { sessionBaseUrl: "https://shed.sm0ky.dev" } },
  );
  await runner.init();

  // Unknown taskId -> TASK_NOT_FOUND
  await assert.rejects(
    runner.result({ taskId: "shed-20261014T000000-deadbe" }, CALLER),
    { code: "TASK_NOT_FOUND" },
  );
  await assert.rejects(
    runner.result({ taskId: "invalid-id" }, CALLER),
    { code: "TASK_NOT_FOUND" },
  );

  const started = await runner.runTask({ ...RUN, harness: "antigravity", model: "gemini-3.8-flash-high" }, CALLER);
  assert.equal(started.status, "running");

  // Running task -> wrong-state error (TASK_NOT_FINISHED)
  await assert.rejects(
    runner.result({ taskId: started.taskId }, CALLER),
    (err) => err.code === "TASK_NOT_FINISHED" && /still running/.test(err.message),
  );

  // Finish task
  broker.finish();
  await runner.whenIdle();

  // Verify reading from persisted task record (even if in-memory map entry is cleared)
  runner.tasks.delete(started.taskId);

  const res = await runner.result({ taskId: started.taskId }, CALLER);
  assert.equal(res.taskId, started.taskId);
  assert.equal(res.status, "pr_opened");
  assert.equal(res.prUrl, "https://github.com/saari-co/site/pull/7");
  assert.equal(res.headSha, HEAD);
  assert.equal(res.harness, "antigravity");
  assert.equal(res.model, "gemini-3.8-flash-high");
  assert.equal(res.session_id, "11111111-2222-3333-4444-555555555555");
  assert.equal(res.session_url, "https://shed.sm0ky.dev/s/11111111-2222-3333-4444-555555555555");
  assert.equal(res.sessionUrl, "https://shed.sm0ky.dev/s/11111111-2222-3333-4444-555555555555");
  assert.doesNotMatch(res.summary, /ghp_abcdefghijklmnop/);
  assert.match(res.summary, /Changed README/);

  // Verify that even if the task record on disk had an unredacted token, result() redacts it on read
  const recordPath = path.join(reposRoot, ".saarius-shed", "tasks", `${started.taskId}.json`);
  const diskRecord = JSON.parse(readFileSync(recordPath, "utf8"));
  diskRecord.summary = "Summary with leaked sk-proj-1234567890abcdefghijklmnop token";
  writeFileSync(recordPath, JSON.stringify(diskRecord, null, 2));

  const resRedacted = await runner.result({ taskId: started.taskId }, CALLER);
  assert.doesNotMatch(resRedacted.summary, /sk-proj-1234567890abcdefghijklmnop/);
  assert.match(resRedacted.summary, /\[redacted/i);
});

test("MCP HTTP end-to-end: shed_task_steer and shed_task_result over authenticated /mcp", async () => {
  const { runner, broker } = shedFixture(
    { backendSessionId: "22222222-3333-4444-5555-666666666666" },
    { runnerOptions: { sessionBaseUrl: "https://shed.sm0ky.dev" } },
  );
  await runner.init();
  const host = await startRemoteShedHost({
    env: { SAARIUS_ACP_HTTP_PORT: "0" },
    bridge: "antigravity-acp",
    authenticate: authenticator(),
    createServer: (caller) => createShedMcpServer(runner, caller),
    log: () => {},
  });
  try {
    const url = new URL(`http://127.0.0.1:${host.port}/mcp`);
    const client = new Client({ name: "acp-runner", version: "0" });
    await client.connect(
      new StreamableHTTPClientTransport(url, {
        requestInit: { headers: { "cf-access-jwt-assertion": jwt() } },
      }),
    );

    // 1. Reject unadvertised model via MCP
    const badModelCall = await client.callTool({
      name: "shed_task_run",
      arguments: { ...RUN, harness: "antigravity", model: "not-a-valid-model" },
    });
    assert.equal(badModelCall.isError, true);
    assert.equal(JSON.parse(badModelCall.content[0].text).error.code, "MODEL_INVALID");

    // 2. Start task with valid advertised model
    const runCall = await client.callTool({
      name: "shed_task_run",
      arguments: { ...RUN, harness: "antigravity", model: "gemini-4-argon-medium" },
    });
    assert.ok(!runCall.isError);
    const started = JSON.parse(runCall.content[0].text);
    assert.equal(started.status, "running");

    // 3. Calling shed_task_result while still running returns wrong-state error
    const earlyResult = await client.callTool({
      name: "shed_task_result",
      arguments: { taskId: started.taskId },
    });
    assert.equal(earlyResult.isError, true);
    assert.equal(JSON.parse(earlyResult.content[0].text).error.code, "TASK_NOT_FINISHED");

    // 4. Calling shed_task_steer with a secret returns SECRET_REFUSED
    const secretSteer = await client.callTool({
      name: "shed_task_steer",
      arguments: {
        taskId: started.taskId,
        instruction: "Use ghp_abcdefghijklmnopqrstuv",
        requested_by: "acp-runner",
      },
    });
    assert.equal(secretSteer.isError, true);
    assert.equal(JSON.parse(secretSteer.content[0].text).error.code, "SECRET_REFUSED");

    // 5. Calling shed_task_steer with valid instruction succeeds
    const okSteer = await client.callTool({
      name: "shed_task_steer",
      arguments: {
        taskId: started.taskId,
        instruction: "Make sure lint passes",
        requested_by: "acp-runner",
      },
    });
    assert.ok(!okSteer.isError);
    assert.equal(JSON.parse(okSteer.content[0].text).steered, true);

    // 6. Finish task and call shed_task_result
    broker.finish();
    await runner.whenIdle();

    const finalResult = await client.callTool({
      name: "shed_task_result",
      arguments: { taskId: started.taskId },
    });
    assert.ok(!finalResult.isError);
    const parsedResult = JSON.parse(finalResult.content[0].text);
    assert.equal(parsedResult.taskId, started.taskId);
    assert.equal(parsedResult.status, "pr_opened");
    assert.equal(parsedResult.prUrl, "https://github.com/saari-co/site/pull/7");
    assert.equal(parsedResult.headSha, HEAD);
    assert.equal(parsedResult.harness, "antigravity");
    assert.equal(parsedResult.model, "gemini-4-argon-medium");
    assert.equal(parsedResult.session_url, "https://shed.sm0ky.dev/s/22222222-3333-4444-5555-666666666666");
    assert.doesNotMatch(parsedResult.summary, /ghp_abcdefghijklmnop/);

    // 7. Steer after finish returns wrong-state error
    const lateSteer = await client.callTool({
      name: "shed_task_steer",
      arguments: {
        taskId: started.taskId,
        instruction: "One more thing",
        requested_by: "acp-runner",
      },
    });
    assert.equal(lateSteer.isError, true);
    assert.equal(JSON.parse(lateSteer.content[0].text).error.code, "TASK_NOT_RUNNING");

    await client.close();
  } finally {
    await host.close();
  }
});
