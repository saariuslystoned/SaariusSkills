#!/usr/bin/env node
import { createInterface } from "node:readline";

const DEFAULT_MODEL = "gemini-3.8-flash-high";
const availableModels = [
  { modelId: "gemini-3.8-flash-high", name: "Gemini 3.8 Flash High" },
  { modelId: "gemini-3.1-pro", name: "Gemini 3.1 Pro" },
  { modelId: "gemini-3-flash", name: "Gemini 3 Flash" },
];

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
    send({
      jsonrpc: "2.0",
      id: request.id,
      result: {
        sessionId,
        models: {
          currentModelId: DEFAULT_MODEL,
          availableModels,
        },
      },
    });
  } else if (request.method === "session/prompt") {
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
