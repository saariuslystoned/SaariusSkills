import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { generateKeyPairSync, sign } from "node:crypto";
import { mkdirSync, mkdtempSync, realpathSync } from "node:fs";
import { request } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { createAccessAuthenticator, parseRemoteCallers, resolveAccessConfig } from "../access-auth.mjs";
import { resolveHttpConfig, resolveTransport, startRemoteShedHost } from "../http-host.mjs";
import { createRepoOwnerGuard, githubOwnerFromRemote, parseRepoOwners } from "../repo-allowlist.mjs";
import { ShedTaskRunner } from "../shed-tasks.mjs";
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

function shedFixture(brokerOptions, { changes = " M README.md" } = {}) {
  const reposRoot = realpathSync(mkdtempSync(path.join(tmpdir(), "shed-root-")));
  mkdirSync(path.join(reposRoot, "saari-co", "site"), { recursive: true });
  const commands = [];
  const logs = [];
  const broker = fakeBroker(brokerOptions);
  const runner = new ShedTaskRunner({
    broker,
    env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: OWNERS, SAARIUS_ACP_REMOTE_REPOS_ROOT: reposRoot },
    guard: async () => {},
    log: async (record) => logs.push(record),
    run: async (command, args) => {
      commands.push([command, ...args]);
      if (args[0] === "status") return changes;
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
  assert.match(delegate.prompt, /Do not commit, push/);
  const flat = commands.map((c) => c.join(" "));
  assert.ok(flat.some((c) => c.startsWith(`git worktree add --quiet -b ${started.branch}`)));
  assert.ok(flat.some((c) => c === `git push --quiet -u origin ${started.branch}`));
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
