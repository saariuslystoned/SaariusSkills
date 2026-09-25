---
name: grok-acp-delegation
description: Use Grok ACP MCP to delegate bounded implementation or verification to the local Grok CLI (`grok agent stdio`) through ACpx grok-build, or diagnose missing Grok ACP tools. Distinct from cursor-acp (cursor-agent acp) and from Puppet grok tmux. Not a Grok Bot VM route.
---

# Grok ACP delegation

Use the `grok-acp` MCP server as an optional local worker route for one
bounded implementation or verification slice. The parent harness stays the
host. ACpx is the local ACP client. The child is the installed Grok CLI
stdio agent, ACpx built-in `grok-build` (`grok agent stdio`). This is not
the Cursor ACP lane, not Puppet's grok tmux harness, and not a Grok Bot
computer.

## Discovery and setup

Tool names may have a plugin/server prefix. Search the available/deferred tool
catalog for `grok_acp_readiness` before concluding the route is unavailable; a
short initial tool list is not proof.

If no callable Grok ACP tool is found, diagnose setup. From this installed
skill's directory, the package check is:

```bash
node ../../bridge/grok-acp/scripts/setup.mjs --check
```

Resolve that relative path against this SKILL.md, not the task's workspace.
`DEPENDENCIES_MISSING` includes an exact repair command. When local setup is
authorized, run that command with `--install`; it installs locked Node
dependencies with lifecycle scripts disabled and verifies MCP initialization
and all six tools. It does not open a Grok login or send a model turn.

The child is whatever `GROK_EXECUTABLE` names, or `grok` on `PATH`. Plugin
manifests do not ship a machine-specific path. Login is a precondition of the
installed Grok CLI, not something this bridge starts. After every plugin
install/update, prepare the persistent runtime:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge grok-acp
```

After repair, reload the host app or start a fresh task so its native tool
inventory is rebuilt. `MCP_READY` proves server startup, not that the current
task has reloaded it. If still unavailable, report `MCP_UNAVAILABLE` with the
setup result and the specific reload/registration action needed. Do not replace
this route with Cursor ACP, Puppet grok, Herdr, or tmux unless the user
explicitly authorizes that alternative.

## Operating contract

- Start with `grok_acp_readiness` for the exact workspace when the route has
  not been checked in the current task. Require the local `grok agent stdio`
  child through ACpx `grok-build`, and the plugin default exact advertised id
  `grok-4.7`. Never silently fall back to `cursor-agent acp`, generic `acp`,
  another executable, or another workspace. `grok_acp_delegate` hard-refuses
  when that readiness is red (runtime / auth / model / workspace). Do not treat
  a red readiness report as advice and submit anyway.
- Use `grok_acp_delegate` with one absolute workspace path, one parent
  conversation id (`hostConversationId` or `SAARIUS_ACP_HOST_CONVERSATION_ID`),
  one bounded prompt, and a bounded timeout. One parent conversation owns one
  worker. Rebind is owner-gated (`binderId` / `SAARIUS_ACP_BINDER_ID`); cwd is
  not exclusive. Prefer an isolated worktree for source mutations. Do not fan
  out by default. Live MCP permissions default to `approve-reads` plus fail on
  write/exec that would prompt. `SAARIUS_ACP_PERMISSION_MODE=approve-all` is
  explicit break-glass. Do not use one-path `allow_once` on this live MCP
  lane. Conversation admission persists the job, including exact broker
  ownership, before the binding is published. Only confirmed unstarted or
  released admissions may be replaced by the same owner; once worker startup
  is attempted, the admission stays fenced until cleanup is explicitly proven.
  Live or unobservable workers stay fenced. Do not retry or delete uncertain
  ownership.
- Save the returned job ID. Use `grok_acp_status` for progress and
  `grok_acp_result` with a bounded wait for the canonical outcome. A
  submitted job, process exit, or progress event is not task success.
- `grok_acp_steer` fails closed with `STEERING_UNSUPPORTED`. Wait for the
  canonical terminal result, then explicitly delegate a bounded follow-up. Use
  `grok_acp_cancel` when the parent decision changes or the bounded budget is
  no longer justified. A missing active session is a fail-closed result, not a
  reason to create a replacement session.
- Treat `completed`, `failed`, `cancelled`, and `needs-input` as distinct
  outcomes. Escalate `needs-input` to the user with the bounded reason; do not
  invent a login flow, API-key fallback, or hidden approval.
- Review changed files, tests, and proof independently before accepting the
  worker handoff. Keep the worker's final handoff compact and do not request or
  expose thought streams, raw ACP transcripts, credential stores, auth logs,
  `.env` files, or tokens.
- Optional host hop (`SAARIUS_ACP_HOP_ARGV` JSON argv on the parent
  launcher): same six tools; ACpx stays a local child on the worker;
  `workspace` is worker-absolute. Do not hop with `acpx --agent`. Prepare and
  Grok login stay on the worker. A live hopped delegate still needs an
  isolated worktree, one intended path, and a stated budget.

## Scope boundary

This is an experimental local MCP slice. Local unset hop is L/A1. Set hop is B
(host-owned SSH/container argv). It does not rebuild ACP or ACpx, open a
gateway, start a Parallels/VM, reach a Grok Bot computer, qualify Puppet's
grok harness, or authorize deployment, publication, external sends, spending,
account/security changes, or destructive cleanup.
