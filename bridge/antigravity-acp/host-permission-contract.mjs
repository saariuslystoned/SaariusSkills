// Host-owned per-session permission contract for the AGY candidate
// createAcpRuntime route. Decisions are one-time and in-memory only.
// This is not an OS sandbox: fs:false/terminal:false disable ACP client
// callbacks, but the agent process can still write any reachable path.
// Agent-supplied paths are matched as host-policy equality only.
import path from "node:path";

export const HOST_PERMISSION_SCHEMA = "puppet.antigravity-acp-host-permission/v1";
export const INTENDED_WRITE_RELATIVE = "bin/normalize-lines.mjs";
export const FORBIDDEN_TURN_PERMISSION_KEYS = Object.freeze([
  "permissionMode",
  "nonInteractivePermissions",
  "permissionPolicy",
  "onPermissionRequest",
  "onElicitation",
  "sessionPermissions",
  "elicitationModes",
]);
export const HOST_PERMISSION_KINDS = Object.freeze([
  "fs_write_file",
  "denied",
  "interaction",
  "elicitation",
  "ambiguous",
]);

const RUNTIME_OUTCOMES = new Set(["allow_once", "reject_once", "cancel"]);

export function isInteractionQuestion(request) {
  const raw = request?.raw ?? request;
  const candidates = [
    raw?.toolCall?.toolCallId,
    raw?.params?.toolCall?.toolCallId,
    raw?.toolCallId,
    request?.toolCallId,
    raw?.params?.toolCallId,
  ];
  return candidates.some((id) => typeof id === "string" && id.startsWith("interaction_"));
}

export function intendedWritePath(workspaceRoot) {
  if (typeof workspaceRoot !== "string" || !workspaceRoot) {
    throw new Error("host permission workspace is missing");
  }
  return path.resolve(workspaceRoot, INTENDED_WRITE_RELATIVE);
}

export function requestToolCallId(request) {
  const raw = request?.raw ?? request;
  const candidates = [
    raw?.toolCall?.toolCallId,
    raw?.params?.toolCall?.toolCallId,
    raw?.toolCallId,
    request?.toolCallId,
    raw?.params?.toolCallId,
  ];
  for (const id of candidates) {
    if (typeof id === "string" && id) return id;
  }
  return undefined;
}

function readPathCandidate(value) {
  if (typeof value === "string" && value.trim()) return value.trim();
  return undefined;
}

export function requestWritePaths(request) {
  const raw = request?.raw ?? request;
  const toolCall = raw?.toolCall ?? raw?.params?.toolCall ?? {};
  const input = toolCall.rawInput ?? toolCall.input ?? {};
  const found = new Set();
  for (const key of ["path", "file", "filePath", "target"]) {
    const candidate = readPathCandidate(input?.[key]);
    if (candidate) found.add(candidate);
  }
  const locations = Array.isArray(toolCall.locations) ? toolCall.locations : [];
  for (const location of locations) {
    const candidate = readPathCandidate(location?.path);
    if (candidate) found.add(candidate);
  }
  return [...found];
}

export function resolveWorkspacePath(workspaceRoot, supplied) {
  if (typeof supplied !== "string" || !supplied) return undefined;
  return path.isAbsolute(supplied) ? path.resolve(supplied) : path.resolve(workspaceRoot, supplied);
}

export function pathMatchesIntendedWrite(workspaceRoot, supplied) {
  const resolved = resolveWorkspacePath(workspaceRoot, supplied);
  return resolved === intendedWritePath(workspaceRoot);
}

export function rejectCallerTurnPermissionHooks(payload, label = "startTurn") {
  if (!payload || typeof payload !== "object") {
    throw new Error(`${label} is invalid`);
  }
  if (FORBIDDEN_TURN_PERMISSION_KEYS.some((key) => Object.hasOwn(payload, key))) {
    const error = new Error("approve-all or MCP broker policy is not imported");
    error.code = "BROKER_POLICY";
    throw error;
  }
  return payload;
}

function receiptOutcome(decision) {
  if (decision.outcome === "allow_once") return "allow_once";
  if (decision.outcome === "reject_once") return "denied";
  return "cancelled";
}

export function decideHostPermission(request, state) {
  if (!state || typeof state.sessionKey !== "string" || !state.sessionKey) {
    return { outcome: "cancel", permission_kind: "ambiguous" };
  }
  if (isInteractionQuestion(request)) {
    return { outcome: "cancel", permission_kind: "interaction" };
  }
  const toolCallId = requestToolCallId(request);
  const paths = requestWritePaths(request);
  if (toolCallId !== "fs_write_file") {
    return { outcome: "cancel", permission_kind: "ambiguous" };
  }
  if (paths.length !== 1) {
    return { outcome: "cancel", permission_kind: "ambiguous" };
  }
  if (!pathMatchesIntendedWrite(state.workspaceRoot, paths[0])) {
    return { outcome: "reject_once", permission_kind: "denied" };
  }
  if (state.grantedWriteOnce === true) {
    return { outcome: "reject_once", permission_kind: "fs_write_file" };
  }
  state.grantedWriteOnce = true;
  return { outcome: "allow_once", permission_kind: "fs_write_file" };
}

export function bodyFreePermissionReceipt(state) {
  const decisions = (state?.decisions ?? []).map((decision) => {
    if (!RUNTIME_OUTCOMES.has(decision?.outcome)) {
      throw new Error("host permission decision is invalid");
    }
    return {
      outcome: receiptOutcome(decision),
      permission_kind: HOST_PERMISSION_KINDS.includes(decision.permission_kind)
        ? decision.permission_kind
        : "ambiguous",
    };
  });
  const last = decisions[decisions.length - 1];
  const grantCount = decisions.filter((decision) => decision.outcome === "allow_once").length;
  const outcome = last?.outcome ?? "cancelled";
  return {
    schema: HOST_PERMISSION_SCHEMA,
    state: outcome,
    outcome,
    permission_id: last?.permission_kind ?? "host",
    permission_kind: last?.permission_kind ?? "ambiguous",
    decisions,
    grant_count: grantCount,
    allowed: grantCount === 1 && decisions.some((decision) => decision.outcome === "allow_once"),
    persisted: false,
    approve_all: false,
    os_sandbox: false,
    fs: false,
    terminal: false,
    ordinary_launch: "unavailable",
    body_retained: false,
    invented_decision: null,
  };
}

export function createHostPermissionContract({ sessionKey, workspaceRoot }) {
  if (typeof sessionKey !== "string" || !sessionKey) {
    throw new Error("host permission contract sessionKey is missing");
  }
  if (typeof workspaceRoot !== "string" || !workspaceRoot) {
    throw new Error("host permission contract workspace is missing");
  }
  const state = {
    sessionKey,
    workspaceRoot: path.resolve(workspaceRoot),
    grantedWriteOnce: false,
    decisions: [],
  };
  const record = (decision) => {
    if (!RUNTIME_OUTCOMES.has(decision.outcome)) {
      throw new Error("host permission decision is invalid");
    }
    state.decisions.push(decision);
    return decision;
  };
  return {
    sessionKey,
    workspaceRoot: state.workspaceRoot,
    intendedRelativePath: INTENDED_WRITE_RELATIVE,
    persisted: false,
    approve_all: false,
    os_sandbox: false,
    fs: false,
    terminal: false,
    ordinary_launch: "unavailable",
    onPermissionRequest: async (request) => {
      const decision = record(decideHostPermission(request, state));
      return { outcome: decision.outcome };
    },
    onElicitation: async () => {
      record({ outcome: "cancel", permission_kind: "elicitation" });
      return { action: "cancel" };
    },
    snapshot() {
      return bodyFreePermissionReceipt(state);
    },
  };
}

export function createHostPermissionContractRegistry() {
  const contracts = new Map();
  return {
    forSession({ sessionKey, workspaceRoot }) {
      const existing = contracts.get(sessionKey);
      if (existing) {
        if (existing.workspaceRoot !== path.resolve(workspaceRoot)) {
          throw new Error("host permission contract workspace drifted");
        }
        return existing;
      }
      const created = createHostPermissionContract({ sessionKey, workspaceRoot });
      contracts.set(sessionKey, created);
      return created;
    },
  };
}
