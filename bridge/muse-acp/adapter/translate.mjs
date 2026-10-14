// Pure ACP <-> MSP translation helpers. No I/O lives here so every mapping is
// unit-testable without a `muse` binary.

export const MSP_SCHEMA_FINGERPRINT_V1_4_7 =
  "sha256:6de32db08bbbe0deb478d2bfcaba001e9fb490986bc80db3aceb4d996abf7df9";

// MSP commandIds are required idempotency handles and must be UUIDv7.
export function uuidv7(now = Date.now()) {
  const ts = now.toString(16).padStart(12, "0").slice(-12);
  const rnd = (n) =>
    [...crypto.getRandomValues(new Uint8Array(n))]
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  const variant = ["8", "9", "a", "b"][Math.floor(Math.random() * 4)];
  return `${ts.slice(0, 8)}-${ts.slice(8)}-7${rnd(2).slice(0, 3)}-${variant}${rnd(2).slice(0, 3)}-${rnd(6)}`;
}

// ACP prompt content blocks -> MSP TurnInputPart list. MSP part types are a
// closed set (text, image, skill, video); file mentions are plain text in MSP.
export function acpPromptToMspInput(blocks) {
  const parts = [];
  for (const block of blocks ?? []) {
    if (!block || typeof block !== "object") continue;
    if (block.type === "text" && typeof block.text === "string" && block.text.length > 0) {
      parts.push({ type: "text", text: block.text });
    } else if (block.type === "resource_link" && typeof block.uri === "string") {
      const label = typeof block.name === "string" && block.name ? block.name : block.uri;
      parts.push({ type: "text", text: `@${label} (${block.uri})` });
    } else if (block.type === "resource" && typeof block.resource?.text === "string") {
      const uri = block.resource.uri ?? "resource";
      parts.push({ type: "text", text: `${uri}:\n${block.resource.text}` });
    } else if (block.type === "image" && typeof block.data === "string" && typeof block.mimeType === "string") {
      parts.push({ type: "image", mediaType: block.mimeType, data: block.data });
    }
    // audio and unknown blocks have no MSP equivalent and are dropped rather
    // than mistranslated; the turn still fails closed below if nothing remains.
  }
  return parts;
}

export function promptDisplayText(parts) {
  return parts
    .filter((p) => p.type === "text")
    .map((p) => p.text)
    .join("\n");
}

// MSP turn terminal vocabulary is closed: completed | failed | cancelled.
export function stopReasonFromTerminal(terminal) {
  switch (terminal) {
    case "cancelled":
      return "cancelled";
    case "failed":
      return "error";
    case "completed":
    default:
      return "end_turn";
  }
}

// MSP ApprovalDecision + scope -> ACP PermissionOption kind.
export function acpOptionKind(choice) {
  const decision = choice?.decision ?? "";
  const scope = choice?.scope ?? "once";
  const allow = decision.startsWith("approved");
  if (allow) return scope === "once" ? "allow_once" : "allow_always";
  return scope === "once" ? "reject_once" : "reject_always";
}

export function acpPermissionOptions(choices) {
  return (choices ?? [])
    .filter((c) => c && typeof c.choiceId === "string")
    .map((c) => ({
      optionId: c.choiceId,
      name: typeof c.label === "string" && c.label ? c.label : c.choiceId,
      kind: acpOptionKind(c),
    }));
}

// Pick the fail-closed choice when the ACP client cancels a permission prompt.
export function denyChoiceId(choices) {
  const deny = (choices ?? []).find(
    (c) =>
      typeof c?.decision === "string" &&
      (c.decision === "denied" || c.decision.startsWith("denied") || c.decision === "abort"),
  );
  return deny?.choiceId ?? null;
}

// MSP model/list result -> ACP SessionModelState.
export function acpModelState(modelListResult) {
  const rows = Array.isArray(modelListResult?.models) ? modelListResult.models : [];
  const availableModels = rows
    .filter((m) => m && typeof m.modelId === "string" && m.modelId)
    .map((m) => ({
      modelId: m.modelId,
      name: typeof m.displayLabel === "string" && m.displayLabel ? m.displayLabel : m.modelId,
      ...(typeof m.description === "string" && m.description ? { description: m.description } : {}),
    }));
  const current =
    rows.find((m) => m?.isActive)?.modelId ??
    rows.find((m) => m?.isDefault)?.modelId ??
    availableModels[0]?.modelId ??
    null;
  if (!availableModels.length || !current) return null;
  return { availableModels, currentModelId: current };
}

export const REASONING_EFFORTS = Object.freeze([
  "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra",
]);

export function reasoningConfigOption(currentValue) {
  return {
    id: "reasoning_effort",
    name: "Reasoning Effort",
    description: "MSP reasoning tier sampled at turn submission.",
    category: "thought_level",
    type: "select",
    currentValue: currentValue ?? "high",
    options: REASONING_EFFORTS.map((value) => ({ value, name: value })),
  };
}

// One MSP item event -> ACP session/update payloads. Returns [] for items the
// client should not see (user messages echo, unknown kinds, empty deltas).
export function itemEventToAcpUpdates(method, params) {
  const updates = [];
  if (method === "item/delta") {
    if (typeof params?.delta === "string" && params.delta && (params.field === undefined || params.field === "text")) {
      updates.push({
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: params.delta },
      });
    }
    return updates;
  }
  const item = params?.item;
  if (!item || typeof item !== "object") return updates;
  if (item.kind === "toolCall") {
    const callId = item.callId ?? item.itemId;
    if (!callId) return updates;
    if (method === "item/started") {
      updates.push({
        sessionUpdate: "tool_call",
        toolCallId: callId,
        title: item.tool ?? item.label ?? "tool",
        kind: "other",
        status: "in_progress",
        ...(item.args !== undefined ? { rawInput: item.args } : {}),
      });
    } else if (method === "item/completed" || method === "item/updated") {
      const done = item.status === "completed" || item.status === "failed";
      updates.push({
        sessionUpdate: "tool_call_update",
        toolCallId: callId,
        ...(done ? { status: item.status === "failed" ? "failed" : "completed" } : {}),
        ...(typeof item.visibleOutput === "string" && item.visibleOutput
          ? { content: [{ type: "content", content: { type: "text", text: item.visibleOutput } }] }
          : {}),
      });
    }
  }
  return updates;
}
