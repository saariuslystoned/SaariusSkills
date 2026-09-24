import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  BREAK_GLASS_PERMISSION_MODE,
  BINDER_ENV,
  HostPolicyError,
  LIVE_NON_INTERACTIVE_PERMISSIONS,
  LIVE_PERMISSION_MODE,
  canRebindConversation,
  claimConversationBind,
  isReadinessRed,
  livePermissionDecision,
  refuseUnlessReady,
  resolveBinderId,
  resolveHostConversationId,
  resolveLivePermissionMode,
} from "../../antigravity-acp/host-policy.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));

test("both live bridges ship the same host-policy module", async () => {
  const left = await readFile(path.join(here, "../../antigravity-acp/host-policy.mjs"), "utf8");
  const right = await readFile(path.join(here, "../../cursor-acp/host-policy.mjs"), "utf8");
  assert.equal(left, right);
});

test("live permission default is approve-reads + fail; approve-all is break-glass only", () => {
  assert.deepEqual(resolveLivePermissionMode({}), {
    permissionMode: LIVE_PERMISSION_MODE,
    nonInteractivePermissions: LIVE_NON_INTERACTIVE_PERMISSIONS,
    breakGlass: false,
  });
  assert.equal(resolveLivePermissionMode({}).permissionMode, "approve-reads");
  const glass = resolveLivePermissionMode({ SAARIUS_ACP_PERMISSION_MODE: BREAK_GLASS_PERMISSION_MODE });
  assert.equal(glass.permissionMode, "approve-all");
  assert.equal(glass.breakGlass, true);
  assert.throws(
    () => resolveLivePermissionMode({ SAARIUS_ACP_PERMISSION_MODE: "allow_once" }),
    (error) => error instanceof HostPolicyError && error.code === "INVALID_PERMISSION_MODE",
  );
});

test("live permission decision never grants one-path allow_once", () => {
  assert.deepEqual(
    livePermissionDecision({ raw: { toolCall: { toolCallId: "fs_write_file" } } }),
    { defer: true, reason: "approve_reads_fail" },
  );
  assert.deepEqual(
    livePermissionDecision(
      { raw: { toolCall: { toolCallId: "interaction_1" } } },
      { isInteractionQuestion: (request) => request.raw.toolCall.toolCallId.startsWith("interaction_") },
    ),
    { outcome: "cancel", reason: "interaction_question" },
  );
});

test("readiness red refuses instead of advising", () => {
  assert.equal(isReadinessRed({ ready: true }), false);
  assert.equal(isReadinessRed({ ready: false, error: { code: "RUNTIME_MISSING" } }), true);
  assert.throws(
    () => refuseUnlessReady({ ready: false, error: { code: "AUTH_FALLBACK_FORBIDDEN", message: "blocked" } }),
    (error) => error instanceof HostPolicyError && error.code === "AUTH_FALLBACK_FORBIDDEN",
  );
});

test("conversation bind is owner-gated and does not lock cwd", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-host-policy-"));
  const bindingsRoot = path.join(root, "bindings");
  await mkdir(bindingsRoot, { recursive: true });
  assert.throws(
    () => resolveHostConversationId(undefined, {}, null),
    (error) => error instanceof HostPolicyError && error.code === "HOST_CONVERSATION_REQUIRED",
  );
  assert.equal(resolveBinderId(undefined, { USER: "bobby" }), "bobby");
  const first = await claimConversationBind(bindingsRoot, {
    hostConversationId: "conv-parent",
    binderId: "owner-a",
    jobId: "11111111-1111-4111-8111-111111111111",
    workspace: "/tmp/one",
  });
  assert.equal(first.binderId, "owner-a");
  assert.equal(canRebindConversation(first, "owner-b").ok, false);
  await assert.rejects(
    () => claimConversationBind(bindingsRoot, {
      hostConversationId: "conv-parent",
      binderId: "owner-b",
      jobId: "22222222-2222-4222-8222-222222222222",
      workspace: "/tmp/one",
    }),
    (error) => error instanceof HostPolicyError && error.code === "CONVERSATION_REBIND_FORBIDDEN",
  );
  const rebound = await claimConversationBind(bindingsRoot, {
    hostConversationId: "conv-parent",
    binderId: "owner-a",
    jobId: "33333333-3333-4333-8333-333333333333",
    workspace: "/tmp/two",
  });
  assert.equal(rebound.jobId, "33333333-3333-4333-8333-333333333333");
  assert.equal(rebound.workspace, "/tmp/two");
  const other = await claimConversationBind(bindingsRoot, {
    hostConversationId: "conv-other",
    binderId: "owner-b",
    jobId: "44444444-4444-4444-8444-444444444444",
    workspace: "/tmp/two",
  });
  assert.equal(other.hostConversationId, "conv-other");
  assert.equal(other.workspace, "/tmp/two");
});

test("binder labels cannot override host authority and unsafe rebinds fail closed", async () => {
  assert.throws(
    () => resolveBinderId("system", { [BINDER_ENV]: "host-owner" }),
    (error) => error instanceof HostPolicyError && error.code === "BINDER_ID_NOT_HOST_CONTROLLED",
  );
  assert.equal(canRebindConversation({ binderId: "system" }, "other-owner").ok, false);

  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-host-policy-rebind-"));
  const bindingsRoot = path.join(root, "bindings");
  await mkdir(bindingsRoot, { recursive: true });
  await claimConversationBind(bindingsRoot, {
    hostConversationId: "conv-active",
    binderId: "host-owner",
    jobId: "55555555-5555-4555-8555-555555555555",
    workspace: "/tmp/one",
  });
  await assert.rejects(
    () => claimConversationBind(bindingsRoot, {
      hostConversationId: "conv-active",
      binderId: "host-owner",
      jobId: "66666666-6666-4666-8666-666666666666",
      workspace: "/tmp/two",
    }, { inspectExisting: async () => ({ ok: false, reason: "active" }) }),
    (error) => error instanceof HostPolicyError && error.code === "CONVERSATION_REBIND_UNSAFE",
  );
});

test("conversation claims serialize across concurrent callers", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-host-policy-race-"));
  const bindingsRoot = path.join(root, "bindings");
  await mkdir(bindingsRoot, { recursive: true });
  const record = (jobId) => ({
    hostConversationId: "conv-race",
    binderId: "host-owner",
    jobId,
    workspace: "/tmp/race",
  });
  const first = claimConversationBind(bindingsRoot, record("77777777-7777-4777-8777-777777777777"), {
    atomicWrite: async (target, serialized) => {
      await new Promise((resolve) => setTimeout(resolve, 40));
      await writeFile(target, serialized);
    },
  });
  const second = claimConversationBind(bindingsRoot, record("88888888-8888-4888-8888-888888888888"));
  const settled = await Promise.allSettled([first, second]);
  assert.equal(settled.filter((item) => item.status === "fulfilled").length, 1);
  assert.equal(
    settled.filter((item) => item.status === "rejected")[0].reason.code,
    "CONVERSATION_BIND_BUSY",
  );
});
