#!/usr/bin/env node
import { createInterface } from "node:readline";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_MODEL = "gemini-3.8-flash-high";
const availableModels = [
  { modelId: "gemini-3.8-flash-high", name: "Gemini 3.8 Flash High" },
  { modelId: "gemini-3.1-pro", name: "Gemini 3.1 Pro" },
  { modelId: "gemini-3-flash", name: "Gemini 3 Flash" },
];
const INTENDED_RELATIVE = "bin/normalize-lines.mjs";
const PROTECTED_RELATIVE = "test/normalize-lines.test.mjs";
const DEFAULT_INTENDED_SOURCE = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../proof/puppet-acp/20260921/antigravity/inputs/v2-fixture/intended/bin/normalize-lines.mjs",
);
const ALLOWED_PERMISSION_MODES = new Set([
  "fs_write_file",
  "locations_path",
  "fs_write_twice",
  "deny_protected",
  "absent_path",
  "multiple_paths",
  "conflicting_paths",
  "absent_kind",
  "other_kind",
  "absent_allow_once",
  "title_only",
  "interaction",
  "elicitation",
  "ambiguous",
]);

const permissionFlag = process.argv.indexOf("--permission");
const permissionMode = permissionFlag >= 0
  ? process.argv[permissionFlag + 1]
  : "fs_write_file";
if (!ALLOWED_PERMISSION_MODES.has(permissionMode)) {
  throw new Error("permission peer mode is not a local test mode");
}

const sessions = new Map();
const pending = new Map();
let nextRequestId = 1000;
let nextOpaqueId = 1;
let workspaceCwd = process.cwd();

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

function request(method, params) {
  const id = nextRequestId++;
  send({ jsonrpc: "2.0", id, method, params });
  return new Promise((resolve) => {
    pending.set(id, resolve);
  });
}

function nextToolCallId() {
  return `call_${nextOpaqueId++}`;
}

function permissionOptions() {
  return [
    { optionId: "allow-once", kind: "allow_once", name: "Allow once" },
    { optionId: "reject-once", kind: "reject_once", name: "Reject once" },
  ];
}

function requestPermission(sessionId, {
  toolCallId = nextToolCallId(),
  kind,
  filePath,
  locations,
  title = "write",
  options = permissionOptions(),
} = {}) {
  const toolCall = {
    toolCallId,
    title,
    status: "pending",
  };
  if (kind !== undefined) toolCall.kind = kind;
  if (filePath !== undefined) {
    toolCall.rawInput = filePath ? { path: filePath } : {};
  }
  if (locations !== undefined) toolCall.locations = locations;
  return request("session/request_permission", {
    sessionId,
    toolCall,
    options,
  });
}

function selectedAllowOnce(response) {
  return response?.result?.outcome?.outcome === "selected"
    && response.result.outcome.optionId === "allow-once";
}

async function writeIntended(workspace) {
  const target = path.join(workspace, INTENDED_RELATIVE);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, await readFile(DEFAULT_INTENDED_SOURCE));
}

async function writeTamper(workspace) {
  const target = path.join(workspace, INTENDED_RELATIVE);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, "tampered-by-second-grant\n");
}

async function maybeWriteIntended(sessionId, workspace, requestArgs) {
  const response = await requestPermission(sessionId, requestArgs);
  if (selectedAllowOnce(response)) {
    await writeIntended(workspace);
  }
  return response;
}

async function handlePrompt(sessionId) {
  const workspace = workspaceCwd;
  const intended = path.join(workspace, INTENDED_RELATIVE);
  const protectedPath = path.join(workspace, PROTECTED_RELATIVE);
  if (permissionMode === "interaction") {
    await requestPermission(sessionId, { toolCallId: "interaction_choose" });
  } else if (permissionMode === "elicitation") {
    await request("elicitation/create", {
      mode: "form",
      message: "Choose a hidden option.",
      sessionId,
      requestedSchema: { type: "object", properties: {} },
    });
  } else if (permissionMode === "ambiguous" || permissionMode === "absent_path") {
    await requestPermission(sessionId, { kind: "edit" });
  } else if (permissionMode === "multiple_paths") {
    await requestPermission(sessionId, {
      kind: "edit",
      locations: [{ path: intended }, { path: protectedPath }],
    });
  } else if (permissionMode === "conflicting_paths") {
    await requestPermission(sessionId, {
      kind: "edit",
      filePath: intended,
      locations: [{ path: protectedPath }],
    });
  } else if (permissionMode === "absent_kind") {
    await requestPermission(sessionId, { title: "", filePath: intended });
  } else if (permissionMode === "other_kind") {
    await requestPermission(sessionId, { kind: "execute", filePath: intended });
  } else if (permissionMode === "absent_allow_once") {
    await requestPermission(sessionId, {
      kind: "edit",
      filePath: intended,
      options: [
        { optionId: "allow-always", kind: "allow_always", name: "Allow always" },
        { optionId: "reject-once", kind: "reject_once", name: "Reject once" },
      ],
    });
  } else if (permissionMode === "title_only") {
    await requestPermission(sessionId, {
      title: "write bin/normalize-lines.mjs",
      filePath: intended,
    });
  } else if (permissionMode === "deny_protected") {
    const first = await requestPermission(sessionId, {
      kind: "edit",
      filePath: protectedPath,
    });
    if (selectedAllowOnce(first)) {
      await writeTamper(workspace);
    }
  } else if (permissionMode === "fs_write_twice") {
    const first = await maybeWriteIntended(sessionId, workspace, {
      kind: "edit",
      filePath: intended,
    });
    const second = await requestPermission(sessionId, {
      kind: "edit",
      filePath: intended,
    });
    if (selectedAllowOnce(second) && selectedAllowOnce(first)) {
      await writeTamper(workspace);
    } else if (selectedAllowOnce(second)) {
      await writeTamper(workspace);
    }
  } else if (permissionMode === "locations_path") {
    await maybeWriteIntended(sessionId, workspace, {
      kind: "edit",
      locations: [{ path: intended }],
    });
  } else {
    await maybeWriteIntended(sessionId, workspace, {
      kind: "edit",
      filePath: intended,
    });
  }
  notify("session/update", {
    sessionId,
    update: {
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: "agy-permission-ack" },
    },
  });
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
let sessionId = "synthetic-session";
let requestChain = Promise.resolve();

async function handleRequest(message) {
  if (message.method === "initialize") {
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        protocolVersion: 1,
        agentCapabilities: { loadSession: false, promptCapabilities: {} },
        agentInfo: { name: "antigravity-synthetic-peer", version: "1.0.0" },
        authMethods: [],
      },
    });
    return;
  }
  if (message.method === "session/new") {
    if (typeof message.params?.cwd === "string" && message.params.cwd) {
      workspaceCwd = message.params.cwd;
    }
    const session = createSession(sessionId);
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        sessionId: session.sessionId,
        models: sessionModels(session),
      },
    });
    return;
  }
  if (message.method === "session/status") {
    const session = requireSession(message.params?.sessionId ?? sessionId);
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        models: sessionModels(session),
      },
    });
    return;
  }
  if (message.method === "session/set_model") {
    const session = requireSession(message.params?.sessionId ?? sessionId);
    if (!availableModels.some((model) => model.modelId === message.params?.modelId)) {
      send({
        jsonrpc: "2.0",
        id: message.id,
        error: { code: -32602, message: `Unsupported model: ${message.params?.modelId}` },
      });
    } else {
      session.modelId = message.params.modelId;
      send({ jsonrpc: "2.0", id: message.id, result: {} });
    }
    return;
  }
  if (message.method === "session/prompt") {
    await handlePrompt(sessionId);
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        stopReason: "end_turn",
      },
    });
    return;
  }
  if (message.method === "session/close") {
    send({
      jsonrpc: "2.0",
      id: message.id,
      result: {},
    });
    process.exit(0);
  }
  send({
    jsonrpc: "2.0",
    id: message.id,
    result: {},
  });
}

lines.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let message;
  try {
    message = JSON.parse(trimmed);
  } catch {
    return;
  }
  if (message.id !== undefined && message.method === undefined) {
    const waiter = pending.get(message.id);
    if (waiter) {
      pending.delete(message.id);
      waiter(message);
    }
    return;
  }
  if (message.id === undefined) return;
  requestChain = requestChain.then(() => handleRequest(message));
});

lines.on("close", () => {
  requestChain.finally(() => process.exit(0));
});
