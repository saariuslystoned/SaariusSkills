import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import path from "node:path";

export const HOP_ARGV_ENV = "SAARIUS_ACP_HOP_ARGV";
export const HOP_ROLE_ENV = "SAARIUS_ACP_HOP_ROLE";
export const HOP_WORKER_ROLE = "worker";
export const HOP_WORKER_FLAG = "--worker";
export const MAX_HOP_ARGS = 32;
export const MAX_HOP_ARG_CHARS = 4_096;

const ACPX_BASENAMES = new Set(["acpx", "acpx.cmd", "acpx.exe"]);
const SECRET_PATTERN =
  /\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,})\b|Bearer\s+[A-Za-z0-9._~+/=-]+/i;

export class HopError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "HopError";
    this.code = code;
    this.details = details;
  }
}

function configuredHopArgv(env) {
  const raw = env[HOP_ARGV_ENV];
  return typeof raw === "string" && raw.trim().length > 0 ? raw : "";
}

function argvRequestsWorker(argv) {
  return Array.isArray(argv) && argv.includes(HOP_WORKER_FLAG);
}

function hopRole(env, argv) {
  if (argvRequestsWorker(argv)) return HOP_WORKER_ROLE;
  const role = env[HOP_ROLE_ENV];
  return typeof role === "string" ? role.trim() : "";
}

function mentionsAcpx(value) {
  const base = path.basename(value).toLowerCase();
  return ACPX_BASENAMES.has(base) || value === "--agent";
}

function parseHopArgv(raw) {
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new HopError("HOP_ARGV_INVALID", "SAARIUS_ACP_HOP_ARGV must be a JSON array of command strings");
  }
  if (!Array.isArray(parsed) || parsed.length === 0 || parsed.length > MAX_HOP_ARGS) {
    throw new HopError("HOP_ARGV_INVALID", "SAARIUS_ACP_HOP_ARGV must be a non-empty JSON array of at most 32 strings");
  }
  const argv = [];
  for (const value of parsed) {
    if (typeof value !== "string" || value.length === 0 || value.trim().length === 0) {
      throw new HopError("HOP_ARGV_INVALID", "SAARIUS_ACP_HOP_ARGV entries must be non-empty strings");
    }
    if (value.length > MAX_HOP_ARG_CHARS) {
      throw new HopError("HOP_ARGV_INVALID", "SAARIUS_ACP_HOP_ARGV entry exceeds the bounded length");
    }
    if (SECRET_PATTERN.test(value)) {
      throw new HopError("HOP_SECRET_REFUSED", "SAARIUS_ACP_HOP_ARGV must not carry token-shaped values");
    }
    if (mentionsAcpx(value)) {
      throw new HopError(
        "HOP_ACPX_REFUSED",
        "ACpx must stay a local child on the worker; SaariusSkills owns the hop",
      );
    }
    argv.push(value);
  }
  return argv;
}

export function hopIdentity(argv) {
  return createHash("sha256").update(JSON.stringify(argv)).digest("hex").slice(0, 16);
}

export function workerHopEnv(env = process.env) {
  const childEnv = { ...env };
  delete childEnv[HOP_ARGV_ENV];
  childEnv[HOP_ROLE_ENV] = HOP_WORKER_ROLE;
  return childEnv;
}

export function resolveHop({ env = process.env, bridge, workerMode = false } = {}) {
  const raw = configuredHopArgv(env);
  const role = workerMode ? HOP_WORKER_ROLE : hopRole(env);
  if (role === HOP_WORKER_ROLE && raw) {
    throw new HopError("HOP_NESTED", "worker hop refused: SAARIUS_ACP_HOP_ARGV cannot be set on the worker side", {
      bridge,
    });
  }
  if (!raw) return { mode: "local", role: role || "parent" };
  const argv = parseHopArgv(raw);
  return {
    mode: "hop",
    argv,
    childEnv: workerHopEnv(env),
    identity: hopIdentity(argv),
    role: role === HOP_WORKER_ROLE || argvRequestsWorker(argv) ? HOP_WORKER_ROLE : role || "parent",
  };
}

export function spawnStdioChild({ command, args, env, cwd, stdio = "inherit" }) {
  const child = spawn(command, args, { cwd, env, stdio });
  const forward = (signal) => {
    if (!child.killed) child.kill(signal);
  };
  const onSigint = () => forward("SIGINT");
  const onSigterm = () => forward("SIGTERM");
  process.once("SIGINT", onSigint);
  process.once("SIGTERM", onSigterm);
  const detach = () => {
    process.removeListener("SIGINT", onSigint);
    process.removeListener("SIGTERM", onSigterm);
  };
  child.once("exit", detach);
  child.once("error", detach);
  return child;
}
