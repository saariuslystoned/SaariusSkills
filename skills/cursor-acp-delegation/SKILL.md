---
name: cursor-acp-delegation
description: Use Cursor ACP MCP to delegate bounded implementation or verification to an advertised local Cursor model, or diagnose missing Cursor ACP tools. Applies with any Codex or Claude Code orchestrator model, including Luna. Developing Puppet does not make Puppet the worker transport.
---

# Cursor ACP delegation

Use the `cursor-acp` MCP server as an optional local worker route for
substantial, bounded implementation or verification work. Cursor is
Bobby's preferred route for that kind of slice when the local route is ready;
the parent agent still owns decisions, scope, review, and any separately gated
external action.

For generic “use the SaariusSkills ACP plugin” requests, start with the
[ACP entry skill](../acp-delegation/SKILL.md). This lane's preferences and
selectors do not prohibit the other harnesses. For mode changes, follow the
[shared permission setup](../acp-delegation/references/permissions.md) and verify
the effective mode before dispatch; retain prior user authorization.
A generic entry-skill request permits another discovered native ACP lane after
this lane fails, unless the user constrained substitution. The restrictions on
alternative transports below still apply to explicit lane requests and to
non-native substitutes.

## Discovery and setup

The orchestrator model does not select the transport: Luna High, other Codex
models, and Claude Code use the same installed MCP tools. Tool names may have a plugin/server
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

After repair, reload the Codex app or start a fresh task (in Claude Code, a
fresh session; confirm with `/mcp`) so its native tool
inventory is rebuilt. `MCP_READY` proves server startup, not that the current
task has reloaded it; verify a native readiness tool call in the fresh task.
If still unavailable, report `MCP_UNAVAILABLE` with the setup result and the
specific reload/registration action needed. Do not replace this route with
Puppet, Herdr, tmux, a different model, or a task-local client unless the user
explicitly authorizes that alternative. Setup diagnosis is not worker execution.

## Operating contract

- Start with `cursor_acp_readiness` for the exact workspace when the route has
  not been checked in the current task. Require the explicit
  `/Users/bobbybones/.local/bin/cursor-agent acp` route. The worker default is the
  plugin alias `gpt-5.6-luna-high`, meaning base `gpt-5.6-luna` plus effort `high`.
  That alias is not a live model id. `preferredDefaultModelId` is the unique
  advertised id only when one exists; otherwise it is null. The parent orchestrator
  (Codex, Claude, or Luna) does not choose this worker model. The same default and
  the explicit per-job `model` / `effort` arguments apply on every orchestrator.
  Do not infer savings, quota, or subscription effects.
- `ready` is selection readiness and matches delegate. `catalogReady` may be true
  while `ready` and `selectionReady` are false. Read `availableModelIds` and
  `availableModels` in that result. A missing Luna High effort returns
  `EFFORT_UNSUPPORTED`; a missing base returns `MODEL_REQUIRED`. Do not dispatch
  either result, and do not substitute the session's current model. On 2026-09-30
  the live catalog advertised Luna only as
  `gpt-5.6-luna[context=272k,reasoning=medium,fast=false]`. Config options were
  `mode` and `model`, with no separate effort setting. Do not downgrade to Medium
  and do not treat a docs slug such as `gpt-5.6-luna-fast` as a live High id.
- Cursor Grok 4.6 and 4.7 prompt turns are on hold. Never send a Cursor Grok
  prompt, and never fall back to another executable, provider, model, or the
  current runtime selection. Duplicate, ambiguous, and conflicting effort
  selections fail closed. The resolved id is rechecked immediately before the
  prompt for both a prepared session and a fresh handle. Drift fails with no
  prompt. `cursor_acp_delegate` hard-refuses when selection readiness is red.
  Do not treat a red readiness report as advice and submit anyway.
- Use `cursor_acp_delegate` with one absolute workspace path, one parent
  conversation id (`hostConversationId` or `SAARIUS_ACP_HOST_CONVERSATION_ID`),
  optional `model` and `effort` overrides, one bounded prompt, and a bounded timeout
  (`timeoutMs` is the wall-clock budget for that one ACP turn: 60 minutes when omitted,
  up to 4 hours when explicitly requested; it is not session duration or
  `cursor_acp_result` `waitMs`). The requested and resolved model and effort are
  immutably bound to the job upon submission and preserved across follow-up,
  recovery, receipts, route, state, and proof. One parent conversation owns one
  worker. Rebind is owner-gated (`binderId` / `SAARIUS_ACP_BINDER_ID`); cwd is
  not exclusive. Prefer an isolated worktree for source mutations. Do not fan
  out by default. Live MCP permissions default to `approve-reads` plus fail on
  write/exec that would prompt. `SAARIUS_ACP_PERMISSION_MODE=approve-all` is
  explicit break-glass. On a Claude Code host the plugin manifest passes
  `SAARIUS_ACP_PERMISSION_MODE` from Claude Code's own environment through to
  the bridge and defaults it to `approve-reads`; a plugin update plus a fresh
  Claude Code session is required before that takes effect.
  `cursor_acp_readiness` reports the resolved `permission.permissionMode` and a
  `permission.warning` when it is `approve-reads`; `cursor_acp_delegate` echoes
  the same `permission` object in its submission receipt. Do not use one-path
  `allow_once` on this live MCP lane. Conversation admission persists the
  job, including exact broker
  ownership, before the binding is published. Only confirmed unstarted or
  released admissions may be replaced by the same owner; once worker startup
  is attempted, the admission stays fenced until cleanup is explicitly proven.
  Live or unobservable workers stay fenced. Do not retry or delete uncertain
  ownership.
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
  non-terminal job owned by another live broker. Startup recovery, and later
  `cursor_acp_status` / `cursor_acp_result` observations of a non-terminal
  job, fail it only when that exact owner identity is demonstrably gone:
  missing/dead, or proven PID reuse after complete matching job/lease
  identities and a definite start-time mismatch. Owner death during a bounded
  result wait is observed within that wait; there is no generic periodic
  recovery service. Unknown or incomplete ownership and probes without a
  definitive start time stay fail-safe. Do not treat bare PID existence as
  proof of liveness or of reuse. Job locks publish complete owner metadata
  atomically and preserve mutual exclusion across stale-lock takeover and
  release.
- Treat `completed`, `failed`, `cancelled`, and `needs-input` as distinct
  outcomes. Escalate `needs-input` to the user with the bounded reason; do not
  invent a login flow, API-key fallback, or hidden approval.
- Review changed files, tests, and proof independently before accepting the
  worker handoff. Keep the worker's final handoff compact and do not request or
  expose thought streams, raw ACP transcripts, credential stores, auth logs,
  `.env` files, or tokens.

## Scope boundary

This is the Codex → Cursor worker lane. Shared `SAARIUS_ACP_HOP_ARGV` can
hop the launcher; ACpx still stays a local child on the worker.
`workspace` is worker-absolute. Live Local / Always-on / Hop hello.mjs
proof is the Antigravity lane. Former aliases: Local was L; Always-on was
A1; Hop was B. This slice does not qualify Puppet's ACP transport,
implement issues #35/#37 wholesale, connect to OpenClaw or SwarmHerdr,
or authorize deployment, publication, external sends, spending,
account/security changes, or destructive cleanup. A separate host that owns
phone or browser chat (for example Swarm Intercom) may start this bridge as
its parent; that host is not part of this plugin and is not proven here.

Cursor's proprietary `ask_question` and `create_plan` requests are not claimed
as supported native surfaces here. If one blocks a task, report the explicit
`needs-input`/unsupported result and let the parent choose a bounded next step.

## Lifecycle receipts and recovery

Read `taskComplete`, `cleanupReady`, `complete`, `admissionEligible`, and
`remediation` separately. A terminal task or `BRIDGE_RESTARTED` error never
proves child cleanup. `complete` requires both task termination and observed
cleanup. `admissionEligible` describes this job's cleanup gate; normal binder
and current-binding checks still apply. Unsupported `session/close` can count
as local cleanup only when every exact owned child launch has a matching exit;
backend history discard remains explicitly unsupported.

The default binder is stable for the same host-controlled state root across
broker restarts. Explicit `SAARIUS_ACP_BINDER_ID` still wins. Keep the genuine
conversation ID. Never provide a previous binder as an impersonation override,
rewrite job records, or delete a binding to bypass admission.

For stranded old process-default binders or interrupted cleanup, use the
plan-first utility documented in [ACP lifecycle recovery](../../docs/acp-lifecycle-recovery.md).
A human must approve the exact plan before applying to live state. It retains
job outcome/history, observes only recorded owned workers, and refuses live,
foreign, ambiguous, missing, or unobservable evidence. No broad PID killing,
plugin reload, permission reset, or timeout increase is a recovery operation.
