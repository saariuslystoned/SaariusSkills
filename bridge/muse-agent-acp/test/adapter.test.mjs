// Integration test: real adapter process <-> fake MSP host, driven by a raw
// ACP JSONL client. Asserts the wire contract an ACP client (acpx) observes.

import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const serverPath = path.join(here, "..", "server.mjs");
const fakeMsp = path.join(here, "fake-msp.mjs");

function startAdapter() {
  const binDir = mkdtempSync(path.join(tmpdir(), "muse-agent-acp-test-"));
  const fakeMuse = path.join(binDir, "muse");
  writeFileSync(fakeMuse, `#!/bin/sh\nexec node ${fakeMsp} "$@"\n`);
  chmodSync(fakeMuse, 0o755);
  const proc = spawn(process.execPath, [serverPath], {
    env: { ...process.env, MUSE_EXECUTABLE: fakeMuse },
    stdio: ["pipe", "pipe", "pipe"],
  });
  let buf = "";
  const waiters = new Map();
  const updates = [];
  const permissionRequests = [];
  proc.stdout.setEncoding("utf8");
  proc.stdout.on("data", (chunk) => {
    buf += chunk;
    let idx;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      const msg = JSON.parse(line);
      if (msg.method === "session/update") updates.push(msg.params);
      else if (msg.method === "session/request_permission") {
        permissionRequests.push(msg);
        const first = msg.params.options[0];
        proc.stdin.write(
          JSON.stringify({
            jsonrpc: "2.0",
            id: msg.id,
            result: { outcome: { outcome: "selected", optionId: first.optionId } },
          }) + "\n",
        );
      } else if (msg.id !== undefined && waiters.has(msg.id)) {
        waiters.get(msg.id)(msg);
        waiters.delete(msg.id);
      }
    }
  });
  let nextId = 1;
  const call = (method, params) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      const timer = setTimeout(() => reject(new Error(`ACP call timed out: ${method}`)), 15000);
      waiters.set(id, (msg) => {
        clearTimeout(timer);
        if (msg.error) reject(new Error(`${method} error: ${JSON.stringify(msg.error)}`));
        else resolve(msg.result);
      });
      proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
    });
  return { proc, call, updates, permissionRequests };
}

test("ACP initialize/new/prompt round-trips through MSP with streamed text", async () => {
  const { proc, call, updates } = startAdapter();
  try {
    const init = await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    assert.equal(init.agentInfo.name, "muse-agent-acp");
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    assert.match(session.sessionId, /^fake-session-/);
    assert.equal(session.models.currentModelId, "fake-model-1");
    assert.equal(session.configOptions[0].id, "reasoning_effort");
    const prompt = await call("session/prompt", {
      sessionId: session.sessionId,
      prompt: [{ type: "text", text: "hello adapter" }],
    });
    assert.equal(prompt.stopReason, "end_turn");
    const chunks = updates.filter((u) => u.update.sessionUpdate === "agent_message_chunk");
    assert.equal(chunks.map((u) => u.update.content.text).join(""), "echo: hello adapter");
  } finally {
    proc.kill("SIGTERM");
  }
});

test("session/close is advertised and forgets the session", async () => {
  const { proc, call } = startAdapter();
  try {
    const init = await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    assert.deepEqual(init.agentCapabilities.sessionCapabilities, { close: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const closed = await call("session/close", { sessionId: session.sessionId });
    assert.deepEqual(closed, {});
    await assert.rejects(
      () => call("session/prompt", { sessionId: session.sessionId, prompt: [{ type: "text", text: "gone" }] }),
      /unknown session/,
    );
  } finally {
    proc.kill("SIGTERM");
  }
});

test("MSP approval becomes ACP request_permission and the decision returns", async () => {
  const { proc, call, permissionRequests } = startAdapter();
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const prompt = await call("session/prompt", {
      sessionId: session.sessionId,
      prompt: [{ type: "text", text: "please run this NEEDS_APPROVAL" }],
    });
    assert.equal(prompt.stopReason, "end_turn");
    assert.equal(permissionRequests.length, 1);
    const kinds = permissionRequests[0].params.options.map((o) => o.kind);
    assert.deepEqual(kinds, ["allow_once", "reject_once"]);
  } finally {
    proc.kill("SIGTERM");
  }
});

test("failed MSP terminal is reported with error stopReason instead of end_turn", async () => {
  const { proc, call } = startAdapter();
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const prompt = await call("session/prompt", {
      sessionId: session.sessionId,
      prompt: [{ type: "text", text: "this FAILS_TURN please" }],
    });
    assert.equal(prompt.stopReason, "error");
    assert.notEqual(prompt.stopReason, "end_turn");
  } finally {
    proc.kill("SIGTERM");
  }
});
