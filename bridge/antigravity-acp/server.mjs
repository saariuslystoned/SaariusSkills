#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { AntigravityAcpBroker, BridgeError } from "./broker.mjs";

const broker = await new AntigravityAcpBroker().init();
const server = new McpServer({
  name: "saarius-antigravity-acp",
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
  "antigravity_acp_readiness",
  {
    description:
      "Diagnose the pinned official Antigravity ACP runtime/helper, GEMINI_HOME personal OAuth policy, advertised models, and setup repair actions without sending a model turn. When model is omitted, readiness selects the plugin default gemini-3.8-flash-high if that exact id is advertised; it does not treat runtime current as the wished default.",
    inputSchema: {
      workspace: z.string().optional(),
      model: z.string().optional(),
      effort: z.any().optional(),
    },
  },
  (args) => call((input) => broker.discover(input), args),
);

server.registerTool(
  "antigravity_acp_delegate",
  {
    description:
      "Submit one bounded implementation task to official Antigravity ACP in exactly one absolute workspace. Refuses when readiness is red. One parent conversation owns one worker; rebind is owner-gated. binderId must match the host-controlled binder identity; it is not an authorization override. Omit model to use the plugin default gemini-3.8-flash-high when that exact id is advertised; otherwise pass an exact advertised model id. Returns a stable job ID.",
    inputSchema: {
      workspace: z.string(),
      prompt: z.string(),
      model: z.string().optional(),
      timeoutMs: z.number().int().min(1_000).max(1_800_000).optional(),
      effort: z.any().optional(),
      hostConversationId: z.string().optional(),
      binderId: z.string().optional(),
    },
  },
  (args) => call((input) => broker.delegate(input), args),
);

server.registerTool(
  "antigravity_acp_status",
  {
    description:
      "Read compact status for an Antigravity ACP delegation job, with an optional bounded wait. complete is true only after a terminal task outcome and observed cleanup; pending cleanup is not cleanup-ready completion.",
    inputSchema: {
      jobId: z.string(),
      waitMs: z.number().int().min(0).max(10_000).optional(),
    },
  },
  (args) => call((input) => broker.status(input), args),
);

server.registerTool(
  "antigravity_acp_result",
  {
    description:
      "Read the bounded task outcome for a job. complete and cleanupReady become true only after observed terminal cleanup; a completed status with pending cleanup is not replacement authority.",
    inputSchema: {
      jobId: z.string(),
      waitMs: z.number().int().min(0).max(300_000).optional(),
    },
  },
  (args) => call((input) => broker.result(input), args),
);

server.registerTool(
  "antigravity_acp_steer",
  {
    description: "Report unsupported active-turn steering for Antigravity ACP; never enqueue an unowned follow-up turn.",
    inputSchema: { jobId: z.string(), message: z.string() },
  },
  (args) => call((input) => broker.steer(input), args),
);

server.registerTool(
  "antigravity_acp_cancel",
  {
    description: "Request cancellation of the active Antigravity ACP turn for an existing job.",
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
