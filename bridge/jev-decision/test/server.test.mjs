import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { handle, TOOLS } from "../server.mjs";

const SERVER = fileURLToPath(new URL("../server.mjs", import.meta.url));

test("speaks the MCP handshake and lists both tools", async () => {
  const init = await handle({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26" } });
  assert.equal(init.result.protocolVersion, "2025-03-26");
  assert.deepEqual(init.result.capabilities, { tools: {} });
  assert.equal(await handle({ jsonrpc: "2.0", method: "notifications/initialized" }), null);
  const list = await handle({ jsonrpc: "2.0", id: 2, method: "tools/list" });
  assert.deepEqual(list.result.tools.map((t) => t.name), ["decision_evaluate", "jev_status"]);
  assert.match(TOOLS[0].description, /must not stop the work/);
  const missing = await handle({ jsonrpc: "2.0", id: 3, method: "resources/list" });
  assert.equal(missing.error.code, -32601);
});

test("jev_status never returns the key", async () => {
  const route = async () => ({ kind: "typesafe-hosted", model: "jev-latest", apiKey: "ts_secret", keySource: "keychain", timeoutMs: 15_000 });
  const res = await handle({ jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "jev_status", arguments: {} } }, { route });
  assert.equal(res.result.structuredContent.ready, true);
  assert.ok(!JSON.stringify(res).includes("ts_secret"));
});

function rpc(child) {
  let buffer = "";
  const waiting = new Map();
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const message = JSON.parse(buffer.slice(0, at));
      buffer = buffer.slice(at + 1);
      waiting.get(message.id)?.(message);
    }
  });
  let next = 0;
  return (method, params) => {
    const id = ++next;
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    return new Promise((resolve) => waiting.set(id, resolve));
  };
}

const ask = {
  state: "Leftover box: rename the private helper in src/checkout.ts.",
  questions: { box1: { type: "choice", criteria: { repair: "agent can fix", "owner-gate": "owner must accept", "do-not-patch": "reverses a lock" } } },
};

test("over stdio with no route, decision_evaluate answers unavailable at once", async (t) => {
  const child = spawn(process.execPath, [SERVER], { env: { PATH: process.env.PATH, JEV_DISABLED: "1" } });
  t.after(() => child.kill());
  const call = rpc(child);
  await call("initialize", {});
  const res = await call("tools/call", { name: "decision_evaluate", arguments: ask });
  assert.equal(res.result.isError, false);
  assert.equal(res.result.structuredContent.status, "unavailable");
  assert.equal(res.result.structuredContent.reason, "disabled");
});

test("over stdio against a local Kev server on loopback, the answer round-trips", async (t) => {
  let seen;
  const kev = createServer(async (req, res) => {
    let body = "";
    for await (const chunk of req) body += chunk;
    seen = { url: req.url, auth: req.headers.authorization, body: JSON.parse(body) };
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        model: "kev-latest",
        answers: { box1: { type: "choice", choice: "repair", confidence: 0.9, probabilities: { repair: 0.9, "owner-gate": 0.06, "do-not-patch": 0.04 } } },
        usage: { input_tokens: 40, output_tokens: 1 },
        latency_ms: 12,
      }),
    );
  });
  kev.listen(0, "127.0.0.1");
  await once(kev, "listening");
  t.after(() => kev.close());
  const child = spawn(process.execPath, [SERVER], {
    env: { PATH: process.env.PATH, TYPESAFE_BASE_URL: `http://127.0.0.1:${kev.address().port}` },
  });
  t.after(() => child.kill());
  const call = rpc(child);
  await call("initialize", {});
  const res = await call("tools/call", { name: "decision_evaluate", arguments: ask });
  const outcome = res.result.structuredContent;
  assert.equal(outcome.status, "ok");
  assert.equal(outcome.result.answers.box1.choice, "repair");
  assert.deepEqual(outcome.provenance, { judge: "jev", route: "kev-local", model: "kev-latest" });
  assert.equal(seen.url, "/v1/systemone");
  assert.equal(seen.auth, undefined);
  assert.equal(seen.body.model, "kev-latest");
});
