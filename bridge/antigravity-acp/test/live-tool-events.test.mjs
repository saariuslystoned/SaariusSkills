import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AntigravityAcpBroker, formatAge } from "../broker.mjs";
import { buildView } from "../shed-sessions.mjs";

const FIXTURE_DIR = path.dirname(fileURLToPath(import.meta.url));
const TOOL_PEER = path.resolve(FIXTURE_DIR, "fixtures/tool-call-peer.mjs");

async function waitUntil(predicate, { timeoutMs = 15_000, intervalMs = 50 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

test("live tool-call events: shell commands show in events.jsonl and status while job is running", { timeout: 30_000 }, async () => {
  const stateRoot = await mkdtemp(path.join(tmpdir(), "agy-tool-events-state-"));
  const workspace = await mkdtemp(path.join(tmpdir(), "agy-tool-events-ws-"));
  const readyFile = path.join(stateRoot, "tools-ready.json");

  const broker = new AntigravityAcpBroker({
    stateRoot,
    defaultWorkspace: workspace,
    defaultHostConversationId: "conv-tool-events",
    runtimeServer: TOOL_PEER,
    helperPath: process.execPath,
    readAuthPolicy: async () => ({
      settingsPresent: true,
      authType: "oauth-personal",
      overageState: "never",
    }),
    processEnv: {
      PATH: process.env.PATH,
      TMPDIR: stateRoot,
      TOOL_READY_FILE: readyFile,
    },
  });

  try {
    const delegateResult = await broker.delegate({
      workspace,
      model: "gemini-3.8-flash-high",
      prompt: "Execute two shell commands",
    });

    const jobId = delegateResult.jobId;

    // Wait until both tools finished executing while turn is still running in tool-peer
    const ready = await waitUntil(async () => {
      try {
        const content = await readFile(readyFile, "utf8");
        return JSON.parse(content).ready === true;
      } catch {
        return false;
      }
    });

    assert.ok(ready, "Expected tools to execute in tool-peer");

    // Check status while the job is still running!
    const liveStatus = await broker.status({ jobId });
    assert.equal(liveStatus.jobId, jobId);
    assert.equal(liveStatus.complete, false, "Job should still be running");
    assert.equal(liveStatus.status, "running", "Job status should be running");

    // Status shows latest event and age
    assert.ok(liveStatus.latestEvent, "status must show latestEvent");
    assert.equal(liveStatus.latestEvent.event, "tool_call_finished");
    assert.equal(liveStatus.latestEvent.tool, "Bash");
    assert.ok(liveStatus.latestEventAge, "status must show latestEventAge");
    assert.ok(typeof liveStatus.latestEventAgeMs === "number");

    // Session viewer (/s/) buildView shows latest event and age
    const view = buildView({
      sessionId: "tool-session",
      task: {
        taskId: "task-test-tool",
        status: "running",
        latestEvent: liveStatus.latestEvent,
      },
    });
    assert.ok(view.latestEvent, "Session view must include latestEvent");
    assert.equal(view.latestEvent.event, "tool_call_finished");
    assert.equal(view.latestEvent.tool, "Bash");
    assert.ok(view.latestEventAge, "Session view must include latestEventAge");

    // Read events.jsonl while running
    const eventsPath = path.join(stateRoot, "runs", jobId, "events.jsonl");
    const eventsRaw = await readFile(eventsPath, "utf8");
    const events = eventsRaw.trim().split("\n").map((line) => JSON.parse(line));

    // Verify tool_call_started and tool_call_finished for both commands in events.jsonl
    const startedEvents = events.filter((e) => e.event === "tool_call_started");
    const finishedEvents = events.filter((e) => e.event === "tool_call_finished");

    assert.equal(startedEvents.length, 2, "Expected 2 tool_call_started events in events.jsonl");
    assert.equal(finishedEvents.length, 2, "Expected 2 tool_call_finished events in events.jsonl");

    // Verify first command tool call
    const start1 = startedEvents[0];
    assert.equal(start1.details.tool, "Bash");
    assert.ok(start1.details.summary.includes("[redacted]"), "Secrets in command 1 must be redacted");
    assert.equal(start1.details.summary.includes("sk-secret12345678901234"), false, "Secret token must not leak");
    assert.ok(start1.details.summary.length <= 200, "Summary must be under 200 chars");

    const finish1 = finishedEvents[0];
    assert.equal(finish1.details.tool, "Bash");
    assert.ok(typeof finish1.details.duration === "number", "Must carry duration");
    assert.ok(typeof finish1.details.durationMs === "number", "Must carry durationMs");
    assert.equal(finish1.details.exitStatus, 0, "Must carry exit status 0");

    // Verify second command tool call
    const start2 = startedEvents[1];
    assert.equal(start2.details.tool, "Bash");
    assert.ok(start2.details.summary.includes("[redacted]"), "Secrets in command 2 must be redacted");
    assert.equal(start2.details.summary.includes("cf-secret-token"), false, "Secret CF token must not leak");
    assert.ok(start2.details.summary.length <= 200, "Summary must be under 200 chars");

    const finish2 = finishedEvents[1];
    assert.equal(finish2.details.tool, "Bash");
    assert.ok(typeof finish2.details.duration === "number", "Must carry duration");
    assert.equal(finish2.details.exitStatus, 0, "Must carry exit status 0");

    // Heartbeat check: heartbeat file updated on events
    const heartbeatPath = path.join(stateRoot, "runs", jobId, "heartbeat");
    const heartbeatContent = await readFile(heartbeatPath, "utf8");
    assert.ok(heartbeatContent.trim().length > 0, "Heartbeat file must be written and non-empty");

    // Let the job complete normally
    const result = await broker.result({ jobId, waitMs: 5_000 });
    assert.equal(result.status, "completed");
    assert.equal(result.taskComplete, true);
  } finally {
    await broker.close();
    await new Promise((r) => setTimeout(r, 100));
    await rm(stateRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
    await rm(workspace, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
});
