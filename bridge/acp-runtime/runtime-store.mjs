import { createHash, randomUUID } from "node:crypto";
import { access, lstat, mkdir, readFile, readdir, readlink, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_RUNTIME_ROOT = path.join(homedir(), ".local", "state", "saarius-skills", "acp-runtime");
const NPM_TIMEOUT_MS = 120_000;
const NPM_TERMINATION_TIMEOUT_MS = 5_000;
const RECOVERY_LOCK_TIMEOUT_MS = NPM_TIMEOUT_MS + NPM_TERMINATION_TIMEOUT_MS + 30_000;
const LOCK_OWNER_GRACE_MS = 5_000;
const LOCK_POLL_MS = 100;
const READY_SCHEMA = "saarius.acp.runtime.v2";
const DEPENDENCY_SCHEMA = "saarius.acp.dependencies.v1";
const QUARANTINE_SCHEMA = "saarius.acp.quarantine.v1";

const BRIDGES = Object.freeze({
  "cursor-acp": Object.freeze({
    files: ["server.mjs", "broker.mjs", "host-policy.mjs"],
  }),
  "antigravity-acp": Object.freeze({
    files: ["server.mjs", "broker.mjs", "contract.mjs", "host-policy.mjs"],
  }),
  "grok-acp": Object.freeze({
    files: ["server.mjs", "server-errors.mjs", "broker.mjs", "host-policy.mjs"],
  }),
});

const REQUIRED_IMPORTS = Object.freeze([
  "node_modules/@modelcontextprotocol/sdk/dist/esm/server/mcp.js",
  "node_modules/@modelcontextprotocol/sdk/dist/esm/server/stdio.js",
  "node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js",
  "node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js",
  "node_modules/acpx/dist/runtime.js",
  "node_modules/zod/index.js",
]);

export class RuntimeStoreError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "RuntimeStoreError";
    this.code = code;
    this.details = details;
  }
}

export function runtimeRoot(env = process.env) {
  const configured = env.SAARIUS_ACP_RUNTIME_ROOT?.trim();
  return path.resolve(configured || DEFAULT_RUNTIME_ROOT);
}

export function bridgeNames() {
  return Object.keys(BRIDGES);
}

function bridgeSpec(bridge) {
  const spec = BRIDGES[bridge];
  if (!spec) throw new RuntimeStoreError("UNKNOWN_BRIDGE", `unsupported ACP bridge: ${bridge}`);
  return spec;
}

function hashBytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function hashFile(filePath) {
  return hashBytes(await readFile(filePath));
}

async function dependencyInventory(root) {
  const entries = [];
  const nodeModules = path.join(root, "node_modules");
  async function visit(directory, relativeDirectory) {
    const children = (await readdir(directory, { withFileTypes: true }))
      .sort((left, right) => left.name < right.name ? -1 : left.name > right.name ? 1 : 0);
    for (const child of children) {
      const relativePath = path.join(relativeDirectory, child.name).split(path.sep).join("/");
      const absolutePath = path.join(directory, child.name);
      if (child.isSymbolicLink()) {
        entries.push({ path: relativePath, type: "symlink", target: await readlink(absolutePath) });
      } else if (child.isDirectory()) {
        await visit(absolutePath, relativePath);
      } else if (child.isFile()) {
        entries.push({ path: relativePath, type: "file", sha256: await hashFile(absolutePath) });
      } else {
        throw new RuntimeStoreError("DEPENDENCY_INTEGRITY_UNSUPPORTED", `unsupported dependency entry: ${relativePath}`, { path: relativePath });
      }
    }
  }
  await visit(nodeModules, "node_modules");
  return entries;
}

function dependencyDigest(inventory) {
  return hashBytes(Buffer.from(JSON.stringify(inventory)));
}

function stableDigest(entries) {
  const hash = createHash("sha256");
  for (const entry of entries) hash.update(`${entry.path}\0${entry.sha256}\0`);
  return hash.digest("hex");
}

function sourceRootFor(pluginRoot, bridge) {
  return path.join(pluginRoot, "bridge", bridge);
}

async function readPackageJson(sourceRoot) {
  try {
    return JSON.parse(await readFile(path.join(sourceRoot, "package.json"), "utf8"));
  } catch (error) {
    throw new RuntimeStoreError("SOURCE_ROOT_UNAVAILABLE", "bridge package metadata is unavailable", {
      cause: error?.code ?? "read_failed",
    });
  }
}

export async function describeSource({ pluginRoot, bridge }) {
  const spec = bridgeSpec(bridge);
  const sourceRoot = sourceRootFor(pluginRoot, bridge);
  const files = ["package.json", "package-lock.json", ...spec.files, "../acp-runtime/lifecycle.mjs", "../acp-runtime/recovery.mjs", "../acp-runtime/process-identity.mjs"];
  const entries = [];
  for (const relativePath of files) {
    const absolutePath = path.join(sourceRoot, relativePath);
    try {
      entries.push({ path: relativePath, sha256: await hashFile(absolutePath) });
    } catch (error) {
      throw new RuntimeStoreError("SOURCE_ROOT_UNAVAILABLE", `required bridge source is unavailable: ${relativePath}`, {
        cause: error?.code ?? "read_failed",
      });
    }
  }
  const packageJson = await readPackageJson(sourceRoot);
  const packageDigest = entries.find((entry) => entry.path === "package.json").sha256;
  const lockDigest = entries.find((entry) => entry.path === "package-lock.json").sha256;
  const sourceDigest = stableDigest(entries.filter((entry) => !["package.json", "package-lock.json"].includes(entry.path)));
  const platform = {
    os: process.platform,
    arch: process.arch,
    nodeAbi: process.versions.modules,
    nodeVersion: process.versions.node,
  };
  const identity = hashBytes(Buffer.from(JSON.stringify({
    schema: READY_SCHEMA,
    bridge,
    packageVersion: packageJson.version,
    packageDigest,
    lockDigest,
    sourceDigest,
    platform,
  })));
  return {
    bridge,
    packageVersion: packageJson.version,
    packageDigest,
    lockDigest,
    sourceDigest,
    platform,
    identity,
    sourceRoot,
    files,
    fileDigests: Object.fromEntries(entries.map((entry) => [entry.path, entry.sha256])),
    dependencies: packageJson.dependencies ?? {},
  };
}

function runtimePath(root, descriptor) {
  return path.join(root, descriptor.bridge, descriptor.identity);
}

function copiedSourceRoot(root, descriptor) {
  return path.join(root, "bridge", descriptor.bridge);
}

async function versionAt(root, packageName) {
  const packagePath = path.join(root, "node_modules", packageName, "package.json");
  try {
    return JSON.parse(await readFile(packagePath, "utf8")).version;
  } catch {
    return null;
  }
}

// First differing inventory entry, in path order. Only paths and entry kinds
// are reported; hashes and symlink targets stay inside the tree.
function inventoryDifference(recorded, current) {
  const before = new Map(recorded.map((entry) => [entry.path, JSON.stringify(entry)]));
  const after = new Map(current.map((entry) => [entry.path, JSON.stringify(entry)]));
  const paths = [...new Set([...before.keys(), ...after.keys()])].sort();
  for (const entryPath of paths) {
    if (!after.has(entryPath)) return { path: entryPath, kind: "removed" };
    if (!before.has(entryPath)) return { path: entryPath, kind: "added" };
    if (before.get(entryPath) !== after.get(entryPath)) return { path: entryPath, kind: "changed" };
  }
  return null;
}

async function readJson(filePath) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

// Returns { ok: true } or the first failing check as { ok: false, check, path,
// kind }, with `path` relative to the runtime tree root. Never file contents.
// Like the boolean validator it replaced, it fails closed and never throws.
async function inspectTree(root, descriptor, requireReady) {
  try {
    return await runTreeChecks(root, descriptor, requireReady);
  } catch (error) {
    return { ok: false, check: "unexpected", path: ".", kind: error?.code ?? "error" };
  }
}

async function runTreeChecks(root, descriptor, requireReady) {
  const bridgePath = (relativePath) => `bridge/${descriptor.bridge}/${relativePath}`;
  const fail = (check, relativePath, kind) => ({ ok: false, check, path: relativePath, kind });
  const sourceRoot = copiedSourceRoot(root, descriptor);
  // Prepared trees are always real directories renamed out of staging, so a
  // link here (dangling or not) is foreign and must stay recoverable.
  try {
    const stats = await lstat(root);
    if (stats.isSymbolicLink()) return fail("runtime_root", ".", "symlink");
    if (!stats.isDirectory()) return fail("runtime_root", ".", "not_directory");
  } catch (error) {
    return fail("runtime_root", ".", error?.code === "ENOENT" ? "missing" : "unreadable");
  }
  for (const relativePath of descriptor.files) {
    try {
      await access(path.join(sourceRoot, relativePath));
    } catch {
      return fail("source_file", bridgePath(relativePath), "missing");
    }
  }
  // A prepared tree owns its dependencies; a linked node_modules points outside
  // the content-addressed store and lets writes escape it.
  try {
    const stats = await lstat(path.join(sourceRoot, "node_modules"));
    if (stats.isSymbolicLink()) return fail("dependency_root", bridgePath("node_modules"), "symlink");
    if (!stats.isDirectory()) return fail("dependency_root", bridgePath("node_modules"), "not_directory");
  } catch {
    return fail("dependency_root", bridgePath("node_modules"), "missing");
  }
  for (const relativePath of REQUIRED_IMPORTS) {
    try {
      await access(path.join(sourceRoot, relativePath));
    } catch {
      return fail("required_import", bridgePath(relativePath), "missing");
    }
  }
  const packageJson = await readJson(path.join(sourceRoot, "package.json"));
  if (!packageJson) return fail("package_version", bridgePath("package.json"), "unreadable");
  if (packageJson.version !== descriptor.packageVersion) return fail("package_version", bridgePath("package.json"), "mismatch");
  for (const [name, expected] of Object.entries(descriptor.dependencies)) {
    if (await versionAt(sourceRoot, name) !== expected) return fail("dependency_version", bridgePath(`node_modules/${name}/package.json`), "mismatch");
  }
  for (const relativePath of descriptor.files) {
    let sha256;
    try {
      sha256 = await hashFile(path.join(sourceRoot, relativePath));
    } catch {
      return fail("source_integrity", bridgePath(relativePath), "unreadable");
    }
    if (sha256 !== descriptor.fileDigests[relativePath]) return fail("source_integrity", bridgePath(relativePath), "changed");
  }
  const dependencyRecord = await readJson(path.join(root, "DEPENDENCIES.json"));
  if (!dependencyRecord || !Array.isArray(dependencyRecord.files)) return fail("dependency_record", "DEPENDENCIES.json", "unreadable");
  if (dependencyRecord.schema !== DEPENDENCY_SCHEMA) return fail("dependency_record", "DEPENDENCIES.json", "schema");
  if (dependencyRecord.identity !== descriptor.identity) return fail("dependency_record", "DEPENDENCIES.json", "identity");
  if (dependencyRecord.digest !== dependencyDigest(dependencyRecord.files)) return fail("dependency_record", "DEPENDENCIES.json", "digest");
  let inventory;
  try {
    inventory = await dependencyInventory(sourceRoot);
  } catch (error) {
    return error?.details?.path
      ? fail("dependency_inventory", bridgePath(error.details.path), "unsupported")
      : fail("dependency_inventory", bridgePath("node_modules"), "unreadable");
  }
  if (JSON.stringify(inventory) !== JSON.stringify(dependencyRecord.files)) {
    const difference = inventoryDifference(dependencyRecord.files, inventory) ?? { path: "node_modules", kind: "reordered" };
    return fail("dependency_inventory", bridgePath(difference.path), difference.kind);
  }
  if (requireReady) {
    const ready = await readJson(path.join(root, "READY.json"));
    if (!ready) return fail("ready_record", "READY.json", "unreadable");
    if (ready.schema !== READY_SCHEMA) return fail("ready_record", "READY.json", "schema");
    if (ready.identity !== descriptor.identity) return fail("ready_record", "READY.json", "identity");
    if (JSON.stringify(ready.platform) !== JSON.stringify(descriptor.platform)) return fail("ready_record", "READY.json", "platform");
    if (ready.dependencyDigest !== dependencyRecord.digest) return fail("ready_record", "READY.json", "dependency_digest");
  }
  return { ok: true };
}

function isMissing(inspection) {
  return inspection.check === "runtime_root" && inspection.kind === "missing";
}

function invalidDetails(root, inspection, bridge) {
  return {
    root,
    check: inspection.check,
    path: inspection.path,
    kind: inspection.kind,
    recovery: setupCommand(bridge, { replaceInvalid: true }),
  };
}

// Reports whether the runtime for the current source and Node identity is
// ready, missing, or present but invalid (with the first failing check).
export async function inspectRuntime({ pluginRoot, bridge, env = process.env }) {
  const descriptor = await describeSource({ pluginRoot, bridge });
  const root = runtimePath(runtimeRoot(env), descriptor);
  const inspection = await inspectTree(root, descriptor, true);
  if (inspection.ok) return { descriptor, root, state: "ready" };
  if (isMissing(inspection)) return { descriptor, root, state: "missing" };
  return { descriptor, root, state: "invalid", failure: { check: inspection.check, path: inspection.path, kind: inspection.kind } };
}

export async function findReady({ pluginRoot, bridge, env = process.env }) {
  const inspection = await inspectRuntime({ pluginRoot, bridge, env });
  return inspection.state === "ready" ? { descriptor: inspection.descriptor, root: inspection.root, reused: true } : null;
}

// Moves an invalid same-identity tree aside so a fresh one can be prepared.
// Never deletes: the tree keeps its bytes for forensics next to a small record.
// Callers hold the recovery lock and have just re-validated the tree.
async function quarantineTree({ env, root, descriptor, failure }) {
  const quarantineRoot = path.join(runtimeRoot(env), ".quarantine", descriptor.bridge);
  await mkdir(quarantineRoot, { recursive: true });
  const quarantinedAt = new Date().toISOString();
  const destination = path.join(quarantineRoot, `${descriptor.identity}-${quarantinedAt.replace(/[:.]/g, "-")}-${randomUUID().slice(0, 8)}`);
  const recorded = { check: failure.check, path: failure.path, kind: failure.kind };
  try {
    await rename(root, destination);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw new RuntimeStoreError("RUNTIME_QUARANTINE_FAILED", "invalid runtime could not be moved to quarantine", {
      root,
      cause: error?.code ?? "unknown",
      ...recorded,
    });
  }
  await writeFile(`${destination}.json`, `${JSON.stringify({
    schema: QUARANTINE_SCHEMA,
    bridge: descriptor.bridge,
    identity: descriptor.identity,
    from: root,
    quarantinedAt,
    failure: recorded,
  }, null, 2)}\n`, { mode: 0o644, flag: "wx" });
  return { destination, record: `${destination}.json`, ...recorded };
}

function processAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

// Serializes recoveries per runtime identity. mkdir is the atomic claim. A
// live holder is waited for; a dead holder's lock is left for the operator
// (fail closed) rather than reclaimed, so two waiters can never both proceed.
async function withRecoveryLock({ env, descriptor, timeoutMs }, action) {
  const lock = path.join(runtimeRoot(env), ".locks", `${descriptor.bridge}-${descriptor.identity}.lock`);
  await mkdir(path.dirname(lock), { recursive: true });
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      await mkdir(lock);
      break;
    } catch (error) {
      if (error?.code !== "EEXIST") {
        throw new RuntimeStoreError("RUNTIME_RECOVERY_LOCK_FAILED", "runtime recovery lock could not be created", { lock, cause: error?.code ?? "unknown" });
      }
    }
    const holder = await readJson(path.join(lock, "owner.json"));
    let stale;
    if (Number.isInteger(holder?.pid)) {
      stale = !processAlive(holder.pid);
    } else {
      // A holder writes owner.json right after mkdir; allow it a moment.
      try {
        stale = Date.now() - (await lstat(lock)).mtimeMs > LOCK_OWNER_GRACE_MS;
      } catch {
        continue;
      }
    }
    const details = { lock, pid: Number.isInteger(holder?.pid) ? holder.pid : null };
    if (stale) {
      throw new RuntimeStoreError("RUNTIME_RECOVERY_LOCK_STALE", "an earlier runtime recovery did not finish; remove its lock once no prepare is running", details);
    }
    if (Date.now() >= deadline) {
      throw new RuntimeStoreError("RUNTIME_RECOVERY_BUSY", "another runtime recovery for this identity is still running", details);
    }
    await new Promise((resolve) => setTimeout(resolve, LOCK_POLL_MS));
  }
  try {
    await writeFile(path.join(lock, "owner.json"), `${JSON.stringify({ pid: process.pid, startedAt: new Date().toISOString() })}\n`, { mode: 0o644, flag: "wx" });
    return await action();
  } finally {
    await rm(lock, { recursive: true, force: true });
  }
}

function sanitizeStderr(value) {
  return String(value ?? "")
    .replace(/\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization)\b\s*[:=]\s*[^\s,;]+/gi, (_match, label) => `${label}=[redacted]`)
    .replace(/\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,})\b/g, "[redacted token]")
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [redacted]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 800);
}

function runNpm({ cwd, npmCommand = "npm", npmEnv = {}, timeoutMs = NPM_TIMEOUT_MS, terminationTimeoutMs = NPM_TERMINATION_TIMEOUT_MS, stagingRoot }) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let terminationTimer;
    let timedOut = false;
    const child = spawn(npmCommand, ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], {
      cwd,
      env: { ...process.env, ...npmEnv, npm_config_ignore_scripts: "true" },
      stdio: ["ignore", "ignore", "pipe"],
    });
    let stderr = "";
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk) => { stderr = `${stderr}${chunk}`.slice(-8_000); });
    const timer = setTimeout(() => {
      if (settled) return;
      timedOut = true;
      child.kill("SIGTERM");
      terminationTimer = setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new RuntimeStoreError("DEPENDENCY_INSTALL_TERMINATION_UNCERTAIN", "locked dependency setup did not confirm termination", {
          cleanupSafe: false,
          pid: child.pid,
          stagingRoot,
        }));
      }, terminationTimeoutMs);
    }, timeoutMs);
    child.once("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(terminationTimer);
      reject(new RuntimeStoreError("DEPENDENCY_INSTALL_FAILED", "locked dependency setup could not start", { cause: error.code }));
    });
    child.once("exit", (code, signal) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(terminationTimer);
      if (!timedOut && code === 0) resolve();
      else reject(new RuntimeStoreError(timedOut ? "DEPENDENCY_INSTALL_TIMEOUT" : "DEPENDENCY_INSTALL_FAILED", timedOut ? "locked dependency setup exceeded its bounded timeout" : "locked dependency setup failed", {
        exitCode: code,
        signal,
        stderr: sanitizeStderr(stderr),
        cleanupSafe: true,
      }));
    });
  });
}

async function copySource(descriptor, stagingRoot) {
  const sourceRoot = path.join(stagingRoot, "bridge", descriptor.bridge);
  await mkdir(sourceRoot, { recursive: true });
  for (const relativePath of descriptor.files) {
    const source = path.join(descriptor.sourceRoot, relativePath);
    const destination = path.join(sourceRoot, relativePath);
    await mkdir(path.dirname(destination), { recursive: true });
    const bytes = await readFile(source);
    await writeFile(destination, bytes, { mode: 0o644 });
  }
}

export async function prepareRuntime({ pluginRoot, bridge, env = process.env, npmCommand, npmEnv, timeoutMs = NPM_TIMEOUT_MS, npmTerminationTimeoutMs = NPM_TERMINATION_TIMEOUT_MS, replaceInvalid = false, recoveryLockTimeoutMs = RECOVERY_LOCK_TIMEOUT_MS }) {
  const descriptor = await describeSource({ pluginRoot, bridge });
  const root = runtimePath(runtimeRoot(env), descriptor);
  const existing = await inspectTree(root, descriptor, true);
  if (existing.ok) return { descriptor, root, reused: true };
  const install = (replaced = {}) => installRuntime({ descriptor, root, env, npmCommand, npmEnv, timeoutMs, npmTerminationTimeoutMs, replaced });
  if (isMissing(existing)) return install();
  if (!replaceInvalid) {
    throw new RuntimeStoreError("RUNTIME_IDENTITY_CONFLICT", "existing runtime identity failed integrity validation", invalidDetails(root, existing, bridge));
  }
  return withRecoveryLock({ env, descriptor, timeoutMs: recoveryLockTimeoutMs }, async () => {
    // Re-validate under the lock: an earlier recovery may already have replaced
    // the tree, and a valid runtime must never be moved, even briefly.
    const current = await inspectTree(root, descriptor, true);
    if (current.ok) return { descriptor, root, reused: true };
    if (isMissing(current)) return install();
    const quarantined = await quarantineTree({ env, root, descriptor, failure: current });
    return install(quarantined ? { quarantined } : {});
  });
}

async function installRuntime({ descriptor, root, env, npmCommand, npmEnv, timeoutMs, npmTerminationTimeoutMs, replaced }) {
  const { bridge } = descriptor;
  const stagingRoot = path.join(runtimeRoot(env), ".staging", `${descriptor.bridge}-${descriptor.identity}-${randomUUID()}`);
  try {
    await copySource(descriptor, stagingRoot);
    await runNpm({ cwd: copiedSourceRoot(stagingRoot, descriptor), npmCommand, npmEnv, timeoutMs, terminationTimeoutMs: npmTerminationTimeoutMs, stagingRoot });
    const inventory = await dependencyInventory(copiedSourceRoot(stagingRoot, descriptor));
    const dependencyRecord = {
      schema: DEPENDENCY_SCHEMA,
      identity: descriptor.identity,
      digest: dependencyDigest(inventory),
      files: inventory,
    };
    await writeFile(path.join(stagingRoot, "DEPENDENCIES.json"), `${JSON.stringify(dependencyRecord, null, 2)}\n`, { mode: 0o644 });
    const staged = await inspectTree(stagingRoot, descriptor, false);
    if (!staged.ok) {
      throw new RuntimeStoreError("READY_INTEGRITY_MISMATCH", "installed runtime failed source or dependency integrity validation", {
        check: staged.check,
        path: staged.path,
        kind: staged.kind,
      });
    }
    await writeFile(path.join(stagingRoot, "READY.json"), `${JSON.stringify({
      schema: READY_SCHEMA,
      identity: descriptor.identity,
      bridge: descriptor.bridge,
      packageVersion: descriptor.packageVersion,
      packageDigest: descriptor.packageDigest,
      lockDigest: descriptor.lockDigest,
      sourceDigest: descriptor.sourceDigest,
      dependencyDigest: dependencyRecord.digest,
      platform: descriptor.platform,
    }, null, 2)}\n`, { mode: 0o644 });
    await mkdir(path.dirname(root), { recursive: true });
    try {
      await rename(stagingRoot, root);
      return { descriptor, root, reused: false, ...replaced };
    } catch (error) {
      if (!(["EEXIST", "ENOTEMPTY", "EISDIR"].includes(error?.code))) throw error;
      const concurrent = await inspectTree(root, descriptor, true);
      if (concurrent.ok) {
        await rm(stagingRoot, { recursive: true, force: true });
        return { descriptor, root, reused: true, ...replaced };
      }
      throw new RuntimeStoreError("RUNTIME_IDENTITY_CONFLICT", "another runtime with the same identity is invalid", invalidDetails(root, concurrent, bridge));
    }
  } catch (error) {
    if (error?.details?.cleanupSafe === false) throw error;
    await rm(stagingRoot, { recursive: true, force: true });
    throw error instanceof RuntimeStoreError
      ? error
      : new RuntimeStoreError("RUNTIME_PREPARE_FAILED", "persistent runtime preparation failed", { cause: error?.code ?? "unknown" });
  }
}

export function pluginRootFromModule() {
  return path.resolve(SCRIPT_DIR, "../..");
}

export function setupCommand(bridge, { replaceInvalid = false } = {}) {
  return `${process.execPath} ${path.join(SCRIPT_DIR, "prepare.mjs")} --bridge ${bridge}${replaceInvalid ? " --replace-invalid" : ""}`;
}
