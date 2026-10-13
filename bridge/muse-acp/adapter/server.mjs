#!/usr/bin/env node
// muse-agent-acp: an ACP agent backed by Muse Session Protocol (MSP).
//
// One `muse serve` child hosts every ACP session on this connection. ACP
// session ids are MSP session ids passed through unchanged. Approvals map
// MSP `approval/request` -> ACP `session/request_permission` -> MSP
// `approval/decide`. Fixed-choice user input (`userInput/request`) is
// declined fail-closed, matching the SaariusSkills host policy.

import { Readable, Writable } from "node:stream";
import { agent, methods, ndJsonStream, PROTOCOL_VERSION } from "@agentclientprotocol/sdk";
import { MspClient, resolveMuseServeArgv } from "./msp-client.mjs";
import {
  acpModelState,
  acpPermissionOptions,
  acpPromptToMspInput,
  denyChoiceId,
  itemEventToAcpUpdates,
  promptDisplayText,
  reasoningConfigOption,
  REASONING_EFFORTS,
  stopReasonFromTerminal,
  uuidv7,
} from "./translate.mjs";

const VERSION = "0.1.0";
const log = (...args) => process.stderr.write(`[muse-agent-acp] ${args.join(" ")}\n`);

let msp = null;
let mspInit = null;
// sessionId -> { turnId, effort, models, onTurnEvent }
const sessions = new Map();
// sessionId -> ACP client handle captured from the active prompt handler.
const liveClients = new Map();

function notifyUpdate(sessionId, update) {
  const client = liveClients.get(sessionId);
  if (!client) return;
  client
    .notify(methods.client.session.update, { sessionId, update })
    .catch((error) => log("session/update failed:", error?.message ?? error));
}

function onMspNotification(method, params) {
  const sessionId = params?.sessionId;
  if (typeof sessionId !== "string") return;
  const state = sessions.get(sessionId);
  if (!state) return;
  if (method.startsWith("item/")) {
    for (const update of itemEventToAcpUpdates(method, params)) notifyUpdate(sessionId, update);
  }
  if (method === "turn/completed" && state.onTurnEvent) state.onTurnEvent(params);
}

async function onMspServerRequest(method, params) {
  // Always ack presentation first; the decision travels as a command.
  if (method === "approval/request") {
    void handleApproval(params).catch((error) => log("approval handling failed:", error?.message ?? error));
    return {};
  }
  if (method === "userInput/request") {
    void declineUserInput(params).catch((error) => log("userInput decline failed:", error?.message ?? error));
    return {};
  }
  return {};
}

async function handleApproval(params) {
  const { sessionId, approvalId, availableChoices, toolName, toolCallId, itemId } = params ?? {};
  const options = acpPermissionOptions(availableChoices);
  let choiceId = null;
  const client = typeof sessionId === "string" ? liveClients.get(sessionId) : undefined;
  if (client && options.length > 0) {
    const response = await client.request(methods.client.session.requestPermission, {
      sessionId,
      toolCall: {
        toolCallId: toolCallId ?? itemId ?? approvalId ?? "muse-approval",
        title: toolName ?? "tool",
        status: "pending",
      },
      options,
    });
    if (response?.outcome?.outcome === "selected") choiceId = response.outcome.optionId;
  }
  if (!choiceId) choiceId = denyChoiceId(availableChoices);
  if (!choiceId) {
    log("approval had no selectable or deny choice; cancelling turn");
    const state = sessions.get(sessionId);
    if (state?.turnId) {
      await msp.request("turn/cancel", { commandId: uuidv7(), sessionId, turnId: state.turnId });
    }
    return;
  }
  await msp.request("approval/decide", {
    commandId: uuidv7(),
    sessionId,
    approvalId,
    choiceId,
  });
}

async function declineUserInput(params) {
  const { sessionId, userInputId } = params ?? {};
  if (typeof sessionId !== "string" || typeof userInputId !== "string") return;
  await msp.request("userInput/cancel", {
    commandId: uuidv7(),
    sessionId,
    userInputId,
    reason: "muse-agent-acp does not present fixed-choice questions; ask in plain text instead",
  });
}

async function ensureMsp(cwd) {
  if (msp) return msp;
  const { executable, args } = resolveMuseServeArgv();
  msp = new MspClient({
    executable,
    args,
    cwd,
    onNotification: onMspNotification,
    onServerRequest: onMspServerRequest,
    onExit: (code, signal) => log(`muse serve exited code=${code} signal=${signal}`),
  });
  mspInit = await msp.request("initialize", {
    clientInfo: { name: "muse_agent_acp", title: "Muse ACP Adapter", version: VERSION },
  });
  msp.notify("initialized", {});
  const fp = mspInit?.schema?.fingerprint;
  if (fp) log("MSP schema fingerprint:", fp);
  return msp;
}

const identity = (params) => params ?? {};

agent({ name: "muse-agent-acp" })
  .onRequest(methods.agent.initialize, async (c) => {
    await ensureMsp(process.cwd());
    return {
      protocolVersion: c.params?.protocolVersion ?? PROTOCOL_VERSION,
      agentCapabilities: {
        loadSession: false,
        promptCapabilities: { image: true, embeddedContext: true },
        sessionCapabilities: { close: {} },
      },
      agentInfo: { name: "muse-agent-acp", title: "Muse (MSP)", version: VERSION },
      authMethods: [],
    };
  })
  .onRequest(methods.agent.session.new, async (c) => {
    const client = await ensureMsp(c.params?.cwd ?? process.cwd());
    if (Array.isArray(c.params?.mcpServers) && c.params.mcpServers.length > 0) {
      log(`ignoring ${c.params.mcpServers.length} ACP mcpServers entries (MSP session config mapping is not implemented yet)`);
    }
    const started = await client.request("session/start", {
      commandId: uuidv7(),
      workspaceRoot: c.params?.cwd,
      ...(Array.isArray(c.params?.additionalDirectories) && c.params.additionalDirectories.length
        ? { workspaceRoots: [c.params.cwd, ...c.params.additionalDirectories] }
        : {}),
    });
    const sessionId = started?.session?.sessionId;
    if (typeof sessionId !== "string") throw new Error("MSP session/start returned no sessionId");
    let models = null;
    try {
      models = acpModelState(await client.request("model/list", {}));
    } catch (error) {
      log("model/list failed:", error?.message ?? error);
    }
    const effort = started?.session?.reasoningEffort ?? "high";
    sessions.set(sessionId, { turnId: null, effort, models, onTurnEvent: null });
    return {
      sessionId,
      ...(models ? { models } : {}),
      configOptions: [reasoningConfigOption(effort)],
    };
  })
  .onRequest(methods.agent.session.prompt, async (c) => {
    const client = await ensureMsp(process.cwd());
    const sessionId = c.params?.sessionId;
    const state = sessions.get(sessionId);
    if (!state) throw new Error(`unknown session ${sessionId}`);
    const input = acpPromptToMspInput(c.params?.prompt);
    if (!input.length) throw new Error("prompt contained no translatable content blocks");
    liveClients.set(sessionId, c.client);
    try {
      const completed = new Promise((resolve) => {
        state.onTurnEvent = (params) => {
          if (!state.turnId || params?.turnId === state.turnId) resolve(params);
        };
      });
      const ack = await client.request("turn/start", {
        commandId: uuidv7(),
        sessionId,
        input,
        displayText: promptDisplayText(input),
        ...(state.effort && REASONING_EFFORTS.includes(state.effort) ? { reasoningEffort: state.effort } : {}),
      });
      state.turnId = ack?.turnId ?? state.turnId;
      const terminal = await completed;
      if (terminal?.terminal === "failed") {
        const reason = terminal?.error?.message ?? terminal?.reason ?? "turn failed";
        notifyUpdate(sessionId, {
          sessionUpdate: "agent_message_chunk",
          content: { type: "text", text: `\n[muse turn failed: ${reason}]` },
        });
      }
      return { stopReason: stopReasonFromTerminal(terminal?.terminal) };
    } finally {
      state.onTurnEvent = null;
      state.turnId = null;
      liveClients.delete(sessionId);
    }
  })
  .onRequest(methods.agent.session.close, async (c) => {
    // MSP has no session/close command; closing means cancelling any active
    // turn and forgetting the session on this connection. The host-side
    // session log remains whatever `muse serve` durability made it.
    const sessionId = c.params?.sessionId;
    const state = sessions.get(sessionId);
    if (state?.turnId && msp) {
      await msp
        .request("turn/cancel", { commandId: uuidv7(), sessionId, turnId: state.turnId })
        .catch((error) => log("turn/cancel on close failed:", error?.message ?? error));
    }
    sessions.delete(sessionId);
    liveClients.delete(sessionId);
    return {};
  })
  .onNotification(methods.agent.session.cancel, async (c) => {
    const sessionId = c.params?.sessionId;
    const state = sessions.get(sessionId);
    if (!msp || !state?.turnId) return;
    await msp
      .request("turn/cancel", { commandId: uuidv7(), sessionId, turnId: state.turnId })
      .catch((error) => log("turn/cancel failed:", error?.message ?? error));
  })
  .onRequest(methods.agent.session.setConfigOption, async (c) => {
    const { sessionId, configId, value } = c.params ?? {};
    const state = sessions.get(sessionId);
    if (!state) throw new Error(`unknown session ${sessionId}`);
    if (configId === "reasoning_effort") {
      if (!REASONING_EFFORTS.includes(value)) throw new Error(`unsupported reasoning_effort ${value}`);
      await msp.request("session/setReasoningEffort", { commandId: uuidv7(), sessionId, reasoningEffort: value });
      state.effort = value;
      return { configOptions: [reasoningConfigOption(value)] };
    }
    if (configId === "model" && typeof value === "string") {
      await msp.request("session/setModel", { commandId: uuidv7(), sessionId, model: value });
      if (state.models) state.models = { ...state.models, currentModelId: value };
      return { configOptions: [reasoningConfigOption(state.effort)] };
    }
    throw new Error(`unsupported config option ${configId}`);
  })
  .onRequest("session/set_model", identity, async (c) => {
    const { sessionId, modelId } = c.params ?? {};
    const state = sessions.get(sessionId);
    if (!state) throw new Error(`unknown session ${sessionId}`);
    await msp.request("session/setModel", { commandId: uuidv7(), sessionId, model: modelId });
    if (state.models) state.models = { ...state.models, currentModelId: modelId };
    return {};
  })
  .connect(ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin)));

const shutdown = () => {
  try { msp?.close(); } catch { /* already gone */ }
  process.exit(0);
};
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
process.stdin.once("end", shutdown);
