import readline from "node:readline";
import { appendFileSync, writeFileSync } from "node:fs";

const model = "gemini-3.8-flash-high";
const [pidFile, heartbeatFile] = process.argv.slice(2);
writeFileSync(pidFile, String(process.pid));
writeFileSync(heartbeatFile, "0\n");

const lines = readline.createInterface({ input: process.stdin });
for await (const line of lines) {
  let request;
  try { request = JSON.parse(line); } catch { continue; }
  if (request.id === undefined) continue;
  let result = {};
  if (request.method === "initialize") {
    result = {
      protocolVersion: 1,
      agentCapabilities: { loadSession: false, promptCapabilities: {} },
      agentInfo: { name: "persistent-synthetic-acp-peer", version: "1.0.0" },
      authMethods: [],
    };
  } else if (request.method === "session/new") {
    result = {
      sessionId: "synthetic-session",
      models: { currentModelId: model, availableModels: [{ modelId: model, name: model }] },
    };
  } else if (request.method === "session/prompt") {
    result = { stopReason: "end_turn" };
  }
  process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result })}\n`);
}

// Keep the synthetic ACP child alive after its broker's stdin closes. This is
// deliberate cleanup uncertainty for the owner-death recovery proof.
let heartbeat = 0;
setInterval(() => appendFileSync(heartbeatFile, `${++heartbeat}\n`), 100);
