import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { randomUUID } from "node:crypto";
import {
  BridgeError,
  CursorAcpBroker,
  DEFAULT_CURSOR_MODEL,
  PREFERRED_DEFAULT_MODEL_BASE,
  PREFERRED_DEFAULT_EFFORT,
  extractEffortFromModelId,
  isOmittedCursorEffort,
  isOmittedCursorModel,
  parseCursorModelId,
  parseModelSlug,
  preferredDefaultAdvertised,
  resolveCursorModelChoice,
  resolvePreferredDefaultCursorModel,
  resolveRequestedCursorModel,
} from "../broker.mjs";

const fixtureCatalog = JSON.parse(
  await readFile(new URL("../fixtures/model-catalog.json", import.meta.url), "utf8"),
);
const FIXTURE_MODEL = fixtureCatalog.currentModelId;

class FixtureRuntime {
  constructor({
    model = FIXTURE_MODEL,
    available = fixtureCatalog.availableModelIds,
    delayMs = 5,
  } = {}) {
    this.model = model;
    this.available = available;
    this.delayMs = delayMs;
    this.ensureCalls = [];
    this.turns = [];
    this.closed = [];
  }

  async ensureSession(input) {
    this.ensureCalls.push(input);
    return {
      sessionKey: input.sessionKey,
      backend: "fixture",
      runtimeSessionName: `fixture:${input.sessionKey}`,
      cwd: input.cwd,
      backendSessionId: `backend-${this.ensureCalls.length}`,
      agentSessionId: `agent-${this.ensureCalls.length}`,
    };
  }

  async getStatus() {
    return {
      models: {
        currentModelId: this.model,
        availableModelIds: this.available,
        availableModels: this.available.map((modelId) => ({ modelId, name: modelId })),
      },
    };
  }

  async setModel({ model }) {
    if (this.available.includes(model)) {
      this.model = model;
    }
  }

  startTurn(input) {
    const turn = {
      requestId: input.requestId,
      promptStarted: Promise.resolve(),
      events: (async function* () {
        yield { type: "text_delta", text: "## Bounded handoff\n\nChanged files: none.\nRisks: none." };
      })(),
      result: (async () => {
        if (this.delayMs > 0) await new Promise((r) => setTimeout(r, this.delayMs));
        return { status: "completed", stopReason: "end_turn" };
      })(),
      cancel: async () => undefined,
    };
    this.turns.push({ input });
    return turn;
  }

  async close(input) {
    this.closed.push(input);
  }

  async shutdown() {}
}

async function makeBroker(options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "saarius-cursor-model-test-"));
  const workspace = path.join(root, "workspace");
  const stateRoot = path.join(root, "state");
  const executable = path.join(root, "cursor-agent");
  await mkdir(workspace, { recursive: true });
  await mkdir(stateRoot, { recursive: true });
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);

  const runtime = options.runtime ?? new FixtureRuntime(options.runtimeOptions);
  const broker = new CursorAcpBroker({
    stateRoot,
    cursorExecutable: executable,
    runtime,
    model: options.model,
    effort: options.effort,
    defaultWorkspace: workspace,
    timeoutMs: options.timeoutMs ?? 5_000,
    execFile: async () => ({ stdout: "2026.08.11-e8db854\n", stderr: "" }),
    defaultHostConversationId: "conv-test",
    defaultBinderId: "binder-test",
  });
  await broker.init();
  return { broker, runtime, workspace, stateRoot, root };
}

test("DEFAULT_CURSOR_MODEL is gpt-5.6-luna-high", () => {
  assert.equal(DEFAULT_CURSOR_MODEL, "gpt-5.6-luna-high");
  assert.equal(PREFERRED_DEFAULT_MODEL_BASE, "gpt-5.6-luna");
  assert.equal(PREFERRED_DEFAULT_EFFORT, "high");
});

test("model id and effort parsing extracts effort and base correctly", () => {
  const parsedLuna = parseCursorModelId("gpt-5.6-luna[context=272k,reasoning=high,fast=false]");
  assert.equal(parsedLuna.baseModelId, "gpt-5.6-luna");
  assert.equal(extractEffortFromModelId("gpt-5.6-luna[context=272k,reasoning=high,fast=false]"), "high");

  const parsedGrok = parseCursorModelId("grok-4.6[effort=high,fast=true]");
  assert.equal(parsedGrok.baseModelId, "grok-4.6");
  assert.equal(extractEffortFromModelId("grok-4.6[effort=high,fast=true]"), "high");

  const parsedGemini = parseCursorModelId("gemini-3.8-flash[reasoning_effort=medium]");
  assert.equal(parsedGemini.baseModelId, "gemini-3.8-flash");
  assert.equal(extractEffortFromModelId("gemini-3.8-flash[reasoning_effort=medium]"), "medium");

  const slugLuna = parseModelSlug("gpt-5.6-luna-high");
  assert.equal(slugLuna.base, "gpt-5.6-luna");
  assert.equal(slugLuna.effort, "high");
  assert.equal(slugLuna.kind, "plugin-default");

  const slugGrok = parseModelSlug("cursor-grok-4.6-medium");
  assert.equal(slugGrok.base, "grok-4.6");
  assert.equal(slugGrok.effort, "medium");
  assert.equal(slugGrok.kind, "legacy-grok-selector");

  assert.equal(parseModelSlug("gpt-5.6-luna-medium"), null);
  assert.equal(parseModelSlug("custom-model-id"), null);
  assert.equal(fixtureCatalog.synthetic, true);
  assert.equal(fixtureCatalog.liveLunaModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
});

test("preferredDefaultAdvertised detects unique advertised default", () => {
  assert.equal(preferredDefaultAdvertised(fixtureCatalog.availableModelIds), true);
  assert.equal(preferredDefaultAdvertised(["cursor-grok-4.6[effort=medium,fast=true]"]), false);
  assert.equal(preferredDefaultAdvertised([]), false);
});

test("resolveRequestedCursorModel resolves advertised non-Grok / high effort default", () => {
  const resolved = resolveRequestedCursorModel("gpt-5.6-luna-high", fixtureCatalog.availableModelIds);
  assert.equal(resolved, "gpt-5.6-luna[context=272k,reasoning=high,fast=false]");

  const resolvedWithEffort = resolveRequestedCursorModel("gpt-5.6-luna", fixtureCatalog.availableModelIds, "high");
  assert.equal(resolvedWithEffort, "gpt-5.6-luna[context=272k,reasoning=high,fast=false]");
});

test("resolveRequestedCursorModel resolves exact advertised ID", () => {
  const exact = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const resolved = resolveRequestedCursorModel(exact, fixtureCatalog.availableModelIds);
  assert.equal(resolved, exact);

  // Matching effort also succeeds
  const resolvedWithMatchingEffort = resolveRequestedCursorModel(exact, fixtureCatalog.availableModelIds, "medium");
  assert.equal(resolvedWithMatchingEffort, exact);
});

test("resolveRequestedCursorModel rejects conflicting effort on exact ID", () => {
  const exact = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  assert.throws(
    () => resolveRequestedCursorModel(exact, fixtureCatalog.availableModelIds, "high"),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED",
  );
});

test("resolveRequestedCursorModel rejects conflicting slug and effort", () => {
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna-high", fixtureCatalog.availableModelIds, "low"),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED",
  );
});

test("resolveRequestedCursorModel rejects unsupported effort and reports available efforts", () => {
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna", fixtureCatalog.availableModelIds, "max"),
    (err) => {
      assert(err instanceof BridgeError);
      assert.equal(err.code, "EFFORT_UNSUPPORTED");
      assert(err.message.includes("does not advertise effort 'max'"));
      return true;
    },
  );
});

test("resolveRequestedCursorModel rejects missing model with MODEL_UNAVAILABLE", () => {
  assert.throws(
    () => resolveRequestedCursorModel("non-existent-model", fixtureCatalog.availableModelIds),
    (err) => err instanceof BridgeError && err.code === "MODEL_UNAVAILABLE",
  );
});

test("resolveRequestedCursorModel rejects ambiguous model match with MODEL_AMBIGUOUS", () => {
  const ambiguousCatalog = [
    "gpt-5.6-luna[context=272k,reasoning=high,fast=false]",
    "gpt-5.6-luna[context=128k,reasoning=high,fast=true]",
  ];
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna-high", ambiguousCatalog),
    (err) => err instanceof BridgeError && err.code === "MODEL_AMBIGUOUS",
  );
});

test("resolveRequestedCursorModel rejects wrapping whitespace and NUL characters", () => {
  assert.throws(
    () => resolveRequestedCursorModel(" gpt-5.6-luna-high ", fixtureCatalog.availableModelIds),
    (err) => err instanceof BridgeError && err.code === "MODEL_UNAVAILABLE",
  );
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna\u0000", fixtureCatalog.availableModelIds),
    (err) => err instanceof BridgeError && err.code === "MODEL_UNAVAILABLE",
  );
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna", fixtureCatalog.availableModelIds, " high "),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED",
  );
});

test("readiness probe discovers default Luna High without a turn", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const discovery = await broker.discover({ workspace });
  assert.equal(discovery.ready, true);
  assert.equal(discovery.route.model, "gpt-5.6-luna[context=272k,reasoning=high,fast=false]");
  assert.equal(discovery.route.effort, "high");
  assert.equal(discovery.model.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=high,fast=false]");
  assert.equal(discovery.model.selectedEffort, "high");
  assert.equal(discovery.model.preferredDefaultAlias, "gpt-5.6-luna-high");
  assert.equal(discovery.model.preferredDefaultModelId, "gpt-5.6-luna[context=272k,reasoning=high,fast=false]");
  assert.equal(discovery.model.preferredDefaultPolicy.liveModelId, null);
  assert.equal(discovery.model.preferredDefaultAvailable, true);
  assert.deepEqual(discovery.model.availableModelIds, fixtureCatalog.availableModelIds);
  assert.equal(discovery.catalogReady, true);
  assert.equal(discovery.selectionReady, true);
  assert.equal(discovery.model.effortPolicy, "unambiguous_advertised_selection");
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.closed.length, 1);
  await broker.close();
});

test("readiness probe discovers custom model override without a turn", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const discovery = await broker.discover({
    workspace,
    model: "gpt-5.6-luna",
    effort: "medium",
  });
  assert.equal(discovery.ready, true);
  assert.equal(discovery.route.model, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(discovery.route.effort, "medium");
  assert.equal(discovery.model.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(discovery.model.selectedEffort, "medium");
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("readiness/delegate consistency: High absent is not selection-ready and returns the catalog", async () => {
  const liveLikeCatalog = fixtureCatalog.availableModelIds.filter(
    (id) => !id.includes("reasoning=high"),
  );
  const medium = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const runtime = new FixtureRuntime({
    model: medium,
    available: liveLikeCatalog,
  });
  const { broker, workspace } = await makeBroker({ runtime });

  const discovery = await broker.discover({ workspace });
  assert.equal(discovery.ready, false);
  assert.equal(discovery.catalogReady, true);
  assert.equal(discovery.selectionReady, false);
  assert.equal(discovery.model.selectedModelId, null);
  assert.equal(discovery.model.selectedEffort, null);
  assert.equal(discovery.model.currentModelId, medium);
  assert.equal(discovery.model.preferredDefaultAlias, "gpt-5.6-luna-high");
  assert.equal(discovery.model.preferredDefaultModelId, null);
  assert.equal(discovery.model.preferredDefaultAvailable, false);
  assert.deepEqual(discovery.model.availableModelIds, liveLikeCatalog);
  assert.equal(discovery.error.code, "EFFORT_UNSUPPORTED");
  assert.equal(runtime.turns.length, 0);

  await assert.rejects(
    () => broker.delegate({ workspace, prompt: "Should fail closed" }),
    (err) => {
      assert(err instanceof BridgeError);
      assert.equal(err.code, "EFFORT_UNSUPPORTED");
      assert(err.message.includes("effort high"));
      assert.deepEqual(err.details.availableModelIds, liveLikeCatalog);
      return true;
    },
  );
  assert.equal(runtime.turns.length, 0);

  // 3. Delegate with explicit override succeeds
  const submitted = await broker.delegate({
    workspace,
    prompt: "Run with explicit override",
    model: "gpt-5.6-luna",
    effort: "medium",
  });
  assert.equal(submitted.status, "submitted");
  assert.equal(submitted.route.model, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(submitted.route.effort, "medium");

  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  assert.equal(runtime.turns.length, 1);

  await broker.close();
});

test("model mismatch fails closed with zero prompts (MODEL_SELECTION_UNCONFIRMED)", async () => {
  const runtime = new FixtureRuntime();
  // Simulate runtime where setModel fails to change the currentModelId
  runtime.setModel = async () => {}; // No-op, will not switch model
  runtime.model = "cursor-grok-4.6[effort=high,fast=true]"; // Different from target Luna High

  const { broker, workspace } = await makeBroker({ runtime });
  await assert.rejects(
    () => broker.delegate({ workspace, prompt: "Must never run" }),
    (err) => {
      assert(err instanceof BridgeError);
      assert.equal(err.code, "MODEL_SELECTION_UNCONFIRMED");
      return true;
    },
  );

  // Zero prompts sent
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("delegation never falls back to Grok or another model when requested model is unavailable", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  await assert.rejects(
    () => broker.delegate({ workspace, prompt: "Must never run", model: "unsupported-model" }),
    (err) => err instanceof BridgeError && err.code === "MODEL_UNAVAILABLE",
  );
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("immutable per-job model selection is preserved across getJob, state, proof, events", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const submitted = await broker.delegate({
    workspace,
    prompt: "Verify immutable model binding",
    model: "gpt-5.6-luna",
    effort: "medium",
  });

  // Verify submission receipt
  assert.equal(submitted.route.model, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(submitted.route.effort, "medium");
  assert.equal(submitted.model, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");

  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");

  // Verify getJob receipt
  const job = await broker.getJob(submitted.jobId);
  assert.equal(job.request.model, "gpt-5.6-luna");
  assert.equal(job.request.effort, "medium");
  assert.equal(job.route.model, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(job.route.effort, "medium");
  assert.equal(job.model.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(job.model.selectedEffort, "medium");

  // Verify persisted STATE.md
  const stateContent = await readFile(job.proof.state, "utf8");
  assert(stateContent.includes("Requested model: gpt-5.6-luna"));
  assert(stateContent.includes("Requested effort: medium"));
  assert(stateContent.includes("Selected model: gpt-5.6-luna[context=272k,reasoning=medium,fast=false]"));
  assert(stateContent.includes("Selected effort: medium"));

  const proofContent = await readFile(job.proof.proof, "utf8");
  assert(proofContent.includes("Selected model: gpt-5.6-luna[context=272k,reasoning=medium,fast=false]"));
  assert(proofContent.includes("Selected effort: medium"));
  assert(proofContent.includes("Requested model: gpt-5.6-luna"));
  assert(proofContent.includes("Requested effort: medium"));

  // Verify events.jsonl
  const eventsContent = await readFile(job.proof.events, "utf8");
  const lines = eventsContent.trim().split("\n").map((l) => JSON.parse(l));
  const submittedEvent = lines.find((e) => e.event === "submitted");
  assert.equal(submittedEvent.details.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(submittedEvent.details.selectedEffort, "medium");

  const confirmedEvent = lines.find((e) => e.event === "model_confirmed");
  assert.equal(confirmedEvent.details.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(confirmedEvent.details.selectedEffort, "medium");
  assert.equal(completed.modelSelection.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(completed.modelSelection.requestedModel, "gpt-5.6-luna");
  assert.equal(completed.modelSelection.requestedEffort, "medium");
  assert.equal(completed.modelSelection.selectedEffort, "medium");
  assert.equal(completed.cleanup.status, "completed");
  assert.equal(job.request.selectionPolicy.kind, "explicit");

  broker.model = "gpt-5.6-luna-high";
  broker.effort = "high";
  runtime.available = ["gpt-5.6-luna[context=272k,reasoning=high,fast=false]"];
  runtime.model = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const observed = await broker.result({ jobId: submitted.jobId });
  assert.equal(observed.modelSelection.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");
  assert.equal(observed.modelSelection.selectionPolicy.requestedModel, "gpt-5.6-luna");
  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${submitted.jobId}.json`), "utf8"));
  assert.equal(persisted.request.model, "gpt-5.6-luna");
  assert.equal(persisted.request.effort, "medium");
  assert.equal(persisted.model.selectedModelId, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]");

  await broker.close();
});

test("duplicate exact ids and conflicting effort fields are rejected", () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  assert.throws(
    () => resolveRequestedCursorModel(high, [high, high]),
    (err) => err instanceof BridgeError && err.code === "MODEL_AMBIGUOUS",
  );
  const conflicted = "gpt-5.6-luna[effort=high,reasoning=medium]";
  assert.throws(
    () => resolveRequestedCursorModel(conflicted, [conflicted]),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED",
  );
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna", [conflicted], "high"),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED",
  );
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna", fixtureCatalog.availableModelIds, "high,medium"),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED",
  );
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna-medium", fixtureCatalog.availableModelIds),
    (err) => err instanceof BridgeError && err.code === "MODEL_UNAVAILABLE",
  );
  const repeated = "gpt-5.6-luna[reasoning=high,reasoning=medium]";
  assert.throws(
    () => resolveRequestedCursorModel(repeated, [repeated]),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED",
  );
  const malformed = "gpt-5.6-luna[reasoning=High]";
  assert.throws(
    () => resolveRequestedCursorModel("gpt-5.6-luna", [malformed], "high"),
    (err) => err instanceof BridgeError && err.code === "EFFORT_UNSUPPORTED"
      && err.details.malformedModelIds.includes(malformed),
  );
});

test("invalid readiness still returns the advertised catalog and is not delegate-ready", async () => {
  const { broker, runtime, workspace } = await makeBroker();
  const discovery = await broker.discover({ workspace, model: "not-a-model" });
  assert.equal(discovery.ready, false);
  assert.equal(discovery.catalogReady, true);
  assert.equal(discovery.selectionReady, false);
  assert.equal(discovery.error.code, "MODEL_UNAVAILABLE");
  assert.deepEqual(discovery.model.availableModelIds, fixtureCatalog.availableModelIds);
  assert.equal(discovery.model.selectedModelId, null);
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("prepared-handle drift fails with zero prompts and keeps the persisted selection", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const drifted = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const runtime = new FixtureRuntime({ model: high });
  let reads = 0;
  runtime.getStatus = async () => {
    reads += 1;
    const current = reads < 3 ? high : drifted;
    return {
      models: {
        currentModelId: current,
        availableModelIds: runtime.available,
        availableModels: runtime.available.map((modelId) => ({ modelId, name: modelId })),
      },
    };
  };
  runtime.setModel = async () => {};
  const { broker, workspace } = await makeBroker({ runtime });
  const submitted = await broker.delegate({ workspace, prompt: "Must not prompt after drift" });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_SELECTION_UNCONFIRMED");
  assert.equal(runtime.turns.length, 0);
  const job = await broker.getJob(submitted.jobId);
  assert.equal(job.model.selectedModelId, high);
  assert.equal(job.model.selectedEffort, "high");
  assert.equal(job.request.model, null);
  assert.equal(job.request.selectionPolicy.kind, "plugin-default");
  assert.equal(job.request.selectionPolicy.alias, "gpt-5.6-luna-high");
  assert.equal(job.request.selectionPolicy.liveModelId, null);
  await broker.close();
});

test("new handle rechecks the persisted id after broker and catalog changes", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const medium = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const { broker, runtime, workspace } = await makeBroker();
  const submitted = await broker.delegate({ workspace, prompt: "Resolve the synthetic high default once" });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "completed");
  const turnsBefore = runtime.turns.length;
  const stored = await broker.getJob(submitted.jobId);
  const replay = structuredClone(stored);
  replay.status = "submitted";
  delete replay.cleanup;
  delete replay.handoff;
  delete replay.error;
  broker.model = "gpt-5.6-luna";
  broker.effort = "medium";
  runtime.model = medium;
  runtime.available = [medium, high];
  const sets = [];
  const originalSet = runtime.setModel.bind(runtime);
  runtime.setModel = async (input) => {
    sets.push(input.model);
    return originalSet(input);
  };
  const outcome = await broker.runJob(replay, "Replay the persisted selection");
  assert.equal(outcome.status, "completed");
  assert.equal(replay.model.selectedModelId, high);
  assert.equal(replay.model.selectedEffort, "high");
  assert.equal(replay.request.model, null);
  assert.equal(replay.request.selectionPolicy.alias, "gpt-5.6-luna-high");
  assert.equal(runtime.model, high);
  assert.deepEqual(sets, [high]);
  assert.equal(runtime.turns.length, turnsBefore + 1);
  assert.equal(outcome.modelSelection.currentModelId, high);
  assert.equal(outcome.modelSelection.requestedEffort, null);
  await broker.close();
});

test("new handle drift does not adopt a newly advertised model", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const medium = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const { broker, runtime, workspace } = await makeBroker();
  const submitted = await broker.delegate({ workspace, prompt: "Persist high then drift" });
  await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  const turnsBefore = runtime.turns.length;
  const replay = structuredClone(await broker.getJob(submitted.jobId));
  replay.status = "submitted";
  delete replay.cleanup;
  broker.model = medium;
  runtime.model = medium;
  runtime.available = [medium];
  runtime.setModel = async () => {};
  const outcome = await broker.runJob(replay, "Must not prompt");
  assert.equal(outcome.status, "failed");
  assert.equal(outcome.error.code, "MODEL_SELECTION_UNCONFIRMED");
  assert.equal(runtime.turns.length, turnsBefore);
  assert.equal(replay.model.selectedModelId, high);
  assert.equal(replay.request.selectionPolicy.kind, "plugin-default");
  await broker.close();
});

test("owner-death recovery preserves the resolved selection and sends no prompt", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const { broker, runtime, stateRoot } = await makeBroker();
  const jobId = "44444444-4444-4444-8444-444444444444";
  const owner = {
    brokerId: "deadsel0-0000-4000-8000-000000000001",
    pid: 8_888_888,
    startTime: "Sun Jan  1 00:00:00 2023",
  };
  const runDir = path.join(stateRoot, "runs", jobId);
  await mkdir(runDir, { recursive: true });
  const selectionPolicy = {
    kind: "plugin-default",
    alias: "gpt-5.6-luna-high",
    baseModel: "gpt-5.6-luna",
    effort: "high",
    liveModelId: null,
  };
  const job = {
    schema: "saarius.cursor-acp.job.v1",
    jobId,
    status: "running",
    workspace: stateRoot,
    runDir,
    createdAt: "2026-09-30T20:00:00.000Z",
    updatedAt: "2026-09-30T20:00:00.000Z",
    route: { executable: "synthetic", argv: ["acp"], model: high, effort: "high" },
    request: {
      promptSha256: "abc",
      promptChars: 4,
      model: null,
      effort: null,
      selectionPolicy,
    },
    model: {
      selectedModelId: high,
      selectedEffort: "high",
      currentModelId: high,
    },
    owner,
    proof: {
      state: path.join(runDir, "STATE.md"),
      events: path.join(runDir, "events.jsonl"),
      proof: path.join(runDir, "PROOF.md"),
    },
  };
  await writeFile(path.join(broker.jobsRoot, `${jobId}.json`), `${JSON.stringify(job, null, 2)}\n`);
  const ownersRoot = path.join(stateRoot, "owners");
  await mkdir(ownersRoot, { recursive: true });
  await writeFile(
    path.join(ownersRoot, `${owner.brokerId}.json`),
    `${JSON.stringify({ schema: "saarius.cursor-acp.owner.v1", ...owner, heartbeatAt: "2026-09-30T20:00:00.000Z", released: false }, null, 2)}\n`,
  );

  const recovered = await broker.result({ jobId });
  assert.equal(recovered.status, "failed");
  assert.equal(recovered.error.code, "BRIDGE_RESTARTED");
  assert.equal(recovered.model, high);
  assert.equal(recovered.modelSelection.selectedModelId, high);
  assert.equal(recovered.modelSelection.selectedEffort, "high");
  assert.equal(recovered.modelSelection.requestedModel, null);
  assert.equal(recovered.modelSelection.requestedEffort, null);
  assert.equal(recovered.modelSelection.currentModelId, high);
  assert.deepEqual(recovered.modelSelection.selectionPolicy, selectionPolicy);
  assert.equal(runtime.turns.length, 0);
  assert.equal(runtime.ensureCalls.length, 0);

  const persisted = JSON.parse(await readFile(path.join(broker.jobsRoot, `${jobId}.json`), "utf8"));
  assert.equal(persisted.model.selectedModelId, high);
  assert.equal(persisted.model.selectedEffort, "high");
  assert.equal(persisted.request.model, null);
  assert.deepEqual(persisted.request.selectionPolicy, selectionPolicy);
  assert.equal(persisted.error.code, "BRIDGE_RESTARTED");
  await broker.close();
});

test("current matches persisted High but catalog missing High fails closed with zero prompts", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const medium = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const runtime = new FixtureRuntime({ model: high });
  let reads = 0;
  runtime.getStatus = async () => {
    reads += 1;
    const available = reads < 3 ? fixtureCatalog.availableModelIds : [medium];
    return {
      models: {
        currentModelId: high,
        availableModelIds: available,
        availableModels: available.map((modelId) => ({ modelId, name: modelId })),
      },
    };
  };
  const { broker, workspace } = await makeBroker({ runtime });
  const submitted = await broker.delegate({ workspace, prompt: "Must reject missing persisted model" });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_SELECTION_UNCONFIRMED");
  assert(completed.error.message.includes("does not advertise selected model"));
  assert.deepEqual(completed.error.details.availableModelIds, [medium]);
  assert.equal(runtime.turns.length, 0);
  const job = await broker.getJob(submitted.jobId);
  assert.equal(job.model.selectedModelId, high);
  assert.equal(job.model.currentModelId, high);
  await broker.close();
});

test("exact High duplicated after admission fails closed with zero prompts", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const runtime = new FixtureRuntime({ model: high });
  let reads = 0;
  runtime.getStatus = async () => {
    reads += 1;
    const available = reads < 3
      ? fixtureCatalog.availableModelIds
      : [high, high, "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]"];
    return {
      models: {
        currentModelId: high,
        availableModelIds: available,
        availableModels: available.map((modelId) => ({ modelId, name: modelId })),
      },
    };
  };
  const { broker, workspace } = await makeBroker({ runtime });
  const submitted = await broker.delegate({ workspace, prompt: "Must reject duplicated persisted model" });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_SELECTION_UNCONFIRMED");
  assert(completed.error.message.includes("ambiguous entries for selected model"));
  assert.equal(completed.error.details.matchCount, 2);
  assert.equal(runtime.turns.length, 0);
  const job = await broker.getJob(submitted.jobId);
  assert.equal(job.model.selectedModelId, high);
  await broker.close();
});

test("prepared current drift with working setter fails closed with zero prompts and no setter call", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const drifted = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const runtime = new FixtureRuntime({ model: high });
  let reads = 0;
  let setterCalls = 0;
  runtime.getStatus = async () => {
    reads += 1;
    const current = reads < 3 ? high : drifted;
    return {
      models: {
        currentModelId: current,
        availableModelIds: runtime.available,
        availableModels: runtime.available.map((modelId) => ({ modelId, name: modelId })),
      },
    };
  };
  runtime.setModel = async ({ model }) => {
    setterCalls += 1;
    runtime.model = model;
  };
  const { broker, workspace } = await makeBroker({ runtime });
  const submitted = await broker.delegate({ workspace, prompt: "Must fail zero prompt without invoking setter" });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_SELECTION_UNCONFIRMED");
  assert.equal(setterCalls, 0);
  assert.equal(runtime.turns.length, 0);
  await broker.close();
});

test("failed confirmation exposes latest current while selected immutable fields are preserved", async () => {
  const high = "gpt-5.6-luna[context=272k,reasoning=high,fast=false]";
  const drifted = "gpt-5.6-luna[context=272k,reasoning=medium,fast=false]";
  const runtime = new FixtureRuntime({ model: high });
  let reads = 0;
  runtime.getStatus = async () => {
    reads += 1;
    const current = reads < 3 ? high : drifted;
    return {
      models: {
        currentModelId: current,
        availableModelIds: runtime.available,
        availableModels: runtime.available.map((modelId) => ({ modelId, name: modelId })),
      },
    };
  };
  const { broker, workspace } = await makeBroker({ runtime });
  const submitted = await broker.delegate({ workspace, prompt: "Verify exposed current after drift" });
  const completed = await broker.result({ jobId: submitted.jobId, waitMs: 1_000 });
  assert.equal(completed.status, "failed");
  assert.equal(completed.error.code, "MODEL_SELECTION_UNCONFIRMED");
  assert.equal(completed.modelSelection.selectedModelId, high);
  assert.equal(completed.modelSelection.selectedEffort, "high");
  assert.equal(completed.modelSelection.currentModelId, drifted);
  assert.equal(completed.modelSelection.currentEffort, "medium");

  const job = await broker.getJob(submitted.jobId);
  assert.equal(job.model.selectedModelId, high);
  assert.equal(job.model.selectedEffort, "high");
  assert.equal(job.model.currentModelId, drifted);
  assert.equal(job.request.model, null);
  assert.equal(job.request.effort, null);
  assert.equal(job.request.selectionPolicy.kind, "plugin-default");

  const stateContent = await readFile(job.proof.state, "utf8");
  assert(stateContent.includes(`Selected model: ${high}`));
  assert(stateContent.includes(`Current model: ${drifted}`));

  const proofContent = await readFile(job.proof.proof, "utf8");
  assert(proofContent.includes(`Selected model: ${high}`));
  assert(proofContent.includes(`Current model: ${drifted}`));
  await broker.close();
});
