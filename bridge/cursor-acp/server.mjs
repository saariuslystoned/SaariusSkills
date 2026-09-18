#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { BridgeError, CursorAcpBroker } from "./broker.mjs";

const broker = await new CursorAcpBroker().init();
const server = new McpServer({
  name: "saarius-cursor-acp",
  version: "0.1.0",
});

const result = (value) => ({
  content: [{ type: "text", text: JSON.stringify(value) }],
});

const failure = (error) => ({
  isError: true,
  content: [{
    type: "text",
    text: JSON.stringify({
      status: "error",
      error: error instanceof BridgeError
        ? { code: error.code, message: error.message, details: error.details }
        : { code: "BRIDGE_ERROR", message: error?.message ?? String(error) },
    }),
  }],
});

async function call(handler, args) {
  try {
    return result(await handler(args ?? {}));
  } catch (error) {
    return failure(error);
  }
}

server.registerTool(
  "cursor_acp_readiness",
  {
    description:
      "Check the explicit local Cursor ACP executable, login/session readiness, and exact advertised Grok model without sending a model turn.",
    inputSchema: { workspace: z.string().optional() },
  },
  (args) => call((input) => broker.discover(input), args),
);

server.registerTool(
  "cursor_acp_delegate",
  {
    description:
      "Submit one bounded implementation task to Cursor Grok 4.6 in exactly one absolute workspace; returns a stable job ID.",
    inputSchema: {
      workspace: z.string(),
      prompt: z.string(),
      timeoutMs: z.number().int().min(1_000).max(1_800_000).optional(),
    },
  },
  (args) => call((input) => broker.delegate(input), args),
);

server.registerTool(
  "cursor_acp_status",
  {
    description: "Read compact status for a Cursor ACP delegation job, with an optional bounded wait.",
    inputSchema: {
      jobId: z.string(),
      waitMs: z.number().int().min(0).max(10_000).optional(),
    },
  },
  (args) => call((input) => broker.status(input), args),
);

server.registerTool(
  "cursor_acp_result",
  {
    description: "Read the bounded final handoff or explicit failure/input/cancellation outcome for a job.",
    inputSchema: {
      jobId: z.string(),
      waitMs: z.number().int().min(0).max(300_000).optional(),
    },
  },
  (args) => call((input) => broker.result(input), args),
);

server.registerTool(
  "cursor_acp_steer",
  {
    description: "Report unsupported active-turn steering for the pinned ACP runtime; never enqueue an unowned follow-up turn.",
    inputSchema: { jobId: z.string(), message: z.string() },
  },
  (args) => call((input) => broker.steer(input), args),
);

server.registerTool(
  "cursor_acp_cancel",
  {
    description: "Request cancellation of the active Cursor ACP turn for an existing job.",
    inputSchema: { jobId: z.string(), reason: z.string().optional() },
  },
  (args) => call((input) => broker.cancel(input), args),
);

const transport = new StdioServerTransport();
await server.connect(transport);

const shutdown = async () => {
  await broker.close();
  process.exit(0);
};
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
