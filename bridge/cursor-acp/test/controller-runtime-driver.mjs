#!/usr/bin/env node
import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import {
  createVerifiedCandidateAcpRuntime,
  discardCandidateTurnEvents,
  materializeVerifiedCandidateAcpx,
  rejectCandidateRuntimeConversationParams,
} from "../puppet-adapter.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PEER = fileURLToPath(new URL("./candidate-peer.mjs", import.meta.url));

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
    throw new Error("cursor-acp candidate executable is missing");
  }
  const agent = payload?.candidate?.agent || payload?.agent || "cursor";
  if (agent !== "cursor") {
    throw new Error("cursor-acp candidate agent must stay on the cursor route");
  }
  return createAgentRegistry({
    overrides: { cursor: [executable, "acp"] },
  });
}

function syntheticRegistry() {
  return {
    resolve() {
      return [process.execPath, PEER];
    },
    list() {
      return ["candidate"];
    },
  };
}

async function create(payload) {
  if (payload.syntheticPeer === true && payload.candidate) {
    throw new Error("synthetic peer injection cannot carry a candidate executable");
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
    await current.close(rejectCandidateRuntimeConversationParams(payload, "close"));
    return {};
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
