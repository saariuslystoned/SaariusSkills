#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { BridgeError, CursorAcpBroker, timeoutMsZod } from "./broker.mjs";

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
      "Check the explicit local Cursor ACP executable, login/session readiness, and full advertised model catalog without sending a model turn. ready matches delegate selection readiness. The durable default is the plugin alias gpt-5.6-luna-medium (base gpt-5.6-luna plus effort medium), not a live model id. When that effort is absent, ready and selectionReady are false, catalogReady can still be true, and the error is MODEL_REQUIRED or EFFORT_UNSUPPORTED with the advertised ids. Optional model and effort inspect a selection. Supports switching between grok-4.6, grok-4.7, and gpt-5.6-luna as needed (effort optional for unique advertised bases). No fallback to the current runtime model.",
    inputSchema: {
      workspace: z.string().optional(),
      model: z.string().optional(),
      effort: z.string().optional(),
    },
  },
  (args) => call((input) => broker.discover(input), args),
);

server.registerTool(
  "cursor_acp_delegate",
  {
    description:
      "Submit one bounded implementation task via Cursor ACP in exactly one absolute workspace. Omitting model and effort uses the durable plugin alias gpt-5.6-luna-medium (base gpt-5.6-luna plus effort medium), resolved once to an advertised id and rechecked before the prompt. Explicit model and effort are per-job, supporting grok-4.6, grok-4.7, and gpt-5.6-luna (effort is optional advanced; unique advertised bases resolve without choosing effort). Finish cleanupReady before switching models because one conversation owns one active worker. Missing, duplicate, ambiguous, or unconfirmed selections fail closed with no prompt. Optional fallbackModels (at most two selectors) configures parent-reviewed fallback only when model and effort are omitted. A recognized terminal Cursor PING failure admits retryOf plus partialWorkReviewed=true only after cleanup; supply a fresh continuation prompt, omit model/effort/timeoutMs/fallbackModels, and retain the original deadline. Each attempt is a separate exact-model job; no automatic prompt replay. Refuses when selection readiness is red. One parent conversation owns one worker; rebind is owner-gated. binderId must match the host-controlled binder identity; it is not an authorization override. Returns a stable job ID.",
    inputSchema: {
      workspace: z.string(),
      prompt: z.string(),
      model: z.string().optional(),
      effort: z.string().optional(),
      timeoutMs: timeoutMsZod(z),
      hostConversationId: z.string().optional(),
      binderId: z.string().optional(),
      fallbackModels: z.array(z.string()).max(2).optional(),
      retryOf: z.string().optional(),
      partialWorkReviewed: z.boolean().optional(),
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
    description: "Read the bounded final handoff or explicit failure/input/cancellation outcome for a job. taskComplete means the turn is terminal, not accepted work; cleanupReady independently proves cleanup. Optional fallback metadata is advice and never dispatches a retry.",
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
