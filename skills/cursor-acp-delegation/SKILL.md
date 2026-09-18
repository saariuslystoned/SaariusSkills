---
name: cursor-acp-delegation
description: Delegate one bounded implementation or verification slice to Bobby's local Cursor ACP session running the explicitly selected Cursor Grok 4.6 model, then inspect the result independently. Use only when the task is authorized for local implementation work and has one clear workspace owner.
---

# Cursor ACP delegation

Use the `cursor-acp` MCP server as an optional local worker route for
substantial, bounded implementation or verification work. Cursor/Grok 4.6 is
Bobby's preferred route for that kind of slice when the local route is ready;
the parent agent still owns decisions, scope, review, and any separately gated
external action.

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
  reason to create a replacement session.
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
