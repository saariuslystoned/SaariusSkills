#!/usr/bin/env node
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  createVerifiedCandidateAcpRuntime,
  discardCandidateTurnEvents,
  rejectCandidateRuntimeConversationParams,
} from "../../cursor-acp/puppet-adapter.mjs";

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

async function create(payload) {
  const created = await createVerifiedCandidateAcpRuntime({
    cwd: payload.cwd,
    sessionStore: memorySessionStore(),
    agentRegistry: {
      resolve() {
        return [process.execPath, PEER];
      },
      list() {
        return ["antigravity", "candidate"];
      },
    },
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
