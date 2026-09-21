import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmod, mkdir, mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  ACPX_ARTIFACT_PATH,
  ACPX_ARTIFACT_SHA256,
  ACPX_CANDIDATE_PACKAGE_VERSION,
  ACPX_HEAD,
  ACPX_MERGE_COMMIT,
  ACPX_NPM_GIT_HEAD,
  ACPX_ORDINARY_PINNED_PACKAGE,
  ACPX_PR_BASE,
  ACPX_PR_HEAD,
  ACPX_SOURCE,
  ACPX_SOURCE_COMMIT,
  AdapterError,
  CursorAcpxAdapter,
  FORBIDDEN_CALLBACKS,
  SyntheticRuntime,
  acpxDependencyIdentity,
  adapterAvailable,
  auditDurableArtifacts,
  callerOutcomes,
  claimIsolatedRoot,
  cutoverSafeguards,
  proveLocalArtifact,
  publicRuntimeBoundary,
  requireHumanQuestion,
  validateAcpxDependencyIdentity,
  validateCutoverSafeguards,
  validatePublicRuntimeOptions,
} from "../puppet-adapter.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

function canonicalJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

function metadataHash(pin) {
  const body = Object.fromEntries(
    Object.entries(pin).filter(([key]) => key !== "schema" && key !== "integrity"),
  );
  return createHash("sha256").update(canonicalJson(body), "utf8").digest("hex");
}

async function privateRoot() {
  const root = await mkdtemp(path.join(os.tmpdir(), "puppet-acpx-"));
  const isolated = path.join(root, "isolated");
  const workspace = path.join(root, "workspace");
  await mkdir(isolated, { mode: 0o700 });
  await chmod(isolated, 0o700);
  await mkdir(workspace);
  return { root, isolated, workspace };
}

test("disabled surface pins merged unreleased acpx identity and does not change ordinary routes", async () => {
  const pin = validateAcpxDependencyIdentity(acpxDependencyIdentity());
  assert.equal(pin.source, ACPX_SOURCE);
  assert.equal(pin.head, ACPX_HEAD);
  assert.equal(pin.status, "merged_unreleased");
  assert.equal(pin.ordinary_pinned_package, ACPX_ORDINARY_PINNED_PACKAGE);
  assert.equal(pin.candidate_package_version, ACPX_CANDIDATE_PACKAGE_VERSION);
  assert.equal(pin.ordinary_route_unchanged, true);
  assert.equal(pin.merged, true);
  assert.equal(pin.released, false);
  assert.equal(pin.integrity, pin.artifact_sha256);
  assert.equal(pin.artifact_sha256, ACPX_ARTIFACT_SHA256);
  assert.notEqual(pin.integrity, metadataHash(pin));
  assert.equal(pin.integrity, acpxDependencyIdentity().integrity);
  const boundary = publicRuntimeBoundary();
  assert.equal(boundary.available, false);
  assert.equal(boundary.fs, false);
  assert.equal(boundary.terminal, false);
  assert.equal(boundary.approve_all, false);
  assert.equal(boundary.ordinary_launch, "unavailable");
  assert.deepEqual(boundary.merged_callback_options, ["fs", "terminal"]);
  assert.equal(adapterAvailable(), false);
  assert.equal(CursorAcpxAdapter.available(), false);
  const ordinary = await readFile(new URL("../broker.mjs", import.meta.url), "utf8");
  const disabled = await readFile(new URL("../puppet-adapter.mjs", import.meta.url), "utf8");
  assert.match(ordinary, /permissionMode: "approve-all"/);
  assert.doesNotMatch(disabled, /permissionMode:\s*"approve-all"/);
  assert.doesNotMatch(disabled, /mcpServers:\s*\[/);
  assert.doesNotMatch(ordinary, /createCursorAcpxAdapter|puppet-adapter/);
  assert.match(ordinary, /acpx 0\.16\.0/);
});

test("merged unreleased provenance stays exact and fail-closed", () => {
  const pin = acpxDependencyIdentity();
  assert.equal(pin.merge_commit, ACPX_MERGE_COMMIT);
  assert.equal(pin.source_commit, ACPX_SOURCE_COMMIT);
  assert.equal(pin.pr_head, ACPX_PR_HEAD);
  assert.equal(pin.pr_base, ACPX_PR_BASE);
  assert.equal(pin.npm_git_head, ACPX_NPM_GIT_HEAD);
  assert.equal(new Set([pin.merge_commit, pin.pr_head, pin.pr_base, pin.npm_git_head]).size, 4);
  assert.notEqual(pin.candidate_package_version, pin.ordinary_pinned_package);
  assert.equal(pin.published_npm_contains_merge, false);
  assert.throws(
    () => validateAcpxDependencyIdentity({ ...pin, status: "draft", merged: false }),
    (error) => error instanceof AdapterError && error.code === "IDENTITY_MISMATCH" && /draft-state/.test(error.message),
  );
  assert.throws(
    () => validateAcpxDependencyIdentity({ ...pin, released: true }),
    (error) => error instanceof AdapterError && /not a released package/.test(error.message),
  );
  assert.throws(
    () => validateAcpxDependencyIdentity({
      ...pin,
      merge_commit: ACPX_NPM_GIT_HEAD,
      source_commit: ACPX_NPM_GIT_HEAD,
      head: ACPX_NPM_GIT_HEAD,
    }),
    (error) => error instanceof AdapterError && /stale npm gitHead/.test(error.message),
  );
  assert.throws(
    () => validateAcpxDependencyIdentity({ ...pin, integrity: metadataHash(pin) }),
    (error) => error instanceof AdapterError && /descriptive metadata/.test(error.message),
  );
  assert.throws(
    () => validateAcpxDependencyIdentity({ ...pin, published_npm_contains_merge: true }),
    (error) => error instanceof AdapterError && /does not contain the merge/.test(error.message),
  );
});

test("local artifact digest is source integrity and exposes callback controls", async () => {
  const proved = await proveLocalArtifact();
  assert.equal(proved.artifact_sha256, ACPX_ARTIFACT_SHA256);
  assert.equal(proved.path, ACPX_ARTIFACT_PATH);
  assert.equal(proved.released, false);
  const artifact = path.join(REPO_ROOT, ACPX_ARTIFACT_PATH);
  const { execFileSync } = await import("node:child_process");
  const runtime = execFileSync("tar", ["-xOf", artifact, "package/dist/runtime.d.ts"], { encoding: "utf8" });
  assert.match(runtime, /fs\?: boolean/);
  assert.match(runtime, /terminal\?: boolean/);
  assert.match(runtime, /createAcpRuntime/);
  const decoy = path.join(os.tmpdir(), `acpx-decoy-${process.pid}.tgz`);
  await writeFile(decoy, "not-the-merged-source");
  await assert.rejects(
    () => proveLocalArtifact(decoy),
    (error) => error instanceof AdapterError && /artifact digest drifted/.test(error.message),
  );
});

test("cutover safeguards keep ordinary route disabled", () => {
  const gates = validateCutoverSafeguards();
  assert.equal(gates.available, false);
  assert.equal(gates.ordinary_launch, "unavailable");
  assert.equal(gates.ordinary_pinned_package, "0.16.0");
  assert.equal(gates.candidate_package_version, "0.18.0");
  assert.equal(gates.released, false);
  assert.equal(gates.production_enabled, false);
  assert.equal(gates.public_pr, false);
  assert.equal(gates.ordinary_route_unchanged, true);
  assert.throws(
    () => validateCutoverSafeguards({ ...cutoverSafeguards(), available: true, production_enabled: true }),
    (error) => error instanceof AdapterError && /cutover safeguards/.test(error.message),
  );
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
