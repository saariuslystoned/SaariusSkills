import { createHash, randomUUID } from "node:crypto";
import { access, mkdir, readFile, readdir, readlink, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_RUNTIME_ROOT = path.join(homedir(), ".local", "state", "saarius-skills", "acp-runtime");
const NPM_TIMEOUT_MS = 120_000;
const NPM_TERMINATION_TIMEOUT_MS = 5_000;
const READY_SCHEMA = "saarius.acp.runtime.v2";
const DEPENDENCY_SCHEMA = "saarius.acp.dependencies.v1";

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
        throw new RuntimeStoreError("DEPENDENCY_INTEGRITY_UNSUPPORTED", `unsupported dependency entry: ${relativePath}`);
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
  const files = ["package.json", "package-lock.json", ...spec.files];
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

async function validateTree(root, descriptor, requireReady) {
  const sourceRoot = copiedSourceRoot(root, descriptor);
  try {
    for (const relativePath of descriptor.files) await access(path.join(sourceRoot, relativePath));
    for (const relativePath of REQUIRED_IMPORTS) await access(path.join(sourceRoot, relativePath));
    const packageJson = JSON.parse(await readFile(path.join(sourceRoot, "package.json"), "utf8"));
    if (packageJson.version !== descriptor.packageVersion) return false;
    for (const [name, expected] of Object.entries(descriptor.dependencies)) {
      if (await versionAt(sourceRoot, name) !== expected) return false;
    }
    const entries = [];
    for (const relativePath of descriptor.files) {
      entries.push({ path: relativePath, sha256: await hashFile(path.join(sourceRoot, relativePath)) });
    }
    if (entries.find((entry) => entry.path === "package.json").sha256 !== descriptor.packageDigest) return false;
    if (entries.find((entry) => entry.path === "package-lock.json").sha256 !== descriptor.lockDigest) return false;
    if (stableDigest(entries.filter((entry) => !["package.json", "package-lock.json"].includes(entry.path))) !== descriptor.sourceDigest) return false;
    const dependencyRecord = JSON.parse(await readFile(path.join(root, "DEPENDENCIES.json"), "utf8"));
    if (dependencyRecord.schema !== DEPENDENCY_SCHEMA || dependencyRecord.identity !== descriptor.identity) return false;
    if (dependencyRecord.digest !== dependencyDigest(dependencyRecord.files)) return false;
    if (JSON.stringify(await dependencyInventory(sourceRoot)) !== JSON.stringify(dependencyRecord.files)) return false;
    if (requireReady) {
      const ready = JSON.parse(await readFile(path.join(root, "READY.json"), "utf8"));
      if (ready.schema !== READY_SCHEMA || ready.identity !== descriptor.identity) return false;
      if (JSON.stringify(ready.platform) !== JSON.stringify(descriptor.platform)) return false;
      if (ready.dependencyDigest !== dependencyRecord.digest) return false;
    }
    return true;
  } catch {
    return false;
  }
}

export async function findReady({ pluginRoot, bridge, env = process.env }) {
  const descriptor = await describeSource({ pluginRoot, bridge });
  const root = runtimePath(runtimeRoot(env), descriptor);
  return (await validateTree(root, descriptor, true)) ? { descriptor, root, reused: true } : null;
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

export async function prepareRuntime({ pluginRoot, bridge, env = process.env, npmCommand, npmEnv, timeoutMs = NPM_TIMEOUT_MS, npmTerminationTimeoutMs = NPM_TERMINATION_TIMEOUT_MS }) {
  const descriptor = await describeSource({ pluginRoot, bridge });
  const root = runtimePath(runtimeRoot(env), descriptor);
  if (await validateTree(root, descriptor, true)) return { descriptor, root, reused: true };
  try {
    await access(root);
    throw new RuntimeStoreError("RUNTIME_IDENTITY_CONFLICT", "existing runtime identity failed integrity validation");
  } catch (error) {
    if (error instanceof RuntimeStoreError) throw error;
  }
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
    if (!(await validateTree(stagingRoot, descriptor, false))) {
      throw new RuntimeStoreError("READY_INTEGRITY_MISMATCH", "installed runtime failed source or dependency integrity validation");
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
      return { descriptor, root, reused: false };
    } catch (error) {
      if (!(["EEXIST", "ENOTEMPTY", "EISDIR"].includes(error?.code))) throw error;
      if (await validateTree(root, descriptor, true)) {
        await rm(stagingRoot, { recursive: true, force: true });
        return { descriptor, root, reused: true };
      }
      throw new RuntimeStoreError("RUNTIME_IDENTITY_CONFLICT", "another runtime with the same identity is invalid");
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

export function setupCommand(bridge) {
  return `${process.execPath} ${path.join(SCRIPT_DIR, "prepare.mjs")} --bridge ${bridge}`;
}
