import { execFile as execFileCallback } from "node:child_process";
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { access, appendFile, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);

export const ACPX_SOURCE = "https://github.com/openclaw/acpx/pull/648";
export const ACPX_MERGE_COMMIT = "ac22c3c8f6d077b542f19524afbe5409e46c56e8";
export const ACPX_SOURCE_COMMIT = ACPX_MERGE_COMMIT;
export const ACPX_HEAD = ACPX_MERGE_COMMIT;
export const ACPX_PR_HEAD = "8de4219c4e87af4dbbc468f0056970d2cda343a2";
export const ACPX_PR_BASE = "4e4dcf5bdf4689509169861fefe5cea3a334d5f8";
export const ACPX_NPM_GIT_HEAD = "8699be1b6428fa7584acc6f07d87f5aec8945f58";
export const ACPX_STATUS = "merged_unreleased";
export const ACPX_ORDINARY_PINNED_PACKAGE = "0.16.0";
export const ACPX_CANDIDATE_PACKAGE_VERSION = "0.18.0";
export const ACPX_PUBLISHED_NPM_VERSION = "0.18.0";
export const ACPX_ARTIFACT_SHA256 = "fe9ba256bc562b01bff007a2e63017a28daebb2dbc460806a6e7ad0f58d32d29";
export const ACPX_ARTIFACT_PATH = "runs/puppet-acpx-merged648-runs/20260921/artifacts/acpx-0.18.0.tgz";
export const ACPX_CANDIDATE_RUNTIME_ROOT = "runs/puppet-acpx-merged648-runs/20260921/runtime";
export const ACPX_CANDIDATE_RUNTIME_MODULE = `${ACPX_CANDIDATE_RUNTIME_ROOT}/node_modules/acpx/dist/runtime.js`;
export const ACPX_ARTIFACT_KIND = "local_exact_source_tarball";
export const ACPX_PUBLIC_SURFACE = "acpx/runtime";
export const ACPX_CONSTRUCTOR = "createAcpRuntime";
export const ACPX_QUALIFICATION = "synthetic_only";
export const CUTOVER_SCHEMA = "puppet.cursor-acpx-cutover/v1";
export const OBSOLETE_DRAFT_HEADS = Object.freeze([
  "02c03c7abeee0324a71e2114e6b1b4cf7b0785ff",
  "2b7627a6b91b4c94c8a83ad0cc4863f72e8f14de",
]);
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SHA1_RE = /^[0-9a-f]{40}$/;
const SHA256_RE = /^[0-9a-f]{64}$/;
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

function metadataIntegrityHash(value) {
  const body = Object.fromEntries(
    Object.entries(value).filter(([key]) => key !== "schema" && key !== "integrity"),
  );
  return createHash("sha256").update(canonicalJson(body), "utf8").digest("hex");
}

function requireSha1(value, label) {
  if (typeof value !== "string" || !SHA1_RE.test(value)) {
    throw new AdapterError("IDENTITY_MISMATCH", `${label} must be a full 40-character lowercase SHA`);
  }
  return value;
}

function requireSha256(value, label) {
  if (typeof value !== "string" || !SHA256_RE.test(value)) {
    throw new AdapterError("IDENTITY_MISMATCH", `${label} must be a lowercase SHA-256`);
  }
  return value;
}

export function acpxDependencyIdentity() {
  const pin = {
    source: ACPX_SOURCE,
    head: ACPX_HEAD,
    merge_commit: ACPX_MERGE_COMMIT,
    source_commit: ACPX_SOURCE_COMMIT,
    pr_head: ACPX_PR_HEAD,
    pr_base: ACPX_PR_BASE,
    npm_git_head: ACPX_NPM_GIT_HEAD,
    status: ACPX_STATUS,
    ordinary_pinned_package: ACPX_ORDINARY_PINNED_PACKAGE,
    candidate_package_version: ACPX_CANDIDATE_PACKAGE_VERSION,
    published_npm_version: ACPX_PUBLISHED_NPM_VERSION,
    published_npm_contains_merge: false,
    ordinary_route_unchanged: true,
    qualification: ACPX_QUALIFICATION,
    merged: true,
    released: false,
    public_surface: ACPX_PUBLIC_SURFACE,
    constructor: ACPX_CONSTRUCTOR,
    artifact_kind: ACPX_ARTIFACT_KIND,
    artifact_path: ACPX_ARTIFACT_PATH,
    artifact_sha256: ACPX_ARTIFACT_SHA256,
  };
  return {
    schema: "puppet.cursor-acpx-dependency/v1",
    ...pin,
    integrity: ACPX_ARTIFACT_SHA256,
  };
}

export function validateAcpxDependencyIdentity(value) {
  if (!value || typeof value !== "object") {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx dependency identity is invalid");
  }
  rejectBodyKeys(value, "acpx identity");
  if (value.status === "draft") {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx draft-state identity is obsolete");
  }
  if (value.merged !== true) {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx source is not the merged commit");
  }
  if (value.released === true) {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx candidate is not a released package");
  }
  if (value.qualification !== ACPX_QUALIFICATION) {
    throw new AdapterError("IDENTITY_MISMATCH", "cursor-acpx cannot claim live qualification");
  }
  if (value.published_npm_contains_merge === true) {
    throw new AdapterError("IDENTITY_MISMATCH", "published npm acpx@0.18.0 does not contain the merge");
  }
  if (value.ordinary_pinned_package !== ACPX_ORDINARY_PINNED_PACKAGE) {
    throw new AdapterError("IDENTITY_MISMATCH", "ordinary production pin must stay 0.16.0");
  }
  if (value.candidate_package_version !== ACPX_CANDIDATE_PACKAGE_VERSION) {
    throw new AdapterError("IDENTITY_MISMATCH", "candidate package version drifted");
  }
  const mergeCommit = requireSha1(value.merge_commit, "merge commit");
  const sourceCommit = requireSha1(value.source_commit, "source commit");
  const head = requireSha1(value.head, "bound head");
  const prHead = requireSha1(value.pr_head, "PR head");
  const prBase = requireSha1(value.pr_base, "PR base");
  const npmGitHead = requireSha1(value.npm_git_head, "npm gitHead");
  if (mergeCommit !== sourceCommit || head !== mergeCommit) {
    throw new AdapterError("IDENTITY_MISMATCH", "merge and source commit must be the exact merged acpx commit");
  }
  if (mergeCommit === npmGitHead) {
    throw new AdapterError("IDENTITY_MISMATCH", "stale npm gitHead is not the merge commit");
  }
  if (mergeCommit === prHead || mergeCommit === prBase) {
    throw new AdapterError("IDENTITY_MISMATCH", "PR head or base is not the merge commit");
  }
  if ([mergeCommit, prHead, prBase, npmGitHead].some((commit) => OBSOLETE_DRAFT_HEADS.includes(commit))) {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx draft-state identity is obsolete");
  }
  const artifact = requireSha256(value.artifact_sha256, "acpx artifact");
  const integrity = requireSha256(value.integrity, "acpx integrity");
  if (integrity === metadataIntegrityHash(value)) {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx artifact integrity must not be a hash of descriptive metadata");
  }
  if (integrity !== artifact) {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx artifact integrity must be the tarball digest");
  }
  const expected = acpxDependencyIdentity();
  if (canonicalJson(value) !== canonicalJson(expected)) {
    throw new AdapterError("IDENTITY_MISMATCH", "acpx source identity drifted");
  }
  return expected;
}

export async function proveLocalArtifact(artifactPath) {
  const relative = artifactPath ?? path.join(REPO_ROOT, ACPX_ARTIFACT_PATH);
  const digest = createHash("sha256").update(await readFile(relative)).digest("hex");
  if (digest !== ACPX_ARTIFACT_SHA256) {
    throw new AdapterError("IDENTITY_MISMATCH", "local acpx artifact digest drifted");
  }
  return {
    kind: ACPX_ARTIFACT_KIND,
    path: artifactPath ? String(relative) : ACPX_ARTIFACT_PATH,
    artifact_sha256: digest,
    candidate_package_version: ACPX_CANDIDATE_PACKAGE_VERSION,
    released: false,
    published_npm_contains_merge: false,
  };
}

export function cutoverSafeguards() {
  return {
    schema: CUTOVER_SCHEMA,
    available: false,
    ordinary_launch: "unavailable",
    ordinary_pinned_package: ACPX_ORDINARY_PINNED_PACKAGE,
    candidate_package_version: ACPX_CANDIDATE_PACKAGE_VERSION,
    released: false,
    published_npm_contains_merge: false,
    qualification: ACPX_QUALIFICATION,
    live_qualification: false,
    production_enabled: false,
    public_pr: false,
    ordinary_route_unchanged: true,
  };
}

export function validateCutoverSafeguards(value) {
  const expected = cutoverSafeguards();
  const current = value ?? expected;
  if (canonicalJson(current) !== canonicalJson(expected)) {
    throw new AdapterError("IDENTITY_MISMATCH", "cursor-acpx cutover safeguards drifted");
  }
  if (
    current.available !== false
    || current.production_enabled !== false
    || current.released !== false
    || current.public_pr !== false
    || current.live_qualification !== false
    || current.ordinary_launch !== "unavailable"
  ) {
    throw new AdapterError("IDENTITY_MISMATCH", "cursor-acpx must not enable production or ordinary launch");
  }
  return expected;
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
    qualification: ACPX_QUALIFICATION,
    live_qualification: false,
    merged_callback_options: ["fs", "terminal"],
    callback_omit_default: "enabled",
    callback_persisted: false,
    os_sandbox: false,
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

function resolveTaskOwnedCandidateRuntimeRoot(runtimeRoot) {
  const allowed = path.resolve(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT);
  const requested = path.resolve(runtimeRoot ?? allowed);
  const bridgeRoot = path.resolve(REPO_ROOT, "bridge");
  const relativeToRepo = path.relative(REPO_ROOT, requested);
  if (
    requested === path.resolve(REPO_ROOT, "node_modules")
    || requested.includes(`${path.sep}node_modules${path.sep}`)
    || requested.endsWith(`${path.sep}node_modules`)
  ) {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime cannot use shared node_modules");
  }
  if (
    requested === bridgeRoot
    || requested.startsWith(`${bridgeRoot}${path.sep}`)
  ) {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime cannot use the repo bridge directory");
  }
  if (
    requested !== allowed
    || relativeToRepo.startsWith("..")
    || path.isAbsolute(relativeToRepo)
  ) {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime root is not the task-owned runtime directory");
  }
  return allowed;
}

export async function materializeVerifiedCandidateAcpx({ runtimeRoot } = {}) {
  const root = resolveTaskOwnedCandidateRuntimeRoot(runtimeRoot);
  const artifact = await proveLocalArtifact();
  await mkdir(root, { recursive: true, mode: 0o700 });
  await execFile(
    "npm",
    ["install", "--ignore-scripts", "--no-save", path.resolve(REPO_ROOT, ACPX_ARTIFACT_PATH)],
    {
      cwd: root,
      timeout: 120_000,
      env: {
        ...process.env,
        npm_config_ignore_scripts: "true",
      },
    },
  );
  const modulePath = path.join(root, "node_modules", "acpx", "dist", "runtime.js");
  await access(modulePath, constants.R_OK);
  return {
    runtimeRoot: root,
    modulePath,
    artifact_sha256: artifact.artifact_sha256,
    lifecycle_scripts: "disabled",
  };
}

export async function createVerifiedCandidateAcpRuntime(options, { runtimeRoot, isolatedRoot } = {}) {
  if (!options || typeof options !== "object") {
    throw new AdapterError("INVALID_RUNTIME", "public runtime options are invalid");
  }
  if (FORBIDDEN_RUNTIME_OPTIONS.some((key) => key in options)) {
    throw new AdapterError("BROKER_POLICY", "approve-all or MCP broker policy is not imported");
  }
  const unknown = Object.keys(options).filter((key) => !PUBLIC_RUNTIME_OPTIONS.includes(key));
  if (unknown.length) {
    throw new AdapterError("PRIVATE_RUNTIME", "public runtime options include private fields");
  }
  if (options.fs === true || options.terminal === true) {
    throw new AdapterError("CALLBACKS_ENABLED", "filesystem and terminal callbacks must stay disabled");
  }
  const forced = {
    ...options,
    fs: false,
    terminal: false,
  };
  validatePublicRuntimeOptions(forced);
  if (isolatedRoot) {
    await requirePrivateRoot(isolatedRoot);
  }
  const materialized = await materializeVerifiedCandidateAcpx({ runtimeRoot });
  const moduleUrl = pathToFileURL(materialized.modulePath).href;
  const { createAcpRuntime } = await import(moduleUrl);
  if (typeof createAcpRuntime !== "function") {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime public export is missing");
  }
  return {
    runtime: createAcpRuntime(forced),
    provenance: {
      module_path: materialized.modulePath,
      artifact_sha256: materialized.artifact_sha256,
      lifecycle_scripts: "disabled",
      available: adapterAvailable(),
      ordinary_launch: "unavailable",
      qualification: ACPX_QUALIFICATION,
    },
  };
}

export function boundedCandidateTurnResult(value) {
  if (!value || typeof value !== "object") {
    throw new AdapterError("PROOF_MISSING", "candidate turn result is missing");
  }
  rejectBodyKeys(value, "candidate turn result");
  if (typeof value.status !== "string" || typeof value.stopReason !== "string") {
    throw new AdapterError("PROOF_MISSING", "candidate turn result is incomplete");
  }
  return {
    status: value.status,
    stopReason: value.stopReason,
    body_retained: false,
    availability: {
      available: adapterAvailable(),
      ordinary_launch: "unavailable",
    },
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
    qualification: ACPX_QUALIFICATION,
    available: false,
    cleanup: "owned",
    replacement_blocked: false,
    acpx: validateAcpxDependencyIdentity(acpxDependencyIdentity()),
  };
  const ownershipPath = path.join(root, "ownership.json");
  try {
    await access(ownershipPath, constants.F_OK);
    const existing = JSON.parse(await readFile(ownershipPath, "utf8"));
    validateAcpxDependencyIdentity(existing.acpx);
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
