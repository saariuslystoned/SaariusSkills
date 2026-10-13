import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync } from "node:fs";
import { request } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { createAccessAuthenticator, createViewerAuthenticator, resolveViewerConfig } from "../access-auth.mjs";
import { startRemoteShedHost } from "../http-host.mjs";
import {
  appendEvent,
  buildView,
  createTranscript,
  isSessionId,
  loadSession,
  normalizeHarness,
  renderSessionHtml,
  resolveViewerHarness,
  saveSession,
} from "../shed-sessions.mjs";
import { ShedTaskRunner } from "../shed-tasks.mjs";
import { redactDeep, redactText } from "../viewer-redact.mjs";

const TEAM = "sm0ky.cloudflareaccess.com";
const MCP_AUD = "a".repeat(64);
const VIEW_AUD = "b".repeat(64);
const CLIENT_ID = "acprunner0001.access";
const EMAIL = "ryan@smokyproduct.co";
const SID = "0f8fad5b-d9cb-469f-a165-70867728950e";
const ENV = {
  SAARIUS_ACP_ACCESS_TEAM_DOMAIN: TEAM,
  SAARIUS_ACP_ACCESS_AUD: MCP_AUD,
  SAARIUS_ACP_REMOTE_CALLERS: `${CLIENT_ID}=acp-runner`,
  SAARIUS_ACP_VIEWER_ACCESS_AUD: VIEW_AUD,
  SAARIUS_ACP_VIEWER_EMAILS: EMAIL,
};
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const JWKS = { keys: [{ ...publicKey.export({ format: "jwk" }), kid: "k1", alg: "RS256" }] };
const fetchJwks = async () => JWKS;
function jwt(claims) {
  const enc = (v) => Buffer.from(JSON.stringify(v)).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const head = enc({ alg: "RS256", kid: "k1", typ: "JWT" });
  const body = enc({ iss: `https://${TEAM}`, exp: now + 300, iat: now, ...claims });
  return `${head}.${body}.${sign("RSA-SHA256", Buffer.from(`${head}.${body}`), privateKey).toString("base64url")}`;
}
const humanJwt = (email = EMAIL, aud = VIEW_AUD) => jwt({ aud: [aud], email, type: "app" });
const serviceJwt = (aud = MCP_AUD) => jwt({ aud: [aud], common_name: CLIENT_ID });

// ---------- redaction ----------
test("redaction removes known secret shapes and keeps ordinary text", () => {
  const ghp = `ghp_${"A1b2".repeat(9)}`;
  const pat = `github_pat_${"x".repeat(22)}_${"Y".repeat(59)}`;
  const cases = [
    [`token ${ghp} here`, ghp],
    [`use ${pat}`, pat],
    ["Authorization: Bearer eyJhbGciOi.abc.def", "eyJhbGciOi"],
    ["curl -H 'Authorization: Bearer s3cr3tvalue123'", "s3cr3tvalue123"],
    [`CF-Access-Client-Secret: ${"f".repeat(64)}`, "f".repeat(64)],
    [`cf_access_client_secret="${"9".repeat(64)}"`, "9".repeat(64)],
    ["CF-Access-Client-Id: abc123.access", "abc123.access"],
    ["CLOUDFLARE_API_TOKEN=Zz9_cfTokenValue_0123456789abcdef", "Zz9_cfTokenValue"],
    ["X-Auth-Key: 0123456789abcdef0123456789abcdef01234", "0123456789abcdef0123456789abcdef01234"],
    ["key AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"],
    ["aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "wJalrXUtnFEMI"],
    ["-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA\n-----END OPENSSH PRIVATE KEY-----", "b3BlbnNzaC1rZXktdjEAAAA"],
    ["-----BEGIN RSA PRIVATE KEY-----\nMIIEtruncated", "MIIEtruncated"],
    ["export API_KEY=abc123", "abc123"],
    ['DB_PASSWORD="hunter2"', "hunter2"],
    ["MY_SECRET: s3cret", "s3cret"],
    ["STRIPE_TOKEN=tok_live_x", "tok_live_x"],
    ["https://user:pa55@github.com/x.git", "pa55"],
    [`assertion ${jwt({ aud: ["x"] })}`, "eyJhbGciOiJSUzI1NiIs"],
  ];
  for (const [input, secret] of cases) {
    const out = redactText(input);
    assert.ok(!out.includes(secret), `leaked ${secret} from ${JSON.stringify(input)} -> ${out}`);
    assert.match(out, /redacted/);
  }
  for (const plain of ["keyboard=yes passenger=1", "sessionId 0f8fad5b-d9cb-469f-a165-70867728950e", "Fixed the README typo", "git push origin HEAD"]) {
    assert.equal(redactText(plain), plain);
  }
});

test("redactDeep walks objects and blanks secret-named keys", () => {
  const out = redactDeep({ a: [`ghp_${"z".repeat(36)}`], nested: { apiKey: "plain", password: "x", note: "ok" }, n: 3 });
  assert.equal(out.a[0], "[redacted github token]");
  assert.equal(out.nested.apiKey, "[redacted]");
  assert.equal(out.nested.password, "[redacted]");
  assert.equal(out.nested.note, "ok");
  assert.equal(out.n, 3);
});

// ---------- transcript + render ----------
test("transcript folds deltas and tool updates; view and HTML are redacted and escaped", () => {
  const t = createTranscript({ prompt: "Fix <b>bug</b> TOKEN=abc" });
  appendEvent(t, { type: "text_delta", stream: "thought", text: "thinking " });
  appendEvent(t, { type: "text_delta", stream: "thought", text: "more" });
  appendEvent(t, { type: "tool_call", toolCallId: "t1", title: "Read file", kind: "read", status: "pending", text: "Read file: a.txt" });
  appendEvent(t, { type: "tool_call", toolCallId: "t1", status: "completed", text: `out ghp_${"q".repeat(36)}` });
  appendEvent(t, { type: "text_delta", text: "Done <script>alert(1)</script>" });
  appendEvent(t, { type: "status", tag: "plan", entries: [{ content: "step 1", status: "completed" }] });
  appendEvent(t, { type: "status", tag: "usage_update", text: "usage" });
  assert.equal(t.entries.length, 3);
  assert.equal(t.entries[0].text, "thinking more");
  assert.equal(t.entries[1].status, "completed");
  const view = buildView({ sessionId: SID, task: { taskId: "shed-1", status: "running", repo: "o/r", prUrl: "javascript:alert(1)" }, transcript: t });
  assert.equal(view.live, true);
  assert.ok(!JSON.stringify(view).includes("q".repeat(36)));
  assert.match(view.prompt, /TOKEN=\[redacted\]/);
  const html = renderSessionHtml(view, { nonce: "n0nce" });
  assert.match(html, /<meta name="robots" content="noindex/);
  assert.ok(!html.includes("<script>alert(1)"));
  assert.ok(!html.includes('href="javascript:'));
  assert.match(html, /&lt;b&gt;bug/);
  assert.match(html, /<script nonce="n0nce">/);
  const done = renderSessionHtml(buildView({ sessionId: SID, task: { status: "pr_opened", prUrl: "https://github.com/o/r/pull/1" }, transcript: t }), { nonce: "n" });
  assert.ok(!done.includes("<script"), "finished sessions do not poll");
  assert.match(done, /href="https:\/\/github.com\/o\/r\/pull\/1"/);
});

// ---------- harness badge tests ----------
test("record with harness=muse renders the Muse badge", () => {
  const view = buildView({
    sessionId: SID,
    harness: "muse",
    task: { taskId: "shed-1", status: "completed", repo: "o/r" },
    transcript: createTranscript(),
  });
  assert.equal(view.harness, "muse");
  const html = renderSessionHtml(view, { nonce: "n" });
  assert.match(html, /class="badge harness-badge harness-muse"/);
  assert.match(html, /Muse/);
  assert.match(html, /<svg /);
  assert.ok(!html.includes("http://"), "no remote assets");
  assert.ok(!html.includes("https://"), "no remote assets in badge");
});

test("record without the field renders Antigravity", () => {
  // Existing records on CP-1 saved without the harness field
  const view = buildView({
    sessionId: SID,
    task: { taskId: "shed-1", status: "completed", repo: "o/r" },
    transcript: createTranscript(),
  });
  assert.equal(view.harness, "antigravity");
  const html = renderSessionHtml(view, { nonce: "n" });
  assert.match(html, /class="badge harness-badge harness-antigravity"/);
  assert.match(html, /Antigravity/);
  assert.match(html, /<svg /);
});

test("unknown value renders a neutral badge", () => {
  const view = buildView({
    sessionId: SID,
    harness: "unknown",
    task: { taskId: "shed-1", status: "completed", repo: "o/r" },
    transcript: createTranscript(),
  });
  assert.equal(view.harness, "unknown");
  const html = renderSessionHtml(view, { nonce: "n" });
  assert.match(html, /class="badge harness-badge harness-neutral/);

  // Unrecognized harness strings also render a neutral badge
  const customView = buildView({
    sessionId: SID,
    harness: "unregistered-runner-lane",
    task: { taskId: "shed-1", status: "completed", repo: "o/r" },
    transcript: createTranscript(),
  });
  assert.equal(customView.harness, "unknown");
  const customHtml = renderSessionHtml(customView, { nonce: "n" });
  assert.match(customHtml, /class="badge harness-badge harness-neutral/);
});

test("harness normalization and persistence in session records", async () => {
  assert.equal(normalizeHarness("antigravity"), "antigravity");
  assert.equal(normalizeHarness("MUSE"), "muse");
  assert.equal(normalizeHarness("grok-build"), "grok-build");
  assert.equal(normalizeHarness("grok"), "grok-build");
  assert.equal(normalizeHarness("cursor"), "cursor");
  assert.equal(normalizeHarness("something-else"), "unknown");
  assert.equal(normalizeHarness(null), "unknown");

  assert.equal(resolveViewerHarness(undefined), "antigravity");
  assert.equal(resolveViewerHarness(null), "antigravity");
  assert.equal(resolveViewerHarness("muse"), "muse");
  assert.equal(resolveViewerHarness("other"), "unknown");

  const dir = mkdtempSync(path.join(tmpdir(), "shed-session-record-"));
  await saveSession(dir, SID, {
    sessionId: SID,
    harness: "muse",
    task: { taskId: "t1", status: "completed" },
    transcript: createTranscript(),
  });
  const loaded = await loadSession(dir, SID);
  assert.equal(loaded.harness, "muse");

  // Record saved without harness field (historical session on CP-1)
  const legacyDir = mkdtempSync(path.join(tmpdir(), "shed-session-legacy-"));
  await saveSession(legacyDir, SID, {
    sessionId: SID,
    task: { taskId: "t1", status: "completed" },
    transcript: createTranscript(),
  });
  const legacyLoaded = await loadSession(legacyDir, SID);
  assert.equal(legacyLoaded.harness, undefined);
  const legacyView = buildView(legacyLoaded);
  assert.equal(legacyView.harness, "antigravity");
  const legacyHtml = renderSessionHtml(legacyView, { nonce: "n" });
  assert.match(legacyHtml, /Antigravity/);
});

test("session id validation is strict UUID", () => {
  assert.equal(isSessionId(SID), true);
  for (const bad of [SID.toUpperCase(), `${SID}x`, "../etc/passwd", "", "0f8fad5b-d9cb-469f-a165-70867728950", `${SID}/..`, null]) assert.equal(isSessionId(bad), false);
});

// ---------- runner integration ----------
function viewerBroker({ sessionId = SID, delegateDelayMs = 0 } = {}) {
  let observer;
  let release;
  const done = new Promise((resolve) => { release = resolve; });
  return {
    emit: (event) => observer?.("job-1", event),
    finish: () => release(),
    addEventObserver(fn) { observer = fn; return () => {}; },
    async delegate() {
      if (delegateDelayMs) await new Promise((r) => setTimeout(r, delegateDelayMs));
      return { jobId: "job-1", backendSessionId: sessionId };
    },
    async result() { await done; return { complete: true, status: "completed", handoff: "Changed README. AWS AKIAIOSFODNN7EXAMPLE" }; },
    async cancel() { release(); return {}; },
  };
}
function runnerFixture(broker, opts = {}) {
  const reposRoot = realpathSync(mkdtempSync(path.join(tmpdir(), "shed-view-")));
  mkdirSync(path.join(reposRoot, "saari-co", "site"), { recursive: true });
  let committed = false;
  const runner = new ShedTaskRunner({
    broker,
    env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: "saari-co", SAARIUS_ACP_REMOTE_REPOS_ROOT: reposRoot },
    guard: async () => {},
    log: async () => {},
    run: async (command, args) => {
      if (args[0] === "status") return " M README.md";
      if (args[0] === "commit") committed = true;
      if (args[0] === "rev-parse") return args[1] === "--verify" ? "a".repeat(40) : "b".repeat(40);
      if (args[0] === "rev-list") return committed ? "1" : "0";
      if (command === "gh") return "https://github.com/saari-co/site/pull/7";
      return "";
    },
    ...opts,
  });
  return { runner, reposRoot };
}
const RUN = { owner: "saari-co", repo: "site", task: "Fix the README typo", requested_by: "grok-bot" };
const settle = () => new Promise((r) => setTimeout(r, 50));

test("shed_task_run returns session_id and session_url in its first response; transcript persists after finish", async () => {
  const broker = viewerBroker();
  const { runner, reposRoot } = runnerFixture(broker);
  await runner.init();
  const started = await runner.runTask(RUN, { label: "acp-runner" });
  assert.equal(started.status, "running");
  assert.equal(started.session_id, SID);
  assert.equal(started.session_url, `https://shed.sm0ky.dev/s/${SID}`);
  broker.emit({ type: "tool_call", toolCallId: "c1", title: "Edit README.md", status: "completed", text: "Edit README.md" });
  broker.emit({ type: "text_delta", text: "Fixed it. GITHUB_TOKEN=leakme" });
  const live = await runner.viewSession(SID);
  assert.equal(live.live, true);
  assert.equal(live.prompt, "Fix the README typo");
  assert.equal(live.entries.length, 2);
  assert.equal(live.harness, "antigravity");
  assert.ok(!JSON.stringify(live).includes("leakme"));
  const status = await runner.status({ taskId: started.taskId });
  assert.equal(status.session_url, started.session_url);
  assert.equal((await runner.status({})).tasks[0].session_id, SID);
  broker.finish();
  await settle();
  // Finished: served from disk, no live process or in-memory transcript.
  assert.equal(runner.transcripts.size, 0);
  const fresh = runnerFixture(viewerBroker(), { stateDir: path.join(reposRoot, ".saarius-shed") }).runner;
  const stored = await fresh.viewSession(SID);
  assert.equal(stored.live, false);
  assert.equal(stored.task.status, "pr_opened");
  assert.equal(stored.task.prUrl, "https://github.com/saari-co/site/pull/7");
  assert.equal(stored.entries.length, 2);
  assert.equal(stored.harness, "antigravity");
  assert.match(stored.result, /Changed README/);
  assert.ok(!JSON.stringify(stored).includes("AKIAIOSFODNN7EXAMPLE"));
  assert.ok(!JSON.stringify(stored).includes("leakme"));
  const files = readdirSync(path.join(reposRoot, ".saarius-shed", "sessions"));
  assert.deepEqual(files, [`${SID}.json`]);
  const storedRaw = JSON.parse(readFileSync(path.join(reposRoot, ".saarius-shed", "sessions", `${SID}.json`), "utf8"));
  assert.equal(storedRaw.harness, "antigravity");
  // task record never carries the prompt
  assert.ok(!readFileSync(path.join(reposRoot, ".saarius-shed", "tasks", `${started.taskId}.json`), "utf8").includes("README typo"));
  assert.equal(await fresh.viewSession("../../etc/passwd"), null);
  assert.equal(await fresh.viewSession("11111111-2222-4333-8444-555555555555"), null);
});

test("a stalled session/new returns without session fields; status exposes them later", async () => {
  const broker = viewerBroker({ delegateDelayMs: 150 });
  const { runner } = runnerFixture(broker, { sessionWaitMs: 30 });
  await runner.init();
  const first = await runner.runTask(RUN, {});
  assert.equal(first.status, "starting");
  assert.equal(first.sessionPending, true);
  assert.equal(first.session_id, undefined);
  await new Promise((r) => setTimeout(r, 250));
  const later = await runner.status({ taskId: first.taskId });
  assert.equal(later.status, "running");
  assert.equal(later.session_id, SID);
  assert.equal(later.session_url, `https://shed.sm0ky.dev/s/${SID}`);
  broker.finish();
  await settle();
});

test("session base URL is configurable and must be https", () => {
  assert.throws(() => new ShedTaskRunner({ broker: {}, env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: "o", SAARIUS_ACP_REMOTE_REPOS_ROOT: "/tmp", SAARIUS_ACP_SESSION_BASE_URL: "http://evil.example" } }), /https/);
  const r = new ShedTaskRunner({ broker: {}, env: { SAARIUS_ACP_REMOTE_REPO_OWNERS: "o", SAARIUS_ACP_REMOTE_REPOS_ROOT: "/tmp", SAARIUS_ACP_SESSION_BASE_URL: "https://view.example/" } });
  assert.equal(r.sessionBaseUrl, "https://view.example");
});

// ---------- viewer auth ----------
test("viewer config is off unless set, and validates AUD + emails", () => {
  assert.equal(resolveViewerConfig({}), null);
  assert.throws(() => resolveViewerConfig({ SAARIUS_ACP_VIEWER_EMAILS: EMAIL }), /AUD/);
  assert.throws(() => resolveViewerConfig({ SAARIUS_ACP_VIEWER_ACCESS_AUD: VIEW_AUD }), /EMAILS/);
  assert.deepEqual([...resolveViewerConfig(ENV).emails], [EMAIL]);
});

test("viewer auth admits only the allowlisted human on the viewer AUD; MCP auth refuses viewer tokens", async () => {
  const viewer = createViewerAuthenticator({ env: ENV, fetchJwks });
  const mcp = createAccessAuthenticator({ env: ENV, fetchJwks });
  assert.deepEqual(await viewer({ "cf-access-jwt-assertion": humanJwt() }), { label: "viewer", email: EMAIL });
  await assert.rejects(viewer({ "cf-access-jwt-assertion": humanJwt("someone@else.com") }), /not accepted/);
  await assert.rejects(viewer({ "cf-access-jwt-assertion": humanJwt(EMAIL, MCP_AUD) }), /not accepted/);
  await assert.rejects(viewer({ "cf-access-jwt-assertion": serviceJwt(VIEW_AUD) }), /not accepted/);
  await assert.rejects(viewer({}), /not accepted/);
  await assert.rejects(mcp({ "cf-access-jwt-assertion": humanJwt(EMAIL, MCP_AUD) }), /not accepted/);
  assert.equal(createViewerAuthenticator({ env: { ...ENV, SAARIUS_ACP_VIEWER_ACCESS_AUD: "", SAARIUS_ACP_VIEWER_EMAILS: "" } }), null);
});

// ---------- HTTP route ----------
function get(port, pathname, { method = "GET", headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const req = request({ host: "127.0.0.1", port, path: pathname, method, headers: { host: `127.0.0.1:${port}`, ...headers } }, (res) => {
      let body = "";
      res.on("data", (c) => { body += c; });
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body }));
    });
    req.on("error", reject);
    req.end();
  });
}

test("GET /s/<id> and /s/<id>.json: auth, noindex, no-store, CSP, read-only, strict ids", async () => {
  const view = buildView({ sessionId: SID, task: { taskId: "shed-1", status: "running", repo: "saari-co/site", requestedBy: "grok-bot" }, transcript: createTranscript({ prompt: "p" }) });
  const lookups = [];
  const host = await startRemoteShedHost({
    env: { SAARIUS_ACP_HTTP_PORT: "0" },
    bridge: "test",
    log: () => {},
    authenticate: createAccessAuthenticator({ env: ENV, fetchJwks }),
    viewerAuthenticate: createViewerAuthenticator({ env: ENV, fetchJwks }),
    viewSession: async (id) => { lookups.push(id); return id === SID ? view : null; },
    createServer: () => { throw new Error("viewer must not create MCP servers"); },
  });
  try {
    const auth = { "cf-access-jwt-assertion": humanJwt() };
    const html = await get(host.port, `/s/${SID}`, { headers: auth });
    assert.equal(html.status, 200);
    assert.match(html.headers["content-type"], /text\/html/);
    assert.match(html.headers["x-robots-tag"], /noindex/);
    assert.match(html.headers["cache-control"], /no-store/);
    assert.match(html.headers["cache-control"], /private/);
    assert.match(html.headers["content-security-policy"], /default-src 'none'/);
    assert.match(html.body, /<meta name="robots" content="noindex/);
    assert.match(html.body, /saari-co\/site/);
    const json = await get(host.port, `/s/${SID}.json`, { headers: auth });
    assert.equal(json.status, 200);
    assert.equal(JSON.parse(json.body).task.taskId, "shed-1");
    assert.match(json.headers["x-robots-tag"], /noindex/);
    assert.equal((await get(host.port, `/s/${SID}`)).status, 401);
    assert.equal((await get(host.port, `/s/${SID}`, { headers: { "cf-access-jwt-assertion": serviceJwt() } })).status, 401);
    assert.equal((await get(host.port, `/s/${SID}`, { method: "POST", headers: auth })).status, 405);
    assert.equal((await get(host.port, `/s/${SID}`, { method: "DELETE", headers: auth })).status, 405);
    for (const bad of ["/s/..%2f..%2fetc%2fpasswd", "/s/not-a-uuid", `/s/${SID.toUpperCase()}`, `/s/${SID}/cancel`, `/s/${SID}.html`, "/s/", `/s/${SID}?x=1`]) {
      const res = await get(host.port, bad, { headers: auth });
      assert.ok([400, 404].includes(res.status), `${bad} -> ${res.status}`);
      assert.match(res.headers["x-robots-tag"], /noindex/);
    }
    assert.equal((await get(host.port, "/s/11111111-2222-4333-8444-555555555555", { headers: auth })).status, 404);
    assert.deepEqual([...new Set(lookups)], [SID, "11111111-2222-4333-8444-555555555555"]);
    // /mcp still refuses a viewer login.
    assert.equal((await get(host.port, "/mcp", { method: "POST", headers: auth })).status, 401);
  } finally {
    await host.close();
  }
});

test("viewer is 404 when not configured", async () => {
  const host = await startRemoteShedHost({
    env: { SAARIUS_ACP_HTTP_PORT: "0" },
    bridge: "test",
    log: () => {},
    authenticate: async () => ({ label: "x", clientId: "x" }),
    createServer: () => { throw new Error("no"); },
  });
  try {
    assert.equal((await get(host.port, `/s/${SID}`)).status, 404);
  } finally {
    await host.close();
  }
});
