#!/usr/bin/env node
// Fake `muse serve` MSP host for adapter tests. Ignores argv. Emits one
// streamed agent message per turn and completes it. If the prompt text
// contains NEEDS_APPROVAL, issues an approval/request and waits for
// approval/decide before completing.

import { appendFileSync } from "node:fs";
import { createInterface } from "node:readline";

const rl = createInterface({ input: process.stdin });
const write = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");
const notify = (method, params) => write({ jsonrpc: "2.0", method, params });
let sessionSeq = 0;
let pendingApproval = null;

function recordEvent(event) {
  const path = process.env.MUSE_FAKE_DECISIONS_FILE;
  if (!path) return;
  try {
    appendFileSync(path, JSON.stringify(event) + "\n", "utf8");
  } catch {
    // ignore
  }
}

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
    case "approval/listPending": {
      recordEvent({ type: "approval/listPending", sessionId: msg.params?.sessionId });
      const approvals =
        pendingApproval && pendingApproval.exposeInListPending !== false && pendingApproval.params
          ? [pendingApproval.params]
          : [];
      respond({ approvals, userInputs: [] });
      break;
    }
    case "turn/start": {
      const { sessionId, input } = msg.params;
      const text = (input ?? []).filter((p) => p.type === "text").map((p) => p.text).join(" ");
      const turnId = `turn-${sessionSeq}`;
      respond({ status: "accepted", turnId });
      const finish = (msgText = `echo: ${text}`) => {
        notify("item/started", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "inProgress", text: "" } });
        notify("item/delta", { sessionId, itemId: "i1", field: "text", delta: msgText });
        notify("item/completed", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "completed", text: msgText } });
        notify("turn/completed", { sessionId, turnId, terminal: "completed" });
      };
      if (text.includes("FAILS_TURN")) {
        notify("item/started", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "inProgress", text: "" } });
        notify("item/delta", { sessionId, itemId: "i1", field: "text", delta: "something failed" });
        notify("item/completed", { sessionId, item: { itemId: "i1", kind: "agentMessage", turnId, status: "failed", text: "something failed" } });
        notify("turn/completed", { sessionId, turnId, terminal: "failed", error: { message: "intentional turn failure" } });
      } else if (text.includes("HUMAN_PENDING_APPROVAL")) {
        const approvalParams = {
          sessionId,
          turnId,
          approvalId: "ap-human-1",
          toolCallId: "call-human-1",
          toolName: "bash",
          presentation: "human_pending",
          rawArgs: {
            command: "npm test",
            sandbox_permissions: "require_escalated",
          },
          availableChoices: [
            { choiceId: "allow-once", label: "Allow once", decision: "approved", scope: "once" },
            { choiceId: "abort-turn", label: "Abort", decision: "abort", scope: "once" },
          ],
        };
        pendingApproval = {
          approvalId: "ap-human-1",
          params: approvalParams,
          exposeInListPending: true,
          onDecide: (choiceId) => {
            notify("approval/resolved", {
              sessionId,
              turnId,
              approvalId: "ap-human-1",
              decision: choiceId === "allow-once" ? "approved" : "abort",
            });
            if (choiceId === "allow-once") {
              finish();
            }
          },
        };
        notify("approval/requested", approvalParams);
      } else if (text.includes("DEDUPE_APPROVAL")) {
        const approvalParams = {
          sessionId,
          turnId,
          approvalId: "ap-dedupe-1",
          toolCallId: "call-dedupe-1",
          toolName: "bash",
          presentation: "human_pending",
          availableChoices: [
            { choiceId: "allow-once", label: "Allow once", decision: "approved", scope: "once" },
            { choiceId: "abort-turn", label: "Abort", decision: "abort", scope: "once" },
          ],
        };
        pendingApproval = {
          approvalId: "ap-dedupe-1",
          params: approvalParams,
          exposeInListPending: true,
          onDecide: (choiceId) => {
            if (choiceId === "allow-once") {
              finish();
            }
          },
        };
        notify("approval/requested", approvalParams);
        write({
          jsonrpc: "2.0",
          id: 9002,
          method: "approval/request",
          params: approvalParams,
        });
      } else if (text.includes("LIST_PENDING_ONLY")) {
        const approvalParams = {
          sessionId,
          turnId,
          approvalId: "ap-polled-1",
          toolCallId: "call-polled-1",
          toolName: "bash",
          presentation: "human_pending",
          availableChoices: [
            { choiceId: "allow-once", label: "Allow once", decision: "approved", scope: "once" },
            { choiceId: "abort-turn", label: "Abort", decision: "abort", scope: "once" },
          ],
        };
        const delayMs = text.includes("DELAYED_LIST_PENDING") ? 60 : 0;
        pendingApproval = {
          approvalId: "ap-polled-1",
          params: approvalParams,
          exposeInListPending: delayMs === 0,
          onDecide: (choiceId) => {
            if (choiceId === "allow-once") {
              finish();
            }
          },
        };
        if (delayMs > 0) {
          setTimeout(() => {
            if (pendingApproval && pendingApproval.approvalId === "ap-polled-1") {
              pendingApproval.exposeInListPending = true;
            }
          }, delayMs).unref?.();
        }
      } else if (text.includes("NEEDS_APPROVAL")) {
        const approvalParams = {
          sessionId,
          approvalId: "ap-1",
          toolCallId: "call-1",
          toolName: "bash",
          availableChoices: [
            { choiceId: "allow-once", label: "Allow once", decision: "approved", scope: "once" },
            { choiceId: "deny-once", label: "Deny", decision: "denied", scope: "once" },
          ],
        };
        pendingApproval = {
          approvalId: "ap-1",
          params: approvalParams,
          exposeInListPending: true,
          onDecide: (choiceId) => {
            if (choiceId === "allow-once") {
              finish();
            }
          },
        };
        write({
          jsonrpc: "2.0",
          id: 9001,
          method: "approval/request",
          params: approvalParams,
        });
      } else {
        finish();
      }
      break;
    }
    case "approval/decide": {
      const choiceId = msg.params?.choiceId;
      const approvalId = msg.params?.approvalId;
      recordEvent({ type: "approval/decide", approvalId, choiceId, sessionId: msg.params?.sessionId });
      respond({ ok: true, choiceId });
      if (pendingApproval && (!approvalId || pendingApproval.approvalId === approvalId)) {
        const current = pendingApproval;
        pendingApproval = null;
        current.onDecide?.(choiceId);
      }
      break;
    }
    case "turn/cancel":
      recordEvent({ type: "turn/cancel", sessionId: msg.params?.sessionId, turnId: msg.params?.turnId });
      pendingApproval = null;
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
