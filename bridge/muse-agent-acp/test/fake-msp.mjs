#!/usr/bin/env node
// Fake `muse serve` MSP host for adapter tests. Ignores argv. Emits one
// streamed agent message per turn and completes it. If the prompt text
// contains NEEDS_APPROVAL, issues an approval/request and waits for
// approval/decide before completing.

import { createInterface } from "node:readline";

const rl = createInterface({ input: process.stdin });
const write = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");
const notify = (method, params) => write({ jsonrpc: "2.0", method, params });
let sessionSeq = 0;
let pendingApproval = null;

for await (const line of rl) {
  if (!line.trim()) continue;
  const msg = JSON.parse(line);
  if (msg.method === undefined) continue; // receipts for our requests
  const respond = (result) => write({ jsonrpc: "2.0", id: msg.id, result });
  switch (msg.method) {
    case "initialize":
      respond({ schema: { version: 1, fingerprint: "sha256:fake" }, serverInfo: { name: "muse-fake", version: "0.0.0" } });
      break;
    case "session/start": {
      sessionSeq += 1;
      const sessionId = `fake-session-${sessionSeq}`;
      respond({ session: { sessionId, status: "idle", reasoningEffort: "high" } });
      notify("session/started", { sessionId });
      break;
    }
    case "model/list":
      respond({
        models: [
          { modelId: "fake-model-1", displayLabel: "Fake 1", isDefault: true, isActive: true },
          { modelId: "fake-model-2", displayLabel: "Fake 2" },
        ],
      });
      break;
    case "turn/start": {
      const { sessionId, input } = msg.params;
      const text = (input ?? []).filter((p) => p.type === "text").map((p) => p.text).join(" ");
      const turnId = `turn-${sessionSeq}`;
      respond({ status: "accepted", turnId });
      const finish = () => {
        notify("item/started", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "inProgress", text: "" } });
        notify("item/delta", { sessionId, itemId: "i1", field: "text", delta: `echo: ${text}` });
        notify("item/completed", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "completed", text: `echo: ${text}` } });
        notify("turn/completed", { sessionId, turnId, terminal: "completed" });
      };
      if (text.includes("FAILS_TURN")) {
        notify("item/started", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "inProgress", text: "" } });
        notify("item/delta", { sessionId, itemId: "i1", field: "text", delta: "something failed" });
        notify("item/completed", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "failed", text: "something failed" } });
        notify("turn/completed", { sessionId, turnId, terminal: "failed", error: { message: "intentional turn failure" } });
      } else if (text.includes("NEEDS_APPROVAL")) {
        pendingApproval = { finish };
        write({
          jsonrpc: "2.0",
          id: 9001,
          method: "approval/request",
          params: {
            sessionId,
            approvalId: "ap-1",
            toolCallId: "call-1",
            toolName: "bash",
            availableChoices: [
              { choiceId: "allow-once", label: "Allow once", decision: "approved", scope: "once" },
              { choiceId: "deny-once", label: "Deny", decision: "denied", scope: "once" },
            ],
          },
        });
      } else {
        finish();
      }
      break;
    }
    case "approval/decide": {
      respond({ ok: true, choiceId: msg.params?.choiceId });
      if (pendingApproval) {
        const { finish } = pendingApproval;
        pendingApproval = null;
        finish();
      }
      break;
    }
    case "turn/cancel":
      respond({ ok: true });
      notify("turn/completed", { sessionId: msg.params?.sessionId, turnId: msg.params?.turnId, terminal: "cancelled" });
      break;
    case "session/setModel":
    case "session/setReasoningEffort":
    case "userInput/cancel":
      respond({ ok: true });
      break;
    default:
      if (msg.id !== undefined) {
        write({ jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: `fake msp: unhandled ${msg.method}` } });
      }
  }
}
