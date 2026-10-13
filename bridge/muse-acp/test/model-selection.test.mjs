import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { z } from "zod";
import {
  BridgeError,
  MuseAcpBroker,
  museFallbackModelsZod,
  museModelZod,
  resolveMuseModelChoice,
  resolveMuseSelectionPolicy,
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
  constructor({ model = "fixture-c", available = fixtureCatalog.availableModelIds, failEnsure = null } = {}) {
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
    super({ model: "fixture-c", available: ["fixture-a", "fixture-b", "fixture-c"] });
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
    session.model = "fixture-b";
    session.available = ["fixture-b", "fixture-a"];
    return super.getStatus(input);
  }
}

function hermeticProcessEnv() {
  const env = { ...process.env };
  delete env.SAARIUS_ACP_PERMISSION_MODE;
  return env;
}

async function harness(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-muse-model-"));
  const workspace = path.join(root, "workspace");
  await mkdir(workspace);
  const executable = path.join(root, "muse");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  const runtime = options.runtime ?? new ModelRuntime(options.runtimeOptions);
  const broker = new MuseAcpBroker({
    stateRoot: path.join(root, "state"),
    museExecutable: executable,
    runtime,
    execFile: async (_exe, args) => ({ stdout: args?.includes("serve") ? "muse serve \u2014 serve an MSP session host over stdio\n" : "2026.08.11-e8db854\n", stderr: "" }),
    processEnv: hermeticProcessEnv(),
    defaultBinderId: "test-owner",
    ...options.brokerOptions,
  });
  await broker.init();
  return { broker, runtime, workspace, root };
}

test("omitted Muse policy is host default; fallbackModels is an ordered preference list", () => {
  const policy = resolveMuseSelectionPolicy();
  assert.deepEqual(policy, { kind: "host" });
  // Host default trusts the session's current model, whatever the catalog order.
  const hostChoice = resolveMuseModelChoice(policy, fixtureCatalog.availableModelIds, "fixture-a");
  assert.equal(hostChoice.selectedModelId, "fixture-a");
  assert.equal(hostChoice.usedDefaultAlternative, false);
  assert.equal(hostChoice.requestedModel, null);
  // Empty catalog + no current model (echo provider): null selection, no set_model.
  assert.equal(resolveMuseModelChoice(policy, [], null).selectedModelId, null);
  assert.equal(resolveMuseModelChoice(policy, fixtureCatalog.availableModelIds, null).selectedModelId, "fixture-a");
  const ordered = resolveMuseSelectionPolicy({ fallbackModels: ["fixture-a", "fixture-b"] });
  assert.equal(ordered.kind, "preferences");
  const prefChoice = resolveMuseModelChoice(ordered, ["fixture-b", "fixture-a"], "fixture-b");
  assert.equal(prefChoice.selectedModelId, "fixture-a");
  assert.equal(prefChoice.usedDefaultAlternative, false);
  const secondPref = resolveMuseModelChoice(ordered, ["fixture-b"], "fixture-b");
  assert.equal(secondPref.selectedModelId, "fixture-b");
  assert.equal(secondPref.usedDefaultAlternative, true);
  assert.throws(
    () => resolveMuseModelChoice(ordered, ["fixture-c"], "fixture-c"),
    (error) => error instanceof BridgeError && error.code === "MODEL_UNAVAILABLE",
  );
  // An empty preference list means host default, not strictness.
  assert.deepEqual(resolveMuseSelectionPolicy({ fallbackModels: [] }), { kind: "host" });
});

test("explicit Muse ids stay exact and fallback lists are validated", () => {
  const explicit = resolveMuseSelectionPolicy({ requestedModel: "fixture-fast" });
  assert.equal(explicit.kind, "explicit");
  assert.equal(
    resolveMuseModelChoice(explicit, fixtureCatalog.availableModelIds).selectedModelId,
    "fixture-fast",
  );
  assert.equal(
    resolveMuseModelChoice(resolveMuseSelectionPolicy({ requestedModel: "fixture-b" }), ["fixture-c", "fixture-b"]).usedDefaultAlternative,
    false,
  );
  assert.throws(
    () => resolveMuseModelChoice(resolveMuseSelectionPolicy({ requestedModel: "fixture-c" }), ["fixture-b"]),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  assert.throws(
    () => resolveMuseSelectionPolicy({ requestedModel: "fixture-b", fallbackModels: ["fixture-a"] }),
    (error) => error.code === "FALLBACK_PINNED",
  );
  for (const fallbackModels of [[""], [" fixture-b"], ["fixture-b", "fixture-b"], ["fixture-b", "fixture-a", "fixture-c", "fixture-fast", "muse-extra"], "fixture-b"]) {
    assert.throws(
      () => resolveMuseSelectionPolicy({ fallbackModels }),
      (error) => error.code === "INVALID_FALLBACK_MODELS",
    );
  }
  assert.throws(
    () => resolveMuseSelectionPolicy({ requestedModel: " fixture-b" }),
    (error) => error.code === "INVALID_MODEL",
  );
  const pinned = resolveMuseSelectionPolicy({ constructorModel: "fixture-b", constructorPinned: true });
  assert.equal(pinned.model, "fixture-b");
  const overridden = resolveMuseSelectionPolicy({
    fallbackModels: ["fixture-a"],
    constructorModel: "fixture-b",
    constructorPinned: true,
  });
  assert.equal(overridden.kind, "preferences");
  assert.deepEqual([...overridden.alternatives], ["fixture-a"]);
});

test("readiness reports the full catalog and the host current model without a prompt", async () => {
  const { broker, runtime, workspace } = await harness();
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(report.catalogReady, true);
  assert.equal(report.selectionReady, true);
  assert.equal(report.model.selectedModelId, "fixture-c");
  assert.equal(report.model.usedDefaultAlternative, false);
  assert.equal(report.model.requestedModel, null);
  assert.equal(report.model.selectionPolicy.kind, "host");
  assert.deepEqual(report.model.availableModelIds, fixtureCatalog.availableModelIds);
  assert.equal(report.model.availableModels.length, fixtureCatalog.availableModelIds.length);
  assert.equal(report.model.reasoningEffort.requested, "high");
  assert.equal(report.model.reasoningEffort.current, "high");
  assert.equal(runtime.turns.length, 0);
  assert.deepEqual(runtime.setModels, []);
  assert.equal(broker.model, null);
  await broker.close();
});

test("omitted model keeps the session's current model and never calls set_model", async () => {
  const { broker, runtime, workspace } = await harness({
    runtimeOptions: { model: "fixture-a", available: ["fixture-a", "fixture-b"] },
  });
  const report = await broker.discover({ workspace });
  assert.equal(report.ready, true);
  assert.equal(report.selectionReady, true);
  assert.equal(report.model.selectedModelId, "fixture-a");
  assert.equal(report.model.usedDefaultAlternative, false);
  assert.equal(report.route.usedDefaultAlternative, false);
  assert.deepEqual(runtime.setModels, []);
  const submitted = await broker.delegate({
    workspace,
    prompt: "Use the host default model.",
    hostConversationId: "conv-host-default",
  });
  assert.equal(submitted.model, "fixture-a");
  assert.equal(submitted.modelSelection.usedDefaultAlternative, false);
  assert.equal(submitted.route.model, "fixture-a");
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.modelSelection.selectedModelId, "fixture-a");
  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(persisted.modelBinding.selectedModelId, "fixture-a");
  assert.equal(persisted.modelBinding.usedDefaultAlternative, false);
  assert.equal(persisted.request.selectionPolicy.kind, "host");
  const proof = await readFile(completed.proof.proof, "utf8");
  const state = await readFile(completed.proof.state, "utf8");
  assert.match(proof, /Model: fixture-a/);
  assert.match(state, /Selected model: fixture-a/);
  assert.deepEqual(runtime.setModels, []);
  assert.equal(broker.model, null);
  await broker.close();
});

test("ordered fallbackModels act as preferences and an empty list means host default", async () => {
  const ordered = await harness({
    runtimeOptions: { model: "fixture-b", available: ["fixture-b", "fixture-a"] },
  });
  const selected = await ordered.broker.delegate({
    workspace: ordered.workspace,
    prompt: "Prefer the first configured preference.",
    fallbackModels: ["fixture-a", "fixture-b"],
    hostConversationId: "conv-ordered",
  });
  assert.equal(selected.model, "fixture-a");
  assert.equal(selected.modelSelection.usedDefaultAlternative, false);
  assert.equal(selected.modelSelection.selectionPolicy.kind, "preferences");
  assert.deepEqual(selected.modelSelection.selectionPolicy.alternatives, ["fixture-a", "fixture-b"]);
  await ordered.broker.result({ jobId: selected.jobId, waitMs: 1_000 });
  await ordered.broker.close();

  const host = await harness({
    runtimeOptions: { model: "fixture-b", available: ["fixture-b", "fixture-a"] },
  });
  const readiness = await host.broker.discover({ workspace: host.workspace, fallbackModels: [] });
  assert.equal(readiness.ready, true);
  assert.equal(readiness.catalogReady, true);
  assert.equal(readiness.selectionReady, true);
  assert.equal(readiness.model.selectedModelId, "fixture-b");
  assert.equal(readiness.model.selectionPolicy.kind, "host");
  assert.deepEqual(readiness.model.availableModelIds, ["fixture-b", "fixture-a"]);
  await host.broker.close();
});

test("explicit models never substitute, and a missing explicit 4.7 sends no prompt", async () => {
  const { broker, runtime, workspace } = await harness();
  const report = await broker.discover({ workspace, model: "fixture-b" });
  assert.equal(report.model.selectedModelId, "fixture-b");
  assert.equal(report.model.usedDefaultAlternative, false);
  assert.equal(report.model.selectionPolicy.kind, "explicit");
  const fast = await broker.discover({ workspace, model: "fixture-fast" });
  assert.equal(fast.model.selectedModelId, "fixture-fast");
  const job = await broker.delegate({
    workspace,
    prompt: "Stay on exact 4.6.",
    model: "fixture-b",
    hostConversationId: "conv-explicit-46",
  });
  assert.equal(job.model, "fixture-b");
  assert.equal(job.modelSelection.usedDefaultAlternative, false);
  await broker.result({ jobId: job.jobId, waitMs: 1_000 });

  const missing = await harness({
    runtimeOptions: { model: "fixture-b", available: ["fixture-b", "fixture-a"] },
  });
  const refused = await missing.broker.discover({ workspace: missing.workspace, model: "fixture-c" });
  assert.equal(refused.ready, false);
  assert.equal(refused.catalogReady, true);
  assert.equal(refused.selectionReady, false);
  assert.equal(refused.error.code, "MODEL_UNAVAILABLE");
  await assert.rejects(
    () => missing.broker.delegate({
      workspace: missing.workspace,
      prompt: "Do not substitute 4.6.",
      model: "fixture-c",
      hostConversationId: "conv-missing-47",
    }),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(missing.runtime.turns.length, 0);
  assert.equal(missing.runtime.setModels.includes("fixture-b"), false);
  await broker.close();
  await missing.broker.close();
  assert.equal(runtime.turns.length >= 1, true);
});

test("unavailable preferences, invalid input, and auth failure send no prompt", async () => {
  const missing = await harness({
    runtimeOptions: { model: "fixture-custom", available: ["fixture-custom"] },
  });
  const report = await missing.broker.discover({ workspace: missing.workspace, fallbackModels: ["fixture-c"] });
  assert.equal(report.ready, false);
  assert.equal(report.catalogReady, true);
  assert.equal(report.selectionReady, false);
  assert.deepEqual(report.model.availableModelIds, ["fixture-custom"]);
  await assert.rejects(
    () => missing.broker.delegate({
      workspace: missing.workspace,
      prompt: "No preferred model.",
      fallbackModels: ["fixture-c"],
      hostConversationId: "conv-none",
    }),
    (error) => error.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(missing.runtime.turns.length, 0);
  // The same catalog is fine under host default: the current model is trusted.
  const hostReport = await missing.broker.discover({ workspace: missing.workspace });
  assert.equal(hostReport.ready, true);
  assert.equal(hostReport.model.selectedModelId, "fixture-custom");
  await missing.broker.close();

  const invalid = await harness();
  const bad = await invalid.broker.discover({
    workspace: invalid.workspace,
    model: "fixture-b",
    fallbackModels: ["fixture-a"],
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
      model: "fixture-c",
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
    model: "fixture-b",
    hostConversationId: "conv-job-46",
  });
  const second = await broker.delegate({
    workspace,
    prompt: "Second exact model.",
    model: "fixture-c",
    hostConversationId: "conv-job-47",
  });
  const [doneFirst, doneSecond] = await Promise.all([
    broker.result({ jobId: first.jobId, waitMs: 1_000 }),
    broker.result({ jobId: second.jobId, waitMs: 1_000 }),
  ]);
  assert.equal(doneFirst.status, "completed");
  assert.equal(doneSecond.status, "completed");
  assert.equal(doneFirst.model, "fixture-b");
  assert.equal(doneSecond.model, "fixture-c");
  assert.equal(broker.model, pinnedModel);
  assert.equal(broker.modelPinned, false);
  const thirdRuntime = new ModelRuntime({ model: "fixture-a", available: ["fixture-a", "fixture-b", "fixture-c"] });
  const sequential = await harness({ runtime: thirdRuntime });
  const older = await sequential.broker.delegate({
    workspace: sequential.workspace,
    prompt: "Sequential 4.5.",
    model: "fixture-a",
    hostConversationId: "conv-seq-45",
  });
  await sequential.broker.result({ jobId: older.jobId, waitMs: 1_000 });
  const newer = await sequential.broker.delegate({
    workspace: sequential.workspace,
    prompt: "Sequential 4.7.",
    model: "fixture-c",
    hostConversationId: "conv-seq-47",
  });
  const newerDone = await sequential.broker.result({ jobId: newer.jobId, waitMs: 1_000 });
  assert.equal(older.model, "fixture-a");
  assert.equal(newerDone.model, "fixture-c");
  assert.equal(sequential.broker.model, null);
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
  assert.equal(submitted.model, "fixture-c");
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_UNAVAILABLE");
  assert.equal(completed.model, "fixture-c");
  assert.equal(completed.modelSelection.usedDefaultAlternative, false);
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.setModels.some((model) => model !== "fixture-c"), false);
  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(persisted.modelBinding.selectedModelId, "fixture-c");
  const events = await readFile(persisted.proof.events, "utf8");
  assert.equal(events.includes("prompt_started"), false);
  await broker.close();
});

test("constructor pin stays strict unless the job supplies its own policy", async () => {
  const { broker, runtime, workspace } = await harness({
    runtimeOptions: { model: "fixture-b", available: ["fixture-b", "fixture-a"] },
    brokerOptions: { model: "fixture-c" },
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
    model: "fixture-b",
    hostConversationId: "conv-pin-override",
  });
  assert.equal(override.model, "fixture-b");
  assert.equal(broker.model, "fixture-c");
  await broker.result({ jobId: override.jobId, waitMs: 1_000 });
  assert.equal(runtime.turns.length, 1);
  await broker.close();
});

test("MCP model schemas accept an optional exact model and at most four preferences", async () => {
  const model = museModelZod(z);
  const fallbacks = museFallbackModelsZod(z);
  assert.equal(model.parse(undefined), undefined);
  assert.equal(model.parse("fixture-b"), "fixture-b");
  assert.deepEqual(fallbacks.parse([]), []);
  assert.deepEqual(fallbacks.parse(["fixture-b", "fixture-a"]), ["fixture-b", "fixture-a"]);
  assert.throws(() => fallbacks.parse(["a", "b", "c", "d", "e"]));
  assert.throws(() => model.parse(""));
  const source = await readFile(new URL("../tools.mjs", import.meta.url), "utf8");
  assert.equal(source.match(/model: museModelZod\(z\)/g).length, 2);
  assert.equal(source.match(/fallbackModels: museFallbackModelsZod\(z\)/g).length, 2);
  assert.match(source, /host default/);
  assert.doesNotMatch(source, /prefers advertised/);
});
