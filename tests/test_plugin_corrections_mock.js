#!/usr/bin/env node
/**
 * Mock verification harness for bundled EmDash plugin corrections.
 *
 * Verifies:
 * 1. Sandboxed route handlers: (routeCtx, ctx) vs flawed single-arg async (ctx) =>.
 * 2. Native route handlers: combined async (ctx) => vs flawed two-arg under native dispatcher.
 * 3. Email deliver hook: required 'from' sender configuration, payload validation,
 *    HTTP 200 success, and sanitized HTTP 401/500 errors without leaking secrets.
 *
 * Note: Small local mock only. Does not claim installed EmDash runtime or live email proof.
 * Uses operator-configured verified sender; never inserts real identity.
 */

import test from "node:test";
import assert from "node:assert/strict";

// ---------------------------------------------------------------------------
// 1. Sandboxed route handler tests (independently labeled)
// ---------------------------------------------------------------------------

test("sandboxed: flawed single-argument form handler throws TypeError on missing kv under sandboxed dispatcher", async () => {
  // Upstream flawed sandboxed pattern: declares async (ctx) =>, but sandboxed dispatcher passes (routeCtx, ctx)
  const flawedSandboxedHandler = async (ctx) => {
    const interaction = ctx.input;
    if (interaction.type === "form_submit") {
      await ctx.kv.set("settings", interaction.values);
    }
  };

  const routeCtx = {
    input: { type: "form_submit", action_id: "save", values: { api_url: "https://example.com" } },
    request: { url: "https://localhost/api/admin", method: "POST", headers: {} },
  };
  const pluginCtx = {
    kv: {
      data: new Map(),
      async set(k, v) { this.data.set(k, v); },
    },
  };

  // Sandboxed route dispatcher calls handler(routeCtx, pluginCtx)
  await assert.rejects(
    async () => {
      await flawedSandboxedHandler(routeCtx, pluginCtx);
    },
    {
      name: "TypeError",
    },
    "single-arg handler binds routeCtx to ctx, so ctx.kv is undefined and must throw TypeError"
  );
});

test("sandboxed: corrected two-argument form handler successfully accesses routeCtx.input and ctx.kv under sandboxed dispatcher", async () => {
  const kvStore = new Map();
  const correctedSandboxedHandler = async (routeCtx, ctx) => {
    const interaction = routeCtx.input;
    if (interaction.type === "form_submit" && interaction.action_id === "save") {
      await ctx.kv.set("settings", interaction.values);
      return {
        blocks: [],
        toast: { message: "Settings saved", type: "success" },
      };
    }
  };

  const routeCtx = {
    input: { type: "form_submit", action_id: "save", values: { api_url: "https://example.com", enabled: true } },
    request: { url: "https://localhost/api/admin", method: "POST", headers: {} },
  };
  const pluginCtx = {
    kv: {
      async set(k, v) { kvStore.set(k, v); },
    },
  };

  // Sandboxed dispatcher calls handler(routeCtx, pluginCtx)
  const result = await correctedSandboxedHandler(routeCtx, pluginCtx);
  assert.equal(result.toast.type, "success");
  assert.deepEqual(kvStore.get("settings"), { api_url: "https://example.com", enabled: true });
});

// ---------------------------------------------------------------------------
// 2. Native route handler tests (independently labeled)
// ---------------------------------------------------------------------------

test("native: dynamic optionsRoute handler succeeds with single combined context under native dispatcher", async () => {
  // Native routes receive one combined context: async (ctx) =>
  const nativeOptionsHandler = async (ctx) => {
    const _input = ctx.input;
    const result = await ctx.storage.cards.query({ limit: 100 });
    return { items: result.items.map((c) => ({ id: c.id, name: c.data.title })) };
  };

  const combinedCtx = {
    input: {},
    request: new Request("https://localhost/api/cards/list"),
    storage: {
      cards: {
        async query() { return { items: [{ id: "c1", data: { title: "Card 1" } }] }; },
      },
    },
  };

  // Native route dispatcher invokes handler with one combined context argument: handler(ctx)
  const res = await nativeOptionsHandler(combinedCtx);
  assert.deepEqual(res, { items: [{ id: "c1", name: "Card 1" }] });
});

test("native: wrong two-argument signature fails under native dispatcher because ctx is undefined", async () => {
  // Mistakenly applying sandboxed (routeCtx, ctx) signature to a native route
  const wrongTwoArgNativeHandler = async (routeCtx, ctx) => {
    // Under native dispatcher, only combinedCtx is passed as 1st argument (routeCtx).
    // ctx (2nd argument) is undefined. Accessing ctx.storage throws TypeError.
    const result = await ctx.storage.cards.query({ limit: 100 });
    return { items: result.items.map((c) => ({ id: c.id, name: c.data.title })) };
  };

  const combinedCtx = {
    input: {},
    request: new Request("https://localhost/api/cards/list"),
    storage: {
      cards: {
        async query() { return { items: [{ id: "c1", data: { title: "Card 1" } }] }; },
      },
    },
  };

  // Native dispatcher calls handler(combinedCtx)
  await assert.rejects(
    async () => {
      await wrongTwoArgNativeHandler(combinedCtx);
    },
    {
      name: "TypeError",
    },
    "two-arg handler under native dispatcher leaves 2nd arg undefined, so ctx.storage throws TypeError"
  );
});

// ---------------------------------------------------------------------------
// 3. Email transport delivery hook tests
// ---------------------------------------------------------------------------

const SECRET_API_KEY = "re_secret_live_key_xyz123456789";
const SENDER_EMAIL = "noreply@example.com"; // Verified domain operator configuration (no real identity)
const RECIPIENT_EMAIL = "customer@example.com";
const PROVIDER_ERROR_BODY = '{"statusCode":401,"message":"Missing API key credentials"}';

function makeMockDeliverHandler(mockFetch) {
  return async ({ message }, ctx) => {
    const apiKey = await ctx.settings.get("apiKey");
    const from = await ctx.settings.get("from");
    if (!from) {
      throw new Error("Email delivery failed: missing configured 'from' sender address");
    }

    const response = await ctx.http.fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: message.to,
        cc: message.cc,
        reply_to: message.replyTo,
        subject: message.subject,
        text: message.text,
      }),
    });

    if (!response.ok) {
      throw new Error(`Email delivery failed with HTTP status ${response.status}`);
    }
  };
}

function createMockSettings(settingsMap = {}) {
  return {
    async get(key) {
      return settingsMap[key];
    },
  };
}

test("email:deliver: throws sanitized configuration error when 'from' sender setting is missing", async () => {
  let fetchCalled = false;
  const mockFetch = async () => {
    fetchCalled = true;
    return new Response(JSON.stringify({ id: "unreachable" }), { status: 200 });
  };

  const handler = makeMockDeliverHandler(mockFetch);
  const pluginCtx = {
    settings: createMockSettings({ apiKey: SECRET_API_KEY /* 'from' omitted */ }),
    http: { fetch: mockFetch },
  };

  await assert.rejects(
    async () => {
      await handler({ message: { to: RECIPIENT_EMAIL, subject: "Test", text: "Hello" } }, pluginCtx);
    },
    {
      name: "Error",
      message: "Email delivery failed: missing configured 'from' sender address",
    }
  );
  assert.equal(fetchCalled, false, "Must fail before sending network request when 'from' is missing");
});

test("email:deliver: validates 'from' and required fields, and resolves cleanly on HTTP 200 with settings keyed by field", async () => {
  let validatedRequestBody = null;
  const mockFetch = async (url, options) => {
    const body = JSON.parse(options.body);
    validatedRequestBody = body;

    // Resend requires from, to, and at least subject or text/html
    if (!body.from || !body.to || !body.subject) {
      return new Response(JSON.stringify({ message: "Missing required fields" }), { status: 422 });
    }
    return new Response(JSON.stringify({ id: "email_ok_123" }), { status: 200 });
  };

  const handler = makeMockDeliverHandler(mockFetch);
  const pluginCtx = {
    settings: createMockSettings({
      apiKey: SECRET_API_KEY,
      from: SENDER_EMAIL,
    }),
    http: { fetch: mockFetch },
  };

  await assert.doesNotReject(async () => {
    await handler({ message: { to: RECIPIENT_EMAIL, subject: "Test Subject", text: "Hello" } }, pluginCtx);
  });
  assert.ok(validatedRequestBody, "Fetch was called");
  assert.equal(validatedRequestBody.from, SENDER_EMAIL, "Payload must include verified from sender");
  assert.equal(validatedRequestBody.to, RECIPIENT_EMAIL);
  assert.equal(validatedRequestBody.subject, "Test Subject");
});

test("email:deliver: throws sanitized error on HTTP 401 without leaking secrets or addresses", async () => {
  const mockFetch = async () => {
    return new Response(PROVIDER_ERROR_BODY, { status: 401, statusText: "Unauthorized" });
  };

  const handler = makeMockDeliverHandler(mockFetch);
  const pluginCtx = {
    settings: createMockSettings({
      apiKey: SECRET_API_KEY,
      from: SENDER_EMAIL,
    }),
    http: { fetch: mockFetch },
  };

  let caughtError;
  try {
    await handler({ message: { to: RECIPIENT_EMAIL, subject: "Test", text: "Hello" } }, pluginCtx);
  } catch (err) {
    caughtError = err;
  }

  assert.ok(caughtError, "Must throw on HTTP 401");
  assert.equal(caughtError.message, "Email delivery failed with HTTP status 401");
  // Security verification: NO token, recipient, sender, or provider body leaked in error
  assert.ok(!caughtError.message.includes(SECRET_API_KEY), "Must not leak API key");
  assert.ok(!caughtError.message.includes(RECIPIENT_EMAIL), "Must not leak recipient email");
  assert.ok(!caughtError.message.includes(SENDER_EMAIL), "Must not leak sender email");
  assert.ok(!caughtError.message.includes("Missing API key credentials"), "Must not leak provider body");
});

test("email:deliver: throws sanitized error on HTTP 500 without leaking secrets or addresses", async () => {
  const mockFetch = async () => {
    return new Response('{"error":"Internal Server Failure"}', { status: 500, statusText: "Internal Server Error" });
  };

  const handler = makeMockDeliverHandler(mockFetch);
  const pluginCtx = {
    settings: createMockSettings({
      apiKey: SECRET_API_KEY,
      from: SENDER_EMAIL,
    }),
    http: { fetch: mockFetch },
  };

  let caughtError;
  try {
    await handler({ message: { to: RECIPIENT_EMAIL, subject: "Test", text: "Hello" } }, pluginCtx);
  } catch (err) {
    caughtError = err;
  }

  assert.ok(caughtError, "Must throw on HTTP 500");
  assert.equal(caughtError.message, "Email delivery failed with HTTP status 500");
  assert.ok(!caughtError.message.includes(SECRET_API_KEY), "Must not leak API key");
  assert.ok(!caughtError.message.includes(RECIPIENT_EMAIL), "Must not leak recipient email");
  assert.ok(!caughtError.message.includes(SENDER_EMAIL), "Must not leak sender email");
  assert.ok(!caughtError.message.includes("Internal Server Failure"), "Must not leak provider body");
});


// Exercise the actual packaged examples; handwritten models alone cannot catch drift.
import { readFileSync } from "node:fs";

function packagedSnippet(file, heading = "") {
  const source = readFileSync(new URL(`../skills/creating-plugins/references/${file}`, import.meta.url), "utf8");
  const section = heading ? source.slice(source.indexOf(heading)) : source;
  const code = section.match(/```typescript\n([\s\S]*?)```/)[1]
    .replace(/^import type .*;\n/gm, "")
    .replace(/ as BlockInteraction/g, "")
    .replace(/ctx\.http!/g, "ctx.http");
  return Function(`return ({${code}});`)();
}

test("packaged sandboxed example dispatches with separate route and plugin contexts", async () => {
  const example = packagedSnippet("block-kit.md");
  const saved = [];
  const result = await example.routes.admin.handler(
    { input: { type: "form_submit", action_id: "save", values: { enabled: true } } },
    { kv: { set: async (...args) => saved.push(args) } },
  );
  assert.deepEqual(saved, [["settings", { enabled: true }]]);
  assert.equal(result.toast.type, "success");
});

test("packaged email example validates sender and HTTP outcome with sanitized errors", async () => {
  const handler = packagedSnippet("hooks.md", "### `email:deliver`")["email:deliver"].handler;
  const message = { to: "recipient@example.invalid", subject: "test", text: "test" };
  let calls = 0;
  let sender;
  let status = 200;
  const context = {
    settings: { get: async (key) => key === "from" ? sender : "synthetic-key" },
    http: { fetch: async (_url, options) => {
      calls++;
      assert.equal(JSON.parse(options.body).from, sender);
      assert.equal(options.headers["Content-Type"], "application/json");
      return { ok: status === 200, status, text: async () => { throw new Error("provider body must not be read"); } };
    } },
  };
  await assert.rejects(handler({ message }, context), /missing configured sender/);
  assert.equal(calls, 0);
  sender = "sender@example.invalid";
  await handler({ message }, context);
  for (status of [401, 500]) {
    await assert.rejects(handler({ message }, context), (error) => {
      assert.equal(error.message, `Email delivery failed with HTTP status ${status}`);
      return true;
    });
  }
  assert.equal(calls, 3);
});
