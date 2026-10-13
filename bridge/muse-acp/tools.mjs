import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { museFallbackModelsZod, museModelZod, timeoutMsZod } from "./broker.mjs";
import { serializeFailure } from "./server-errors.mjs";

export const SERVER_INFO = Object.freeze({ name: "saarius-muse-acp", version: "0.1.0" });

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

// The six local/stdio tools. Remote-shed mode does not expose these; it
// serves only the narrow task tools in shed-tools.mjs.
export function createMuseMcpServer(broker) {
  const server = new McpServer({ ...SERVER_INFO });

  async function call(handler, args) {
    try {
      return result(await handler(args ?? {}));
    } catch (error) {
      return failure(error);
    }
  }

  server.registerTool(
    "muse_acp_readiness",
    {
      description:
        "Check the local muse binary (version + MSP `serve` host) and full advertised Muse model catalog without sending a model turn. ready matches selection readiness. Omitting model means host default: whatever model `muse serve` resolves, with no session/set_model call; an empty catalog (for example the echo provider) is still ready under host default. Optional model is an exact advertised id and never substitutes. Optional fallbackModels is an ordered preference list of at most four exact ids used only when model is omitted; an empty list means host default. Do not pass model together with fallbackModels. catalogReady can be true when selectionReady is false. This lane is Muse through the muse-agent-acp adapter (ACP to MSP), separate from Cursor ACP, Antigravity ACP, and Grok ACP.",
      inputSchema: {
        workspace: z.string().optional(),
        model: museModelZod(z),
        fallbackModels: museFallbackModelsZod(z),
      },
    },
    (args) => call((input) => broker.discover(input), args),
  );

  server.registerTool(
    "muse_acp_delegate",
    {
      description:
        "Submit one bounded implementation task to local Muse ACP in exactly one absolute workspace. Omitting model means host default (no set_model call). Explicit model is exact, must be advertised, and never substitutes; that choice is bound to the job and rechecked before the prompt, and catalog drift fails with no prompt. Optional fallbackModels is an ordered preference list used only when model is omitted. Do not pass model together with fallbackModels. Refuses when selection readiness is red. One parent conversation owns one worker; rebind is owner-gated. binderId must match the host-controlled binder identity; it is not an authorization override. Returns a stable job ID.",
      inputSchema: {
        workspace: z.string(),
        prompt: z.string(),
        timeoutMs: timeoutMsZod(z),
        hostConversationId: z.string().optional(),
        binderId: z.string().optional(),
        model: museModelZod(z),
        fallbackModels: museFallbackModelsZod(z),
      },
    },
    (args) => call((input) => broker.delegate(input), args),
  );

  server.registerTool(
    "muse_acp_status",
    {
      description: "Read compact status for a Muse ACP delegation job, with an optional bounded wait.",
      inputSchema: {
        jobId: z.string(),
        waitMs: z.number().int().min(0).max(10_000).optional(),
      },
    },
    (args) => call((input) => broker.status(input), args),
  );

  server.registerTool(
    "muse_acp_result",
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
    "muse_acp_steer",
    {
      description: "Report unsupported active-turn steering for the pinned ACP runtime; never enqueue an unowned follow-up turn.",
      inputSchema: { jobId: z.string(), message: z.string() },
    },
    (args) => call((input) => broker.steer(input), args),
  );

  server.registerTool(
    "muse_acp_cancel",
    {
      description: "Request cancellation of the active Muse ACP turn for an existing job.",
      inputSchema: { jobId: z.string(), reason: z.string().optional() },
    },
    (args) => call((input) => broker.cancel(input), args),
  );

  return server;
}
