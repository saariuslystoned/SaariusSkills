import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { access, appendFile, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";

export const ACPX_SOURCE = "https://github.com/openclaw/acpx/pull/648";
export const ACPX_HEAD = "2b7627a6b91b4c94c8a83ad0cc4863f72e8f14de";
export const ACPX_STATUS = "draft";
export const ACPX_ORDINARY_PINNED_PACKAGE = "0.16.0";
export const ACPX_PUBLIC_SURFACE = "acpx/runtime";
export const ACPX_CONSTRUCTOR = "createAcpRuntime";
export const TRANSPORT_ID = "cursor-acp";
export const ADAPTER_ID = "cursor-acpx";
export const FORBIDDEN_CALLBACKS = Object.freeze([
  "fs/read",
  "fs/write",
  "terminal",
  "terminal/create",
  "terminal/write",
]);
export const BODY_FIELDS = Object.freeze([
  "prompt",
  "response",
  "output",
  "content",
  "text",
  "transcript",
  "title",
  "options",
  "messages",
  "rawInput",
  "rawOutput",
  "body",
]);
export const SECRET_FIELDS = Object.freeze([
  "token",
  "secret",
  "password",
  "credential",
  "authorization",
  "api_key",
]);
export const FORBIDDEN_RUNTIME_OPTIONS = Object.freeze([
  "permissionMode",
  "nonInteractivePermissions",
  "permissionPolicy",
  "onPermissionRequest",
  "mcpServers",
  "sessionPermissions",
  "elicitationModes",
  "agentProcessEnv",
]);
export const PUBLIC_RUNTIME_OPTIONS = Object.freeze([
  "cwd",
  "sessionStore",
  "agentRegistry",
  "fs",
  "terminal",
  "timeoutMs",
  "processLifecycle",
  "probeAgent",
]);

export class AdapterError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "AdapterError";
    this.code = code;
  }
}

function canonicalJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

export function acpxDependencyIdentity() {
  const pin = {
    source: ACPX_SOURCE,
    head: ACPX_HEAD,
    status: ACPX_STATUS,
    ordinary_pinned_package: ACPX_ORDINARY_PINNED_PACKAGE,
    ordinary_route_unchanged: true,
    qualification: "synthetic_only",
    merged: false,
    released: false,
    public_surface: ACPX_PUBLIC_SURFACE,
    constructor: ACPX_CONSTRUCTOR,
  };
  return {
    schema: "puppet.cursor-acpx-dependency/v1",
    ...pin,
    integrity: createHash("sha256").update(canonicalJson(pin), "utf8").digest("hex"),
  };
}

export function publicRuntimeBoundary() {
  return {
    schema: "puppet.cursor-acpx-public-runtime/v1",
    surface: ACPX_PUBLIC_SURFACE,
    constructor: ACPX_CONSTRUCTOR,
    allowed_options: [...PUBLIC_RUNTIME_OPTIONS],
    forbidden_options: [...FORBIDDEN_RUNTIME_OPTIONS],
    fs: false,
    terminal: false,
    permission_policy: "not_imported",
    mcp_broker_policy: "not_imported",
    approve_all: false,
    private_internals: false,
    ordinary_launch: "unavailable",
    available: false,
    qualification: "synthetic_only",
    live_qualification: false,
  };
}

export function adapterAvailable() {
  return false;
}

export function validatePublicRuntimeOptions(value) {
  if (!value || typeof value !== "object") {
    throw new AdapterError("INVALID_RUNTIME", "public runtime options are invalid");
  }
  if (FORBIDDEN_RUNTIME_OPTIONS.some((key) => key in value)) {
    throw new AdapterError("BROKER_POLICY", "approve-all or MCP broker policy is not imported");
  }
  const unknown = Object.keys(value).filter((key) => !PUBLIC_RUNTIME_OPTIONS.includes(key));
  if (unknown.length) {
    throw new AdapterError("PRIVATE_RUNTIME", "public runtime options include private fields");
  }
  if (value.fs !== false || value.terminal !== false) {
    throw new AdapterError("CALLBACKS_ENABLED", "filesystem and terminal callbacks must stay disabled");
  }
  if (!value.cwd || !value.sessionStore || !value.agentRegistry) {
    throw new AdapterError("INVALID_RUNTIME", "public runtime identity is incomplete");
  }
  return {
    cwd: value.cwd,
    sessionStore: "memory_only",
    agentRegistry: "synthetic_peer",
    fs: false,
    terminal: false,
  };
}

function rejectBodyKeys(value, label = "artifact") {
  if (Array.isArray(value)) {
    for (const nested of value) rejectBodyKeys(nested, label);
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, nested] of Object.entries(value)) {
    if (BODY_FIELDS.includes(key) || SECRET_FIELDS.includes(key)) {
      throw new AdapterError("BODY_RETAINED", `${label} contains body-bearing field ${key}`);
    }
    rejectBodyKeys(nested, label);
  }
}

async function requirePrivateRoot(isolatedRoot) {
  const root = path.resolve(isolatedRoot);
  const info = await stat(root);
  if (!info.isDirectory() || (info.mode & 0o777) !== 0o700) {
    throw new AdapterError("ROOT_NOT_PRIVATE", "isolated state root is not current-UID mode 0700");
  }
  return root;
}

async function writeJson(filePath, value) {
  rejectBodyKeys(value, path.basename(filePath));
  await writeFile(filePath, `${JSON.stringify(value)}\n`, { encoding: "utf8", mode: 0o600 });
}

async function appendEvent(root, event) {
  rejectBodyKeys(event, "event");
  await appendFile(path.join(root, "events.jsonl"), `${JSON.stringify(event)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
}

export async function claimIsolatedRoot(isolatedRoot, { owner, session, conversationId }) {
  const root = await requirePrivateRoot(isolatedRoot);
  const claim = {
    schema: "puppet.cursor-acpx-ownership/v1",
    adapter: ADAPTER_ID,
    transport: TRANSPORT_ID,
    owner,
    isolated_root: root,
    session,
    conversation_id: conversationId,
    lease: "not_admitted",
    ordinary_launch: "unavailable",
    qualification: "synthetic_only",
    available: false,
    cleanup: "owned",
    replacement_blocked: false,
    acpx: acpxDependencyIdentity(),
  };
  const ownershipPath = path.join(root, "ownership.json");
  try {
    await access(ownershipPath, constants.F_OK);
    const existing = JSON.parse(await readFile(ownershipPath, "utf8"));
    if (existing.owner !== owner) {
      throw new AdapterError("DUPLICATE_OWNER", "isolated state root is already owned by a different adapter");
    }
    if (existing.cleanup === "unknown" || existing.replacement_blocked) {
      throw new AdapterError("CLEANUP_UNKNOWN", "process-query failure left cleanup unknown; replacement is blocked");
    }
    if (existing.session !== session || existing.conversation_id !== conversationId) {
      throw new AdapterError("SESSION_MISMATCH", "isolated-root session identity does not match the bound session");
    }
    return existing;
  } catch (error) {
    if (error instanceof AdapterError) throw error;
    if (error?.code !== "ENOENT") throw error;
  }
  await writeJson(ownershipPath, claim);
  await appendEvent(root, {
    event: "ownership_claimed",
    owner,
    session,
    conversation_id: conversationId,
  });
  return claim;
}

export class SyntheticRuntime {
  constructor({ isolatedRoot, workspaceRoot, requestedCallbacks = [], processQuery } = {}) {
    this.isolatedRoot = isolatedRoot;
    this.workspaceRoot = workspaceRoot ?? isolatedRoot;
    this.requestedCallbacks = requestedCallbacks;
    this.processQuery = processQuery;
    this.sessions = new Map();
    this.options = validatePublicRuntimeOptions({
      cwd: isolatedRoot,
      sessionStore: { mode: "memory_only" },
      agentRegistry: { peer: "synthetic" },
      fs: false,
      terminal: false,
    });
    this.cancelled = false;
    this.halted = false;
  }

  ensureSession(session, conversationId) {
    const handle = { session, conversation_id: conversationId };
    this.sessions.set(session, handle);
    return { ...handle };
  }

  loadSession(session, conversationId) {
    const stored = this.sessions.get(session);
    if (!stored) {
      throw new AdapterError("PROOF_MISSING", "synthetic runtime session proof is missing");
    }
    if (stored.session !== session || stored.conversation_id !== conversationId) {
      throw new AdapterError("SESSION_MISMATCH", "reconnect did not retain the exact session identity");
    }
    return { ...stored };
  }

  rejectCallbacks() {
    const rejected = [];
    for (const method of this.requestedCallbacks) {
      rejected.push(method);
    }
    return {
      fs: false,
      terminal: false,
      rejected,
      local_side_effect: false,
    };
  }

  async queryProcess() {
    if (!this.processQuery) {
      throw new AdapterError("PROOF_MISSING", "process-query proof is missing");
    }
    try {
      return await this.processQuery();
    } catch (error) {
      const ownershipPath = path.join(this.isolatedRoot, "ownership.json");
      const current = JSON.parse(await readFile(ownershipPath, "utf8"));
      current.cleanup = "unknown";
      current.replacement_blocked = true;
      await writeJson(ownershipPath, current);
      await appendEvent(this.isolatedRoot, {
        event: "cleanup_unknown",
        session: current.session,
        conversation_id: current.conversation_id,
        replacement_blocked: true,
      });
      throw new AdapterError("CLEANUP_UNKNOWN", "process query failed; cleanup is unknown");
    }
  }
}

export function requireHumanQuestion(question) {
  if (question?.state !== "interaction_required" || question.human_required !== true) {
    throw new AdapterError("HUMAN_REQUIRED", "unsupported question requires human input");
  }
  if (question.invented_answer != null) {
    throw new AdapterError("INVENTED_ANSWER", "cursor-acpx must not invent a question answer");
  }
  if (question.outcome !== "cancelled") {
    throw new AdapterError("QUESTION_CANCEL", "unsupported question must cancel without an answer");
  }
  return {
    state: "cancelled",
    interaction_id: question.interaction_id,
    human_required: true,
    outcome: "cancelled",
    invented_answer: null,
  };
}

export function callerOutcomes({ workerCompletion = "none", controllerAcceptance = "none", halt = "none" } = {}) {
  if (workerCompletion === "reported" && controllerAcceptance === "accepted" && halt === "none") {
    return {
      worker_completion: "reported",
      controller_acceptance: "accepted",
      halt: "none",
      distinct: true,
    };
  }
  return {
    worker_completion: workerCompletion,
    controller_acceptance: controllerAcceptance,
    halt,
    distinct: workerCompletion !== controllerAcceptance,
  };
}

export async function auditDurableArtifacts(isolatedRoot) {
  const root = await requirePrivateRoot(isolatedRoot);
  const names = await readdir(root);
  if (!names.length) {
    throw new AdapterError("PROOF_MISSING", "durable cursor-acpx proof is missing");
  }
  let inspected = 0;
  for (const name of names) {
    if (name.endsWith(".lock")) continue;
    const filePath = path.join(root, name);
    const info = await stat(filePath);
    if (!info.isFile()) continue;
    inspected += 1;
    const raw = await readFile(filePath, "utf8");
    for (const line of raw.split(/\n/).filter(Boolean)) {
      rejectBodyKeys(JSON.parse(line), name);
    }
  }
  if (!inspected) {
    throw new AdapterError("PROOF_MISSING", "durable cursor-acpx proof is missing");
  }
  return { ok: true, inspected, body_retained: false };
}

export class CursorAcpxAdapter {
  constructor({ isolatedRoot, owner, session, conversationId, runtime }) {
    this.isolatedRoot = isolatedRoot;
    this.owner = owner;
    this.session = session;
    this.conversationId = conversationId;
    this.runtime = runtime ?? new SyntheticRuntime({ isolatedRoot });
  }

  static available() {
    return false;
  }

  async claim() {
    this.ownership = await claimIsolatedRoot(this.isolatedRoot, {
      owner: this.owner,
      session: this.session,
      conversationId: this.conversationId,
    });
    return this.ownership;
  }

  bindSession() {
    return this.runtime.ensureSession(this.session, this.conversationId);
  }

  reconnect() {
    return this.runtime.loadSession(this.session, this.conversationId);
  }

  requestCancel() {
    this.runtime.cancelled = true;
    return {
      status: "cancellation-requested",
      session: this.session,
      conversation_id: this.conversationId,
      halt: "none",
    };
  }

  observeHalt({ observed = false } = {}) {
    if (!observed) {
      throw new AdapterError("HALT_UNOBSERVED", "cancellation is not independently observed halt");
    }
    this.runtime.halted = true;
    return {
      session: this.session,
      conversation_id: this.conversationId,
      halted: true,
    };
  }
}

export async function ensureDisabledSurfaceRoot(isolatedRoot) {
  await mkdir(isolatedRoot, { recursive: true, mode: 0o700 });
  return isolatedRoot;
}
