#!/usr/bin/env node
import { createInterface } from "node:readline";
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

const rl = createInterface({ input: process.stdin, terminal: false });

let child = null;

rl.on("line", (line) => {
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
        agentInfo: { name: "antigravity-sleep-peer", version: "1.0.0" },
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
        sessionId: "sleep-session",
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
    // Start long running child process sleep 600
    child = spawn("sleep", ["600"], { stdio: "ignore" });
    const targetDir = process.env.TMPDIR || process.env.GEMINI_HOME || "/tmp";
    const pidFile = path.join(targetDir, "sleep-pids.json");
    writeFileSync(pidFile, JSON.stringify({ workerPid: process.pid, childPid: child.pid }));
    // Do not reply immediately; stay running until cancelled
    return;
  }

  if (method === "session/cancel") {
    if (id !== undefined) send({ jsonrpc: "2.0", id, result: {} });
    return;
  }
});
