#!/usr/bin/env node
// muse-agent-acp: an ACP agent backed by Muse Session Protocol (MSP).
//
// One `muse serve` child hosts every ACP session on this connection. ACP
// session ids are MSP session ids passed through unchanged. Approvals map
// MSP `approval/request`, `approval/requested`, and `approval/listPending` ->
// ACP `session/request_permission` -> MSP `approval/decide`. Fixed-choice user
// input (`userInput/request`) is declined fail-closed, matching the
// SaariusSkills host policy.

import { appendFileSync } from "node:fs";
import { Readable, Writable } from "node:stream";
import { agent, methods, ndJsonStream, PROTOCOL_VERSION, RequestError } from "@agentclientprotocol/sdk";
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
const DEFAULT_PERMISSION_TIMEOUT_MS = 30_000;
const DEFAULT_APPROVAL_TIMEOUT_MS = 3 * 60 * 1000;
const DEFAULT_APPROVAL_POLL_MS = 1_000;

function writeErrLogFile(line) {
  const errLogPath = process.env.MUSE_AGENT_ACP_ERR_LOG || process.env.MUSE_ACP_ERR_LOG;
  if (!errLogPath) return;
  try {
    appendFileSync(errLogPath, line, "utf8");
  } catch {
    // Ignore secondary file write errors; stderr already received the log line.
  }
}

const log = (...args) => {
  const line = `[muse-agent-acp] ${args.join(" ")}\n`;
  process.stderr.write(line);
  writeErrLogFile(line);
};

const logError = (...args) => {
  const line = `[muse-agent-acp] ERROR: ${args.join(" ")}\n`;
  process.stderr.write(line);
  writeErrLogFile(line);
};

function parsePositiveMs(value) {
  if (value === undefined || value === null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function getPermissionTimeoutMs(params) {
  return (
    parsePositiveMs(params?.permissionTimeoutMs) ??
    parsePositiveMs(params?._meta?.permissionTimeoutMs) ??
    parsePositiveMs(process.env.MUSE_AGENT_ACP_PERMISSION_TIMEOUT_MS) ??
    parsePositiveMs(process.env.MUSE_ACP_PERMISSION_TIMEOUT_MS) ??
    DEFAULT_PERMISSION_TIMEOUT_MS
  );
}

function getApprovalTimeoutMs(params) {
  return (
    parsePositiveMs(params?.approvalTimeoutMs) ??
    parsePositiveMs(params?._meta?.approvalTimeoutMs) ??
    parsePositiveMs(process.env.MUSE_AGENT_ACP_APPROVAL_TIMEOUT_MS) ??
    parsePositiveMs(process.env.MUSE_ACP_APPROVAL_TIMEOUT_MS) ??
    parsePositiveMs(process.env.MUSE_AGENT_ACP_PENDING_APPROVAL_TIMEOUT_MS) ??
    DEFAULT_APPROVAL_TIMEOUT_MS
  );
}

function getApprovalPollMs(params, approvalTimeoutMs = DEFAULT_APPROVAL_TIMEOUT_MS) {
  return (
    parsePositiveMs(params?.approvalPollIntervalMs) ??
    parsePositiveMs(params?._meta?.approvalPollIntervalMs) ??
    parsePositiveMs(process.env.MUSE_AGENT_ACP_APPROVAL_POLL_MS) ??
    parsePositiveMs(process.env.MUSE_ACP_APPROVAL_POLL_MS) ??
    Math.min(DEFAULT_APPROVAL_POLL_MS, Math.max(25, Math.floor(approvalTimeoutMs / 3)))
  );
}

function createInputRequiredError(message, data = {}) {
  const err = new RequestError(-32000, message, {
    code: "INPUT_REQUIRED",
    ...data,
  });
  err.errorCode = "INPUT_REQUIRED";
  return err;
}

function withTimeout(promise, timeoutMs, message, onRegisterAbort) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      const err = new Error(message);
      err.code = "TIMEOUT";
      reject(err);
    }, timeoutMs);
    timer.unref?.();

    if (typeof onRegisterAbort === "function") {
      onRegisterAbort((abortErr) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(abortErr);
      });
    }

    Promise.resolve(promise).then(
      (value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

let msp = null;
let mspInit = null;
// sessionId -> { turnId, effort, models, onTurnEvent, onTurnError, turnError, approvalTimeoutMs, handledApprovals, pendingApprovals, pollingPending }
const sessions = new Map();
// sessionId -> ACP client handle captured from the active prompt handler.
const liveClients = new Map();
// approvalId -> Promise for deduplication across approval/request, approval/requested, and approval/listPending.
const handledApprovalsById = new Map();

function notifyUpdate(sessionId, update) {
  const client = liveClients.get(sessionId);
  if (!client) return;
  client
    .notify(methods.client.session.update, { sessionId, update })
    .catch((error) => logError("session/update failed:", error?.message ?? error));
}

function clearPendingApproval(state, approvalId) {
  if (!state?.pendingApprovals || !approvalId) return;
  const entry = state.pendingApprovals.get(approvalId);
  if (!entry) return;
  if (entry.timer) clearTimeout(entry.timer);
  state.pendingApprovals.delete(approvalId);
}

function clearAllPendingApprovals(state) {
  if (!state?.pendingApprovals) return;
  for (const entry of state.pendingApprovals.values()) {
    if (entry.timer) clearTimeout(entry.timer);
  }
  state.pendingApprovals.clear();
}

async function expirePendingApproval(sessionId, state, approvalId, approvalTimeoutMs) {
  const entry = state?.pendingApprovals?.get(approvalId);
  if (!entry || entry.expired) return;
  entry.expired = true;
  clearPendingApproval(state, approvalId);

  const msg = `INPUT_REQUIRED: approval ${approvalId} pending longer than ${approvalTimeoutMs}ms in session ${sessionId}`;
  logError(msg);

  const inputErr = createInputRequiredError(msg, {
    approvalId,
    sessionId,
    timeoutMs: approvalTimeoutMs,
  });
  state.turnError = state.turnError ?? inputErr;

  if (typeof entry.abortPermissionWait === "function") {
    entry.abortPermissionWait(inputErr);
  }

  if (!entry.decided && msp) {
    entry.decided = true;
    const choiceId = denyChoiceId(entry.params?.availableChoices);
    if (choiceId) {
      await withTimeout(
        msp.request("approval/decide", {
          commandId: uuidv7(),
          sessionId,
          approvalId,
          choiceId,
          ...(entry.params?.currentRequirementId !== undefined
            ? { requirementId: entry.params.currentRequirementId }
            : {}),
        }),
        Math.min(getPermissionTimeoutMs(), 5_000),
        `approval/decide timed out while expiring approval ${approvalId}`,
      ).catch((error) =>
        logError(`approval/decide failed while expiring approval ${approvalId}:`, error?.message ?? error),
      );
    }
  }

  if (state.turnId && msp) {
    await withTimeout(
      msp.request("turn/cancel", { commandId: uuidv7(), sessionId, turnId: state.turnId }),
      Math.min(getPermissionTimeoutMs(), 5_000),
      `turn/cancel timed out while expiring approval ${approvalId}`,
    ).catch((error) =>
      logError(`turn/cancel failed while expiring approval ${approvalId}:`, error?.message ?? error),
    );
  }

  if (state.onTurnError) {
    state.onTurnError(state.turnError);
  }
}

function checkPendingApprovalTimeouts(sessionId, state, approvalTimeoutMs) {
  if (!state?.pendingApprovals) return;
  const now = Date.now();
  for (const [approvalId, entry] of state.pendingApprovals.entries()) {
    if (!entry.expired && now - entry.startedAt >= approvalTimeoutMs) {
      void expirePendingApproval(sessionId, state, approvalId, approvalTimeoutMs);
    }
  }
}

async function pollPendingApprovals(sessionId) {
  const state = sessions.get(sessionId);
  if (!state || !state.turnOpen || !msp) return;
  if (state.pollingPending) return state.pollingPending;
  const run = (async () => {
    try {
      const res = await withTimeout(
        msp.request("approval/listPending", { sessionId }),
        getPermissionTimeoutMs(),
        `approval/listPending timed out for session ${sessionId}`,
      );
      const approvals = Array.isArray(res?.approvals)
        ? res.approvals
        : Array.isArray(res?.pending)
          ? res.pending
          : Array.isArray(res)
            ? res
            : [];
      for (const approval of approvals) {
        if (!approval || typeof approval !== "object") continue;
        void handleApproval({ sessionId, ...approval }).catch((error) =>
          logError("pending approval handling failed:", error?.message ?? error),
        );
      }
    } catch (error) {
      if (state.turnOpen) {
        logError(`approval/listPending failed for session ${sessionId}:`, error?.message ?? error);
      }
    } finally {
      state.pollingPending = null;
    }
  })();
  state.pollingPending = run;
  return run;
}

function onMspNotification(method, params) {
  const sessionId = params?.sessionId;
  if (typeof sessionId !== "string") return;
  const state = sessions.get(sessionId);
  if (!state) return;
  if (method === "approval/requested") {
    void handleApproval(params).catch((error) =>
      logError("approval handling failed:", error?.message ?? error),
    );
    return;
  }
  if (method === "approval/resolved") {
    clearPendingApproval(state, params?.approvalId);
    return;
  }
  if (method.startsWith("item/")) {
    for (const update of itemEventToAcpUpdates(method, params)) notifyUpdate(sessionId, update);
  }
  if (method === "turn/completed") {
    clearAllPendingApprovals(state);
    if (state.onTurnEvent) state.onTurnEvent(params);
  }
}

async function onMspServerRequest(method, params) {
  // Always ack presentation first; the decision travels as a command.
  if (method === "approval/request") {
    void handleApproval(params).catch((error) =>
      logError("approval handling failed:", error?.message ?? error),
    );
    return {};
  }
  if (method === "userInput/request") {
    void declineUserInput(params).catch((error) =>
      logError("userInput decline failed:", error?.message ?? error),
    );
    return {};
  }
  return {};
}

function handleApproval(params) {
  const { sessionId, approvalId } = params ?? {};
  const state = typeof sessionId === "string" ? sessions.get(sessionId) : undefined;
  if (typeof approvalId === "string" && approvalId) {
    if (state?.handledApprovals?.has(approvalId)) {
      return state.handledApprovals.get(approvalId);
    }
    if (handledApprovalsById.has(approvalId)) {
      return handledApprovalsById.get(approvalId);
    }
  }
  const promise = executeHandleApproval(params);
  if (typeof approvalId === "string" && approvalId) {
    handledApprovalsById.set(approvalId, promise);
    state?.handledApprovals?.set(approvalId, promise);
  }
  return promise;
}

async function executeHandleApproval(params) {
  const {
    sessionId,
    approvalId,
    availableChoices,
    toolName,
    toolCallId,
    itemId,
    currentRequirementId,
  } = params ?? {};
  const state = typeof sessionId === "string" ? sessions.get(sessionId) : undefined;
  const approvalTimeoutMs = state?.approvalTimeoutMs ?? getApprovalTimeoutMs(params);
  const permissionTimeoutMs = getPermissionTimeoutMs(params);

  let pendingEntry = null;
  if (state && typeof approvalId === "string" && approvalId) {
    pendingEntry = {
      approvalId,
      params,
      startedAt: Date.now(),
      decided: false,
      expired: false,
      abortPermissionWait: null,
      timer: null,
    };
    const timer = setTimeout(() => {
      void expirePendingApproval(sessionId, state, approvalId, approvalTimeoutMs);
    }, approvalTimeoutMs);
    timer.unref?.();
    pendingEntry.timer = timer;
    state.pendingApprovals.set(approvalId, pendingEntry);
  }

  const options = acpPermissionOptions(availableChoices);
  let choiceId = null;
  let response = null;
  let permissionError = null;
  const client = typeof sessionId === "string" ? liveClients.get(sessionId) : undefined;

  if (!client) {
    permissionError = new Error(
      `no active ACP client for session/request_permission (sessionId=${sessionId}, approvalId=${approvalId})`,
    );
    logError(permissionError.message);
  } else if (options.length === 0) {
    permissionError = new Error(
      `approval ${approvalId ?? "unknown"} had no selectable permission options`,
    );
    logError(permissionError.message);
  } else {
    try {
      response = await withTimeout(
        client.request(methods.client.session.requestPermission, {
          sessionId,
          toolCall: {
            toolCallId: toolCallId ?? itemId ?? approvalId ?? "muse-approval",
            title: toolName ?? "tool",
            status: "pending",
          },
          options,
        }),
        permissionTimeoutMs,
        `session/request_permission timed out after ${permissionTimeoutMs}ms (sessionId=${sessionId}, approvalId=${approvalId})`,
        (abortFn) => {
          if (pendingEntry) pendingEntry.abortPermissionWait = abortFn;
        },
      );
      if (response?.outcome?.outcome === "selected") {
        choiceId = response.outcome.optionId;
      } else {
        logError(
          `session/request_permission was not selected (outcome=${response?.outcome?.outcome ?? "none"}, sessionId=${sessionId}, approvalId=${approvalId})`,
        );
      }
    } catch (error) {
      permissionError = error;
      logError(
        `session/request_permission failed (sessionId=${sessionId}, approvalId=${approvalId}):`,
        error?.message ?? error,
      );
    }
  }

  if (pendingEntry?.expired) {
    return;
  }

  if (!choiceId) {
    choiceId = denyChoiceId(availableChoices);
  }

  const selectedChoice = (availableChoices ?? []).find((c) => c?.choiceId === choiceId);
  const isApproved =
    !permissionError &&
    response?.outcome?.outcome === "selected" &&
    Boolean(choiceId) &&
    (selectedChoice
      ? typeof selectedChoice.decision === "string" && selectedChoice.decision.startsWith("approved")
      : choiceId !== denyChoiceId(availableChoices));

  if (pendingEntry) {
    pendingEntry.decided = true;
  }

  if (!isApproved && state) {
    const reason = permissionError
      ? permissionError.message
      : `outcome=${response?.outcome?.outcome ?? "denied"}, choiceId=${choiceId ?? "none"}`;
    const inputErr = createInputRequiredError(
      `INPUT_REQUIRED: approval ${approvalId ?? "unknown"} for ${toolName ?? "tool"} was denied or not approved (${reason})`,
      { approvalId, sessionId, choiceId, reason },
    );
    state.turnError = state.turnError ?? inputErr;
  }

  if (!choiceId) {
    logError("approval had no selectable or deny choice; cancelling turn");
    if (state?.turnId && msp) {
      await withTimeout(
        msp.request("turn/cancel", { commandId: uuidv7(), sessionId, turnId: state.turnId }),
        permissionTimeoutMs,
        `turn/cancel timed out (sessionId=${sessionId}, approvalId=${approvalId})`,
      ).catch((error) => logError("turn/cancel failed:", error?.message ?? error));
    }
    if (state && approvalId) clearPendingApproval(state, approvalId);
    if (state?.onTurnError && state.turnError) {
      state.onTurnError(state.turnError);
    }
    return;
  }

  let decideFailed = false;
  await withTimeout(
    msp.request("approval/decide", {
      commandId: uuidv7(),
      sessionId,
      approvalId,
      choiceId,
      ...(currentRequirementId !== undefined ? { requirementId: currentRequirementId } : {}),
    }),
    permissionTimeoutMs,
    `approval/decide timed out (sessionId=${sessionId}, approvalId=${approvalId})`,
  ).catch((error) => {
    decideFailed = true;
    logError(
      `approval/decide failed (sessionId=${sessionId}, approvalId=${approvalId}, choiceId=${choiceId}):`,
      error?.message ?? error,
    );
  });

  if (state && approvalId && (!decideFailed || !isApproved)) {
    clearPendingApproval(state, approvalId);
  }

  if (state && (!isApproved || decideFailed)) {
    if (!state.turnError) {
      state.turnError = createInputRequiredError(
        `INPUT_REQUIRED: approval ${approvalId ?? "unknown"} failed to resolve`,
        { approvalId, sessionId, choiceId },
      );
    }
    if (state.onTurnError) {
      state.onTurnError(state.turnError);
    }
  }
}

async function declineUserInput(params) {
  const { sessionId, userInputId } = params ?? {};
  if (typeof sessionId !== "string" || typeof userInputId !== "string") return;
  await msp
    .request("userInput/cancel", {
      commandId: uuidv7(),
      sessionId,
      userInputId,
      reason: "muse-agent-acp does not present fixed-choice questions; ask in plain text instead",
    })
    .catch((error) => logError("userInput/cancel failed:", error?.message ?? error));
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
      logError("model/list failed:", error?.message ?? error);
    }
    const effort = started?.session?.reasoningEffort ?? "high";
    sessions.set(sessionId, {
      turnId: null,
      turnOpen: false,
      effort,
      models,
      onTurnEvent: null,
      onTurnError: null,
      turnError: null,
      approvalTimeoutMs: getApprovalTimeoutMs(c.params),
      handledApprovals: new Map(),
      pendingApprovals: new Map(),
      pollingPending: null,
    });
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
    state.turnError = null;
    state.turnOpen = true;
    const approvalTimeoutMs = getApprovalTimeoutMs(c.params);
    state.approvalTimeoutMs = approvalTimeoutMs;
    const pollIntervalMs = getApprovalPollMs(c.params, approvalTimeoutMs);
    let pollTimer = null;

    try {
      const completed = new Promise((resolve, reject) => {
        state.onTurnEvent = (params) => {
          if (!state.turnId || params?.turnId === state.turnId) resolve(params);
        };
        state.onTurnError = (err) => {
          reject(err);
        };
      });
      completed.catch(() => {});

      const ack = await client.request("turn/start", {
        commandId: uuidv7(),
        sessionId,
        input,
        displayText: promptDisplayText(input),
        ...(state.effort && REASONING_EFFORTS.includes(state.effort) ? { reasoningEffort: state.effort } : {}),
      });
      state.turnId = ack?.turnId ?? state.turnId;

      void pollPendingApprovals(sessionId);
      pollTimer = setInterval(() => {
        void pollPendingApprovals(sessionId);
        checkPendingApprovalTimeouts(sessionId, state, approvalTimeoutMs);
      }, pollIntervalMs);
      pollTimer.unref?.();

      const terminal = await completed;
      await Promise.allSettled([...state.handledApprovals.values()]);
      if (state.turnError) {
        throw state.turnError;
      }
      if (terminal?.terminal === "failed") {
        const reason = terminal?.error?.message ?? terminal?.reason ?? "turn failed";
        if (terminal?.error?.code === "INPUT_REQUIRED") {
          throw createInputRequiredError(`INPUT_REQUIRED: ${reason}`, { sessionId });
        }
        notifyUpdate(sessionId, {
          sessionUpdate: "agent_message_chunk",
          content: { type: "text", text: `\n[muse turn failed: ${reason}]` },
        });
      }
      return { stopReason: stopReasonFromTerminal(terminal?.terminal) };
    } catch (error) {
      await Promise.allSettled([...state.handledApprovals.values()]);
      if (state.turnError) {
        throw state.turnError;
      }
      throw error;
    } finally {
      state.turnOpen = false;
      state.onTurnEvent = null;
      state.onTurnError = null;
      state.turnId = null;
      if (pollTimer) clearInterval(pollTimer);
      clearAllPendingApprovals(state);
      liveClients.delete(sessionId);
    }
  })
  .onRequest(methods.agent.session.close, async (c) => {
    // MSP has no session/close command; closing means cancelling any active
    // turn and forgetting the session on this connection. The host-side
    // session log remains whatever `muse serve` durability made it.
    const sessionId = c.params?.sessionId;
    const state = sessions.get(sessionId);
    if (state) {
      clearAllPendingApprovals(state);
    }
    if (state?.turnId && msp) {
      await msp
        .request("turn/cancel", { commandId: uuidv7(), sessionId, turnId: state.turnId })
        .catch((error) => logError("turn/cancel on close failed:", error?.message ?? error));
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
      .catch((error) => logError("turn/cancel failed:", error?.message ?? error));
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
