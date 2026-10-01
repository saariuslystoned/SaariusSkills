import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { z } from "zod";
import {
  BridgeError,
  DEFAULT_GROK_FALLBACK_MODELS,
  DEFAULT_GROK_MODEL,
  GrokAcpBroker,
  grokFallbackModelsZod,
  grokModelZod,
  resolveGrokModelChoice,
  resolveGrokSelectionPolicy,
} from "../broker.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);

function reasoningStatus(modelId, available) {
  return {
    models: {
      currentModelId: modelId,
      availableModelIds: available,
      availableModels: available.map((id) => ({ modelId: id, name: id })),
    },
    details: {
      configOptions: [{
        id: "reasoning_effort",
        category: "thought_level",
        type: "select",
        currentValue: "xhigh",
        options: ["xhigh", "high", "medium", "low"].map((value) => ({ value, name: value })),
      }],
    },
  };
}

class ModelRuntime {
  constructor({ model = "grok-4.7", available = fixtureCatalog.availableModelIds, failEnsure = null } = {}) {
    this.model = model;
    this.available = available;
    this.failEnsure = failEnsure;
    this.ensureCalls = [];
    this.turns = [];
    this.setModels = [];
    this.sessions = new Map();
    this.reasoning = new Map();
  }

  session(handle) {
    return this.sessions.get(handle.sessionKey);
  }

  async ensureSession(input) {
    this.ensureCalls.push(input);
    if (this.failEnsure) throw this.failEnsure;
    this.sessions.set(input.sessionKey, { model: this.model, available: [...this.available] });
    this.reasoning.set(input.sessionKey, "xhigh");
    return { sessionKey: input.sessionKey, cwd: input.cwd, backend: "fixture" };
  }

  async getStatus({ handle }) {
    const session = this.session(handle);
    const status = reasoningStatus(session.model, session.available);
    status.details.configOptions[0].currentValue = this.reasoning.get(handle.sessionKey) ?? "xhigh";
    return status;
  }

  async setModel({ handle, model }) {
    this.setModels.push(model);
    const session = this.session(handle);
    if (session.available.includes(model)) session.model = model;
  }

  async setConfigOption({ handle, key, value }) {
    if (key === "reasoning_effort") this.reasoning.set(handle.sessionKey, value);
  }

  startTurn(input) {
    const turn = {
      requestId: input.requestId,
      promptStarted: Promise.resolve(),
      events: (async function* () {})(),
      result: Promise.resolve({ status: "completed", stopReason: "fixture complete" }),
      cancel: async () => undefined,
      closeStream: async () => undefined,
    };
    this.turns.push({ input, turn });
    return turn;
  }

  async close() {}
  async shutdown() {}
}

class DriftRuntime extends ModelRuntime {
  constructor() {
    super({ model: "grok-4.7", available: ["grok-4.5", "grok-4.6", "grok-4.7"] });
    this.confirmationsLeft = 0;
    this.armed = false;
  }

  async setConfigOption(input) {
    await super.setConfigOption(input);
    this.confirmationsLeft = 1;
  }

  async getStatus(input) {
    if (this.confirmationsLeft > 0) {
      this.confirmationsLeft -= 1;
      if (this.confirmationsLeft === 0) this.armed = true;
      return super.getStatus(input);
    }
    if (!this.armed) return super.getStatus(input);
    const session = this.session(input.handle);
    session.model = "grok-4.6";
    session.available = ["grok-4.6", "grok-4.5"];
    return super.getStatus(input);
  }
}

function hermeticProcessEnv() {
  const env = { ...process.env };
  delete env.SAARIUS_ACP_PERMISSION_MODE;
  return env;
}

async function harness(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-grok-model-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "grok");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const runtime = options.runtime ?? new ModelRuntime(options.runtimeOptions);
  const broker = new GrokAcpBroker({
    stateRoot: path.join(root, "state"),
    grokExecutable: executable,
    runtime,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    processEnv: hermeticProcessEnv(),
    defaultBinderId: "test-owner",
    ...options.brokerOptions,
  });
  await broker.init();
  return { broker, runtime, workspace, root };
}

test("omitted Grok policy prefers advertised 4.7, then 4.6, then 4.5", () => {
  const policy = resolveGrokSelectionPolicy();
  assert.deepEqual(policy, {
    kind: "default",
    preferred: DEFAULT_GROK_MODEL,
    alternatives: [...DEFAULT_GROK_FALLBACK_MODELS],
  });
  assert.equal(resolveGrokModelChoice(policy, fixtureCatalog.availableModelIds).selectedModelId, "grok-4.7");
  const onlyOlder = resolveGrokModelChoice(policy, ["grok-4.5", "grok-4.6"]);
  assert.equal(onlyOlder.selectedModelId, "grok-4.6");
  assert.equal(onlyOlder.usedDefaultAlternative, true);
  assert.equal(onlyOlder.requestedModel, null);
  const ordered = resolveGrokSelectionPolicy({ fallbackModels: ["grok-4.5", "grok-4.6"] });
  assert.equal(resolveGrokModelChoice(ordered, ["grok-4.6", "grok-4.5"]).selectedModelId, "grok-4.5");
  assert.throws(
    () => resolveGrokModelChoice(resolveGrokSelectionPolicy({ fallbackModels: [] }), ["grok-4.6", "grok-4.5"]),
    (error) => error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE",
  );
});

test("explicit Grok ids stay exact and fallback lists are validated", () => {
  const explicit = resolveGrokSelectionPolicy({ requestedModel: "grok-4.7-build-fast" });
  assert.equal(explicit.kind, "explicit");
  assert.equal(
    resolveGrokModelChoice(explicit, fixtureCatalog.availableModelIds).selectedModelId,
    "grok-4.7-build-fast",
  );
  assert.equal(
    resolveGrokModelChoice(resolveGrokSelectionPolicy({ requestedModel: "grok-4.6" }), ["grok-4.7", "grok-4.6"]).usedDefaultAlternative,
    false,
  );
  assert.throws(
    () => resolveGrokModelChoice(resolveGrokSelectionPolicy({ requestedModel: "grok-4.7" }), ["grok-4.6"]),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  assert.throws(
    () => resolveGrokSelectionPolicy({ requestedModel: "grok-4.6", fallbackModels: ["grok-4.5"] }),
    (error) => error.code === "FALLBACK_PINNED",
  );
  for (const fallbackModels of [[""], [" grok-4.6"], ["grok-4.6", "grok-4.6"], ["grok-4.7"], ["grok-4.6", "grok-4.5", "grok-4.7-build-fast"], "grok-4.6"]) {
    assert.throws(
      () => resolveGrokSelectionPolicy({ fallbackModels }),
      (error) => error.code === "INVALID_FALLBACK_MODELS",
    );
  }
  assert.throws(
    () => resolveGrokSelectionPolicy({ requestedModel: " grok-4.6" }),
    (error) => error.code === "INVALID_MODEL",
  );
  const pinned = resolveGrokSelectionPolicy({ constructorModel: "grok-4.6", constructorPinned: true });
  assert.equal(pinned.model, "grok-4.6");
  const overridden = resolveGrokSelectionPolicy({
    fallbackModels: ["grok-4.5"],
    constructorModel: "grok-4.6",
    constructorPinned: true,
  });
  assert.equal(overridden.kind, "default");
  assert.deepEqual([...overridden.alternatives], ["grok-4.5"]);
});

test("readiness reports the full catalog and default 4.7 without a prompt", async () => {
  const { broker, runtime, workspace } = await harness();
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(report.catalogReady, true);
  assert.equal(report.selectionReady, true);
  assert.equal(report.model.selectedModelId, "grok-4.7");
  assert.equal(report.model.usedDefaultAlternative, false);
  assert.equal(report.model.requestedModel, null);
  assert.equal(report.model.selectionPolicy.kind, "default");
  assert.deepEqual(report.model.availableModelIds, fixtureCatalog.availableModelIds);
  assert.equal(report.model.availableModels.length, fixtureCatalog.availableModelIds.length);
  assert.equal(report.model.reasoningEffort.requested, "high");
  assert.equal(report.model.reasoningEffort.current, "high");
  assert.equal(runtime.turns.length, 0);
  assert.equal(broker.model, DEFAULT_GROK_MODEL);
  await broker.close();
});

test("omitted model selects advertised 4.6 before the session's current 4.5", async () => {
  const { broker, runtime, workspace } = await harness({
    runtimeOptions: { model: "grok-4.5", available: ["grok-4.5", "grok-4.6"] },
  });
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(report.selectionReady, true);
  assert.equal(report.model.selectedModelId, "grok-4.6");
  assert.equal(report.model.usedDefaultAlternative, true);
  assert.equal(report.route.usedDefaultAlternative, true);
  assert.deepEqual(runtime.setModels, ["grok-4.6"]);
  const submitted = await broker.delegate({
    workspace,
    prompt: "Use the default advertised alternative.",
    hostConversationId: "conv-default-46",
  });
  assert.equal(submitted.model, "grok-4.6");
  assert.equal(submitted.modelSelection.usedDefaultAlternative, true);
  assert.equal(submitted.route.model, "grok-4.6");
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.modelSelection.selectedModelId, "grok-4.6");
  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(persisted.modelBinding.selectedModelId, "grok-4.6");
  assert.equal(persisted.modelBinding.usedDefaultAlternative, true);
  assert.equal(persisted.request.selectionPolicy.kind, "default");
  const proof = await readFile(completed.proof.proof, "utf8");
  const state = await readFile(completed.proof.state, "utf8");
  assert.match(proof, /Model: grok-4\.6/);
  assert.match(proof, /Default alternative: selected/);
  assert.match(state, /Selected model: grok-4\.6/);
  assert.equal(broker.model, DEFAULT_GROK_MODEL);
  await broker.close();
});

test("ordered fallbackModels replace the defaults and an empty list is strict 4.7", async () => {
  const ordered = await harness({
    runtimeOptions: { model: "grok-4.6", available: ["grok-4.6", "grok-4.5"] },
  });
  const selected = await ordered.broker.delegate({
    workspace: ordered.workspace,
    prompt: "Prefer the first configured alternative.",
    fallbackModels: ["grok-4.5", "grok-4.6"],
    hostConversationId: "conv-ordered",
  });
  assert.equal(selected.model, "grok-4.5");
  assert.equal(selected.modelSelection.usedDefaultAlternative, true);
  assert.deepEqual(selected.modelSelection.selectionPolicy.alternatives, ["grok-4.5", "grok-4.6"]);
  await ordered.broker.result({ jobId: selected.jobId, waitMs: 1_000 });
  await ordered.broker.close();

  const strict = await harness({
    runtimeOptions: { model: "grok-4.6", available: ["grok-4.6", "grok-4.5"] },
  });
  const readiness = await strict.broker.discover({ workspace: strict.workspace, fallbackModels: [] });
  assert.equal(readiness.ready, false);
  assert.equal(readiness.catalogReady, true);
  assert.equal(readiness.selectionReady, false);
  assert.equal(readiness.error.code, "MODEL_UNAVAILABLE");
  assert.deepEqual(readiness.model.availableModelIds, ["grok-4.6", "grok-4.5"]);
  await assert.rejects(
    () => strict.broker.delegate({
      workspace: strict.workspace,
      prompt: "Strict default must not run.",
      fallbackModels: [],
      hostConversationId: "conv-strict",
    }),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(strict.runtime.turns.length, 0);
  await strict.broker.close();
});

test("explicit models never substitute, and a missing explicit 4.7 sends no prompt", async () => {
  const { broker, runtime, workspace } = await harness();
  const report = await broker.discover({ workspace, model: "grok-4.6" });
  assert.equal(report.model.selectedModelId, "grok-4.6");
  assert.equal(report.model.usedDefaultAlternative, false);
  assert.equal(report.model.selectionPolicy.kind, "explicit");
  const fast = await broker.discover({ workspace, model: "grok-4.7-build-fast" });
  assert.equal(fast.model.selectedModelId, "grok-4.7-build-fast");
  const job = await broker.delegate({
    workspace,
    prompt: "Stay on exact 4.6.",
    model: "grok-4.6",
    hostConversationId: "conv-explicit-46",
  });
  assert.equal(job.model, "grok-4.6");
  assert.equal(job.modelSelection.usedDefaultAlternative, false);
  await broker.result({ jobId: job.jobId, waitMs: 1_000 });

  const missing = await harness({
    runtimeOptions: { model: "grok-4.6", available: ["grok-4.6", "grok-4.5"] },
  });
  const refused = await missing.broker.discover({ workspace: missing.workspace, model: "grok-4.7" });
  assert.equal(refused.ready, false);
  assert.equal(refused.catalogReady, true);
  assert.equal(refused.selectionReady, false);
  assert.equal(refused.error.code, "MODEL_UNAVAILABLE");
  await assert.rejects(
    () => missing.broker.delegate({
      workspace: missing.workspace,
      prompt: "Do not substitute 4.6.",
      model: "grok-4.7",
      hostConversationId: "conv-missing-47",
    }),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(missing.runtime.turns.length, 0);
  assert.equal(missing.runtime.setModels.includes("grok-4.6"), false);
  await broker.close();
  await missing.broker.close();
  assert.equal(runtime.turns.length >= 1, true);
});

test("missing allowed models, invalid input, and auth failure send no prompt", async () => {
  const missing = await harness({
    runtimeOptions: { model: "grok-custom", available: ["grok-custom"] },
  });
  const report = await missing.broker.discover({ workspace: missing.workspace });
  assert.equal(report.ready, false);
  assert.equal(report.catalogReady, true);
  assert.equal(report.selectionReady, false);
  assert.deepEqual(report.model.availableModelIds, ["grok-custom"]);
  await assert.rejects(
    () => missing.broker.delegate({
      workspace: missing.workspace,
      prompt: "No allowed model.",
      hostConversationId: "conv-none",
    }),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(missing.runtime.turns.length, 0);
  await missing.broker.close();

  const invalid = await harness();
  const bad = await invalid.broker.discover({
    workspace: invalid.workspace,
    model: "grok-4.6",
    fallbackModels: ["grok-4.5"],
  });
  assert.equal(bad.ready, false);
  assert.equal(bad.catalogReady, false);
  assert.equal(bad.selectionReady, false);
  assert.equal(bad.error.code, "FALLBACK_PINNED");
  assert.equal(invalid.runtime.ensureCalls.length, 0);
  await assert.rejects(
    () => invalid.broker.delegate({
      workspace: invalid.workspace,
      prompt: "Contradictory selection.",
      model: "grok-4.7",
      fallbackModels: [],
      hostConversationId: "conv-invalid",
    }),
    (error) => error.code === "FALLBACK_PINNED",
  );
  assert.equal(invalid.runtime.turns.length, 0);
  assert.equal(invalid.runtime.ensureCalls.length, 0);
  await invalid.broker.close();

  const auth = await harness({
    runtimeOptions: { failEnsure: new Error("authentication required") },
  });
  const authReport = await auth.broker.discover({ workspace: auth.workspace });
  assert.equal(authReport.ready, false);
  assert.equal(authReport.catalogReady, false);
  assert.equal(authReport.selectionReady, false);
  await assert.rejects(() => auth.broker.delegate({
    workspace: auth.workspace,
    prompt: "Auth must not prompt.",
    hostConversationId: "conv-auth",
  }));
  assert.equal(auth.runtime.turns.length, 0);
  await auth.broker.close();
});

test("per-job selections stay local to each job", async () => {
  const runtime = new ModelRuntime();
  const { broker, workspace } = await harness({ runtime });
  const pinnedModel = broker.model;
  const first = await broker.delegate({
    workspace,
    prompt: "First exact model.",
    model: "grok-4.6",
    hostConversationId: "conv-job-46",
  });
  const second = await broker.delegate({
    workspace,
    prompt: "Second exact model.",
    model: "grok-4.7",
    hostConversationId: "conv-job-47",
  });
  const [doneFirst, doneSecond] = await Promise.all([
    broker.result({ jobId: first.jobId, waitMs: 1_000 }),
    broker.result({ jobId: second.jobId, waitMs: 1_000 }),
  ]);
  assert.equal(doneFirst.status, "completed");
  assert.equal(doneSecond.status, "completed");
  assert.equal(doneFirst.model, "grok-4.6");
  assert.equal(doneSecond.model, "grok-4.7");
  assert.equal(broker.model, pinnedModel);
  assert.equal(broker.modelPinned, false);
  const thirdRuntime = new ModelRuntime({ model: "grok-4.5", available: ["grok-4.5", "grok-4.6", "grok-4.7"] });
  const sequential = await harness({ runtime: thirdRuntime });
  const older = await sequential.broker.delegate({
    workspace: sequential.workspace,
    prompt: "Sequential 4.5.",
    model: "grok-4.5",
    hostConversationId: "conv-seq-45",
  });
  await sequential.broker.result({ jobId: older.jobId, waitMs: 1_000 });
  const newer = await sequential.broker.delegate({
    workspace: sequential.workspace,
    prompt: "Sequential 4.7.",
    model: "grok-4.7",
    hostConversationId: "conv-seq-47",
  });
  const newerDone = await sequential.broker.result({ jobId: newer.jobId, waitMs: 1_000 });
  assert.equal(older.model, "grok-4.5");
  assert.equal(newerDone.model, "grok-4.7");
  assert.equal(sequential.broker.model, DEFAULT_GROK_MODEL);
  await broker.close();
  await sequential.broker.close();
});

test("catalog drift before the prompt does not renegotiate or send a prompt", async () => {
  const runtime = new DriftRuntime();
  const { broker, workspace } = await harness({ runtime });
  const submitted = await broker.delegate({
    workspace,
    prompt: "This prompt must not be sent after drift.",
    hostConversationId: "conv-drift",
  });
  assert.equal(submitted.model, "grok-4.7");
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_UNAVAILABLE");
  assert.equal(completed.model, "grok-4.7");
  assert.equal(completed.modelSelection.usedDefaultAlternative, false);
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.setModels.some((model) => model !== "grok-4.7"), false);
  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(persisted.modelBinding.selectedModelId, "grok-4.7");
  const events = await readFile(persisted.proof.events, "utf8");
  assert.equal(events.includes("prompt_started"), false);
  await broker.close();
});

test("constructor pin stays strict unless the job supplies its own policy", async () => {
  const { broker, runtime, workspace } = await harness({
    runtimeOptions: { model: "grok-4.6", available: ["grok-4.6", "grok-4.5"] },
    brokerOptions: { model: "grok-4.7" },
  });
  assert.equal(broker.modelPinned, true);
  await assert.rejects(
    () => broker.delegate({
      workspace,
      prompt: "Pinned 4.7 is absent.",
      hostConversationId: "conv-pin",
    }),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  const override = await broker.delegate({
    workspace,
    prompt: "Per-job exact override.",
    model: "grok-4.6",
    hostConversationId: "conv-pin-override",
  });
  assert.equal(override.model, "grok-4.6");
  assert.equal(broker.model, "grok-4.7");
  await broker.result({ jobId: override.jobId, waitMs: 1_000 });
  assert.equal(runtime.turns.length, 1);
  await broker.close();
});

test("MCP model schemas accept an optional exact model and at most two fallbacks", async () => {
  const model = grokModelZod(z);
  const fallbacks = grokFallbackModelsZod(z);
  assert.equal(model.parse(undefined), undefined);
  assert.equal(model.parse("grok-4.6"), "grok-4.6");
  assert.deepEqual(fallbacks.parse([]), []);
  assert.deepEqual(fallbacks.parse(["grok-4.6", "grok-4.5"]), ["grok-4.6", "grok-4.5"]);
  assert.throws(() => fallbacks.parse(["grok-4.6", "grok-4.5", "grok-4.7-build-fast"]));
  assert.throws(() => model.parse(""));
  const source = await readFile(new URL("../server.mjs", import.meta.url), "utf8");
  assert.equal(source.match(/model: grokModelZod\(z\)/g).length, 2);
  assert.equal(source.match(/fallbackModels: grokFallbackModelsZod\(z\)/g).length, 2);
  assert.match(source, /grok-4\.6, then grok-4\.5/);
  assert.doesNotMatch(source, /gpt-5\.6-luna/);
  assert.match(source, /does not run Luna/);
});
