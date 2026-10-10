#!/usr/bin/env node
// Dependency-free stdio MCP server that gives Claude, Cursor, Codex and
// Antigravity the same `decision_evaluate` tool OpenClaw has, backed by
// TypeSafe Jev (hosted) or a local Kev server when one is set up.
//
//   node bridge/jev-decision/server.mjs           MCP server on stdio
//   node bridge/jev-decision/server.mjs --check   which route is set up (no network)
//   node bridge/jev-decision/server.mjs --probe   one tiny paid call to prove the route

import { realpathSync } from "node:fs";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import { describeRoute, evaluate, resolveRoute } from "./client.mjs";

const SERVER_INFO = { name: "jev-decision", version: "0.1.0" };
const DEFAULT_PROTOCOL = "2025-06-18";

const entry = { anyOf: [{ type: "string" }, { type: "object" }, { type: "array" }, { type: "null" }] };

export const TOOLS = [
  {
    name: "decision_evaluate",
    description:
      "Same contract as OpenClaw's decision_evaluate. Ask Jev independent boolean, choice or score questions about supplied state only. " +
      "Returns {status:'ok', result:{answers}, provenance} or {status:'unavailable', reason, guidance}. " +
      "Unavailable is not a negative answer and must not stop the work: apply the rubric by hand and say Jev did not run. " +
      "Results never authorize actions. Hosted Jev sends the state to TypeSafe and may charge.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["state", "questions"],
      properties: {
        state: { ...entry, description: "Only the evidence the judge needs." },
        questions: {
          type: "object",
          minProperties: 1,
          description:
            "Map of question id to {type:'boolean'|'choice'|'score', instructions?, criteria}. Choice criteria map 2+ labels to descriptions; score criteria are 2 to 10 ordered levels.",
          additionalProperties: {
            type: "object",
            required: ["type"],
            properties: {
              type: { enum: ["boolean", "choice", "score"] },
              instructions: entry,
              criteria: { anyOf: [{ type: "object" }, { type: "array" }, { type: "null" }] },
            },
          },
        },
      },
    },
  },
  {
    name: "jev_status",
    description:
      "Say whether this machine has a Jev route (hosted key or local Kev) without sending anything. Never returns the key.",
    inputSchema: { type: "object", additionalProperties: false, properties: {} },
  },
];

function toolResult(payload) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: false,
  };
}

/** Handle one JSON-RPC message; returns the response object or null for notifications. */
export async function handle(message, deps = {}) {
  const { route = resolveRoute, fetchImpl } = deps;
  const { id, method, params } = message ?? {};
  const isRequest = id !== undefined && id !== null;
  const reply = (result) => (isRequest ? { jsonrpc: "2.0", id, result } : null);
  const fail = (code, text) => (isRequest ? { jsonrpc: "2.0", id, error: { code, message: text } } : null);

  switch (method) {
    case "initialize":
      return reply({
        protocolVersion: params?.protocolVersion || DEFAULT_PROTOCOL,
        capabilities: { tools: {} },
        serverInfo: SERVER_INFO,
      });
    case "ping":
      return reply({});
    case "tools/list":
      return reply({ tools: TOOLS });
    case "tools/call": {
      const name = params?.name;
      if (name === "jev_status") return reply(toolResult(describeRoute(await route())));
      if (name === "decision_evaluate") {
        return reply(toolResult(await evaluate(params?.arguments, await route(), fetchImpl)));
      }
      return fail(-32602, `Unknown tool: ${name}`);
    }
    default:
      if (typeof method === "string" && method.startsWith("notifications/")) return null;
      return fail(-32601, `Method not found: ${method}`);
  }
}

function serve() {
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const write = (response) => {
    if (response) process.stdout.write(`${JSON.stringify(response)}\n`);
  };
  lines.on("line", async (line) => {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      write({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } });
      return;
    }
    try {
      write(await handle(message));
    } catch {
      write({ jsonrpc: "2.0", id: message?.id ?? null, error: { code: -32603, message: "Internal error" } });
    }
  });
}

async function main(argv) {
  if (argv.includes("--check")) {
    process.stdout.write(`${JSON.stringify(describeRoute(await resolveRoute()), null, 2)}\n`);
    return;
  }
  if (argv.includes("--probe")) {
    const outcome = await evaluate(
      {
        state: "The sky is blue on a clear day.",
        questions: { probe: { type: "boolean", instructions: "Is the statement true?" } },
      },
      await resolveRoute(),
    );
    process.stdout.write(`${JSON.stringify(outcome, null, 2)}\n`);
    process.exitCode = outcome.status === "ok" ? 0 : 1;
    return;
  }
  serve();
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main(process.argv.slice(2));
}
