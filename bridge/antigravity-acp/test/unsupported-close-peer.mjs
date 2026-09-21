#!/usr/bin/env node
import { createInterface } from "node:readline";

const DEFAULT_MODEL = "gemini-3.8-flash-high";
const availableModels = [
  { modelId: "gemini-3.8-flash-high", name: "Gemini 3.8 Flash High" },
  { modelId: "gemini-3.1-pro", name: "Gemini 3.1 Pro" },
  { modelId: "gemini-3-flash", name: "Gemini 3 Flash" },
];
const survive = process.argv.includes("--survive");
const sessions = new Map();

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function notify(method, params) {
  send({ jsonrpc: "2.0", method, params });
}

function createSession(sessionId) {
  const session = { sessionId, modelId: DEFAULT_MODEL };
  sessions.set(sessionId, session);
  return session;
}

function requireSession(sessionId) {
  return sessions.get(sessionId) ?? createSession(sessionId);
}

function models(session) {
  return { currentModelId: session.modelId, availableModels };
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed) continue;
  let request;
  try {
    request = JSON.parse(trimmed);
  } catch {
    continue;
  }
  if (request.id === undefined) continue;
  const sessionId = request.params?.sessionId ?? "agy-candidate-session";
  if (request.method === "initialize") {
    send({
      jsonrpc: "2.0",
      id: request.id,
      result: {
        protocolVersion: 1,
        agentCapabilities: { loadSession: false, promptCapabilities: {} },
        agentInfo: { name: "antigravity-unsupported-close-peer", version: "0.0.0" },
        authMethods: [],
      },
    });
  } else if (request.method === "session/new") {
    const session = createSession(sessionId);
    send({ jsonrpc: "2.0", id: request.id, result: { sessionId, models: models(session) } });
  } else if (request.method === "session/status") {
    const session = requireSession(sessionId);
    send({ jsonrpc: "2.0", id: request.id, result: { models: models(session) } });
  } else if (request.method === "session/set_model") {
    const session = requireSession(sessionId);
    if (!availableModels.some((model) => model.modelId === request.params?.modelId)) {
      send({ jsonrpc: "2.0", id: request.id, error: { code: -32602, message: "Unsupported model" } });
    } else {
      session.modelId = request.params.modelId;
      send({ jsonrpc: "2.0", id: request.id, result: {} });
    }
  } else if (request.method === "session/prompt") {
    notify("session/update", {
      sessionId,
      update: {
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: "agy-unsupported-close-ack" },
      },
    });
    send({ jsonrpc: "2.0", id: request.id, result: { stopReason: "end_turn" } });
  } else if (request.method === "session/close") {
    send({
      jsonrpc: "2.0",
      id: request.id,
      error: { code: -32601, message: "Agent does not support session/close for synthetic peer." },
    });
    if (!survive) process.exit(0);
  } else {
    send({ jsonrpc: "2.0", id: request.id, result: {} });
  }
}

if (survive) setInterval(() => {}, 1000);
else process.exit(0);
