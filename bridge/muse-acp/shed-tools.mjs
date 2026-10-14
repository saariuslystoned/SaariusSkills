// Narrow MCP tool surface for remote-shed mode. No shell, exec, file, or raw
// ACP session tools are registered here.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import * as z from "zod";
import { BridgeError, redactSensitive, safeMessage } from "./broker.mjs";
import { ShedTaskError } from "./shed-tasks.mjs";

export const SHED_TOOL_NAMES = Object.freeze([
  "shed_task_run",
  "shed_task_status",
  "shed_task_cancel",
  "shed_task_steer",
  "shed_task_result",
]);

function respond(payload, isError = false) {
  return {
    isError,
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
  };
}

function errorPayload(error) {
  const known = error instanceof ShedTaskError || error instanceof BridgeError;
  return {
    ok: false,
    error: known
      ? {
          code: error.code,
          message: safeMessage(error.message),
          details: error.details && Object.keys(error.details).length ? JSON.parse(redactSensitive(JSON.stringify(error.details))) : undefined,
        }
      : { code: "SHED_ERROR", message: "remote-shed request failed" },
  };
}

async function call(handler) {
  try {
    return respond(await handler());
  } catch (error) {
    return respond(errorPayload(error), true);
  }
}

export function createShedMcpServer(runner, caller) {
  const server = new McpServer({ name: "muse-acp-shed", version: "0.1.0" });

  server.registerTool(
    "shed_task_run",
    {
      description: "Run one bounded coding task on the AI Shed inside an allowlisted repo. With no headBranch, starts a fresh worktree on shed/<taskId> from origin/<baseBranch> and opens a draft PR. With headBranch, checks out that existing PR branch in a fresh worktree and fast-forward pushes to it (refusing if another shed task is on that branch or if origin/<headBranch> moved). Returns busy (with running tasks) when the concurrency cap is full.",
      inputSchema: {
        owner: z.string().describe("Repo owner (must be on the shed allowlist for the selected forge)"),
        repo: z.string().describe("Repository name under the shed repos root"),
        task: z.string().describe("Bounded coding task instructions (no secrets)"),
        requested_by: z.string().describe("Operator or bot label for the PR body and audit log"),
        baseBranch: z.string().optional().describe("Base branch to branch from and open the draft PR against; default main"),
        headBranch: z.string().optional().describe("Existing PR head branch to continue and fast-forward push instead of opening a new PR"),
        forge: z.enum(["github", "origin"]).optional().describe("Where the repo lives; default github"),
        title: z.string().optional().describe("Draft PR title"),
        harness: z.enum(["antigravity", "muse"]).optional().describe("Execution harness (antigravity or muse; default antigravity)"),
        model: z.string().optional().describe("Requested model ID validated against the harness's advertised models"),
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
    (args) => call(() => runner.status(args)),
  );

  server.registerTool(
    "shed_task_cancel",
    {
      description: "Cancel one running shed task by taskId. Cancels any in-flight ACP agent job, rescues uncommitted edits to refs/shed/keep/<taskId>, tears down the task worktree, and marks the task cancelled. Safe to call multiple times.",
      inputSchema: { taskId: z.string() },
    },
    (args) => call(() => runner.cancel(args)),
  );

  server.registerTool(
    "shed_task_steer",
    {
      description: "Send a follow-up instruction into a running shed task's ACP session.",
      inputSchema: {
        taskId: z.string().describe("Running shed task ID"),
        instruction: z.string().describe("Follow-up instruction for the running ACP session (no secrets)"),
        requested_by: z.string().describe("Operator or bot label for the audit log"),
      },
    },
    (args) => call(() => runner.steer(args, caller)),
  );

  server.registerTool(
    "shed_task_result",
    {
      description: "Read the final result of a finished shed task by taskId (redacted summary, PR URL, head SHA, harness, model, and session viewer link).",
      inputSchema: {
        taskId: z.string().describe("Finished shed task ID"),
      },
    },
    (args) => call(() => runner.result(args, caller)),
  );

  return server;
}
