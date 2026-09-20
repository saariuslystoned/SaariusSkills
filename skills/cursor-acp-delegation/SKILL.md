---
name: cursor-acp-delegation
description: Use Cursor ACP MCP to delegate bounded implementation or verification to local Cursor Grok 4.6, or diagnose missing Cursor ACP tools. Applies with any Codex orchestrator model, including Luna. Developing Puppet does not make Puppet the worker transport.
---

# Cursor ACP delegation

Use the `cursor-acp` MCP server as an optional local worker route for
substantial, bounded implementation or verification work. Cursor/Grok 4.6 is
Bobby's preferred route for that kind of slice when the local route is ready;
the parent agent still owns decisions, scope, review, and any separately gated
external action.

## Discovery and setup

The orchestrator model does not select the transport: Luna High and other Codex
models use the same installed MCP tools. Tool names may have a plugin/server
prefix. Search the available/deferred tool catalog for `cursor_acp_readiness`
before concluding it is unavailable; a short initial tool list is not proof.

If no callable Cursor ACP tool is found, read the handoff and diagnose setup;
do not stop before gathering the cause. From this installed skill's directory,
the package check is:

```bash
node ../../bridge/cursor-acp/scripts/setup.mjs --check
```

Resolve that relative path against this SKILL.md, not the task's workspace.
`DEPENDENCIES_MISSING` includes an exact repair command. When local setup is
authorized, run that command with `--install`; it installs locked dependencies
with lifecycle scripts disabled and verifies MCP initialization and all six
tools, without opening Cursor or sending a model turn. Run it after every plugin
install/update: copying the plugin does not install its Node dependencies.

After repair, reload the Codex app or start a fresh task so its native tool
inventory is rebuilt. `MCP_READY` proves server startup, not that the current
task has reloaded it; verify a native readiness tool call in the fresh task.
If still unavailable, report `MCP_UNAVAILABLE` with the setup result and the
specific reload/registration action needed. Do not replace this route with
Puppet, Herdr, tmux, a different model, or a task-local client unless the user
explicitly authorizes that alternative. Setup diagnosis is not worker execution.

## Operating contract

- Start with `cursor_acp_readiness` for the exact workspace when the route has
  not been checked in the current task. Require the explicit
  `/Users/bobbybones/.local/bin/cursor-agent acp` route and the exact
  `cursor-grok-4.6-high` selector resolved to one advertised ACP model ID
  (currently the live install reports `grok-4.6[effort=high,fast=true]`). Never
  silently fall back to another executable, provider, model, or workspace.
- Use `cursor_acp_delegate` with one absolute workspace path, one bounded
  prompt, and a bounded timeout. Prefer an isolated worktree for source
  mutations. One worker owns one source slice; do not fan out by default.
- Save the returned job ID. Use `cursor_acp_status` for progress and
  `cursor_acp_result` with a bounded wait for the canonical outcome. A
  submitted job, process exit, or progress event is not task success.
- `cursor_acp_steer` fails closed with `STEERING_UNSUPPORTED`: the pinned
  runtime queues a second turn rather than steering the active turn. Wait for
  the canonical terminal result, then explicitly delegate a bounded follow-up. Use
  `cursor_acp_cancel` when the parent decision changes or the bounded budget is
  no longer justified. A missing active session is a fail-closed result, not a
  reason to create a replacement session. `cursor_acp_status` and
  `cursor_acp_result` may observe shared job state; cancel and steer stay
  owner-local.
- A second broker initialization or setup/readiness check must not fail a
  non-terminal job owned by another live broker. Startup recovery fails a job
  only when that exact owner identity is demonstrably dead; unknown or
  incomplete ownership and PID reuse stay fail-safe. Do not treat bare PID
  existence as proof of liveness.
- Treat `completed`, `failed`, `cancelled`, and `needs-input` as distinct
  outcomes. Escalate `needs-input` to the user with the bounded reason; do not
  invent a login flow, API-key fallback, or hidden approval.
- Review changed files, tests, and proof independently before accepting the
  worker handoff. Keep the worker's final handoff compact and do not request or
  expose thought streams, raw ACP transcripts, credential stores, auth logs,
  `.env` files, or tokens.

## Scope boundary

This is an experimental local MCP slice. It does not qualify Puppet's ACP
transport, implement issues #35/#37 wholesale, connect to OpenClaw or
SwarmHerdr, operate remote hosts, or authorize deployment, publication,
external sends, spending, account/security changes, or destructive cleanup.

Cursor's proprietary `ask_question` and `create_plan` requests are not claimed
as supported native surfaces here. If one blocks a task, report the explicit
`needs-input`/unsupported result and let the parent choose a bounded next step.
