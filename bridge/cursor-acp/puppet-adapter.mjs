import { execFile as execFileCallback } from "node:child_process";
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { access, appendFile, lstat, mkdir, readFile, readdir, realpath, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);

export const ACPX_SOURCE = "https://github.com/openclaw/acpx/commit/ce8c3689fe830fd5c6199a8a683dc979d180af1d";
export const ACPX_MERGE_COMMIT = "ce8c3689fe830fd5c6199a8a683dc979d180af1d";
export const ACPX_SOURCE_COMMIT = ACPX_MERGE_COMMIT;
export const ACPX_SOURCE_TREE = "04661dbf3af3b3c2a11d16c3061b40e20ce29f4a";
export const ACPX_HEAD = ACPX_MERGE_COMMIT;
export const ACPX_PR_HEAD = "c64b2751f0b8ca6e9d5613e98f7ed87f778de1b5";
export const ACPX_PR_BASE = "7879505dcf79448cd71cafd82a21aa6c937a3f3e";
export const ACPX_NPM_GIT_HEAD = "8699be1b6428fa7584acc6f07d87f5aec8945f58";
export const ACPX_STATUS = "merged_unreleased";
export const ACPX_ORDINARY_PINNED_PACKAGE = "0.16.0";
export const ACPX_CANDIDATE_PACKAGE_VERSION = "0.18.0";
export const ACPX_PUBLISHED_NPM_VERSION = "0.18.0";
export const ACPX_ARTIFACT_SHA256 = "ad9bc677a6687268010da9c57b83fd96d2d35eddafdb55a6e043fd70679cc342";
export const ACPX_ARTIFACT_PATH = "runs/puppet-acpx-refresh-runs/20260921/artifacts/acpx-0.18.0.tgz";
export const ACPX_CANDIDATE_RUNTIME_ROOT = "runs/puppet-acpx-refresh-runs/20260921/runtime";
export const ACPX_CANDIDATE_RUNTIME_MODULE = `${ACPX_CANDIDATE_RUNTIME_ROOT}/node_modules/acpx/dist/runtime.js`;
export const ACPX_ARTIFACT_RUNTIME_ENTRY = "package/dist/runtime.js";
export const ACPX_ARTIFACT_KIND = "local_exact_source_tarball";
export const ACPX_PUBLIC_SURFACE = "acpx/runtime";
export const ACPX_CONSTRUCTOR = "createAcpRuntime";
export const ACPX_QUALIFICATION = "synthetic_only";
export const CUTOVER_SCHEMA = "puppet.cursor-acpx-cutover/v1";
export const HISTORICAL_ACPX_SOURCE = "https://github.com/openclaw/acpx/pull/648";
export const HISTORICAL_ACPX_MERGE_COMMIT = "ac22c3c8f6d077b542f19524afbe5409e46c56e8";
export const HISTORICAL_ACPX_PR_HEAD = "8de4219c4e87af4dbbc468f0056970d2cda343a2";
export const HISTORICAL_ACPX_PR_BASE = "4e4dcf5bdf4689509169861fefe5cea3a334d5f8";
export const HISTORICAL_ACPX_ARTIFACT_SHA256 = "fe9ba256bc562b01bff007a2e63017a28daebb2dbc460806a6e7ad0f58d32d29";
export const HISTORICAL_ACPX_ARTIFACT_PATH = "runs/puppet-acpx-merged648-runs/20260921/artifacts/acpx-0.18.0.tgz";
export const HISTORICAL_ACPX_CANDIDATE_RUNTIME_ROOT = "runs/puppet-acpx-merged648-runs/20260921/runtime";
export const OBSOLETE_DRAFT_HEADS = Object.freeze([
  "02c03c7abeee0324a71e2114e6b1b4cf7b0785ff",
  "2b7627a6b91b4c94c8a83ad0cc4863f72e8f14de",
]);
export const HISTORICAL_MERGED_HEADS = Object.freeze([
  HISTORICAL_ACPX_MERGE_COMMIT,
  HISTORICAL_ACPX_PR_HEAD,
  HISTORICAL_ACPX_PR_BASE,
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
export const CANDIDATE_TURN_OBSERVED_TYPE_BOUND = 16;
export const CANDIDATE_TURN_OBSERVED_TYPE_LABEL_BOUND = 64;
export const CANDIDATE_TURN_UNKNOWN_TYPE = "unknown";

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
    source_tree: ACPX_SOURCE_TREE,
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
  const sourceTree = requireSha1(value.source_tree, "source tree");
  const head = requireSha1(value.head, "bound head");
  const prHead = requireSha1(value.pr_head, "PR head");
  const prBase = requireSha1(value.pr_base, "PR base");
  const npmGitHead = requireSha1(value.npm_git_head, "npm gitHead");
  if (mergeCommit !== sourceCommit || head !== mergeCommit) {
    throw new AdapterError("IDENTITY_MISMATCH", "merge and source commit must be the exact merged acpx commit");
  }
  if (sourceTree === mergeCommit) {
    throw new AdapterError("IDENTITY_MISMATCH", "source tree is not the merge commit");
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
  if (
    [mergeCommit, sourceCommit, head].some((commit) => HISTORICAL_MERGED_HEADS.includes(commit))
    || value.artifact_sha256 === HISTORICAL_ACPX_ARTIFACT_SHA256
    || value.artifact_path === HISTORICAL_ACPX_ARTIFACT_PATH
    || value.source === HISTORICAL_ACPX_SOURCE
  ) {
    throw new AdapterError("IDENTITY_MISMATCH", "historical #648 candidate identity is not the current pin");
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

function isContainedPath(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === ""
    || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

async function resolveExistingPrefix(targetPath) {
  let current = path.resolve(targetPath);
  const missing = [];
  for (;;) {
    try {
      await lstat(current);
      return path.join(await realpath(current), ...missing.reverse());
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
      const parent = path.dirname(current);
      if (parent === current) throw error;
      missing.push(path.basename(current));
      current = parent;
    }
  }
}

export async function resolveContainedOwnedPath(ownedRoot, targetPath, label = "path") {
  let ownedReal;
  try {
    ownedReal = await realpath(path.resolve(ownedRoot));
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new AdapterError("INVALID_RUNTIME", `${label} owned root is missing`);
    }
    throw error;
  }
  const resolved = await resolveExistingPrefix(targetPath);
  if (!isContainedPath(ownedReal, resolved)) {
    throw new AdapterError("INVALID_RUNTIME", `${label} escapes the owned root`);
  }
  return resolved;
}

async function readArtifactEntry(artifactPath, entryName) {
  const { stdout } = await execFile("tar", ["-xOf", artifactPath, entryName], {
    encoding: "buffer",
    maxBuffer: 8 * 1024 * 1024,
    timeout: 30_000,
  });
  return stdout;
}

function relativeImportSpecifiers(source) {
  const specifiers = new Set();
  const pattern = /(?:from\s+|import\s*\(\s*|import\s+)["'](\.\/[^"']+)["']/g;
  for (const match of String(source).matchAll(pattern)) {
    specifiers.add(match[1]);
  }
  return specifiers;
}

function resolveImportedArtifactEntry(entryName, specifier) {
  if (
    typeof specifier !== "string"
    || !specifier.startsWith("./")
    || specifier.includes("\\")
    || specifier.includes("\0")
    || specifier.includes("..")
  ) {
    throw new AdapterError("IDENTITY_MISMATCH", "installed candidate imported chunk specifier is invalid");
  }
  const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(entryName), specifier));
  if (
    resolved === ".."
    || resolved.startsWith("../")
    || !resolved.startsWith("package/")
    || resolved.includes("..")
  ) {
    throw new AdapterError("IDENTITY_MISMATCH", "installed candidate imported chunk escapes the artifact");
  }
  return resolved;
}

async function proveInstalledRegularFile({
  filePath,
  artifactPath,
  entryName,
  label,
}) {
  let info;
  try {
    info = await lstat(filePath);
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new AdapterError("IDENTITY_MISMATCH", `${label} is missing`);
    }
    throw error;
  }
  if (!info.isFile() || info.isSymbolicLink()) {
    throw new AdapterError("IDENTITY_MISMATCH", `${label} is not a regular file`);
  }
  const installed = await readFile(filePath);
  let expected;
  try {
    expected = await readArtifactEntry(artifactPath, entryName);
  } catch {
    throw new AdapterError("IDENTITY_MISMATCH", `${label} is missing from the artifact`);
  }
  const installedDigest = createHash("sha256").update(installed).digest("hex");
  const expectedDigest = createHash("sha256").update(expected).digest("hex");
  if (installedDigest !== expectedDigest) {
    throw new AdapterError("IDENTITY_MISMATCH", `${label} digest drifted`);
  }
  return { bytes: expected, digest: installedDigest };
}

async function proveInstalledCandidateImportedChunks({
  modulePath,
  artifactPath,
  entryName,
  source,
}) {
  const pending = [{ filePath: modulePath, entryName, source }];
  const seen = new Set([entryName]);
  const imported = [];
  const moduleDir = path.dirname(modulePath);
  while (pending.length) {
    const current = pending.shift();
    for (const specifier of relativeImportSpecifiers(current.source)) {
      const nextEntry = resolveImportedArtifactEntry(current.entryName, specifier);
      if (seen.has(nextEntry)) continue;
      seen.add(nextEntry);
      const nextPath = path.resolve(path.dirname(current.filePath), specifier);
      if (!isContainedPath(moduleDir, nextPath)) {
        throw new AdapterError("IDENTITY_MISMATCH", "installed candidate imported chunk escapes the module directory");
      }
      const proved = await proveInstalledRegularFile({
        filePath: nextPath,
        artifactPath,
        entryName: nextEntry,
        label: "installed candidate imported chunk",
      });
      imported.push({
        artifact_entry: nextEntry,
        sha256: proved.digest,
      });
      pending.push({
        filePath: nextPath,
        entryName: nextEntry,
        source: proved.bytes,
      });
    }
  }
  imported.sort((left, right) => left.artifact_entry.localeCompare(right.artifact_entry));
  return imported;
}

export async function proveInstalledCandidateModule({
  modulePath,
  artifactPath,
  entryName = ACPX_ARTIFACT_RUNTIME_ENTRY,
} = {}) {
  if (!modulePath || !artifactPath) {
    throw new AdapterError("IDENTITY_MISMATCH", "installed candidate runtime proof is incomplete");
  }
  let info;
  try {
    info = await lstat(modulePath);
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new AdapterError("IDENTITY_MISMATCH", "installed candidate runtime is missing");
    }
    throw error;
  }
  if (!info.isFile() || info.isSymbolicLink()) {
    throw new AdapterError("IDENTITY_MISMATCH", "installed candidate runtime is not a regular file");
  }
  const installed = await readFile(modulePath);
  const expected = await readArtifactEntry(artifactPath, entryName);
  const installedDigest = createHash("sha256").update(installed).digest("hex");
  const expectedDigest = createHash("sha256").update(expected).digest("hex");
  if (installedDigest !== expectedDigest) {
    throw new AdapterError("IDENTITY_MISMATCH", "installed candidate runtime digest drifted");
  }
  const importedChunks = await proveInstalledCandidateImportedChunks({
    modulePath,
    artifactPath,
    entryName,
    source: expected,
  });
  return {
    modulePath,
    module_sha256: installedDigest,
    artifact_entry: entryName,
    imported_chunks: importedChunks,
  };
}

async function resolveTaskOwnedCandidateRuntimeRoot(runtimeRoot) {
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
  if (requested === path.resolve(REPO_ROOT, HISTORICAL_ACPX_CANDIDATE_RUNTIME_ROOT)) {
    throw new AdapterError("INVALID_RUNTIME", "historical #648 runtime root is not the current candidate runtime");
  }
  if (
    requested !== allowed
    || relativeToRepo.startsWith("..")
    || path.isAbsolute(relativeToRepo)
  ) {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime root is not the task-owned runtime directory");
  }
  const repoReal = await realpath(REPO_ROOT);
  const resolved = await resolveContainedOwnedPath(repoReal, requested, "candidate runtime root");
  if (resolved !== path.join(repoReal, ACPX_CANDIDATE_RUNTIME_ROOT)) {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime root is not the task-owned runtime directory");
  }
  return resolved;
}

export async function materializeVerifiedCandidateAcpx({ runtimeRoot } = {}) {
  const root = await resolveTaskOwnedCandidateRuntimeRoot(runtimeRoot);
  const artifact = await proveLocalArtifact();
  const artifactPath = path.resolve(REPO_ROOT, ACPX_ARTIFACT_PATH);
  await mkdir(root, { recursive: true, mode: 0o700 });
  const ownedRoot = await resolveContainedOwnedPath(await realpath(REPO_ROOT), root, "candidate runtime root");
  await execFile(
    "npm",
    ["install", "--ignore-scripts", "--no-save", artifactPath],
    {
      cwd: ownedRoot,
      timeout: 120_000,
      env: {
        ...process.env,
        npm_config_ignore_scripts: "true",
      },
    },
  );
  const modulePath = await resolveContainedOwnedPath(
    ownedRoot,
    path.join(ownedRoot, "node_modules", "acpx", "dist", "runtime.js"),
    "candidate runtime module",
  );
  await access(modulePath, constants.R_OK);
  const installed = await proveInstalledCandidateModule({
    modulePath,
    artifactPath,
  });
  return {
    runtimeRoot: ownedRoot,
    modulePath,
    artifact_sha256: artifact.artifact_sha256,
    module_sha256: installed.module_sha256,
    imported_chunks: installed.imported_chunks,
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
  const installed = await proveInstalledCandidateModule({
    modulePath: materialized.modulePath,
    artifactPath: path.resolve(REPO_ROOT, ACPX_ARTIFACT_PATH),
  });
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
      module_sha256: installed.module_sha256,
      imported_chunks: installed.imported_chunks,
      merge_commit: ACPX_MERGE_COMMIT,
      source_tree: ACPX_SOURCE_TREE,
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

function emptyDiscardedTurnEvents(observer) {
  return {
    observer,
    observed_types: [],
    event_count: 0,
    observed_types_truncated: false,
    body_retained: false,
  };
}

function observedTurnEventType(event) {
  if (!event || typeof event !== "object" || typeof event.type !== "string" || event.type.length === 0) {
    return CANDIDATE_TURN_UNKNOWN_TYPE;
  }
  if (event.type.length > CANDIDATE_TURN_OBSERVED_TYPE_LABEL_BOUND) {
    return event.type.slice(0, CANDIDATE_TURN_OBSERVED_TYPE_LABEL_BOUND);
  }
  return event.type;
}

export async function discardCandidateTurnEvents(turn, { limit } = {}) {
  if (!turn || typeof turn !== "object") {
    throw new AdapterError("INVALID_TURN_EVIDENCE", "runtime turn is missing");
  }
  const events = turn.events;
  if (events == null) {
    return emptyDiscardedTurnEvents("absent");
  }
  if (typeof events[Symbol.asyncIterator] !== "function") {
    throw new AdapterError("INVALID_TURN_EVIDENCE", "runtime turn events are not iterable");
  }
  const observed = [];
  let count = 0;
  let truncated = false;
  try {
    for await (const event of events) {
      const label = observedTurnEventType(event);
      if (!observed.includes(label)) {
        if (observed.length < CANDIDATE_TURN_OBSERVED_TYPE_BOUND) {
          observed.push(label);
        } else {
          truncated = true;
        }
      }
      count += 1;
      if (Number.isInteger(limit) && limit > 0 && count >= limit) {
        break;
      }
    }
  } finally {
    // Upstream #672 releases queued events only after iteration ends. This
    // does not prove never-started or indefinitely slow observers. A metadata
    // cap must not break this loop; only an explicit consume limit may.
  }
  return {
    observer: "ended",
    observed_types: observed,
    event_count: count,
    observed_types_truncated: truncated,
    body_retained: false,
  };
}

export async function recordBoundCandidateTurn(options = {}) {
  if (!options || typeof options !== "object") {
    throw new AdapterError("INVALID_RUNTIME", "candidate turn options are invalid");
  }
  rejectCandidateRuntimeConversationParams(options, "candidate turn");
  const {
    isolatedRoot,
    workspaceRoot,
    owner,
    hostSession,
    hostConversationId,
    requestId,
    runtime,
    agent = "candidate",
    mode = "oneshot",
    text,
  } = options;
  const root = await requirePrivateRoot(isolatedRoot);
  requireIdentityString(owner, "host owner identity");
  requireIdentityString(hostSession, "host session identity");
  requireIdentityString(hostConversationId, "host conversation identity");
  requireIdentityString(requestId, "host request identity");
  requireIdentityString(workspaceRoot, "candidate workspace");
  requireIdentityString(text, "candidate turn input");
  if (typeof agent !== "string" || !agent) {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime agent is missing");
  }
  if (mode !== "oneshot" && mode !== "persistent") {
    throw new AdapterError("INVALID_RUNTIME", "candidate runtime session mode is invalid");
  }
  if (
    !runtime
    || typeof runtime.ensureSession !== "function"
    || typeof runtime.getStatus !== "function"
    || typeof runtime.startTurn !== "function"
    || typeof runtime.close !== "function"
  ) {
    throw new AdapterError("INVALID_RUNTIME", "candidate public runtime is incomplete");
  }

  await requireBoundCandidateClaim({
    isolatedRoot,
    owner,
    hostSession,
    hostConversationId,
  });

  const ensureInput = rejectCandidateRuntimeConversationParams({
    sessionKey: hostSession,
    agent,
    mode,
    cwd: workspaceRoot,
  }, "ensureSession");
  const handle = await runtime.ensureSession(ensureInput);
  try {
    requireOwnedCandidateHandle(handle, { hostSession, workspaceRoot });
  } catch (error) {
    await persistCleanupUnknownBestEffort(root);
    throw error;
  }

  let settled = false;
  try {
    const binding = await bindCandidateRuntime({
      isolatedRoot,
      workspaceRoot,
      owner,
      hostSession,
      hostConversationId,
      requestId,
      handle,
    });

    const statusInput = rejectCandidateRuntimeConversationParams({ handle }, "getStatus");
    await runtime.getStatus(statusInput);

    const startInput = rejectCandidateRuntimeConversationParams({
      handle,
      text,
      mode: "prompt",
      requestId,
    }, "startTurn");
    const turn = runtime.startTurn(startInput);
    if (!turn || typeof turn !== "object") {
      throw new AdapterError("INVALID_TURN_EVIDENCE", "runtime turn is missing");
    }
    await turn.promptStarted;
    const discardedEvents = await discardCandidateTurnEvents(turn);
    if (discardedEvents.body_retained !== false) {
      throw new AdapterError("BODY_RETAINED", "candidate turn events retained a body");
    }
    const result = await turn.result;
    const bounded = boundedCandidateTurnResult(result);
    if (typeof turn.requestId !== "string" || !turn.requestId) {
      throw new AdapterError("INVALID_TURN_EVIDENCE", "returned turn request identity is missing");
    }
    if (turn.requestId !== requestId) {
      throw new AdapterError("INVALID_TURN_EVIDENCE", "returned turn request does not match the host request");
    }

    const afterStatus = await runtime.getStatus({ handle });
    let lastRequestId;
    if (afterStatus && typeof afterStatus === "object" && Object.hasOwn(afterStatus, "lastRequestId")) {
      if (typeof afterStatus.lastRequestId !== "string" || afterStatus.lastRequestId !== turn.requestId) {
        throw new AdapterError(
          "INVALID_TURN_EVIDENCE",
          "status lastRequestId does not match the completed turn request",
        );
      }
      lastRequestId = afterStatus.lastRequestId;
    }

    const terminal = {
      event: "runtime_turn_completed",
      host: binding.host,
      turn: {
        requestId: turn.requestId,
        status: bounded.status,
        stopReason: bounded.stopReason,
      },
    };
    if (lastRequestId !== undefined) {
      terminal.status = { lastRequestId };
    }
    rejectBodyKeys(terminal, "runtime turn");
    await appendEvent(root, terminal);

    try {
      await closeOwnedCandidateSession(runtime, handle);
      settled = true;
    } catch (error) {
      await persistCleanupUnknownBestEffort(root);
      settled = true;
      throw error;
    }

    return {
      binding,
      handle: binding.runtime,
      turn: {
        requestId: turn.requestId,
        status: bounded.status,
        stopReason: bounded.stopReason,
      },
      result: bounded,
      status: lastRequestId === undefined ? {} : { lastRequestId },
      closed: true,
      body_retained: false,
      available: adapterAvailable(),
      ordinary_launch: "unavailable",
    };
  } catch (error) {
    if (!settled) {
      try {
        await closeOwnedCandidateSession(runtime, handle);
      } catch {
        await persistCleanupUnknownBestEffort(root);
      }
    }
    throw error;
  }
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

const CONVERSATION_PARAM_KEYS = Object.freeze([
  "conversation",
  "conversationId",
  "conversation_id",
]);
const CANDIDATE_RUNTIME_HANDLE_FIELDS = Object.freeze([
  "sessionKey",
  "backend",
  "runtimeSessionName",
  "cwd",
  "acpxRecordId",
  "backendSessionId",
  "agentSessionId",
]);
const REQUIRED_CANDIDATE_RUNTIME_HANDLE_FIELDS = Object.freeze([
  "sessionKey",
  "backend",
  "runtimeSessionName",
  "cwd",
  "acpxRecordId",
  "backendSessionId",
]);

export function rejectCandidateRuntimeConversationParams(value, label = "runtime call") {
  if (!value || typeof value !== "object") {
    throw new AdapterError("INVALID_RUNTIME", `${label} is invalid`);
  }
  for (const key of CONVERSATION_PARAM_KEYS) {
    if (Object.hasOwn(value, key)) {
      throw new AdapterError(
        "INVALID_RUNTIME",
        `${label} must not include nonexistent conversation parameters`,
      );
    }
  }
  if (value.handle && typeof value.handle === "object") {
    for (const key of CONVERSATION_PARAM_KEYS) {
      if (Object.hasOwn(value.handle, key)) {
        throw new AdapterError(
          "INVALID_RUNTIME",
          `${label} must not include nonexistent conversation parameters`,
        );
      }
    }
  }
  return value;
}

function requireIdentityString(value, label) {
  if (typeof value !== "string" || !value) {
    throw new AdapterError("PROOF_MISSING", `${label} is missing`);
  }
  return value;
}

function projectCandidateRuntimeHandle(handle) {
  if (!handle || typeof handle !== "object") {
    throw new AdapterError("PROOF_MISSING", "runtime handle is missing");
  }
  rejectBodyKeys(handle, "runtime handle");
  rejectCandidateRuntimeConversationParams(handle, "runtime handle");
  const projected = {};
  for (const key of CANDIDATE_RUNTIME_HANDLE_FIELDS) {
    if (!Object.hasOwn(handle, key)) {
      if (REQUIRED_CANDIDATE_RUNTIME_HANDLE_FIELDS.includes(key)) {
        throw new AdapterError("PROOF_MISSING", `runtime handle ${key} is missing`);
      }
      continue;
    }
    const value = handle[key];
    if (typeof value !== "string" || !value) {
      if (REQUIRED_CANDIDATE_RUNTIME_HANDLE_FIELDS.includes(key)) {
        throw new AdapterError("PROOF_MISSING", `runtime handle ${key} is missing`);
      }
      continue;
    }
    projected[key] = value;
  }
  return projected;
}

async function loadOwnedCandidateClaim(isolatedRoot) {
  const root = await requirePrivateRoot(isolatedRoot);
  const ownershipPath = path.join(root, "ownership.json");
  let claim;
  try {
    claim = JSON.parse(await readFile(ownershipPath, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new AdapterError("PROOF_MISSING", "isolated-root ownership proof is missing");
    }
    throw error;
  }
  rejectBodyKeys(claim, "ownership");
  if (claim.acpx) {
    validateAcpxDependencyIdentity(claim.acpx);
  }
  if (claim.cleanup === "unknown" || claim.replacement_blocked) {
    throw new AdapterError("CLEANUP_UNKNOWN", "process query failed; cleanup is unknown");
  }
  return { root, claim };
}

async function requireBoundCandidateClaim({ isolatedRoot, owner, hostSession, hostConversationId }) {
  const { root, claim } = await loadOwnedCandidateClaim(isolatedRoot);
  const boundOwner = requireIdentityString(owner, "host owner identity");
  const boundSession = requireIdentityString(hostSession, "host session identity");
  const boundConversation = requireIdentityString(hostConversationId, "host conversation identity");
  if (claim.owner !== boundOwner) {
    throw new AdapterError("OWNER_MISMATCH", "ownership claim owner does not match the bound owner");
  }
  if (claim.session !== boundSession) {
    throw new AdapterError("SESSION_MISMATCH", "ownership claim session does not match the host session");
  }
  if (claim.conversation_id !== boundConversation) {
    throw new AdapterError("SESSION_MISMATCH", "ownership claim conversation does not match the host conversation");
  }
  return { root, claim, owner: boundOwner, hostSession: boundSession, hostConversationId: boundConversation };
}

function requireOwnedCandidateHandle(handle, { hostSession, workspaceRoot }) {
  const runtimeHandle = projectCandidateRuntimeHandle(handle);
  if (runtimeHandle.sessionKey !== hostSession) {
    throw new AdapterError("SESSION_MISMATCH", "runtime sessionKey does not match the host session");
  }
  if (path.resolve(runtimeHandle.cwd) !== path.resolve(workspaceRoot)) {
    throw new AdapterError("WORKSPACE_MISMATCH", "runtime cwd does not match the candidate workspace");
  }
  return runtimeHandle;
}

export async function markCleanupUnknown(isolatedRoot) {
  const root = await requirePrivateRoot(isolatedRoot);
  const ownershipPath = path.join(root, "ownership.json");
  const current = JSON.parse(await readFile(ownershipPath, "utf8"));
  rejectBodyKeys(current, "ownership");
  if (current.acpx) {
    validateAcpxDependencyIdentity(current.acpx);
  }
  current.cleanup = "unknown";
  current.replacement_blocked = true;
  await writeJson(ownershipPath, current);
  await appendEvent(root, {
    event: "cleanup_unknown",
    session: current.session,
    conversation_id: current.conversation_id,
    replacement_blocked: true,
  });
  return current;
}

async function persistCleanupUnknownBestEffort(isolatedRoot) {
  try {
    await markCleanupUnknown(isolatedRoot);
  } catch {
    // Keep the original failure when the existing claim fence cannot be persisted.
  }
}

function closeOwnedCandidateSession(runtime, handle) {
  return runtime.close({
    handle,
    reason: "candidate-runtime-bound-close",
    discardPersistentState: true,
  });
}

export async function bindCandidateRuntime({
  isolatedRoot,
  workspaceRoot,
  owner,
  hostSession,
  hostConversationId,
  requestId,
  handle,
} = {}) {
  const { root } = await requireBoundCandidateClaim({
    isolatedRoot,
    owner,
    hostSession,
    hostConversationId,
  });
  const boundSession = requireIdentityString(hostSession, "host session identity");
  const boundConversation = requireIdentityString(hostConversationId, "host conversation identity");
  const boundRequest = requireIdentityString(requestId, "host request identity");
  const boundWorkspace = requireIdentityString(workspaceRoot, "candidate workspace");
  const runtimeHandle = requireOwnedCandidateHandle(handle, {
    hostSession: boundSession,
    workspaceRoot: boundWorkspace,
  });
  const binding = {
    host: {
      session: boundSession,
      conversation_id: boundConversation,
      request_id: boundRequest,
    },
    runtime: runtimeHandle,
  };
  rejectBodyKeys(binding, "runtime binding");
  await appendEvent(root, {
    event: "runtime_bound",
    host: binding.host,
    runtime: binding.runtime,
  });
  return binding;
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
      await markCleanupUnknown(this.isolatedRoot);
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
