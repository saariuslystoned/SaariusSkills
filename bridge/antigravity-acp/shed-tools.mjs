import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { BridgeError } from "./broker.mjs";

export const SHED_SERVER_INFO = Object.freeze({ name: "saarius-antigravity-shed", version: "0.1.0" });
export const SHED_TOOL_NAMES = Object.freeze(["shed_task_run", "shed_task_status", "shed_task_cancel"]);

const text = (value) => ({ content: [{ type: "text", text: JSON.stringify(value) }] });
const failure = (error) => ({
  isError: true,
  ...text({
    status: "error",
    error: error instanceof BridgeError
      ? { code: error.code, message: error.message, details: error.details }
      : { code: "SHED_ERROR", message: "remote-shed request failed" },
  }),
});
const call = async (fn) => {
  try {
    return text(await fn());
  } catch (error) {
    return failure(error);
  }
};

// Remote-shed MCP surface: three narrow task tools and nothing else. There is
// no exec, shell, file, or raw ACP tool on the remote endpoint.
export function createShedMcpServer(runner, caller) {
  const server = new McpServer({ ...SHED_SERVER_INFO });

  server.registerTool(
    "shed_task_run",
    {
      description:
        "Run one coding task with official Antigravity ACP on the owner's AI Shed, in an allowlisted GitHub repo, on a new shed/<taskId> branch, then open a draft PR. One task at a time: returns status \"busy\" when another task is running and \"unavailable\" when the shed cannot run Antigravity right now, so callers can fall back. Never put secrets in any field.",
      inputSchema: {
        owner: z.string().describe("GitHub owner; must be on the shed allowlist"),
        repo: z.string().describe("GitHub repository name, already cloned on the shed"),
        task: z.string().describe("Plain-language coding task"),
        requested_by: z.string().describe("Name of the bot or agent that asked for this task, for the audit log"),
        baseBranch: z.string().optional().describe("Branch to start from; default main"),
        title: z.string().optional().describe("Draft PR title"),
      },
    },
    (args) => call(() => runner.runTask(args, caller)),
  );

  server.registerTool(
    "shed_task_status",
    {
      description: "Read one shed task (status, branch, draft PR URL, redacted summary). Omit taskId to see whether the shed is idle or busy.",
      inputSchema: { taskId: z.string().optional() },
    },
    (args) => call(() => runner.status(args ?? {})),
  );

  server.registerTool(
    "shed_task_cancel",
    {
      description: "Cancel the running shed task. No PR is opened for a cancelled task.",
      inputSchema: { taskId: z.string() },
    },
    (args) => call(() => runner.cancel(args ?? {})),
  );

  return server;
}
