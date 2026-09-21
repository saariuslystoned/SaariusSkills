#!/usr/bin/env node
import { createInterface } from "node:readline";

const DEFAULT_MODEL = "gemini-3.8-flash-high";
const availableModels = [
  { modelId: "gemini-3.8-flash-high", name: "Gemini 3.8 Flash High" },
  { modelId: "gemini-3.1-pro", name: "Gemini 3.1 Pro" },
  { modelId: "gemini-3-flash", name: "Gemini 3 Flash" },
];

const hangPrompt = process.argv.includes("--hang-prompt");
const sessions = new Map();

function createSession(sessionId) {
  const session = {
    sessionId,
    modelId: DEFAULT_MODEL,
  };
  sessions.set(sessionId, session);
  return session;
}

function requireSession(sessionId) {
  return sessions.get(sessionId) ?? createSession(sessionId);
}

function sessionModels(session) {
  return {
    currentModelId: session.modelId,
    availableModels,
  };
}

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function notify(method, params) {
  send({ jsonrpc: "2.0", method, params });
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
let sessionId = "synthetic-session";

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

  if (request.method === "initialize") {
    send({
      jsonrpc: "2.0",
      id: request.id,
      result: {
        protocolVersion: 1,
        agentCapabilities: { loadSession: false, promptCapabilities: {} },
        agentInfo: { name: "antigravity-synthetic-peer", version: "1.0.0" },
        authMethods: [],
      },
    });
  } else if (request.method === "session/new") {
    const session = createSession(sessionId);
    send({
      jsonrpc: "2.0",
      id: request.id,
      result: {
        sessionId: session.sessionId,
        models: sessionModels(session),
      },
    });
  } else if (request.method === "session/status") {
    const session = requireSession(request.params?.sessionId ?? sessionId);
    send({
      jsonrpc: "2.0",
      id: request.id,
      result: {
        models: sessionModels(session),
      },
    });
  } else if (request.method === "session/set_model") {
    const session = requireSession(request.params?.sessionId ?? sessionId);
    if (!availableModels.some((model) => model.modelId === request.params?.modelId)) {
      send({
        jsonrpc: "2.0",
        id: request.id,
        error: { code: -32602, message: `Unsupported model: ${request.params?.modelId}` },
      });
    } else {
      session.modelId = request.params.modelId;
      send({ jsonrpc: "2.0", id: request.id, result: {} });
    }
  } else if (request.method === "session/prompt") {
    if (hangPrompt) {
      await new Promise(() => {});
    }
    notify("session/update", {
      sessionId,
      update: {
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: "agy-ack" },
      },
    });
    send({
      jsonrpc: "2.0",
      id: request.id,
      result: {
        stopReason: "end_turn",
      },
    });
  } else if (request.method === "session/close") {
    if (process.env.PUPPET_ANTIGRAVITY_UNSUPPORTED_CLOSE === "1") {
      send({
        jsonrpc: "2.0",
        id: request.id,
        error: {
          code: -32601,
          message: "Agent does not support session/close for surviving-peer.",
        },
      });
      if (process.env.PUPPET_ANTIGRAVITY_SURVIVING_PEER !== "1") {
        process.exit(0);
      }
    } else {
      send({
        jsonrpc: "2.0",
        id: request.id,
        result: {},
      });
      process.exit(0);
    }
  } else {
    send({
      jsonrpc: "2.0",
      id: request.id,
      result: {},
    });
  }
}

if (process.env.PUPPET_ANTIGRAVITY_SURVIVING_PEER === "1") {
  setInterval(() => {}, 1000);
} else {
  process.exit(0);
}
