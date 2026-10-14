import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { startRemoteShedHost } from "../http-host.mjs";
import {
  buildCardModel,
  CARD_ASSET_FILES,
  HARNESS_CARD_TABLE,
  renderCardHtml,
  resolveHarnessCardEntry,
} from "../shed-card.mjs";
import { appendEvent, buildView, createTranscript } from "../shed-sessions.mjs";

const SESSION_ID = "0f8fad5b-d9cb-469f-a165-70867728950e";
const UNKNOWN_SESSION_ID = "22222222-3333-4444-8555-666666666666";
const PNG_MAGIC = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function requestRaw(port, pathname, { method = "GET", headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      host: "127.0.0.1",
      port,
      path: pathname,
      method,
      headers: { host: `127.0.0.1:${port}`, ...headers },
    }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const buffer = Buffer.concat(chunks);
        resolve({
          status: res.statusCode,
          headers: res.headers,
          buffer,
          body: buffer.toString("utf8"),
        });
      });
    });
    req.on("error", reject);
    req.end();
  });
}

test("harness card data table maps antigravity, muse, and unknown fallback to static logos", () => {
  assert.deepEqual(Object.keys(HARNESS_CARD_TABLE), ["antigravity", "muse", "generic"]);
  assert.deepEqual(resolveHarnessCardEntry("antigravity"), {
    harness: "antigravity",
    displayName: "Antigravity",
    logoAsset: "antigravity.png",
    logoPath: "/c/assets/antigravity.png",
  });
  assert.deepEqual(resolveHarnessCardEntry("MUSE"), {
    harness: "muse",
    displayName: "Muse",
    logoAsset: "muse.png",
    logoPath: "/c/assets/muse.png",
  });
  assert.deepEqual(resolveHarnessCardEntry("unknown"), {
    harness: "generic",
    displayName: "Unknown",
    logoAsset: "generic.png",
    logoPath: "/c/assets/generic.png",
  });
  assert.deepEqual(resolveHarnessCardEntry(null), HARNESS_CARD_TABLE.generic);
  assert.deepEqual(Object.keys(CARD_ASSET_FILES).sort(), ["antigravity.png", "generic.png", "muse.png"]);
});

test("card HTML renders exact title, description, logo, noindex, and redirect per harness", () => {
  const agHtml = renderCardHtml(SESSION_ID, {
    harness: "antigravity",
    task: {
      repo: "saari-co/site",
      harness: "antigravity",
      model: "gemini-4-argon-medium",
    },
  });
  assert.match(agHtml, /<meta property="og:title" content="saari-co\/site — Antigravity">/);
  assert.match(agHtml, /<meta name="twitter:title" content="saari-co\/site — Antigravity">/);
  assert.match(agHtml, /<meta property="og:description" content="harness: Antigravity, model: gemini-4-argon-medium">/);
  assert.match(agHtml, /<meta property="og:image" content="\/c\/assets\/antigravity\.png">/);
  assert.match(agHtml, /<meta name="robots" content="noindex">/);
  assert.match(agHtml, new RegExp(`<meta http-equiv="refresh" content="0; url=/s/${SESSION_ID}">`));
  assert.match(agHtml, new RegExp(`<a href="/s/${SESSION_ID}">/s/${SESSION_ID}</a>`));

  const museHtml = renderCardHtml(SESSION_ID, {
    harness: "muse",
    task: {
      repo: "saariuslystoned/SaariusSkills",
      harness: "muse",
      model: "claude-opus-4-6",
    },
  });
  assert.match(museHtml, /<meta property="og:title" content="saariuslystoned\/SaariusSkills — Muse">/);
  assert.match(museHtml, /<meta name="twitter:title" content="saariuslystoned\/SaariusSkills — Muse">/);
  assert.match(museHtml, /<meta property="og:description" content="harness: Muse, model: claude-opus-4-6">/);
  assert.match(museHtml, /<meta property="og:image" content="\/c\/assets\/muse\.png">/);
});

test("card uses 'unconfirmed' model label when model is missing, empty, or unknown", () => {
  for (const modelValue of [undefined, null, "", "   ", "unknown", "UNKNOWN"]) {
    const html = renderCardHtml(SESSION_ID, {
      harness: "antigravity",
      task: {
        repo: "saari-co/site",
        harness: "antigravity",
        model: modelValue,
      },
    });
    assert.match(html, /<meta property="og:description" content="harness: Antigravity, model: unconfirmed">/);
  }
});

test("card never leaks prompt, transcript, summary, branch, diff, task title, or requestedBy/caller markers", () => {
  const transcript = createTranscript({ prompt: "LEAKMARKER_PROMPT fix secret bug" });
  appendEvent(transcript, {
    type: "text_delta",
    text: "LEAKMARKER_TRANSCRIPT some agent output",
  });
  appendEvent(transcript, {
    type: "tool_call",
    toolCallId: "tc-1",
    title: "Edit file",
    kind: "edit",
    status: "completed",
    text: "LEAKMARKER_DIFF LEAKMARKER_TOOL_OUTPUT",
  });

  const view = buildView({
    sessionId: SESSION_ID,
    harness: "antigravity",
    task: {
      taskId: "shed-20260420T010203-abcdef",
      repo: "saari-co/site",
      baseBranch: "LEAKMARKER_BASE_BRANCH",
      branch: "shed/LEAKMARKER_BRANCH",
      requestedBy: "LEAKMARKER_REQUESTED_BY",
      caller: "LEAKMARKER_CALLER",
      title: "LEAKMARKER_TITLE",
      harness: "antigravity",
      model: "gemini-4-argon-medium",
      status: "pr_opened",
      prUrl: "https://github.com/saari-co/site/pull/999?marker=LEAKMARKER_PRURL",
      headSha: "deadbeef",
      summary: "LEAKMARKER_SUMMARY completed changes",
      error: "LEAKMARKER_ERROR",
    },
    transcript,
    result: "LEAKMARKER_SUMMARY completed changes",
  });
  view.harness = "antigravity";

  // Sanity-check that the underlying session view actually has the markers
  const fullViewJson = JSON.stringify(view);
  assert.match(fullViewJson, /LEAKMARKER_PROMPT/);
  assert.match(fullViewJson, /LEAKMARKER_TRANSCRIPT/);
  assert.match(fullViewJson, /LEAKMARKER_SUMMARY/);
  assert.match(fullViewJson, /LEAKMARKER_BRANCH/);
  assert.match(fullViewJson, /LEAKMARKER_REQUESTED_BY/);

  const cardHtml = renderCardHtml(SESSION_ID, view);
  for (const marker of [
    "LEAKMARKER_PROMPT",
    "LEAKMARKER_TRANSCRIPT",
    "LEAKMARKER_SUMMARY",
    "LEAKMARKER_BRANCH",
    "LEAKMARKER_BASE_BRANCH",
    "LEAKMARKER_REQUESTED_BY",
    "LEAKMARKER_CALLER",
    "LEAKMARKER_TITLE",
    "LEAKMARKER_DIFF",
    "LEAKMARKER_TOOL_OUTPUT",
    "LEAKMARKER_PRURL",
    "LEAKMARKER_ERROR",
    "shed-20260420T010203-abcdef",
  ]) {
    assert.equal(cardHtml.includes(marker), false, `card HTML must not contain ${marker}`);
  }
  assert.match(cardHtml, /saari-co\/site — Antigravity/);
  assert.match(cardHtml, /harness: Antigravity, model: gemini-4-argon-medium/);
});

test("card escapes HTML and rejects unsafe repo or model strings without reflecting raw input", () => {
  const maliciousView = {
    harness: "<script>alert(1)</script>",
    task: {
      repo: "<img src=x onerror=alert(1)>",
      model: '"><script>alert(2)</script>',
    },
  };
  const html = renderCardHtml(SESSION_ID, maliciousView);
  assert.equal(html.includes("<script>"), false);
  assert.equal(html.includes("<img"), false);
  assert.equal(html.includes("onerror"), false);
  assert.match(html, /<meta property="og:title" content="Shed — Unknown">/);
  assert.match(html, /<meta property="og:description" content="harness: Unknown, model: unconfirmed">/);
  assert.match(html, /<meta property="og:image" content="\/c\/assets\/generic\.png">/);

  assert.throws(() => buildCardModel("not-a-uuid", {}), /Invalid sessionId/);
});

test("GET /c/<sessionId> and /c/assets/<harness>.png serve cards, assets, validate IDs, and avoid existence oracles", async () => {
  const views = new Map([
    [
      SESSION_ID,
      {
        sessionId: SESSION_ID,
        harness: "muse",
        task: {
          repo: "saari-co/site",
          harness: "muse",
          model: undefined,
          prompt: "LEAKMARKER_PROMPT",
          requestedBy: "LEAKMARKER_REQUESTED_BY",
          branch: "shed/LEAKMARKER_BRANCH",
          summary: "LEAKMARKER_SUMMARY",
        },
        entries: [{ kind: "agent", text: "LEAKMARKER_TRANSCRIPT" }],
      },
    ],
  ]);

  const host = await startRemoteShedHost({
    env: { SAARIUS_ACP_HTTP_PORT: "0" },
    authenticate: async () => {
      throw Object.assign(new Error("mcp auth should not be called for /c/*"), { code: "DENIED" });
    },
    viewerAuthenticate: async () => {
      throw Object.assign(new Error("viewer auth should not be called for /c/*"), { code: "DENIED" });
    },
    viewSession: async (id) => views.get(id) ?? null,
    createServer: () => new McpServer({ name: "test", version: "0.0.0" }),
    log: () => {},
  });

  try {
    // 1. Known session renders harness card with unconfirmed model and no sensitive markers
    const known = await requestRaw(host.port, `/c/${SESSION_ID}`);
    assert.equal(known.status, 200);
    assert.match(known.headers["content-type"], /^text\/html/);
    assert.match(known.headers["x-robots-tag"], /noindex/);
    assert.match(known.body, /<meta name="robots" content="noindex">/);
    assert.match(known.body, /<meta property="og:title" content="saari-co\/site — Muse">/);
    assert.match(known.body, /<meta name="twitter:title" content="saari-co\/site — Muse">/);
    assert.match(known.body, /<meta property="og:description" content="harness: Muse, model: unconfirmed">/);
    assert.match(known.body, /<meta property="og:image" content="\/c\/assets\/muse\.png">/);
    assert.match(known.body, new RegExp(`<meta http-equiv="refresh" content="0; url=/s/${SESSION_ID}">`));
    assert.match(known.body, new RegExp(`<a href="/s/${SESSION_ID}">/s/${SESSION_ID}</a>`));
    for (const marker of ["LEAKMARKER_PROMPT", "LEAKMARKER_TRANSCRIPT", "LEAKMARKER_REQUESTED_BY", "LEAKMARKER_BRANCH", "LEAKMARKER_SUMMARY"]) {
      assert.equal(known.body.includes(marker), false);
    }

    // 2. Unknown but valid UUID returns 200 generic fallback card (no existence oracle vs unconfirmed session)
    const unknownValid = await requestRaw(host.port, `/c/${UNKNOWN_SESSION_ID}`);
    assert.equal(unknownValid.status, 200);
    assert.match(unknownValid.body, /<meta property="og:title" content="Shed — Unknown">/);
    assert.match(unknownValid.body, /<meta name="twitter:title" content="Shed — Unknown">/);
    assert.match(unknownValid.body, /<meta property="og:description" content="harness: Unknown, model: unconfirmed">/);
    assert.match(unknownValid.body, /<meta property="og:image" content="\/c\/assets\/generic\.png">/);
    assert.match(unknownValid.body, new RegExp(`<meta http-equiv="refresh" content="0; url=/s/${UNKNOWN_SESSION_ID}">`));
    assert.match(unknownValid.body, new RegExp(`<a href="/s/${UNKNOWN_SESSION_ID}">/s/${UNKNOWN_SESSION_ID}</a>`));

    // 3. Malformed IDs return constant 404 without reflecting input
    for (const badPath of [
      "/c",
      "/c/",
      "/c/not-a-uuid",
      `/c/${SESSION_ID.toUpperCase()}`,
      `/c/${SESSION_ID}.json`,
      `/c/${SESSION_ID}/extra`,
      `/c/${SESSION_ID}?leak=1`,
      "/c/%3Cscript%3Ealert(1)%3C/script%3E",
      "/c/..%2f..%2fetc%2fpasswd",
    ]) {
      const res = await requestRaw(host.port, badPath);
      assert.equal(res.status, 404, `expected 404 for ${badPath}`);
      assert.equal(res.body, "not found\n");
    }

    // 4. Static per-harness PNG logos served from /c/assets/<harness>.png
    for (const logo of ["antigravity.png", "muse.png", "generic.png"]) {
      const asset = await requestRaw(host.port, `/c/assets/${logo}`);
      assert.equal(asset.status, 200, `expected 200 for /c/assets/${logo}`);
      assert.equal(asset.headers["content-type"], "image/png");
      assert.equal(asset.headers["x-content-type-options"], "nosniff");
      assert.ok(asset.buffer.length > PNG_MAGIC.length);
      assert.deepEqual(asset.buffer.subarray(0, PNG_MAGIC.length), PNG_MAGIC);
    }

    // Unknown or traversal asset paths return 404
    for (const badAsset of ["/c/assets/", "/c/assets/other.png", "/c/assets/../shed-card.mjs"]) {
      const res = await requestRaw(host.port, badAsset);
      assert.equal(res.status, 404, `expected 404 for ${badAsset}`);
      assert.equal(res.body, "not found\n");
    }

    // 5. Non-GET/HEAD methods are rejected with 405
    const postRes = await requestRaw(host.port, `/c/${SESSION_ID}`, { method: "POST" });
    assert.equal(postRes.status, 405);
  } finally {
    await host.close();
  }
});
