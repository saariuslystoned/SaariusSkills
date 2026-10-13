---
name: muse-acp-delegation
description: Use Muse ACP MCP to delegate bounded implementation or verification to local Muse (`muse serve`, MSP) through the muse-agent-acp adapter and ACpx, or diagnose missing Muse ACP tools. Distinct from cursor-acp, antigravity-acp, grok-acp, and from archived Puppet. Also covers remote-shed HTTP mode for shed-hosted Muse.
---

# Muse ACP delegation

Use the `muse-acp` MCP server as an optional local worker route for one
bounded implementation or verification slice. The parent harness stays the
host. ACpx is the local ACP client. The ACP child is `muse-agent-acp`, the
adapter in `bridge/muse-acp/adapter/` that translates ACP to Muse
Session Protocol (MSP) over `muse serve` stdio; `muse` itself does not
speak ACP natively. This is not the Cursor, Antigravity, or Grok ACP lane,
and not archived Puppet. The same bridge also serves remote-shed HTTP mode
(`shed_task_*` only) for shed-hosted Muse; see
[remote-shed](references/remote-shed.md).

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

Tool names may have a plugin/server prefix. Search the available/deferred tool
catalog for `muse_acp_readiness` before concluding the route is unavailable; a
short initial tool list is not proof.

If no callable Muse ACP tool is found, diagnose setup. From this installed
skill's directory, the package check is:

```bash
node ../../bridge/muse-acp/scripts/setup.mjs --check
```

Resolve that relative path against this SKILL.md, not the task's workspace.
`DEPENDENCIES_MISSING` includes an exact repair command. When local setup is
authorized, run that command with `--install`; it installs locked Node
dependencies with lifecycle scripts disabled and verifies MCP initialization
and all six tools. It does not open a Muse login or send a model turn.

The adapter spawns whatever `MUSE_EXECUTABLE` names, or `muse` on `PATH`,
as `muse serve`. Optional adapter knobs: `MUSE_AGENT_ACP_PROVIDER`,
`MUSE_AGENT_ACP_MODEL`, and `MUSE_AGENT_ACP_SERVE_ARGS` (a JSON array of
extra `muse serve` flags). Plugin manifests do not ship a machine-specific
path. Provider login is a precondition of the installed Muse CLI, not
something this bridge starts. After every plugin install/update, prepare
the persistent runtime:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge muse-acp
```

After repair, reload the host app or start a fresh task so its native tool
inventory is rebuilt. `MCP_READY` proves server startup, not that the current
task has reloaded it. If still unavailable, report `MCP_UNAVAILABLE` with the
setup result and the specific reload/registration action needed. Do not replace
this route with another ACP lane, archived Puppet, Herdr, or tmux unless the user
explicitly authorizes that alternative.

## Operating contract

- Start with `muse_acp_readiness` for the exact workspace when the route has
  not been checked in the current task. Require the local `muse serve` MSP
  host through the `muse-agent-acp` adapter and ACpx agent `muse`. Muse
  model ids come from the host's provider-dependent MSP catalog, so there is
  no hard-coded default id: when `model` is omitted the policy is host
  default — the session's current model, with no `session/set_model` call.
  Optional `fallbackModels` (at most four exact ids) is an ordered preference
  list used only when `model` is omitted; an empty list also means host
  default. An explicit `model` stays exact, must be advertised, and never
  substitutes. Do not send `model` together with `fallbackModels`. Readiness
  returns `catalogReady`, `selectionReady`, the full advertised catalog, the
  requested policy, and the selected model; an empty catalog (for example
  the `echo` provider) is ready only under host default. A missing explicit
  or preferred id, invalid input, or auth failure fails with no prompt. The
  ACP `reasoning_effort` option stays pinned to `high`
  (`SAARIUS_MUSE_ACP_REASONING_EFFORT` overrides with an MSP tier —
  `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra` — or
  `inherit` for the CLI default) and maps to MSP `session/setReasoningEffort`.
  Never silently fall back to another ACP lane, executable, or workspace.
  `muse_acp_delegate` hard-refuses when that readiness is red (runtime / auth
  / model / workspace). Do not treat a red readiness report as advice and
  submit anyway. Fixed-choice questions from the worker (`userInput/request`)
  are declined fail-closed by the adapter; ask the user in plain text instead.
- Use `muse_acp_delegate` with one absolute workspace path, one parent
  conversation id (`hostConversationId` or `SAARIUS_ACP_HOST_CONVERSATION_ID`),
  the optional `model` or `fallbackModels` policy from readiness, one bounded
  prompt, and a bounded timeout (`timeoutMs` is the wall-clock
  budget for that one ACP turn: 60 minutes when omitted, up to 4 hours when
  explicitly requested; it is not session duration or `muse_acp_result`
  `waitMs`). The requested policy and resolved exact model are bound to that
  job and rechecked on the session immediately before the prompt. If the
  catalog no longer advertises that exact id, the job fails with no prompt and
  does not switch models. One parent conversation owns one
  worker. Rebind is owner-gated (`binderId` / `SAARIUS_ACP_BINDER_ID`); cwd is
  not exclusive. Prefer an isolated worktree for source mutations. Do not fan
  out by default. Live MCP permissions default to `approve-reads` plus fail on
  write/exec that would prompt. `SAARIUS_ACP_PERMISSION_MODE=approve-all` is
  explicit break-glass. On a Claude Code host the plugin manifest passes
  `SAARIUS_ACP_PERMISSION_MODE` from Claude Code's own environment through to
  the bridge and defaults it to `approve-reads`; a plugin update plus a fresh
  Claude Code session is required before that takes effect.
  `muse_acp_readiness` reports the resolved `permission.permissionMode` and a
  `permission.warning` when it is `approve-reads`; `muse_acp_delegate` echoes
  the same `permission` object in its submission receipt. Do not use one-path
  `allow_once` on this live MCP lane. Conversation admission persists the
  job, including exact broker
  ownership, before the binding is published. Only confirmed unstarted or
  released admissions may be replaced by the same owner; once worker startup
  is attempted, the admission stays fenced until cleanup is explicitly proven.
  Live or unobservable workers stay fenced. Do not retry or delete uncertain
  ownership.
- Save the returned job ID. Use `muse_acp_status` for progress and
  `muse_acp_result` with a bounded wait for the canonical outcome. A
  submitted job, process exit, or progress event is not task success.
- `muse_acp_steer` fails closed with `STEERING_UNSUPPORTED`. Wait for the
  canonical terminal result, then explicitly delegate a bounded follow-up. Use
  `muse_acp_cancel` when the parent decision changes or the bounded budget is
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
  Muse login stay on the worker. A live hopped delegate still needs an
  isolated worktree, one intended path, and a stated budget.

## Scope boundary

This is an experimental local MCP slice. Local unset hop is Local/Always-on.
Set hop is Hop (host-owned SSH/container argv). Remote-shed HTTP mode on the
same bridge serves only `shed_task_*` behind the operator's Cloudflare
Tunnel + Access (see [remote-shed](references/remote-shed.md)); it never
combines with hop. This lane does not rebuild ACP, ACpx, or MSP, start a
Parallels/VM, revive archived Puppet, or authorize deployment, publication,
external sends, spending, account/security changes, or destructive cleanup.
A separate host that owns phone or browser chat (for example Swarm Intercom)
may start this bridge as its parent; that host is not part of this plugin
and is not proven here.

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
