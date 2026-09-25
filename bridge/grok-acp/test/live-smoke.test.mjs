import assert from "node:assert/strict";
import test from "node:test";
import { HostPolicyError } from "../host-policy.mjs";
import {
  BREAK_GLASS_PERMISSION_MODE,
  PERMISSION_MODE_ENV,
} from "../host-policy.mjs";
import {
  createLiveSmokeBroker,
  requireLiveSmokePermission,
} from "../scripts/live-smoke-policy.mjs";

const fakeRuntime = { shutdown: async () => undefined };

test("live smoke refuses default permissions before runtime creation", () => {
  let runtimeCreated = false;
  assert.throws(
    () => createLiveSmokeBroker({
      processEnv: { PATH: "/fake" },
      grokExecutable: "/fake/grok",
      runtimeFactory: () => {
        runtimeCreated = true;
        return fakeRuntime;
      },
    }),
    (error) => error instanceof HostPolicyError && error.code === "LIVE_SMOKE_PERMISSION_REQUIRED",
  );
  assert.equal(runtimeCreated, false);
});

test("live smoke accepts only explicit break-glass and aligns host identity", async () => {
  const processEnv = {
    PATH: "/fake",
    [PERMISSION_MODE_ENV]: BREAK_GLASS_PERMISSION_MODE,
    SAARIUS_ACP_HOST_CONVERSATION_ID: "host-smoke-conversation",
    SAARIUS_ACP_BINDER_ID: "host-smoke-binder",
  };
  let runtimeCreated = false;
  const smoke = createLiveSmokeBroker({
    processEnv,
    grokExecutable: "/fake/grok",
    runtimeFactory: () => {
      runtimeCreated = true;
      return fakeRuntime;
    },
  });
  assert.equal(runtimeCreated, true);
  assert.equal(smoke.hostConversationId, "host-smoke-conversation");
  assert.equal(smoke.binderId, "host-smoke-binder");
  assert.equal(smoke.broker.defaultHostConversationId, smoke.hostConversationId);
  assert.equal(smoke.broker.defaultBinderId, smoke.binderId);
  await smoke.broker.close();
});

test("permission preflight reports the explicit break-glass requirement", () => {
  assert.throws(
    () => requireLiveSmokePermission({}),
    (error) => error instanceof HostPolicyError &&
      error.message.includes(`${PERMISSION_MODE_ENV}=${BREAK_GLASS_PERMISSION_MODE}`),
  );
});
