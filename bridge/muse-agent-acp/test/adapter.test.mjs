// Integration test: real adapter process <-> fake MSP host, driven by a raw
// ACP JSONL client. Asserts the wire contract an ACP client (acpx) observes.

import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chmodSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const serverPath = path.join(here, "..", "server.mjs");
const fakeMsp = path.join(here, "fake-msp.mjs");

function startAdapter(options = {}) {
  const {
    permissionMode = "approve-all",
    env: extraEnv = {},
  } = options;
  const binDir = mkdtempSync(path.join(tmpdir(), "muse-agent-acp-test-"));
  const fakeMuse = path.join(binDir, "muse");
  const decisionsFile = path.join(binDir, "decisions.jsonl");
  const errLogFile = path.join(binDir, "err.log");
  writeFileSync(fakeMuse, `#!/bin/sh\nexec node ${fakeMsp} "$@"\n`);
  chmodSync(fakeMuse, 0o755);
  const proc = spawn(process.execPath, [serverPath], {
    env: {
      ...process.env,
      MUSE_EXECUTABLE: fakeMuse,
      MUSE_FAKE_DECISIONS_FILE: decisionsFile,
      MUSE_AGENT_ACP_ERR_LOG: errLogFile,
      ...extraEnv,
    },
    stdio: ["pipe", "pipe", "pipe"],
  });
  let buf = "";
  let stderrBuf = "";
  const waiters = new Map();
  const updates = [];
  const permissionRequests = [];
  proc.stderr.setEncoding("utf8");
  proc.stderr.on("data", (chunk) => {
    stderrBuf += chunk;
  });
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
        if (typeof permissionMode === "function") {
          permissionMode(msg, proc);
        } else if (permissionMode === "approve-all") {
          const allowOpt =
            msg.params.options.find(
              (o) => o.kind === "allow_once" || o.kind === "allow_always",
            ) ?? msg.params.options[0];
          proc.stdin.write(
            JSON.stringify({
              jsonrpc: "2.0",
              id: msg.id,
              result: { outcome: { outcome: "selected", optionId: allowOpt.optionId } },
            }) + "\n",
          );
        } else if (permissionMode === "fail") {
          proc.stdin.write(
            JSON.stringify({
              jsonrpc: "2.0",
              id: msg.id,
              result: { outcome: { outcome: "cancelled" } },
            }) + "\n",
          );
        } else if (permissionMode === "hang") {
          // Intentionally never respond to session/request_permission.
        }
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
        if (msg.error) {
          const err = new Error(`${method} error: ${JSON.stringify(msg.error)}`);
          err.rpcError = msg.error;
          reject(err);
        } else {
          resolve(msg.result);
        }
      });
      proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
    });
  const readMspEvents = () => {
    if (!existsSync(decisionsFile)) return [];
    return readFileSync(decisionsFile, "utf8")
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  };
  const readErrLog = () => (existsSync(errLogFile) ? readFileSync(errLogFile, "utf8") : "");
  return {
    proc,
    call,
    updates,
    permissionRequests,
    getStderr: () => stderrBuf,
    readMspEvents,
    readErrLog,
  };
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

test("human_pending approval/requested notification is auto-allowed under approve-all mode", async () => {
  const { proc, call, updates, permissionRequests, readMspEvents } = startAdapter({
    permissionMode: "approve-all",
  });
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const prompt = await call("session/prompt", {
      sessionId: session.sessionId,
      prompt: [{ type: "text", text: "run npm test HUMAN_PENDING_APPROVAL" }],
    });
    assert.equal(prompt.stopReason, "end_turn");
    assert.equal(permissionRequests.length, 1);
    const chunks = updates.filter((u) => u.update.sessionUpdate === "agent_message_chunk");
    assert.equal(
      chunks.map((u) => u.update.content.text).join(""),
      "echo: run npm test HUMAN_PENDING_APPROVAL",
    );
    const decides = readMspEvents().filter((e) => e.type === "approval/decide");
    assert.equal(decides.length, 1);
    assert.equal(decides[0].approvalId, "ap-human-1");
    assert.equal(decides[0].choiceId, "allow-once");
  } finally {
    proc.kill("SIGTERM");
  }
});

test("human_pending approval/requested notification fails fast with INPUT_REQUIRED and abort decision under fail mode", async () => {
  const { proc, call, permissionRequests, readMspEvents, getStderr, readErrLog } = startAdapter({
    permissionMode: "fail",
  });
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const startedAt = Date.now();
    await assert.rejects(
      () =>
        call("session/prompt", {
          sessionId: session.sessionId,
          prompt: [{ type: "text", text: "run npm test HUMAN_PENDING_APPROVAL" }],
        }),
      (err) => {
        assert.match(err.message, /INPUT_REQUIRED/);
        assert.equal(err.rpcError?.data?.code, "INPUT_REQUIRED");
        return true;
      },
    );
    assert.ok(Date.now() - startedAt < 5000, "should fail fast without hanging");
    assert.equal(permissionRequests.length, 1);
    const decides = readMspEvents().filter((e) => e.type === "approval/decide");
    assert.equal(decides.length, 1);
    assert.equal(decides[0].approvalId, "ap-human-1");
    assert.equal(decides[0].choiceId, "abort-turn");
    assert.match(getStderr(), /ERROR:/);
    assert.match(readErrLog(), /ERROR:/);
  } finally {
    proc.kill("SIGTERM");
  }
});

test("approval/requested, approval/request, and approval/listPending are deduped by approvalId", async () => {
  const { proc, call, permissionRequests, readMspEvents } = startAdapter({
    permissionMode: "approve-all",
  });
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const prompt = await call("session/prompt", {
      sessionId: session.sessionId,
      prompt: [{ type: "text", text: "run DEDUPE_APPROVAL" }],
    });
    assert.equal(prompt.stopReason, "end_turn");
    assert.equal(permissionRequests.length, 1);
    const decides = readMspEvents().filter((e) => e.type === "approval/decide");
    assert.equal(decides.length, 1);
    assert.equal(decides[0].approvalId, "ap-dedupe-1");
    assert.equal(decides[0].choiceId, "allow-once");
  } finally {
    proc.kill("SIGTERM");
  }
});

test("approval/listPending is polled after turn/start and periodically while turn is open", async () => {
  const { proc, call, permissionRequests, readMspEvents } = startAdapter({
    permissionMode: "approve-all",
    env: {
      MUSE_AGENT_ACP_APPROVAL_POLL_MS: "25",
    },
  });
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const prompt = await call("session/prompt", {
      sessionId: session.sessionId,
      prompt: [{ type: "text", text: "run LIST_PENDING_ONLY DELAYED_LIST_PENDING" }],
    });
    assert.equal(prompt.stopReason, "end_turn");
    assert.equal(permissionRequests.length, 1);
    const events = readMspEvents();
    const listPendingCalls = events.filter((e) => e.type === "approval/listPending");
    assert.ok(listPendingCalls.length >= 2, "expected initial + periodic approval/listPending polls");
    const decides = events.filter((e) => e.type === "approval/decide");
    assert.equal(decides.length, 1);
    assert.equal(decides[0].approvalId, "ap-polled-1");
    assert.equal(decides[0].choiceId, "allow-once");
  } finally {
    proc.kill("SIGTERM");
  }
});

test("handleApproval times out stalled session/request_permission and logs persistent error", async () => {
  const { proc, call, permissionRequests, readMspEvents, getStderr, readErrLog } = startAdapter({
    permissionMode: "hang",
    env: {
      MUSE_AGENT_ACP_PERMISSION_TIMEOUT_MS: "80",
      MUSE_AGENT_ACP_APPROVAL_TIMEOUT_MS: "5000",
    },
  });
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    await assert.rejects(
      () =>
        call("session/prompt", {
          sessionId: session.sessionId,
          prompt: [{ type: "text", text: "run HUMAN_PENDING_APPROVAL" }],
        }),
      (err) => {
        assert.match(err.message, /INPUT_REQUIRED/);
        return true;
      },
    );
    assert.equal(permissionRequests.length, 1);
    assert.match(getStderr(), /session\/request_permission timed out/);
    assert.match(readErrLog(), /session\/request_permission timed out/);
    const decides = readMspEvents().filter((e) => e.type === "approval/decide");
    assert.equal(decides.length, 1);
    assert.equal(decides[0].choiceId, "abort-turn");
  } finally {
    proc.kill("SIGTERM");
  }
});

test("session/prompt fails with INPUT_REQUIRED when approval remains pending past configurable threshold", async () => {
  const { proc, call, permissionRequests, readMspEvents, getStderr, readErrLog } = startAdapter({
    permissionMode: "hang",
    env: {
      MUSE_AGENT_ACP_PERMISSION_TIMEOUT_MS: "10000",
      MUSE_AGENT_ACP_APPROVAL_TIMEOUT_MS: "90",
      MUSE_AGENT_ACP_APPROVAL_POLL_MS: "25",
    },
  });
  try {
    await call("initialize", { protocolVersion: 1, clientCapabilities: {} });
    const session = await call("session/new", { cwd: process.cwd(), mcpServers: [] });
    const startedAt = Date.now();
    await assert.rejects(
      () =>
        call("session/prompt", {
          sessionId: session.sessionId,
          prompt: [{ type: "text", text: "run HUMAN_PENDING_APPROVAL" }],
        }),
      (err) => {
        assert.match(err.message, /INPUT_REQUIRED/);
        assert.equal(err.rpcError?.data?.code, "INPUT_REQUIRED");
        return true;
      },
    );
    assert.ok(Date.now() - startedAt < 5000, "should expire pending approval fast");
    assert.equal(permissionRequests.length, 1);
    assert.match(getStderr(), /pending longer than 90ms/);
    assert.match(readErrLog(), /pending longer than 90ms/);
    const decides = readMspEvents().filter((e) => e.type === "approval/decide");
    assert.equal(decides.length, 1);
    assert.equal(decides[0].choiceId, "abort-turn");
  } finally {
    proc.kill("SIGTERM");
  }
});
