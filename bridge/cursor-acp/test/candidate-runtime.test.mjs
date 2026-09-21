import assert from "node:assert/strict";
import { mkdtemp, mkdir, chmod, readFile, readdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  ACPX_ARTIFACT_SHA256,
  ACPX_CANDIDATE_RUNTIME_MODULE,
  ACPX_CANDIDATE_RUNTIME_ROOT,
  ACPX_QUALIFICATION,
  AdapterError,
  CursorAcpxAdapter,
  adapterAvailable,
  auditDurableArtifacts,
  boundedCandidateTurnResult,
  claimIsolatedRoot,
  createVerifiedCandidateAcpRuntime,
  materializeVerifiedCandidateAcpx,
} from "../puppet-adapter.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PEER = fileURLToPath(new URL("./candidate-peer.mjs", import.meta.url));
const TEST_PROMPT = "candidate runtime proof ping";

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

async function privateRoot() {
  const root = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-candidate-"));
  const isolated = path.join(root, "isolated");
  const workspace = path.join(root, "workspace");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  await mkdir(workspace);
  return { root, isolated, workspace };
}

test("candidate runtime rejects bridge, shared modules, and arbitrary roots", async () => {
  await assert.rejects(
    () => materializeVerifiedCandidateAcpx({
      runtimeRoot: path.join(REPO_ROOT, "bridge", "cursor-acp"),
    }),
    (error) => error instanceof AdapterError && /bridge directory/.test(error.message),
  );
  await assert.rejects(
    () => materializeVerifiedCandidateAcpx({
      runtimeRoot: path.join(REPO_ROOT, "bridge", "cursor-acp", "node_modules"),
    }),
    (error) => error instanceof AdapterError && /shared node_modules/.test(error.message),
  );
  await assert.rejects(
    () => materializeVerifiedCandidateAcpx({ runtimeRoot: os.tmpdir() }),
    (error) => error instanceof AdapterError && /task-owned runtime directory/.test(error.message),
  );
});

test("candidate runtime helper stays unavailable and omits prompt bodies", async () => {
  assert.equal(CursorAcpxAdapter.available(), false);
  assert.equal(adapterAvailable(), false);
  await assert.rejects(
    () => createVerifiedCandidateAcpRuntime({
      cwd: "/tmp/isolated",
      sessionStore: memorySessionStore(),
      agentRegistry: { resolve() { return ["candidate"]; }, list() { return ["candidate"]; } },
      fs: false,
      terminal: false,
      permissionMode: "approve-all",
    }, { runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT) }),
    (error) => error instanceof AdapterError && error.code === "BROKER_POLICY",
  );
  await assert.rejects(
    () => createVerifiedCandidateAcpRuntime({
      cwd: "/tmp/isolated",
      sessionStore: memorySessionStore(),
      agentRegistry: { resolve() { return ["candidate"]; }, list() { return ["candidate"]; } },
      fs: true,
      terminal: false,
    }, { runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT) }),
    (error) => error instanceof AdapterError && error.code === "CALLBACKS_ENABLED",
  );
  const bounded = boundedCandidateTurnResult({ status: "completed", stopReason: "end_turn" });
  assert.deepEqual(Object.keys(bounded).sort(), [
    "availability",
    "body_retained",
    "status",
    "stopReason",
  ]);
  assert.equal(bounded.availability.available, false);
  assert.equal(bounded.availability.ordinary_launch, "unavailable");
  assert.throws(
    () => boundedCandidateTurnResult({
      status: "completed",
      stopReason: "end_turn",
      prompt: TEST_PROMPT,
    }),
    (error) => error instanceof AdapterError && error.code === "BODY_RETAINED",
  );
});

test("verified candidate acpx runtime completes one isolated turn", { timeout: 180_000 }, async () => {
  const { isolated, workspace } = await privateRoot();
  const capabilitiesPath = path.join(isolated, "callback-capabilities.json");
  process.env.PUPPET_ACPX_CANDIDATE_PEER_CAPABILITIES = capabilitiesPath;
  await claimIsolatedRoot(isolated, {
    owner: "puppet-owner",
    session: "cursor-acp-session",
    conversationId: "conv-cursor-acp-1",
  });
  const { runtime, provenance } = await createVerifiedCandidateAcpRuntime({
    cwd: workspace,
    sessionStore: memorySessionStore(),
    agentRegistry: {
      resolve() {
        return [process.execPath, PEER];
      },
      list() {
        return ["candidate"];
      },
    },
    fs: false,
    terminal: false,
    timeoutMs: 30_000,
  }, {
    runtimeRoot: path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_ROOT),
    isolatedRoot: isolated,
  });
  try {
    assert.equal(provenance.module_path, path.join(REPO_ROOT, ACPX_CANDIDATE_RUNTIME_MODULE));
    assert.equal(provenance.artifact_sha256, ACPX_ARTIFACT_SHA256);
    assert.equal(provenance.lifecycle_scripts, "disabled");
    assert.equal(provenance.available, false);
    assert.equal(provenance.ordinary_launch, "unavailable");
    assert.equal(provenance.qualification, ACPX_QUALIFICATION);
    assert.equal(CursorAcpxAdapter.available(), false);
    assert.equal(adapterAvailable(), false);

    const handle = await runtime.ensureSession({
      sessionKey: "candidate-runtime-session",
      agent: "candidate",
      mode: "oneshot",
      cwd: workspace,
    });
    const turn = runtime.startTurn({
      handle,
      text: TEST_PROMPT,
      mode: "prompt",
      requestId: "candidate-runtime-turn",
    });
    const result = await turn.result;
    const bounded = boundedCandidateTurnResult(result);
    assert.equal(bounded.status, "completed");
    assert.equal(bounded.stopReason, "end_turn");
    assert.equal(bounded.body_retained, false);
    assert.equal(bounded.availability.available, false);
    assert.equal(bounded.availability.ordinary_launch, "unavailable");
    assert.equal("prompt" in bounded, false);
    assert.equal("response" in bounded, false);
    assert.equal("transcript" in bounded, false);

    const capabilities = JSON.parse(await readFile(capabilitiesPath, "utf8"));
    assert.equal(capabilities.fs, false);
    assert.equal(capabilities.terminal, false);
    assert.deepEqual(Object.keys(capabilities).sort(), ["fs", "terminal"]);

    const audit = await auditDurableArtifacts(isolated);
    assert.equal(audit.body_retained, false);
    const names = await readdir(isolated);
    for (const name of names) {
      if (name.endsWith(".lock")) continue;
      const raw = await readFile(path.join(isolated, name), "utf8");
      assert.equal(raw.includes(TEST_PROMPT), false);
      assert.equal(raw.includes('"prompt"'), false);
      assert.equal(raw.includes('"transcript"'), false);
    }
    assert.equal(CursorAcpxAdapter.available(), false);
    assert.equal(adapterAvailable(), false);
  } finally {
    try {
      await runtime.shutdown();
    } catch {
      // Shutdown must not hide the turn proof.
    }
    delete process.env.PUPPET_ACPX_CANDIDATE_PEER_CAPABILITIES;
  }
});
