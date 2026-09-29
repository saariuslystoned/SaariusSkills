import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createAcpRuntime } from "acpx/runtime";
import { createAgentRegistry } from "acpx/agent-registry";
import { createProcessLifecycleTracker, discardCandidateTurnEvents } from "../puppet-adapter.mjs";

// A local ACP peer exercises the published runtime's real timers without a
// provider call or an hour-long soak. Concurrent handling permits cancel/close
// while the synthetic prompt is deliberately delayed.
const peerSource = `
import { createInterface } from "node:readline";
const send = (id, result) => process.stdout.write(JSON.stringify({jsonrpc:"2.0",id,result})+"\\n");
const lines = createInterface({input:process.stdin});
lines.on("line", async (line) => {
  const {id,method,params} = JSON.parse(line);
  if (id === undefined) return;
  if (method === "initialize") return send(id, {
    protocolVersion:params.protocolVersion,
    agentCapabilities:{loadSession:true,sessionCapabilities:{close:{}}},
    authMethods:[]
  });
  if (method === "session/new") return send(id,{sessionId:"timeout-peer"});
  if (method === "session/prompt") {
    const text = params.prompt.find((block) => block.type === "text").text;
    await new Promise((resolve) => setTimeout(resolve,Number(text)));
    return send(id,{stopReason:"end_turn"});
  }
  send(id,{});
});
`;

for (const scenario of [
  { name: "explicit turn budget outlives the shorter control timeout", delayMs: 1_500, turnMs: 4_000, status: "completed" },
  { name: "explicit short turn budget expires and owned peer cleanup completes", delayMs: 5_000, turnMs: 1_000, status: "failed" },
]) {
  test(`published acpx 0.19.3: ${scenario.name}`, { timeout: 20_000 }, async () => {
    const cwd = await mkdtemp(path.join(os.tmpdir(), "acpx-turn-timeout-"));
    const peer = path.join(cwd, "peer.mjs");
    await writeFile(peer, peerSource);
    const sessions = new Map();
    const tracker = createProcessLifecycleTracker();
    const sessionKey = `timeout-${scenario.status}`;
    const runtime = createAcpRuntime({
      cwd,
      timeoutMs: 1_000,
      agentRegistry: createAgentRegistry({ overrides: { cursor: [process.execPath, peer] } }),
      sessionStore: {
        async load(id) { return structuredClone(sessions.get(id)); },
        async save(record) { sessions.set(record.acpxRecordId, structuredClone(record)); },
      },
      fs: false,
      terminal: false,
      processLifecycle: tracker.processLifecycle,
    });
    try {
      const handle = await runtime.ensureSession({ sessionKey, agent: "cursor", mode: "persistent", cwd });
      const started = Date.now();
      const turn = runtime.startTurn({ handle, text: String(scenario.delayMs), mode: "prompt", requestId: sessionKey, timeoutMs: scenario.turnMs });
      const events = discardCandidateTurnEvents(turn);
      const result = await turn.result;
      await events;
      assert.equal(result.status, scenario.status);
      if (scenario.status === "completed") {
        assert.equal(result.stopReason, "end_turn");
        assert.ok(Date.now() - started > runtime.options.timeoutMs);
      } else {
        assert.match(`${result.error?.code} ${result.error?.message}`, /timeout|timed out/i);
      }
      await runtime.close({ handle, reason: "timeout-regression-complete", discardPersistentState: true });
      const proof = await tracker.waitForOwnedExit(sessionKey, { timeoutMs: 5_000 });
      assert.equal(proof.status, "exited");
      assert.ok(proof.started.length > 0);
      assert.equal(proof.exits.length, proof.started.length);
    } finally {
      await runtime.shutdown();
    }
  });
}
