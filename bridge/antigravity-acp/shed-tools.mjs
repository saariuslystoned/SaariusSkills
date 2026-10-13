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
        "Run one coding task with official Antigravity or Muse ACP on the owner's AI Shed, in an allowlisted GitHub repo, on a new shed/<taskId> branch, then open a draft PR (or continue an existing PR branch via headBranch). Up to the shed's concurrency cap of tasks run at once per harness, each in its own worktree: returns status \"busy\" (naming which harness is full, with running count and cap) when the cap is reached so the caller can queue and retry, error BRANCH_BUSY when the same repo+headBranch already has a running task, and \"unavailable\" when the shed cannot run the agent right now, so callers can fall back. When the ACP session starts within ~10s the response includes session_id and session_url (a read-only viewer page for the owner); otherwise sessionPending is true and shed_task_status returns them once ready. Never put secrets in any field.",
      inputSchema: {
        owner: z.string().describe("GitHub owner; must be on the shed allowlist"),
        repo: z.string().describe("GitHub repository name, already cloned on the shed"),
        task: z.string().describe("Plain-language coding task"),
        requested_by: z.string().describe("Name of the bot or agent that asked for this task, for the audit log"),
        baseBranch: z.string().optional().describe("Branch to start from; default main"),
        headBranch: z.string().optional().describe("Existing PR head branch to continue on (existing shed/ or codex/ branch, fast-forward only); pushed fast-forward only (fails if the remote moved), no new PR"),
        forge: z.enum(["github", "origin"]).optional().describe("Where the repo lives; default github"),
        title: z.string().optional().describe("Draft PR title"),
        harness: z.enum(["antigravity", "muse"]).optional().describe("Execution harness (antigravity or muse; default antigravity)"),
      },
    },
    (args) => call(() => runner.runTask(args, caller)),
  );

  server.registerTool(
    "shed_task_status",
    {
      description: "Read one shed task by taskId (status, branch, draft PR URL, session_id / session_url for the read-only viewer, redacted summary). Omit taskId to get shed state: idle / available / busy, running count, cap, and every running task (taskId, repo, branch, requestedBy, startedAt).",
      inputSchema: { taskId: z.string().optional() },
    },
    (args) => call(() => runner.status(args ?? {})),
  );

  server.registerTool(
    "shed_task_cancel",
    {
      description: "Cancel a running shed task by taskId. No PR is opened for a cancelled task.",
      inputSchema: { taskId: z.string() },
    },
    (args) => call(() => runner.cancel(args ?? {})),
  );

  return server;
}
