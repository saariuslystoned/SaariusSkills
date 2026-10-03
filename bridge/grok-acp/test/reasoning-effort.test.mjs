import test from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { BridgeError, DEFAULT_GROK_MODEL, DEFAULT_GROK_REASONING_EFFORT, GrokAcpBroker, resolveReasoningEffort } from "../broker.mjs";

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
  const stateRoot = await mkdtemp(path.join(os.tmpdir(), "grok-effort-"));
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

// setModel resets thought_level to Low. The realistic success path drifts the
// advertised current model once after the initial High confirmation and before
// the pre-prompt check, so recheck must setModel again. Repeated/coupled drift
// after every effort setter is a separate fail-closed fixture.
class PrePromptReselectionRuntime {
  constructor({
    currentModel = "grok-4.5",
    available = ["grok-4.5", "grok-4.6", "grok-4.7"],
    effort = "xhigh",
    resetEffort = "low",
    advertise = true,
    availableEfforts = ["xhigh", "high", "medium", "low"],
    obey = true,
    driftAfterEffortSet = false,
    driftOnceAfterInitialHigh = true,
    driftAfterFirstStatus = false,
    afterReselection = {},
  } = {}) {
    this.currentModel = currentModel;
    this.available = [...available];
    this.effort = effort;
    this.resetEffort = resetEffort;
    this.advertise = advertise;
    this.availableEfforts = [...availableEfforts];
    this.obey = obey;
    this.driftAfterEffortSet = driftAfterEffortSet;
    this.driftOnceAfterInitialHigh = driftOnceAfterInitialHigh;
    this.driftAfterFirstStatus = driftAfterFirstStatus;
    this.afterReselection = afterReselection;
    this.effortSets = 0;
    this.statusCalls = 0;
    this.modelSets = [];
    this.turns = [];
    this.effortAtStartTurn = null;
    this.armDrift = false;
    this.armedOnceDrift = false;
  }

  status() {
    return {
      models: {
        currentModelId: this.currentModel,
        availableModelIds: this.available,
        availableModels: this.available.map((modelId) => ({ modelId, name: modelId })),
      },
      details: this.advertise
        ? {
          configOptions: [{
            id: "reasoning_effort",
            category: "thought_level",
            type: "select",
            currentValue: this.effort,
            options: this.availableEfforts.map((value) => ({ value, name: value })),
          }],
        }
        : {},
    };
  }

  applyReselectionSideEffects() {
    const next = this.afterReselection;
    if (next.advertise !== undefined) this.advertise = next.advertise;
    if (next.availableEfforts) this.availableEfforts = [...next.availableEfforts];
    if (next.obey !== undefined) this.obey = next.obey;
  }

  async ensureSession(input) {
    return { sessionKey: input.sessionKey, cwd: input.cwd, backend: "fixture" };
  }

  async getStatus() {
    if (this.armDrift) {
      this.currentModel = "grok-4.5";
      this.armDrift = false;
    }
    const status = this.status();
    this.statusCalls += 1;
    if (this.driftAfterFirstStatus && this.statusCalls === 1) this.armDrift = true;
    if (
      this.driftOnceAfterInitialHigh
      && this.effortSets === 1
      && this.effort === "high"
      && !this.armedOnceDrift
    ) {
      this.armDrift = true;
      this.armedOnceDrift = true;
    }
    return status;
  }

  async setModel({ model }) {
    this.modelSets.push(model);
    if (this.available.includes(model)) this.currentModel = model;
    this.effort = this.resetEffort;
    if (this.effortSets > 0) this.applyReselectionSideEffects();
  }

  async setConfigOption({ key, value }) {
    if (key !== "reasoning_effort") return;
    this.effortSets += 1;
    if (this.obey) this.effort = value;
    if (this.driftAfterEffortSet) this.armDrift = true;
  }

  startTurn(input) {
    this.effortAtStartTurn = this.effort;
    const turn = {
      requestId: input.requestId,
      promptStarted: Promise.resolve(),
      events: (async function* () {})(),
      result: Promise.resolve({ status: "completed", stopReason: "fixture complete" }),
      cancel: async () => undefined,
      closeStream: async () => undefined,
    };
    this.turns.push({ input, effort: this.effort, model: this.currentModel });
    return turn;
  }

  async close() {}
  async shutdown() {}
}

function hermeticProcessEnv(overrides = {}) {
  const env = { ...process.env, ...overrides };
  delete env.SAARIUS_ACP_PERMISSION_MODE;
  if (!Object.hasOwn(overrides, "SAARIUS_GROK_ACP_REASONING_EFFORT")) {
    delete env.SAARIUS_GROK_ACP_REASONING_EFFORT;
  }
  return env;
}

async function delegateHarness({ runtime, processEnv } = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-grok-effort-delegate-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "grok");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const broker = new GrokAcpBroker({
    stateRoot: path.join(root, "state"),
    grokExecutable: executable,
    runtime,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    processEnv: hermeticProcessEnv(processEnv),
    defaultBinderId: "test-owner",
  });
  await broker.init();
  return { broker, runtime, workspace, root };
}

test("pre-prompt model reselection keeps required High effort at startTurn", async () => {
  const runtime = new PrePromptReselectionRuntime();
  const { broker, workspace } = await delegateHarness({ runtime });
  const submitted = await broker.delegate({
    workspace,
    prompt: "Keep required High after pre-prompt model reselection.",
    hostConversationId: "conv-effort-reselection",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(runtime.turns.length, 1);
  assert.equal(runtime.effortAtStartTurn, "high");
  assert.equal(runtime.turns[0].model, DEFAULT_GROK_MODEL);
  assert.equal(runtime.turns[0].model, completed.model);
  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(persisted.model.selectedModelId, DEFAULT_GROK_MODEL);
  assert.equal(persisted.model.currentModelId, runtime.turns[0].model);
  assert.equal(persisted.model.reasoningEffort.requested, "high");
  assert.equal(persisted.model.reasoningEffort.current, "high");
  assert.equal(completed.route.reasoningEffort, "high");
  await broker.close();
});

test("pre-prompt coupled model drift after every effort set fails closed without a prompt", async () => {
  const runtime = new PrePromptReselectionRuntime({
    driftAfterEffortSet: true,
    driftOnceAfterInitialHigh: false,
  });
  const { broker, workspace } = await delegateHarness({ runtime });
  const submitted = await broker.delegate({
    workspace,
    prompt: "Do not prompt when effort confirmation drifts the bound model.",
    hostConversationId: "conv-effort-coupled-drift",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_SELECTION_UNCONFIRMED");
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.effortAtStartTurn, null);
  assert.equal(completed.model, DEFAULT_GROK_MODEL);
  await broker.close();
});

test("pre-prompt effort setting unsupported, unavailable, or refused sends no prompt", async () => {
  for (const [afterReselection, code] of [
    [{ advertise: false }, "REASONING_EFFORT_UNSUPPORTED"],
    [{ availableEfforts: ["low", "medium"] }, "REASONING_EFFORT_UNAVAILABLE"],
    [{ obey: false }, "REASONING_EFFORT_UNCONFIRMED"],
  ]) {
    const runtime = new PrePromptReselectionRuntime({ afterReselection });
    const { broker, workspace } = await delegateHarness({ runtime });
    const submitted = await broker.delegate({
      workspace,
      prompt: "Do not prompt when pre-prompt effort cannot be confirmed.",
      hostConversationId: `conv-effort-${code.toLowerCase()}`,
    });
    const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
    assert.equal(completed.status, "failed");
    assert.equal(completed.error.code, code);
    assert.equal(runtime.turns.length, 0);
    assert.equal(runtime.effortAtStartTurn, null);
    await broker.close();
  }
});

test("inherit leaves the actual changed current effort after pre-prompt reselection", async () => {
  const runtime = new PrePromptReselectionRuntime({
    currentModel: "grok-4.7",
    driftAfterEffortSet: false,
    driftOnceAfterInitialHigh: false,
    driftAfterFirstStatus: true,
  });
  const { broker, workspace } = await delegateHarness({
    runtime,
    processEnv: { SAARIUS_GROK_ACP_REASONING_EFFORT: "inherit" },
  });
  const submitted = await broker.delegate({
    workspace,
    prompt: "Inherit must record the effort left by model reselection.",
    hostConversationId: "conv-effort-inherit-reselection",
  });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(runtime.turns.length, 1);
  assert.equal(runtime.effortAtStartTurn, "low");
  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(persisted.model.reasoningEffort.requested, "inherit");
  assert.equal(persisted.model.reasoningEffort.current, "low");
  assert.equal(completed.route.reasoningEffort, "inherited");
  await broker.close();
});
