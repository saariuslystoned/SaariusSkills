#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { GrokAcpBroker, grokFallbackModelsZod, grokModelZod, timeoutMsZod } from "./broker.mjs";
import { serializeFailure } from "./server-errors.mjs";

const broker = await new GrokAcpBroker().init();
const server = new McpServer({
  name: "saarius-grok-acp",
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
      error: serializeFailure(error),
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
  "grok_acp_readiness",
  {
    description:
      "Check the explicit local Grok ACP executable, login/session readiness, and full advertised Grok model catalog without sending a model turn. ready matches selection readiness. Omitting model prefers advertised grok-4.7, then grok-4.6, then grok-4.5. Optional model is an exact id and never substitutes, including grok-4.6, grok-4.7, and grok-4.7-build-fast. Optional fallbackModels accepts at most two exact ids and replaces those default alternatives; an empty list requires grok-4.7. Do not pass model together with fallbackModels. catalogReady can be true when selectionReady is false. Missing allowed ids, invalid input, and auth failure do not prompt. The session's current model is not a selection. This lane is native Grok CLI, not Cursor and not Luna.",
    inputSchema: {
      workspace: z.string().optional(),
      model: grokModelZod(z),
      fallbackModels: grokFallbackModelsZod(z),
    },
  },
  (args) => call((input) => broker.discover(input), args),
);

server.registerTool(
  "grok_acp_delegate",
  {
    description:
      "Submit one bounded implementation task to local native Grok ACP in exactly one absolute workspace. Omitting model prefers advertised grok-4.7, then grok-4.6, then grok-4.5. That choice is bound to the job and rechecked before the prompt; catalog drift fails with no prompt and no other model. Explicit model is exact and never substitutes. Optional fallbackModels accepts at most two exact ids and replaces the default alternatives only when model is omitted; an empty list requires grok-4.7. Do not pass model together with fallbackModels. Refuses when selection readiness is red. One parent conversation owns one worker; rebind is owner-gated. binderId must match the host-controlled binder identity; it is not an authorization override. Returns a stable job ID. This lane does not run Luna.",
    inputSchema: {
      workspace: z.string(),
      prompt: z.string(),
      timeoutMs: timeoutMsZod(z),
      hostConversationId: z.string().optional(),
      binderId: z.string().optional(),
      model: grokModelZod(z),
      fallbackModels: grokFallbackModelsZod(z),
    },
  },
  (args) => call((input) => broker.delegate(input), args),
);

server.registerTool(
  "grok_acp_status",
  {
    description: "Read compact status for a Grok ACP delegation job, with an optional bounded wait.",
    inputSchema: {
      jobId: z.string(),
      waitMs: z.number().int().min(0).max(10_000).optional(),
    },
  },
  (args) => call((input) => broker.status(input), args),
);

server.registerTool(
  "grok_acp_result",
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
  "grok_acp_steer",
  {
    description: "Report unsupported active-turn steering for the pinned ACP runtime; never enqueue an unowned follow-up turn.",
    inputSchema: { jobId: z.string(), message: z.string() },
  },
  (args) => call((input) => broker.steer(input), args),
);

server.registerTool(
  "grok_acp_cancel",
  {
    description: "Request cancellation of the active Grok ACP turn for an existing job.",
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
