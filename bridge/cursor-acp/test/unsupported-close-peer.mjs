#!/usr/bin/env node
import { createInterface } from "node:readline";
import { appendFileSync, writeFileSync } from "node:fs";

const FAIL_PROMPT = "candidate runtime fail";
const DEFAULT_MODEL = "candidate-default";
const FAST_MODEL = "candidate-fast";
const survive = process.argv.includes("--survive");
const pidFile = process.env.PUPPET_ACPX_PEER_PID_FILE;
const heartbeatFile = process.env.PUPPET_ACPX_PEER_HEARTBEAT_FILE;

if (pidFile) writeFileSync(pidFile, `${process.pid}\n`);

const availableModels = [
  { modelId: DEFAULT_MODEL, name: "Candidate Default" },
  { modelId: FAST_MODEL, name: "Candidate Fast" },
];
const sessions = new Map();

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function notify(method, params) {
  send({ jsonrpc: "2.0", method, params });
}

function promptText(params) {
  if (typeof params?.text === "string" && params.text) return params.text;
  const blocks = params?.prompt;
  if (!Array.isArray(blocks)) return "";
  return blocks
    .filter((block) => block && block.type === "text" && typeof block.text === "string")
    .map((block) => block.text)
    .join("");
}

function createSession(sessionId) {
  const session = { sessionId, modelId: DEFAULT_MODEL };
  sessions.set(sessionId, session);
  return session;
}

function requireSession(sessionId) {
  return sessions.get(sessionId) ?? createSession(sessionId);
}

function sessionCatalog(session) {
  return {
    models: {
      currentModelId: session.modelId,
      availableModels,
    },
  };
}

async function handle(message) {
  if (!message || typeof message !== "object") return;
  const { id, method, params } = message;
  if (method == null || id === undefined) return;
  if (method === "initialize") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: params?.protocolVersion ?? 1,
        agentCapabilities: {
          loadSession: true,
          promptCapabilities: { image: false, audio: false, embeddedContext: false },
        },
        agentInfo: { name: "puppet-acpx-unsupported-close-peer", version: "0.0.0" },
        authMethods: [],
      },
    });
    return;
  }
  if (method === "session/new") {
    const session = createSession("candidate-session");
    send({ jsonrpc: "2.0", id, result: { sessionId: session.sessionId, ...sessionCatalog(session) } });
    return;
  }
  if (method === "session/load") {
    const session = requireSession(params?.sessionId ?? "candidate-session");
    send({ jsonrpc: "2.0", id, result: sessionCatalog(session) });
    return;
  }
  if (method === "session/set_model") {
    const session = requireSession(params?.sessionId);
    if (!availableModels.some((model) => model.modelId === params?.modelId)) {
      send({
        jsonrpc: "2.0",
        id,
        error: { code: -32602, message: `Unsupported model: ${params?.modelId}` },
      });
      return;
    }
    session.modelId = params.modelId;
    send({ jsonrpc: "2.0", id, result: {} });
    return;
  }
  if (method === "session/prompt") {
    const text = promptText(params);
    const session = requireSession(params?.sessionId);
    if (text === FAIL_PROMPT) {
      send({
        jsonrpc: "2.0",
        id,
        error: { code: -32603, message: "candidate peer failed the turn" },
      });
      return;
    }
    notify("session/update", {
      sessionId: session.sessionId,
      update: {
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: "candidate-ack" },
      },
    });
    send({ jsonrpc: "2.0", id, result: { stopReason: "end_turn" } });
    return;
  }
  if (method === "session/cancel") {
    send({ jsonrpc: "2.0", id, result: {} });
    return;
  }
  send({
    jsonrpc: "2.0",
    id,
    error: { code: -32601, message: `Method not found: ${method}` },
  });
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed) continue;
  let message;
  try {
    message = JSON.parse(trimmed);
  } catch {
    continue;
  }
  await handle(message);
}

if (survive) {
  let heartbeat = 0;
  setInterval(() => {
    if (heartbeatFile) appendFileSync(heartbeatFile, `${++heartbeat}\n`);
  }, 100);
} else {
  process.exit(0);
}
