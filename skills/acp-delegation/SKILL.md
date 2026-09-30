---
name: acp-delegation
description: Route generic requests to use the SaariusSkills ACP plugin or delegate through ACP. Discover Grok CLI, Cursor, and Antigravity native tools, select a suitable harness, verify effective permissions, and submit a bounded task. Use a lane skill directly for an already selected harness.
---

# SaariusSkills ACP delegation

Use this entry point when the user has not selected a worker harness. The
plugin supports three native MCP lanes; a preference is not an exclusivity rule.
The parent owns task scope, result verification, and external-action gates.
This workflow concerns native plugin lanes, not Puppet's ACP transport roadmap.

## Discover and select

Search the available and deferred native tool catalog for all three families
before declaring a route unavailable or writing a restricted handoff:

| Worker harness | Native readiness tool | Selected lane contract |
| --- | --- | --- |
| Grok CLI (`grok agent stdio`) | `grok_acp_readiness` | [Grok](../grok-acp-delegation/SKILL.md) |
| Cursor (`cursor-agent acp`) | `cursor_acp_readiness` | [Cursor](../cursor-acp-delegation/SKILL.md) |
| Google Antigravity ACP | `antigravity_acp_readiness` | [Antigravity](../antigravity-acp-delegation/SKILL.md) |

Names may include server/plugin prefixes. Discoverability is not readiness.
Codex and Claude Code package all three servers; Cursor's host package includes
Grok and Antigravity and omits the Cursor worker lane. Check live tools anyway;
do not assume every host has the same inventory.

Honor an explicit harness and any prohibition on substitution. Read only the
selected lane's detailed contract. For a generic request, use established user
preferences and task requirements to choose a candidate; Cursor is Bobby's
preferred implementation route when available and suitable. Probe that candidate
for the exact absolute workspace. If it fails, report its concrete error; for a
generic request without a substitution constraint, select another discovered
candidate and load its contract before probing it. Stop after one readiness
attempt per available lane unless a concrete repair changed the state.

A harness is not a model. Distinguish the parent Codex or Claude Code orchestrator
model from the worker harness and its delegated worker model. Use readiness's
advertised model catalog and selected model ID. Cursor's durable worker default
is the plugin alias `gpt-5.6-luna-medium` (base `gpt-5.6-luna` plus effort `medium`),
not a live id; pass that lane's explicit `model` and `effort` for one job. For
Cursor, `ready` matches delegate selection readiness. A `catalogReady` result
with `ready: false` and `MODEL_REQUIRED` or `EFFORT_UNSUPPORTED` is not
dispatchable, including when default Luna Medium is absent or an unsupported effort
is requested. Never infer a model from
the harness name, rely on speculative billing or subscription assumptions, or
copy a historical advertised ID. The Cursor integration supports switching between
`grok-4.6`, `grok-4.7`, and `gpt-5.6-luna` as needed (effort is optional advanced
for unique advertised bases; ensure cleanupReady before switching jobs).

## Establish task readiness

Summarize runtime/model/auth/workspace evidence separately from tool approval.
`ready: true` confirms lane readiness; it does not make `approve-reads`
write/exec-ready. Preserve exact readiness (including thrown setup errors),
selected model, workspace, and `permission` in the task's proof.

Read [permission setup](references/permissions.md) when permission configuration
is needed. Both `approve-reads` and `approve-all` are supported. Check the active
`permission.permissionMode`, `supportedModes`, and `toolApproval` fields. Read
approval alone cannot satisfy an implementation or exec task. For that task,
require user-authorized `approve-all` and verify it in a fresh native readiness
call before submission. An authorization from earlier in the session or a
trusted user handoff persists: do not ask for the same authorization again.
If authorization or a host reload is missing, request only that precise action
and explain the cause. Never fabricate a `permissionMode` delegate argument.

`approve-all` grants tool execution within the authorized task. It does not
authorize unrelated changes, publication, deployment, merges, account/device
changes, secret access, or external sends. Retain repo and user gates.

## Dispatch and close out

Use the selected native `*_acp_delegate` with the lane's accepted arguments:
one isolated workspace for source changes, one parent conversation identity,
one bounded prompt and timeout. `timeoutMs` is the wall-clock budget for that
one delegated ACP turn: omit it for the 60-minute default, or request up to 4
hours explicitly. It is not the parent conversation lifetime, the MCP session
duration, or `*_acp_result` `waitMs`. Result wait stays a short poll (max 5
minutes); keep polling status/result while the turn runs. Setup, npm, lock,
and cleanup timers are separate and stay unchanged. Compare the returned
`permission` and selected route/model to the verified readiness. If they
differ, report the mismatch and use the lane's cancellation contract rather
than accepting the job as verified. Save the job ID and follow
`*_acp_status` / `*_acp_result` to its canonical terminal outcome. A
submission receipt is not success. Independently verify the changed files and
relevant checks before accepting the result.

A cross-session handoff must retain: selected harness and reason; discovered
alternatives and their known readiness (unprobed is unknown); exact readiness
and effective mode; prior user authorization and substitution constraints;
repo/branch/worktree; job ID/result; concrete blocker and exact remediation.
Keep scope and external-action gates intact. Never turn a preferred route into
a prohibition on other harnesses.

For regression evaluation, use [the scenarios](references/evaluations.md).
