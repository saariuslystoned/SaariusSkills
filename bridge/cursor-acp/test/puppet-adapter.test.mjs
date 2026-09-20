import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  ACPX_HEAD,
  ACPX_ORDINARY_PINNED_PACKAGE,
  ACPX_SOURCE,
  AdapterError,
  CursorAcpxAdapter,
  FORBIDDEN_CALLBACKS,
  SyntheticRuntime,
  acpxDependencyIdentity,
  adapterAvailable,
  auditDurableArtifacts,
  callerOutcomes,
  claimIsolatedRoot,
  publicRuntimeBoundary,
  requireHumanQuestion,
  validatePublicRuntimeOptions,
} from "../puppet-adapter.mjs";

async function privateRoot() {
  const root = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-"));
  const isolated = path.join(root, "isolated");
  const workspace = path.join(root, "workspace");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  await mkdir(workspace);
  return { root, isolated, workspace };
}

test("disabled surface pins draft acpx identity and does not change ordinary routes", async () => {
  const pin = acpxDependencyIdentity();
  assert.equal(pin.source, ACPX_SOURCE);
  assert.equal(pin.head, ACPX_HEAD);
  assert.equal(pin.status, "draft");
  assert.equal(pin.ordinary_pinned_package, ACPX_ORDINARY_PINNED_PACKAGE);
  assert.equal(pin.ordinary_route_unchanged, true);
  assert.equal(pin.merged, false);
  assert.equal(pin.released, false);
  assert.equal(pin.integrity, acpxDependencyIdentity().integrity);
  const boundary = publicRuntimeBoundary();
  assert.equal(boundary.available, false);
  assert.equal(boundary.fs, false);
  assert.equal(boundary.terminal, false);
  assert.equal(boundary.approve_all, false);
  assert.equal(boundary.ordinary_launch, "unavailable");
  assert.equal(adapterAvailable(), false);
  assert.equal(CursorAcpxAdapter.available(), false);
  const ordinary = await readFile(new URL("../broker.mjs", import.meta.url), "utf8");
  const disabled = await readFile(new URL("../puppet-adapter.mjs", import.meta.url), "utf8");
  assert.match(ordinary, /permissionMode: "approve-all"/);
  assert.doesNotMatch(disabled, /permissionMode:\s*"approve-all"/);
  assert.doesNotMatch(disabled, /mcpServers:\s*\[/);
  assert.doesNotMatch(ordinary, /createCursorAcpxAdapter|puppet-adapter/);
});

test("public runtime rejects approve-all and MCP broker policy", () => {
  const accepted = validatePublicRuntimeOptions({
    cwd: "/tmp/isolated",
    sessionStore: { mode: "memory" },
    agentRegistry: { peer: "synthetic" },
    fs: false,
    terminal: false,
  });
  assert.equal(accepted.sessionStore, "memory_only");
  assert.throws(
    () => validatePublicRuntimeOptions({
      cwd: "/tmp/isolated",
      sessionStore: {},
      agentRegistry: {},
      fs: false,
      terminal: false,
      permissionMode: "approve-all",
    }),
    (error) => error instanceof AdapterError && error.code === "BROKER_POLICY",
  );
});

test("completion stays distinct from controller acceptance", () => {
  const completed = callerOutcomes({ workerCompletion: "reported" });
  assert.equal(completed.worker_completion, "reported");
  assert.equal(completed.controller_acceptance, "none");
  assert.equal(completed.distinct, true);
  const accepted = callerOutcomes({
    workerCompletion: "reported",
    controllerAcceptance: "accepted",
  });
  assert.equal(accepted.controller_acceptance, "accepted");
  assert.notEqual(accepted.worker_completion, accepted.controller_acceptance);
});

test("reconnect/load retains exact session identity", async () => {
  const { isolated } = await privateRoot();
  const runtime = new SyntheticRuntime({ isolatedRoot: isolated });
  const adapter = new CursorAcpxAdapter({
    isolatedRoot: isolated,
    owner: "puppet-owner",
    session: "cursor-acp-session",
    conversationId: "conv-cursor-acp-1",
    runtime,
  });
  await adapter.claim();
  const first = adapter.bindSession();
  const loaded = adapter.reconnect();
  assert.deepEqual(first, loaded);
  runtime.sessions.set("cursor-acp-session", {
    session: "other-session",
    conversation_id: "conv-cursor-acp-1",
  });
  assert.throws(
    () => adapter.reconnect(),
    (error) => error instanceof AdapterError && error.code === "SESSION_MISMATCH",
  );
});

test("cancellation is not independently observed halt", async () => {
  const { isolated } = await privateRoot();
  const adapter = new CursorAcpxAdapter({
    isolatedRoot: isolated,
    owner: "puppet-owner",
    session: "cursor-acp-session",
    conversationId: "conv-cursor-acp-1",
  });
  await adapter.claim();
  const requested = adapter.requestCancel();
  assert.equal(requested.status, "cancellation-requested");
  assert.equal(requested.halt, "none");
  assert.throws(
    () => adapter.observeHalt(),
    (error) => error instanceof AdapterError && error.code === "HALT_UNOBSERVED",
  );
  const halt = adapter.observeHalt({ observed: true });
  assert.equal(halt.halted, true);
});

test("unsupported question requires human input and cancels without an invented answer", () => {
  const cancelled = requireHumanQuestion({
    state: "interaction_required",
    interaction_id: "question-1",
    human_required: true,
    outcome: "cancelled",
    invented_answer: null,
  });
  assert.equal(cancelled.outcome, "cancelled");
  assert.equal(cancelled.invented_answer, null);
  assert.throws(
    () => requireHumanQuestion({
      state: "interaction_required",
      interaction_id: "question-1",
      human_required: true,
      outcome: "cancelled",
      invented_answer: "yes",
    }),
    (error) => error instanceof AdapterError && error.code === "INVENTED_ANSWER",
  );
});

test("forbidden callbacks have no local side effect", async () => {
  const { isolated, workspace } = await privateRoot();
  const runtime = new SyntheticRuntime({
    isolatedRoot: isolated,
    workspaceRoot: workspace,
    requestedCallbacks: FORBIDDEN_CALLBACKS,
  });
  const rejected = runtime.rejectCallbacks();
  assert.equal(rejected.local_side_effect, false);
  assert.deepEqual(rejected.rejected, [...FORBIDDEN_CALLBACKS]);
  assert.deepEqual(await readdir(workspace), []);
});

test("durable artifacts stay body-free and missing proof fails closed", async () => {
  const { isolated } = await privateRoot();
  await claimIsolatedRoot(isolated, {
    owner: "puppet-owner",
    session: "cursor-acp-session",
    conversationId: "conv-cursor-acp-1",
  });
  const audit = await auditDurableArtifacts(isolated);
  assert.equal(audit.body_retained, false);
  const ownership = await readFile(path.join(isolated, "ownership.json"), "utf8");
  assert.equal(ownership.includes('"prompt"'), false);
  assert.equal(ownership.includes('"messages"'), false);
  const empty = path.join(isolated, "empty");
  await mkdir(empty, { mode: 0o700 });
  await chmod(empty, 0o700);
  await assert.rejects(
    () => auditDurableArtifacts(empty),
    (error) => error instanceof AdapterError && error.code === "PROOF_MISSING",
  );
});

test("process-query failure leaves cleanup unknown and blocks replacement", async () => {
  const { isolated } = await privateRoot();
  const runtime = new SyntheticRuntime({
    isolatedRoot: isolated,
    processQuery: async () => {
      throw new Error("process query failed");
    },
  });
  const adapter = new CursorAcpxAdapter({
    isolatedRoot: isolated,
    owner: "puppet-owner",
    session: "cursor-acp-session",
    conversationId: "conv-cursor-acp-1",
    runtime,
  });
  await adapter.claim();
  await assert.rejects(
    () => runtime.queryProcess(),
    (error) => error instanceof AdapterError && error.code === "CLEANUP_UNKNOWN",
  );
  await assert.rejects(
    () => claimIsolatedRoot(isolated, {
      owner: "puppet-owner",
      session: "cursor-acp-session",
      conversationId: "conv-cursor-acp-1",
    }),
    (error) => error instanceof AdapterError && error.code === "CLEANUP_UNKNOWN",
  );
});

test("duplicate isolated-root ownership is rejected", async () => {
  const { isolated } = await privateRoot();
  await claimIsolatedRoot(isolated, {
    owner: "puppet-owner",
    session: "cursor-acp-session",
    conversationId: "conv-cursor-acp-1",
  });
  await assert.rejects(
    () => claimIsolatedRoot(isolated, {
      owner: "other-owner",
      session: "cursor-acp-session",
      conversationId: "conv-cursor-acp-1",
    }),
    (error) => error instanceof AdapterError && error.code === "DUPLICATE_OWNER",
  );
});
