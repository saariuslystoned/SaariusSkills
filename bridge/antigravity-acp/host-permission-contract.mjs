// Host-owned per-session permission contract for the AGY candidate
// createAcpRuntime route. Decisions are one-time and in-memory only.
// This is not an OS sandbox: fs:false/terminal:false disable ACP client
// callbacks, but the agent process can still write any reachable path.
// Agent-supplied paths are matched as host-policy equality only.
// toolCallId is an opaque per-session identifier, never a permission kind.
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
  "edit",
  "denied",
  "interaction",
  "elicitation",
  "ambiguous",
]);
export const ACP_TOOL_KINDS = Object.freeze([
  "read",
  "edit",
  "delete",
  "move",
  "search",
  "execute",
  "think",
  "fetch",
  "switch_mode",
  "other",
]);
export const KIND_SOURCES = Object.freeze(["standardized", "inferred", "absent"]);
export const ID_CLASSES = Object.freeze(["opaque", "interaction", "absent"]);
export const PATH_SOURCES = Object.freeze([
  "raw_input",
  "locations",
  "both",
  "absent",
  "multiple",
  "conflicting",
]);
export const PATH_CARDINALITIES = Object.freeze(["zero", "one", "multiple"]);
export const PATH_CLASSES = Object.freeze(["intended", "non_intended", "absent", "ambiguous"]);
export const OPTION_KINDS = Object.freeze([
  "allow_once",
  "allow_always",
  "reject_once",
  "reject_always",
]);
export const PERMISSION_REASONS = Object.freeze([
  "granted_once",
  "replay",
  "absent_kind",
  "other_kind",
  "inferred_kind_only",
  "absent_path",
  "multiple_paths",
  "conflicting_paths",
  "non_intended_path",
  "absent_allow_once",
  "interaction",
  "elicitation",
  "ambiguous",
  "missing_session",
]);

const RUNTIME_OUTCOMES = new Set(["allow_once", "reject_once", "cancel"]);
const ACP_KIND_SET = new Set(ACP_TOOL_KINDS);
const OPTION_KIND_SET = new Set(OPTION_KINDS);

function pickEnum(value, allowed, fallback) {
  return allowed.includes(value) ? value : fallback;
}

function requestRaw(request) {
  return request?.raw ?? request;
}

function requestToolCall(request) {
  const raw = requestRaw(request);
  return raw?.toolCall ?? raw?.params?.toolCall ?? {};
}

export function isInteractionQuestion(request) {
  return classifyIdClass(requestToolCallId(request)) === "interaction";
}

export function intendedWritePath(workspaceRoot) {
  if (typeof workspaceRoot !== "string" || !workspaceRoot) {
    throw new Error("host permission workspace is missing");
  }
  return path.resolve(workspaceRoot, INTENDED_WRITE_RELATIVE);
}

export function requestToolCallId(request) {
  const raw = requestRaw(request);
  const toolCall = requestToolCall(request);
  const candidates = [
    toolCall?.toolCallId,
    raw?.toolCallId,
    request?.toolCallId,
    raw?.params?.toolCallId,
  ];
  for (const id of candidates) {
    if (typeof id === "string" && id) return id;
  }
  return undefined;
}

export function classifyIdClass(toolCallId) {
  if (typeof toolCallId !== "string" || !toolCallId) return "absent";
  if (toolCallId.startsWith("interaction_")) return "interaction";
  return "opaque";
}

function readPathCandidate(value) {
  if (typeof value === "string" && value.trim()) return value.trim();
  return undefined;
}

function officialRawInputPath(toolCall) {
  const input = toolCall?.rawInput;
  if (!input || typeof input !== "object" || Array.isArray(input)) return undefined;
  return readPathCandidate(input.path);
}

function officialLocationPaths(toolCall) {
  const locations = Array.isArray(toolCall?.locations) ? toolCall.locations : [];
  const found = [];
  for (const location of locations) {
    const candidate = readPathCandidate(location?.path);
    if (candidate) found.push(candidate);
  }
  return found;
}

export function requestWritePaths(request) {
  const toolCall = requestToolCall(request);
  const found = new Set();
  const rawInputPath = officialRawInputPath(toolCall);
  if (rawInputPath) found.add(rawInputPath);
  for (const locationPath of officialLocationPaths(toolCall)) {
    found.add(locationPath);
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

function classifyKind(request) {
  const standardized = requestToolCall(request)?.kind;
  const inferred = request?.inferredKind;
  if (ACP_KIND_SET.has(standardized)) {
    return { kind: standardized, kind_source: "standardized" };
  }
  if (ACP_KIND_SET.has(inferred)) {
    return { kind: inferred, kind_source: "inferred" };
  }
  return { kind: "absent", kind_source: "absent" };
}

function classifyOfficialPaths(request, workspaceRoot) {
  const toolCall = requestToolCall(request);
  const rawInputPath = officialRawInputPath(toolCall);
  const locationPaths = officialLocationPaths(toolCall);
  const resolvedRaw = rawInputPath ? resolveWorkspacePath(workspaceRoot, rawInputPath) : undefined;
  const resolvedLocations = [
    ...new Set(
      locationPaths
        .map((candidate) => resolveWorkspacePath(workspaceRoot, candidate))
        .filter(Boolean),
    ),
  ];
  const unique = new Set();
  if (resolvedRaw) unique.add(resolvedRaw);
  for (const location of resolvedLocations) unique.add(location);
  if (unique.size === 0) {
    return {
      paths: [],
      path_source: "absent",
      path_cardinality: "zero",
      path_class: "absent",
    };
  }
  if (unique.size > 1) {
    const bothSources = Boolean(resolvedRaw) && resolvedLocations.length > 0;
    return {
      paths: [...unique],
      path_source: bothSources ? "conflicting" : "multiple",
      path_cardinality: "multiple",
      path_class: "ambiguous",
    };
  }
  const [resolved] = unique;
  const bothSources = Boolean(resolvedRaw) && resolvedLocations.length > 0;
  return {
    paths: [resolved],
    path_source: bothSources ? "both" : (resolvedRaw ? "raw_input" : "locations"),
    path_cardinality: "one",
    path_class: "ambiguous",
  };
}

export function offeredOptionKinds(request) {
  const raw = requestRaw(request);
  const options = Array.isArray(raw?.options)
    ? raw.options
    : (Array.isArray(raw?.params?.options) ? raw.params.options : []);
  const kinds = [];
  for (const option of options) {
    if (OPTION_KIND_SET.has(option?.kind) && !kinds.includes(option.kind)) {
      kinds.push(option.kind);
    }
  }
  return kinds;
}

function emptyDiagnostics(overrides = {}) {
  return {
    kind: "absent",
    kind_source: "absent",
    id_class: "absent",
    path_source: "absent",
    path_cardinality: "zero",
    path_class: "absent",
    offered_option_kinds: [],
    ...overrides,
  };
}

function decisionWith(outcome, permissionKind, reason, diagnostics) {
  return {
    outcome,
    permission_kind: permissionKind,
    reason,
    ...diagnostics,
  };
}

function receiptOutcome(decision) {
  if (decision.outcome === "allow_once") return "allow_once";
  if (decision.outcome === "reject_once") return "denied";
  return "cancelled";
}

function boundOfferedOptionKinds(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((kind) => OPTION_KIND_SET.has(kind)))];
}

export function boundPermissionDecision(decision) {
  if (!RUNTIME_OUTCOMES.has(decision?.outcome)) {
    throw new Error("host permission decision is invalid");
  }
  return {
    outcome: receiptOutcome(decision),
    permission_kind: pickEnum(decision.permission_kind, HOST_PERMISSION_KINDS, "ambiguous"),
    kind: pickEnum(decision.kind, [...ACP_TOOL_KINDS, "absent"], "absent"),
    kind_source: pickEnum(decision.kind_source, KIND_SOURCES, "absent"),
    id_class: pickEnum(decision.id_class, ID_CLASSES, "absent"),
    path_source: pickEnum(decision.path_source, PATH_SOURCES, "absent"),
    path_cardinality: pickEnum(decision.path_cardinality, PATH_CARDINALITIES, "zero"),
    path_class: pickEnum(decision.path_class, PATH_CLASSES, "absent"),
    offered_option_kinds: boundOfferedOptionKinds(decision.offered_option_kinds),
    reason: pickEnum(decision.reason, PERMISSION_REASONS, "ambiguous"),
  };
}

export function decideHostPermission(request, state) {
  if (!state || typeof state.sessionKey !== "string" || !state.sessionKey) {
    return decisionWith("cancel", "ambiguous", "missing_session", emptyDiagnostics());
  }
  const toolCallId = requestToolCallId(request);
  const idClass = classifyIdClass(toolCallId);
  const classifiedKind = classifyKind(request);
  const paths = classifyOfficialPaths(request, state.workspaceRoot);
  const options = offeredOptionKinds(request);
  const diagnostics = {
    ...classifiedKind,
    id_class: idClass,
    path_source: paths.path_source,
    path_cardinality: paths.path_cardinality,
    path_class: paths.path_class,
    offered_option_kinds: options,
  };
  if (idClass === "interaction") {
    return decisionWith("cancel", "interaction", "interaction", {
      ...diagnostics,
      path_class: paths.path_cardinality === "one" ? "ambiguous" : paths.path_class,
    });
  }
  if (classifiedKind.kind_source !== "standardized") {
    const reason = classifiedKind.kind_source === "inferred" ? "inferred_kind_only" : "absent_kind";
    return decisionWith("cancel", "ambiguous", reason, diagnostics);
  }
  if (classifiedKind.kind !== "edit") {
    return decisionWith("cancel", "ambiguous", "other_kind", diagnostics);
  }
  if (paths.path_source === "conflicting") {
    return decisionWith("cancel", "ambiguous", "conflicting_paths", diagnostics);
  }
  if (paths.path_cardinality === "multiple") {
    return decisionWith("cancel", "ambiguous", "multiple_paths", diagnostics);
  }
  if (paths.path_cardinality !== "one") {
    return decisionWith("cancel", "ambiguous", "absent_path", diagnostics);
  }
  const intended = pathMatchesIntendedWrite(state.workspaceRoot, paths.paths[0]);
  diagnostics.path_class = intended ? "intended" : "non_intended";
  if (!intended) {
    return decisionWith(
      options.includes("reject_once") ? "reject_once" : "cancel",
      "denied",
      "non_intended_path",
      diagnostics,
    );
  }
  if (!options.includes("allow_once")) {
    return decisionWith("cancel", "ambiguous", "absent_allow_once", diagnostics);
  }
  if (state.grantedWriteOnce === true) {
    return decisionWith(
      options.includes("reject_once") ? "reject_once" : "cancel",
      "edit",
      "replay",
      diagnostics,
    );
  }
  state.grantedWriteOnce = true;
  return decisionWith("allow_once", "edit", "granted_once", diagnostics);
}

export function bodyFreePermissionReceipt(state) {
  const decisions = (state?.decisions ?? []).map((decision) => boundPermissionDecision(decision));
  const last = decisions[decisions.length - 1];
  const grantCount = decisions.filter((decision) => decision.outcome === "allow_once").length;
  const outcome = last?.outcome ?? "cancelled";
  return {
    schema: HOST_PERMISSION_SCHEMA,
    state: outcome,
    outcome,
    permission_id: last?.permission_kind ?? "host",
    permission_kind: last?.permission_kind ?? "ambiguous",
    kind: last?.kind ?? "absent",
    kind_source: last?.kind_source ?? "absent",
    id_class: last?.id_class ?? "absent",
    path_source: last?.path_source ?? "absent",
    path_cardinality: last?.path_cardinality ?? "zero",
    path_class: last?.path_class ?? "absent",
    offered_option_kinds: last?.offered_option_kinds ?? [],
    reason: last?.reason ?? "ambiguous",
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
      record(decisionWith(
        "cancel",
        "elicitation",
        "elicitation",
        emptyDiagnostics({ reason: "elicitation" }),
      ));
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
