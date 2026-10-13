#!/usr/bin/env node
import { createInterface } from "node:readline";
import { writeFileSync } from "node:fs";
import path from "node:path";

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function notify(method, params) {
  send({ jsonrpc: "2.0", method, params });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const rl = createInterface({ input: process.stdin, terminal: false });

rl.on("line", async (line) => {
  if (!line.trim()) return;
  const msg = JSON.parse(line);
  const { id, method, params } = msg;

  if (method === "initialize") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: 1,
        agentCapabilities: {
          loadSession: true,
          promptCapabilities: { image: false, audio: false, embeddedContext: false },
          sessionCapabilities: { close: {} },
        },
        agentInfo: { name: "antigravity-tool-peer", version: "1.0.0" },
        authMethods: [],
      },
    });
    return;
  }

  if (method === "session/new") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        sessionId: "tool-session",
        modes: { currentModeId: "auto", availableModes: [{ id: "auto", name: "Auto" }] },
        models: {
          currentModelId: "gemini-3.8-flash-high",
          availableModels: [{ modelId: "gemini-3.8-flash-high", name: "Gemini 3.8 Flash High" }],
        },
      },
    });
    return;
  }

  if (method === "session/prompt") {
    const sessionId = params?.sessionId || "tool-session";

    // 1. Tool call 1 started
    notify("session/update", {
      sessionId,
      update: {
        sessionUpdate: "tool_call",
        toolCallId: "call-1",
        title: "Bash",
        kind: "execute",
        status: "in_progress",
        rawInput: { command: "curl -H 'Authorization: Bearer sk-secret12345678901234' https://api.example.com" },
      },
    });

    await sleep(60);

    // 2. Tool call 1 finished
    notify("session/update", {
      sessionId,
      update: {
        sessionUpdate: "tool_call_update",
        toolCallId: "call-1",
        title: "Bash",
        status: "completed",
        rawOutput: { exitCode: 0, output: "ok" },
      },
    });

    await sleep(60);

    // 3. Tool call 2 started
    notify("session/update", {
      sessionId,
      update: {
        sessionUpdate: "tool_call",
        toolCallId: "call-2",
        title: "Bash",
        kind: "execute",
        status: "in_progress",
        rawInput: { command: "echo CF_API_TOKEN=cf-secret-token-abcdef1234567890" },
      },
    });

    await sleep(60);

    // 4. Tool call 2 finished
    notify("session/update", {
      sessionId,
      update: {
        sessionUpdate: "tool_call_update",
        toolCallId: "call-2",
        title: "Bash",
        status: "completed",
        rawOutput: { exitCode: 0, output: "done" },
      },
    });

    const targetDir = process.env.TMPDIR || process.env.GEMINI_HOME || "/tmp";
    const readyFile = path.join(targetDir, "tools-ready.json");
    writeFileSync(readyFile, JSON.stringify({ ready: true, time: Date.now() }));

    // Keep the turn alive for 800ms so caller can inspect live status
    await sleep(800);

    // Complete the turn
    notify("session/update", {
      sessionId,
      update: {
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: "Finished executing tools successfully." },
      },
    });

    send({
      jsonrpc: "2.0",
      id,
      result: { stopReason: "end_turn" },
    });
    return;
  }

  if (method === "session/cancel") {
    if (id !== undefined) send({ jsonrpc: "2.0", id, result: {} });
    return;
  }
});
