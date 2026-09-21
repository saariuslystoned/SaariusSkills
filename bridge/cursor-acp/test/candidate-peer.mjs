#!/usr/bin/env node
import { createInterface } from "node:readline";
import { writeFile } from "node:fs/promises";

const capabilitiesPath = process.env.PUPPET_ACPX_CANDIDATE_PEER_CAPABILITIES;

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function callbackBooleans(capabilities = {}) {
  const fs = capabilities.fs;
  return {
    fs: fs === true || fs?.readTextFile === true || fs?.writeTextFile === true,
    terminal: capabilities.terminal === true,
  };
}

async function recordCapabilities(capabilities) {
  if (!capabilitiesPath) return;
  await writeFile(capabilitiesPath, `${JSON.stringify(callbackBooleans(capabilities))}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
}

async function handle(message) {
  if (!message || typeof message !== "object") return;
  const { id, method, params } = message;
  if (method == null) return;
  if (id === undefined) return;
  try {
    if (method === "initialize") {
      await recordCapabilities(params?.clientCapabilities);
      send({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: params?.protocolVersion ?? 1,
          agentCapabilities: {
            loadSession: false,
            promptCapabilities: { image: false, audio: false, embeddedContext: false },
            sessionCapabilities: { close: {} },
          },
          agentInfo: { name: "puppet-acpx-candidate-peer", version: "0.0.0" },
          authMethods: [],
        },
      });
      return;
    }
    if (method === "session/new") {
      send({ jsonrpc: "2.0", id, result: { sessionId: "candidate-session" } });
      return;
    }
    if (method === "session/prompt") {
      send({ jsonrpc: "2.0", id, result: { stopReason: "end_turn" } });
      return;
    }
    if (method === "session/close") {
      send({ jsonrpc: "2.0", id, result: {} });
      return;
    }
    send({
      jsonrpc: "2.0",
      id,
      error: { code: -32601, message: `Method not found: ${method}` },
    });
  } catch (error) {
    send({
      jsonrpc: "2.0",
      id,
      error: { code: -32603, message: error instanceof Error ? error.message : "peer failed" },
    });
  }
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed) continue;
  let message;
  try {
    message = JSON.parse(trimmed);
  } catch {
    continue;
  }
  await handle(message);
}
