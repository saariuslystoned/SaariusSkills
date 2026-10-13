import test from "node:test";
import assert from "node:assert/strict";
import {
  acpModelState,
  acpPermissionOptions,
  acpPromptToMspInput,
  denyChoiceId,
  itemEventToAcpUpdates,
  stopReasonFromTerminal,
  uuidv7,
} from "../../muse-acp/adapter/translate.mjs";

test("uuidv7 has version 7 and RFC variant", () => {
  const id = uuidv7(1791854251800);
  assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test("prompt blocks translate to closed MSP part types", () => {
  const parts = acpPromptToMspInput([
    { type: "text", text: "hello" },
    { type: "resource_link", uri: "file:///tmp/a.md", name: "a.md" },
    { type: "resource", resource: { uri: "file:///tmp/b", text: "body" } },
    { type: "image", data: "AAAA", mimeType: "image/png" },
    { type: "audio", data: "AAAA", mimeType: "audio/wav" },
    { type: "text", text: "" },
    null,
  ]);
  assert.deepEqual(
    parts.map((p) => p.type),
    ["text", "text", "text", "image"],
  );
  assert.equal(parts[0].text, "hello");
  assert.match(parts[1].text, /@a\.md/);
  assert.match(parts[2].text, /body/);
  assert.deepEqual(acpPromptToMspInput([]), []);
  assert.deepEqual(acpPromptToMspInput(undefined), []);
});

test("terminal mapping is fail-safe", () => {
  assert.equal(stopReasonFromTerminal("completed"), "end_turn");
  assert.equal(stopReasonFromTerminal("failed"), "end_turn");
  assert.equal(stopReasonFromTerminal("cancelled"), "cancelled");
  assert.equal(stopReasonFromTerminal("something-new"), "end_turn");
  assert.equal(stopReasonFromTerminal(undefined), "end_turn");
});

test("approval choices map to ACP option kinds and deny is fail-closed", () => {
  const choices = [
    { choiceId: "a1", label: "Allow once", decision: "approved", scope: "once" },
    { choiceId: "a2", label: "Allow session", decision: "approvedForSession", scope: "session" },
    { choiceId: "d1", label: "Deny", decision: "denied", scope: "once" },
  ];
  assert.deepEqual(
    acpPermissionOptions(choices).map((o) => o.kind),
    ["allow_once", "allow_always", "reject_once"],
  );
  assert.equal(denyChoiceId(choices), "d1");
  assert.equal(denyChoiceId([{ choiceId: "x", decision: "approved" }]), null);
  assert.deepEqual(acpPermissionOptions(undefined), []);
});

test("model state prefers active then default rows", () => {
  const state = acpModelState({
    models: [
      { modelId: "m-old", displayLabel: "Old" },
      { modelId: "m-def", displayLabel: "Default", isDefault: true },
      { modelId: "m-live", displayLabel: "Live", isActive: true },
      { displayLabel: "no id" },
    ],
  });
  assert.equal(state.currentModelId, "m-live");
  assert.deepEqual(state.availableModels.map((m) => m.modelId), ["m-old", "m-def", "m-live"]);
  assert.equal(acpModelState({ models: [] }), null);
  assert.equal(acpModelState(undefined), null);
});

test("item deltas become message chunks; user echoes stay hidden", () => {
  assert.deepEqual(itemEventToAcpUpdates("item/delta", { delta: "hi", field: "text" }), [
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "hi" } },
  ]);
  assert.deepEqual(itemEventToAcpUpdates("item/delta", { delta: "x", field: "summary.0" }), []);
  assert.deepEqual(
    itemEventToAcpUpdates("item/completed", { item: { kind: "userMessage", text: "hello" } }),
    [],
  );
  assert.deepEqual(
    itemEventToAcpUpdates("item/completed", { item: { kind: "agentMessage", text: "done" } }),
    [],
  );
});

test("tool call items become ACP tool call updates", () => {
  const started = itemEventToAcpUpdates("item/started", {
    item: { kind: "toolCall", callId: "c1", tool: "bash", args: { command: "ls" } },
  });
  assert.equal(started[0].sessionUpdate, "tool_call");
  assert.equal(started[0].toolCallId, "c1");
  const done = itemEventToAcpUpdates("item/completed", {
    item: { kind: "toolCall", callId: "c1", status: "completed", visibleOutput: "out" },
  });
  assert.equal(done[0].sessionUpdate, "tool_call_update");
  assert.equal(done[0].status, "completed");
});
