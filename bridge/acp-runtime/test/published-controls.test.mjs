import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { createProcessLifecycleTracker } from "../../cursor-acp/puppet-adapter.mjs";

const exact = "fixture-model[reasoning=medium]";
const peer = fileURLToPath(new URL("./fixtures/control-peer.mjs", import.meta.url));
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";

async function fixture(lane, scenario) {
  // Resolve each bridge's own public package exports, never a stub runtime.
  const require = createRequire(new URL(`../../${lane}/package.json`, import.meta.url));
  assert.equal(require("acpx/package.json").version, "0.19.4");
  const { createAcpRuntime } = await import(pathToFileURL(require.resolve("acpx/runtime")));
  const { createAgentRegistry } = await import(pathToFileURL(require.resolve("acpx/agent-registry")));
  const cwd = await mkdtemp(path.join(tmpdir(), "acpx-0194-controls-"));
  const trace = path.join(cwd, "wire.jsonl"), marker = path.join(cwd, "timeout-marker");
  const executable = path.join(cwd, "cursor-agent");
  await writeFile(executable, `#!/bin/sh\nexec ${quote(process.execPath)} ${quote(peer)} acp ${quote(scenario)} ${quote(trace)} ${quote(marker)}\n`, { mode: 0o700 });
  const records = new Map(), tracker = createProcessLifecycleTracker();
  const runtime = createAcpRuntime({ cwd, timeoutMs: 5000,
    agentRegistry: createAgentRegistry({ overrides: { cursor: [executable, "acp"] } }),
    sessionStore: { async load(id) { return structuredClone(records.get(id)); },
      async save(record) { records.set(record.acpxRecordId, structuredClone(record)); } },
    fs: false, terminal: false, processLifecycle: tracker.processLifecycle });
  return { runtime, records, tracker, cwd, marker,
    async wire() { return (await readFile(trace, "utf8")).trim().split("\n").map(JSON.parse); } };
}

async function turn(runtime, handle, requestId, timeoutMs = 5000) {
  const turn = runtime.startTurn({ handle, text: requestId, mode: "prompt", requestId, timeoutMs });
  const output = (async () => { let text = ""; for await (const event of turn.events)
    if (event.type === "text_delta" && event.stream !== "thought") text += event.text; return text; })();
  const result = await turn.result;
  return { result, text: await output };
}

async function exits(f, key) {
  const proof = await f.tracker.waitForOwnedExit(key, { timeoutMs: 5000 });
  assert.equal(proof.status, "exited", JSON.stringify(proof));
  assert.ok(proof.started.length > 0);
  assert.equal(proof.exits.length, proof.started.length);
  for (const launch of proof.started) {
    assert.ok(proof.exits.some(exit => exit.launchId === launch.launchId && exit.pid === launch.pid));
    assert.throws(() => process.kill(launch.pid, 0), error => error.code === "ESRCH");
  }
}

for (const lane of ["cursor-acp", "antigravity-acp", "grok-acp"]) {
  for (const scenario of ["alias", "omitted", "non-list"]) {
    test(`${lane} 0.19.4: ${scenario} acknowledgement preserves resolved selection and reconnect alias`, { timeout: 15000 }, async () => {
      const f = await fixture(lane, scenario), key = `${lane}-${scenario}`;
      try {
        const handle = await f.runtime.ensureSession({ sessionKey: key, agent: "cursor", mode: "persistent", cwd: f.cwd });
        await f.runtime.setModel({ handle, model: "fixture-model" });
        assert.equal((await f.runtime.getStatus({ handle })).models.currentModelId, exact);
        assert.equal(f.records.get(handle.acpxRecordId).acpx.session_options.model, "fixture-model");
        const first = await turn(f.runtime, handle, "first");
        assert.equal(first.result.status, "completed"); assert.equal(first.text, exact);
        // The synthetic adapter exits after its response. Reconnect must replay
        // the saved alias and retain the resolved current id on a fresh child.
        await exits(f, key);
        const next = await turn(f.runtime, handle, "reconnected");
        assert.equal(next.result.status, "completed"); assert.equal(next.text, exact);
        assert.equal((await f.runtime.getStatus({ handle })).models.currentModelId, exact);
        const prompts = (await f.wire()).filter(event => event.method === "session/prompt");
        assert.equal(prompts.length, 2); assert.notEqual(prompts[0].pid, prompts[1].pid);
      } finally { await f.runtime.shutdown(); }
    });
  }

  test(`${lane} 0.19.4: reused provider IDs preserve histories and replacement ownership`, { timeout: 15000 }, async () => {
    const f = await fixture(lane, "alias");
    const key = `${lane}-shared-key`;
    try {
      const one = await f.runtime.ensureSession({ sessionKey: key, agent: "cursor", mode: "oneshot", cwd: f.cwd });
      assert.equal((await turn(f.runtime, one, "history-one")).result.status, "completed");
      const two = await f.runtime.ensureSession({ sessionKey: key, agent: "cursor", mode: "oneshot", cwd: f.cwd });
      assert.equal(one.backendSessionId, two.backendSessionId);
      assert.notEqual(one.acpxRecordId, two.acpxRecordId);
      await f.runtime.close({ handle: one, reason: "old-record-close", discardPersistentState: true });
      assert.equal((await turn(f.runtime, two, "history-two")).result.status, "completed");
      const historyOne = JSON.stringify(f.records.get(one.acpxRecordId));
      const historyTwo = JSON.stringify(f.records.get(two.acpxRecordId));
      assert.match(historyOne, /history-one/); assert.doesNotMatch(historyOne, /history-two/);
      assert.match(historyTwo, /history-two/); assert.doesNotMatch(historyTwo, /history-one/);
      await f.runtime.close({ handle: two, reason: "replacement-close", discardPersistentState: true });
    } finally { await f.runtime.shutdown(); }
    await exits(f, key);
  });

  for (const scenario of ["startup", "removed"]) {
    const claim = scenario === "removed"
      ? "rejects a model absent from the initial catalog"
      : "selects a model advertised by the initial catalog";
    test(`${lane} 0.19.4: published temporary exec ${claim}`, { timeout: 15000 }, async () => {
      const f = await fixture(lane, scenario);
      const require = createRequire(new URL(`../../${lane}/package.json`, import.meta.url));
      const { execFile } = await import("node:child_process");
      const { promisify } = await import("node:util");
      const executable = path.join(f.cwd, "cursor-agent");
      let outcome;
      try {
        outcome = await promisify(execFile)(process.execPath, [require.resolve("acpx"), "--agent", executable,
          "--cwd", f.cwd, "--model", "fixture-model", "--no-fs", "--no-terminal", "--deny-all",
          "--timeout", "5", "exec", "startup-proof"], {
          env: { HOME: f.cwd, PATH: process.env.PATH }, timeout: 10000 });
      } catch (error) { outcome = error; }
      const wire = await f.wire();
      const prompts = wire.filter(event => event.method === "session/prompt");
      if (scenario === "removed") {
        assert.equal(outcome.code, 1); assert.match(outcome.stderr, /model|support/i); assert.equal(prompts.length, 0);
        assert.equal(wire.filter(event => ["session/set_config_option", "session/set_model"].includes(event.method)).length, 0);
      } else {
        assert.equal(outcome.code, undefined, outcome.stderr); assert.equal(prompts.length, 1);
        assert.equal(wire.find(event => event.method === "session/set_config_option").value, exact);
      }
      for (const pid of new Set(wire.map(event => event.pid)))
        assert.throws(() => process.kill(pid, 0), error => error.code === "ESRCH");
      await f.runtime.shutdown();
    });
  }

  for (const scenario of ["bound-add", "bound-remove"]) {
    const claim = scenario === "bound-remove"
      ? "fail-closes after a bound catalog removal"
      : "applies a bound catalog addition before setModel";
    test(`${lane} 0.19.4: published runtime ${claim}`, { timeout: 15000 }, async () => {
      const f = await fixture(lane, scenario), key = `${lane}-${scenario}`;
      try {
        const handle = await f.runtime.ensureSession({ sessionKey: key, agent: "cursor", mode: "persistent", cwd: f.cwd });
        const before = await f.runtime.getStatus({ handle });
        assert.equal(before.models.currentModelId, "old-model");
        assert.deepEqual(before.models.availableModelIds, scenario === "bound-remove" ? ["old-model", exact] : ["old-model"]);
        await f.runtime.setMode({ handle, mode: "catalog-handshake" });
        const after = await f.runtime.getStatus({ handle });
        const beforeSelection = await f.wire();
        assert.equal(beforeSelection.filter(event => event.method === "session/set_mode").length, 1);
        assert.equal(beforeSelection.filter(event => ["session/set_config_option", "session/set_model"].includes(event.method)).length, 0);
        if (scenario === "bound-remove") {
          assert.equal(after.models, undefined);
          await assert.rejects(() => f.runtime.setModel({ handle, model: "fixture-model" }), /model|support/i);
        } else {
          assert.equal(after.models.currentModelId, "old-model");
          assert.deepEqual(after.models.availableModelIds, ["old-model", exact]);
          await f.runtime.setModel({ handle, model: "fixture-model" });
          assert.equal((await f.runtime.getStatus({ handle })).models.currentModelId, exact);
        }
        const wire = await f.wire();
        const setters = wire.filter(event => ["session/set_config_option", "session/set_model"].includes(event.method));
        if (scenario === "bound-remove") assert.equal(setters.length, 0);
        else { assert.equal(setters.length, 1); assert.equal(setters[0].value, exact); }
      } finally { await f.runtime.shutdown(); }
      for (const pid of new Set((await f.wire()).map(event => event.pid)))
        assert.throws(() => process.kill(pid, 0), error => error.code === "ESRCH");
    });
  }

  test(`${lane} 0.19.4: timed-out prompt model control retires adapter before reconnect`, { timeout: 15000 }, async () => {
    const f = await fixture(lane, "timeout"), key = `${lane}-timeout`;
    try {
      const handle = await f.runtime.ensureSession({ sessionKey: key, agent: "cursor", mode: "persistent", cwd: f.cwd,
        sessionOptions: { model: "fixture-model" } });
      assert.equal((await turn(f.runtime, handle, "first-before-timeout")).result.status, "completed");
      await exits(f, key);
      const timed = await turn(f.runtime, handle, "model-control-timeout", 1000);
      assert.equal(timed.result.status, "failed");
      assert.match(timed.result.error.message, /timed out|timeout/i);
      await exits(f, key);
      const prior = await f.wire();
      assert.equal(prior.filter(event => event.method === "session/prompt").length, 1);
      assert.equal(prior.filter(event => event.method === "session/set_config_option").length, 2);
      // Change the local fixture's deliberate failure, then demand a new child.
      const { unlink } = await import("node:fs/promises"); await unlink(f.marker);
      const next = await turn(f.runtime, handle, "after-retirement");
      assert.equal(next.result.status, "completed"); assert.equal(next.text, exact);
      const wire = await f.wire();
      const prompts = wire.filter(event => event.method === "session/prompt");
      assert.equal(prompts.length, 2); assert.notEqual(prompts[0].pid, prompts[1].pid);
    } finally { await f.runtime.shutdown(); }
    await exits(f, key);
  });
}
