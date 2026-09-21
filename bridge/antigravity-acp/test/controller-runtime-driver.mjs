#!/usr/bin/env node
import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import {
  createVerifiedCandidateAcpRuntime,
  discardCandidateTurnEvents,
  materializeVerifiedCandidateAcpx,
  rejectCandidateRuntimeConversationParams,
} from "../../cursor-acp/puppet-adapter.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PEER = fileURLToPath(new URL("./candidate-peer.mjs", import.meta.url));
const ALLOWED_PROCESS_ENV_NAMES = new Set([
  "PATH",
  "GEMINI_HOME",
  "AGY_ACP_FORCE_FILE_STORAGE",
  "HOME",
  "TMPDIR",
  "LANG",
  "ANTIGRAVITY_HARNESS_PATH",
]);
const REQUIRED_PROCESS_ENV_NAMES = [
  "PATH",
  "GEMINI_HOME",
  "AGY_ACP_FORCE_FILE_STORAGE",
  "ANTIGRAVITY_HARNESS_PATH",
];

function memorySessionStore() {
  const sessions = new Map();
  return {
    async load(id) {
      const record = sessions.get(id);
      return record === undefined ? undefined : structuredClone(record);
    },
    async save(record) {
      sessions.set(record.acpxRecordId, structuredClone(record));
    },
  };
}

let runtime;

function send(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

async function candidateRegistry(payload) {
  const materialized = await materializeVerifiedCandidateAcpx({
    runtimeRoot: path.join(REPO_ROOT, "runs/puppet-dual-acp-controller-runs/20260921/runtime"),
  });
  const moduleUrl = pathToFileURL(materialized.modulePath).href;
  const { createAgentRegistry } = await import(moduleUrl);
  const executable = payload?.candidate?.executable;
  if (!executable) {
    throw new Error("antigravity-acp candidate executable is missing");
  }
  const agent = payload?.candidate?.agent || payload?.agent || "antigravity";
  if (agent !== "antigravity") {
    throw new Error("antigravity-acp candidate agent must stay on the agy route");
  }
  return createAgentRegistry({
    overrides: { antigravity: [executable, ...(payload?.candidate?.args || [])] },
  });
}

function syntheticRegistry() {
  return {
    resolve() {
      return [process.execPath, PEER];
    },
    list() {
      return ["antigravity", "candidate"];
    },
  };
}

function applyAllowedProcessEnv(allowed) {
  if (allowed == null || typeof allowed !== "object" || Array.isArray(allowed)) {
    throw new Error("antigravity-acp official candidate process environment is missing");
  }
  const names = Object.keys(allowed);
  if (names.some((name) => !ALLOWED_PROCESS_ENV_NAMES.has(name) || typeof allowed[name] !== "string")) {
    throw new Error("antigravity-acp official candidate process environment is invalid");
  }
  if (REQUIRED_PROCESS_ENV_NAMES.some((name) => typeof allowed[name] !== "string")) {
    throw new Error("antigravity-acp official candidate process environment is invalid");
  }
  if (allowed.AGY_ACP_FORCE_FILE_STORAGE !== "1" || !allowed.GEMINI_HOME || !allowed.ANTIGRAVITY_HARNESS_PATH) {
    throw new Error("antigravity-acp official candidate process environment is invalid");
  }
  for (const key of Object.keys(process.env)) {
    delete process.env[key];
  }
  Object.assign(process.env, allowed);
}

async function create(payload) {
  if (payload.syntheticPeer === true && payload.candidate) {
    throw new Error("synthetic peer injection cannot carry a candidate executable");
  }
  if (payload.syntheticPeer === true && payload.allowedProcessEnv != null) {
    throw new Error("synthetic peer injection cannot carry a candidate process environment");
  }
  if (payload.syntheticPeer !== true) {
    applyAllowedProcessEnv(payload.allowedProcessEnv);
  }
  const agentRegistry = payload.syntheticPeer === true
    ? syntheticRegistry()
    : await candidateRegistry(payload);
  const created = await createVerifiedCandidateAcpRuntime({
    cwd: payload.cwd,
    sessionStore: memorySessionStore(),
    agentRegistry,
    fs: false,
    terminal: false,
    timeoutMs: 30_000,
  }, {
    runtimeRoot: path.join(REPO_ROOT, "runs/puppet-dual-acp-controller-runs/20260921/runtime"),
    isolatedRoot: payload.isolatedRoot,
  });
  runtime = created.runtime;
  return {
    available: false,
    ordinary_launch: "unavailable",
    kind: payload.syntheticPeer === true ? "synthetic_peer" : "qualified_archive",
    artifact_sha256: created.provenance.artifact_sha256,
    merge_commit: created.provenance.merge_commit,
  };
}

function requireRuntime() {
  if (!runtime) {
    throw new Error("controller runtime driver has no public runtime");
  }
  return runtime;
}

async function handle(message) {
  const op = message?.op;
  const payload = message?.payload ?? {};
  if (op === "create") {
    return create(payload);
  }
  const current = requireRuntime();
  if (op === "ensureSession") {
    return current.ensureSession(rejectCandidateRuntimeConversationParams(payload, "ensureSession"));
  }
  if (op === "getStatus") {
    return current.getStatus(rejectCandidateRuntimeConversationParams(payload, "getStatus"));
  }
  if (op === "setModel") {
    if (typeof current.setModel !== "function") {
      throw new Error("setModel is unsupported");
    }
    await current.setModel(rejectCandidateRuntimeConversationParams(payload, "setModel"));
    return {};
  }
  if (op === "startTurn") {
    const turn = current.startTurn(rejectCandidateRuntimeConversationParams(payload, "startTurn"));
    await turn.promptStarted;
    const discarded = await discardCandidateTurnEvents(turn);
    const result = await turn.result;
    return {
      requestId: turn.requestId,
      events: discarded.observed_types.map((type) => ({ type })),
      discarded,
      result: {
        status: result.status,
        stopReason: result.stopReason,
      },
    };
  }
  if (op === "close") {
    try {
      await current.close(rejectCandidateRuntimeConversationParams(payload, "close"));
      return { status: "completed" };
    } catch (error) {
      const isUnsupported = /session\/close/i.test(String(error?.message ?? "")) ||
        error?.code === "ACP_BACKEND_UNSUPPORTED_CONTROL";
      if (isUnsupported && process.env.PUPPET_ANTIGRAVITY_SURVIVING_PEER !== "1") {
        return {
          status: "completed",
          observed: "local_worker_terminated_backend_session_discard_unsupported",
          backendSessionDiscard: "unsupported",
        };
      }
      throw error;
    }
  }
  if (op === "shutdown") {
    await current.shutdown();
    runtime = undefined;
    return {};
  }
  throw new Error(`unsupported controller runtime driver op ${op}`);
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed) continue;
  let message;
  try {
    message = JSON.parse(trimmed);
  } catch {
    send({ ok: false, error: "controller runtime driver message is invalid" });
    continue;
  }
  try {
    const value = await handle(message);
    send({ ok: true, value });
    if (message.op === "shutdown") {
      break;
    }
  } catch (error) {
    send({
      ok: false,
      code: error?.code,
      error: error instanceof Error ? error.message : "controller runtime driver failed",
    });
  }
}
