import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { BridgeError, DEFAULT_GROK_REASONING_EFFORT, GrokAcpBroker, resolveReasoningEffort } from "../broker.mjs";

test("delegated jobs pin high reasoning effort by default", () => {
  assert.equal(DEFAULT_GROK_REASONING_EFFORT, "high");
  assert.equal(resolveReasoningEffort({}), "high");
});

test("the effort can be overridden or inherited, and bad values fail closed", () => {
  assert.equal(resolveReasoningEffort({ SAARIUS_GROK_ACP_REASONING_EFFORT: " Medium " }), "medium");
  assert.equal(resolveReasoningEffort({ SAARIUS_GROK_ACP_REASONING_EFFORT: "inherit" }), null);
  assert.throws(() => resolveReasoningEffort({ SAARIUS_GROK_ACP_REASONING_EFFORT: "turbo" }), (e) => e instanceof BridgeError && e.code === "INVALID_CONFIG");
});

function fakeRuntime({ advertise = true, obey = true, current = "xhigh" } = {}) {
  const rt = {
    effort: current,
    sets: [],
    async getStatus() {
      return {
        models: { currentModelId: "grok-4.7", availableModelIds: ["grok-4.7"] },
        details: advertise
          ? { configOptions: [{ id: "reasoning_effort", category: "thought_level", currentValue: rt.effort, options: ["xhigh", "high", "medium", "low"].map((value) => ({ value })) }] }
          : {},
      };
    },
    async setConfigOption({ key, value }) { rt.sets.push([key, value]); if (obey) rt.effort = value; },
  };
  return rt;
}

async function broker(runtime, env = {}) {
  const stateRoot = await mkdtemp(path.join(tmpdir(), "grok-effort-"));
  const b = new GrokAcpBroker({ stateRoot, grokExecutable: "/usr/bin/true", processEnv: env, runtime });
  return { b, cleanup: () => rm(stateRoot, { recursive: true, force: true }) };
}

test("the ACP reasoning_effort option is set and confirmed after model selection", async () => {
  const rt = fakeRuntime();
  const { b, cleanup } = await broker(rt);
  try {
    const m = await b.verifyModel({ sessionKey: "k" }, "/tmp");
    assert.deepEqual(rt.sets, [["reasoning_effort", "high"]]);
    assert.deepEqual({ requested: m.reasoningEffort.requested, current: m.reasoningEffort.current }, { requested: "high", current: "high" });
  } finally { await cleanup(); }
});

test("inherit leaves the CLI default untouched", async () => {
  const rt = fakeRuntime();
  const { b, cleanup } = await broker(rt, { SAARIUS_GROK_ACP_REASONING_EFFORT: "inherit" });
  try {
    const m = await b.verifyModel({ sessionKey: "k" }, "/tmp");
    assert.deepEqual(rt.sets, []);
    assert.equal(m.reasoningEffort.current, "xhigh");
  } finally { await cleanup(); }
});

test("missing, unavailable or unconfirmed effort fails closed", async () => {
  for (const [rt, env, code] of [
    [fakeRuntime({ advertise: false }), {}, "REASONING_EFFORT_UNSUPPORTED"],
    [fakeRuntime(), { SAARIUS_GROK_ACP_REASONING_EFFORT: "xhigh" }, null],
    [fakeRuntime({ obey: false }), {}, "REASONING_EFFORT_UNCONFIRMED"],
  ]) {
    const { b, cleanup } = await broker(rt, env);
    try {
      if (code) await assert.rejects(() => b.verifyModel({ sessionKey: "k" }, "/tmp"), (e) => e instanceof BridgeError && e.code === code);
      else assert.equal((await b.verifyModel({ sessionKey: "k" }, "/tmp")).reasoningEffort.current, "xhigh");
    } finally { await cleanup(); }
  }
});
