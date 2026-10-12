import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { generateKeyPairSync, sign } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { request } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { createAccessAuthenticator, parseRemoteCallers, resolveAccessConfig } from "../access-auth.mjs";
import { resolveHttpConfig, resolveTransport, startRemoteShedHost } from "../http-host.mjs";
import { createRepoOwnerGuard, githubOwnerFromRemote, originOwnerFromRemote, parseRepoOwners } from "../repo-allowlist.mjs";
import { parseMaxConcurrent, ShedTaskRunner } from "../shed-tasks.mjs";
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

function fakeBroker({ delegateError, jobStatus = "completed" } = {}) {
  const calls = [];
  let release;
  const done = new Promise((resolve) => { release = resolve; });
  return {
    calls,
    finish: () => release(),
    async delegate(input) {
      calls.push({ name: "delegate", input });
      if (delegateError) throw delegateError;
      return { jobId: "job-1" };
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
  };
}

const START = "a".repeat(40);
const HEAD = "b".repeat(40);
function shedFixture(brokerOptions, { changes = " M README.md", ahead, remoteHead = START, pushError, broker: customBroker, env: extraEnv = {} } = {}) {
  const reposRoot = realpathSync(mkdtempSync(path.join(tmpdir(), "shed-root-")));
  mkdirSync(path.join(reposRoot, "saari-co", "site"), { recursive: true });
  mkdirSync(path.join(reposRoot, "smoky", "motors"), { recursive: true });
  let committed = false;
  const commands = [];
  const logs = [];
  const broker = customBroker ?? fakeBroker(brokerOptions);
  const runner = new ShedTaskRunner({
    broker,
    env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS, SAARIUS_ACP_REMOTE_REPOS_ROOT: reposRoot, SAARIUS_ACP_REMOTE_ORIGIN_OWNERS: "smoky", ...extraEnv },
    guard: async () => {},
    log: async (record) => logs.push(record),
    run: async (command, args) => {
      commands.push([command, ...args]);
      if (args[0] === "status") return changes;
      if (args[0] === "commit") committed = true;
      if (args[0] === "rev-parse") return args[1] === "--verify" ? START : HEAD;
      if (args[0] === "rev-list") return String(ahead ?? (committed ? 1 : 0));
      if (args[0] === "ls-remote") return `${remoteHead}\trefs/heads/x`;
      if (args[0] === "push" && pushError) throw pushError;
      if (command === "origin") return "Created change https://origin.cursor.com/smoky/motors/pull/3";
      if (command === "gh") return "https://github.com/saari-co/site/pull/7";
      return "";
    },
  });
  return { runner, broker, commands, logs, reposRoot };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 50));
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

test("remote endpoint requires Access and exposes only the three narrow task tools", async () => {
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
  assert.equal((await runner.status({})).status, "idle");
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
  const started = await runner.runTask({ ...RUN, headBranch: "feature/x" }, CALLER);
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
  const started = await runner.runTask({ ...RUN, headBranch: "feature/x" }, CALLER);
  broker.finish();
  await settle();
  assert.equal((await runner.status({ taskId: started.taskId })).error.code, "REMOTE_BRANCH_MOVED");
});

test("headBranch validation", async () => {
  const { runner } = shedFixture();
  await runner.init();
  await assert.rejects(runner.runTask({ ...RUN, headBranch: "--force" }, CALLER), { code: "HEAD_BRANCH_INVALID" });
  await assert.rejects(runner.runTask({ ...RUN, headBranch: "main" }, CALLER), { code: "HEAD_BRANCH_INVALID" });
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
function multiBroker({ onDelegate } = {}) {
  const jobs = new Map();
  let n = 0;
  return {
    jobs,
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
  await settle();
  assert.equal((await runner.status({ taskId: started[1].taskId })).status, "cancelled");
  const after = await runner.status({});
  assert.equal(after.status, "available");
  assert.equal(after.running, 2);
  const again = await runner.runTask({ ...RUN, task: "t5" }, CALLER);
  assert.equal(again.status, "running");
  for (const id of broker.jobs.keys()) broker.finish(id);
  await settle();
  assert.equal((await runner.status({})).status, "idle");
});

test("a second task on the same repo+headBranch is refused while the first runs", async () => {
  const broker = multiBroker();
  const { runner } = shedFixture(undefined, { broker, env: { SAARIUS_ACP_REMOTE_MAX_CONCURRENT: "5" } });
  await runner.init();
  const first = await runner.runTask({ ...RUN, headBranch: "feature/x" }, CALLER);
  assert.equal(first.status, "running");
  await assert.rejects(
    runner.runTask({ ...RUN, task: "other", headBranch: "feature/x" }, CALLER),
    (error) => error.code === "BRANCH_BUSY" && error.details.taskId === first.taskId,
  );
  const otherBranch = await runner.runTask({ ...RUN, headBranch: "feature/y" }, CALLER);
  assert.equal(otherBranch.status, "running");
  const otherRepo = await runner.runTask({ ...RUN, owner: "smoky", repo: "motors", forge: "origin", headBranch: "feature/x" }, CALLER);
  assert.equal(otherRepo.status, "running");
  for (const id of broker.jobs.keys()) broker.finish(id, "cancelled");
  await settle();
  const freed = await runner.runTask({ ...RUN, task: "later", headBranch: "feature/x" }, CALLER);
  assert.equal(freed.status, "running");
  for (const id of broker.jobs.keys()) broker.finish(id, "cancelled");
  await settle();
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
  for (let i = 0; i < 100 && (await runner.status({})).status !== "idle"; i++) await settle();
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
