#!/usr/bin/env node
import { createInterface } from "node:readline";
import { writeFile } from "node:fs/promises";

const capabilitiesPath = process.env.PUPPET_ACPX_CANDIDATE_PEER_CAPABILITIES;
const FAIL_PROMPT = "candidate runtime fail";
const DEFAULT_MODE = "auto";
const DEFAULT_MODEL = "candidate-default";
const FAST_MODEL = "candidate-fast";
const DEFAULT_EFFORT = "medium";

const availableModes = [
  { id: DEFAULT_MODE, name: "Auto" },
  { id: "plan", name: "Plan" },
];
const availableModels = [
  { modelId: DEFAULT_MODEL, name: "Candidate Default" },
  { modelId: FAST_MODEL, name: "Candidate Fast" },
];
const effortOptions = [
  { value: "low", name: "Low" },
  { value: "medium", name: "Medium" },
  { value: "high", name: "High" },
];

const sessions = new Map();

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function notify(method, params) {
  send({ jsonrpc: "2.0", method, params });
}

function callbackBooleans(capabilities = {}) {
  const fs = capabilities.fs;
  return {
    fs: fs === true || fs?.readTextFile === true || fs?.writeTextFile === true,
    terminal: capabilities.terminal === true,
  };
}

async function recordCapabilities(capabilities) {
  if (!capabilitiesPath) return;
  await writeFile(capabilitiesPath, `${JSON.stringify(callbackBooleans(capabilities))}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
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
  const session = {
    sessionId,
    modeId: DEFAULT_MODE,
    modelId: DEFAULT_MODEL,
    configValues: { reasoning_effort: DEFAULT_EFFORT },
  };
  sessions.set(sessionId, session);
  return session;
}

function requireSession(sessionId) {
  return sessions.get(sessionId) ?? createSession(sessionId);
}

function configOptions(session) {
  return [
    {
      id: "reasoning_effort",
      name: "Reasoning Effort",
      type: "select",
      currentValue: session.configValues.reasoning_effort,
      options: effortOptions,
    },
  ];
}

function sessionCatalog(session) {
  return {
    modes: {
      currentModeId: session.modeId,
      availableModes,
    },
    models: {
      currentModelId: session.modelId,
      availableModels,
    },
    configOptions: configOptions(session),
  };
}

function sendTextDelta(sessionId, text) {
  notify("session/update", {
    sessionId,
    update: {
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text },
    },
  });
}

async function handle(message) {
  if (!message || typeof message !== "object") return;
  const { id, method, params } = message;
  if (method == null) return;
  if (id === undefined) return;
  try {
    if (method === "initialize") {
      await recordCapabilities(params?.clientCapabilities);
      send({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: params?.protocolVersion ?? 1,
          agentCapabilities: {
            loadSession: true,
            promptCapabilities: { image: false, audio: false, embeddedContext: false },
            sessionCapabilities: { close: {} },
          },
          agentInfo: { name: "puppet-acpx-candidate-peer", version: "0.0.0" },
          authMethods: [],
        },
      });
      return;
    }
    if (method === "session/new") {
      const session = createSession("candidate-session");
      send({
        jsonrpc: "2.0",
        id,
        result: {
          sessionId: session.sessionId,
          ...sessionCatalog(session),
        },
      });
      return;
    }
    if (method === "session/load") {
      const session = requireSession(params?.sessionId ?? "candidate-session");
      send({
        jsonrpc: "2.0",
        id,
        result: sessionCatalog(session),
      });
      return;
    }
    if (method === "session/set_mode") {
      const session = requireSession(params?.sessionId);
      if (!availableModes.some((mode) => mode.id === params?.modeId)) {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32602, message: `Unsupported mode: ${params?.modeId}` },
        });
        return;
      }
      session.modeId = params.modeId;
      send({ jsonrpc: "2.0", id, result: {} });
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
    if (method === "session/set_config_option") {
      const session = requireSession(params?.sessionId);
      if (params?.configId === "mode") {
        send({
          jsonrpc: "2.0",
          id,
          error: {
            code: -32602,
            message: "generic config mode is distinct from legacy session/set_mode",
          },
        });
        return;
      }
      if (params?.configId !== "reasoning_effort") {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32602, message: `Unsupported config option: ${params?.configId}` },
        });
        return;
      }
      if (!effortOptions.some((option) => option.value === params?.value)) {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32602, message: `Unsupported config value: ${params?.value}` },
        });
        return;
      }
      session.configValues.reasoning_effort = params.value;
      send({
        jsonrpc: "2.0",
        id,
        result: { configOptions: configOptions(session) },
      });
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
      sendTextDelta(session.sessionId, "candidate-ack");
      send({ jsonrpc: "2.0", id, result: { stopReason: "end_turn" } });
      return;
    }
    if (method === "session/cancel") {
      send({ jsonrpc: "2.0", id, result: {} });
      return;
    }
    if (method === "session/close") {
      if (params?.sessionId) sessions.delete(params.sessionId);
      send({ jsonrpc: "2.0", id, result: {} });
      return;
    }
    send({
      jsonrpc: "2.0",
      id,
      error: { code: -32601, message: `Method not found: ${method}` },
    });
  } catch (error) {
    send({
      jsonrpc: "2.0",
      id,
      error: { code: -32603, message: error instanceof Error ? error.message : "peer failed" },
    });
  }
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
