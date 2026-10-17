# Local Grok ACP delegation

> **Where the server lives.** The `grok-acp` MCP server ships in the separate
> `ai-shed` plugin ([saari-co/ai-shed](https://github.com/saari-co/ai-shed)); `saarius-skills` ships
> skills and instructions only and must not also bundle the server. Broker
> source, tests, and runtime preparation live in ai-shed. Install steps:
> [the ai-shed plugin reference](../skills/acp-delegation/references/ai-shed-plugin.md).

This guide documents an experimental local-only bridge, separate from the
Cursor ACP lane and from Puppet's grok tmux harness. The bridge exposes a
small stdio MCP server named `grok-acp` and uses pinned `acpx@0.19.4` to
open an ACP session with ACpx's built-in `grok-build` agent:

```text
grok agent stdio
```

Omitting `model` on `grok_acp_readiness` and `grok_acp_delegate` selects the
first advertised id among `grok-4.7`, then `grok-4.6`, then `grok-4.5`.
Optional `fallbackModels` accepts at most two ordered exact Grok model ids
and replaces `grok-4.6` and `grok-4.5`; an empty list requires `grok-4.7`.
An explicit `model`, such as `grok-4.6`, `grok-4.7`, or `grok-4.7-build-fast`,
stays exact and never substitutes, including no silent use of the session's
current model. Do not pass `model` and `fallbackModels` together. The child
executable is `GROK_EXECUTABLE` when set, otherwise `grok` resolved from
`PATH`. Plugin manifests do not ship a machine-specific path. The bridge
fails closed when the executable is missing, the existing Grok login cannot
open a session, none of the allowed models is advertised, the input is
invalid, or the selected model is not confirmed by session status. Readiness
returns the full advertised catalog, `catalogReady`, `selectionReady`, the
requested policy, and the selected model. A missing `grok-4.7` is still
selection-ready when an allowed alternative is advertised. The resolved id is
bound to the job and checked again immediately before the prompt; catalog
drift fails with no prompt and no other model. Live `grok_acp_delegate` refuses when
readiness is red, defaults to `approve-reads` plus fail on write/exec that
would prompt (`approve-all` is an explicit `SAARIUS_ACP_PERMISSION_MODE`
break-glass), and binds one parent conversation to one worker with
owner-gated rebind. It does not lock cwd and does not use one-path
`allow_once`.

This is not `cursor-agent acp`, not a Grok Bot computer, not a phone or
browser chat host, and not an ACpx rebuild. A separate chat host (for example
Swarm Intercom) may start this bridge as its parent. That host is not part of
this plugin and is not proven here.

Conversation ownership is host-controlled. `hostConversationId` identifies the
parent conversation; a request `binderId` is only an assertion and must match
the host-controlled `SAARIUS_ACP_BINDER_ID` value or the broker's configured
default. Admission writes the durable job record, including exact broker
ownership, before publishing the conversation binding. Only confirmed
unstarted or released admissions can be replaced by the same owner; once
worker startup is attempted, the admission stays fenced until cleanup is
explicitly proven.

## Local development

Broker source and its tests live in [saari-co/ai-shed](https://github.com/saari-co/ai-shed) under
`grok-acp/`. Develop, test, and run the opt-in live smoke there (see that
package's `package.json` scripts); this repository no longer carries the
broker. Its live smoke needs `SAARIUS_ACP_PERMISSION_MODE=approve-all` as a
break-glass precondition because it exercises local `pwd`/`sleep` exec; it
does not push, deploy, send messages, change accounts, or use an API-key
fallback.

## Reasoning effort

Delegated jobs pin Grok's ACP `reasoning_effort` session option to `high`.
Without that, every job inherits the interactive CLI default from
`~/.grok/config.toml` (`default_reasoning_effort`), and `xhigh` there made
cockpit case-study jobs spend almost all of their 900 s budget reasoning
(3 s of tool time in one 885 s run). The `grok agent stdio` CLI ignores the
`--reasoning-effort` flag, so the bridge sets the ACP option after model
selection and confirms it; readiness reports it under `model.reasoningEffort`.

Set `SAARIUS_GROK_ACP_REASONING_EFFORT` to `low`, `medium`, `high` or `xhigh`
to choose another level, or to `inherit` to keep the CLI default. An
unadvertised, unavailable or unconfirmed effort fails closed.

## Delegation timeout

`timeoutMs` on `grok_acp_delegate` is the wall-clock budget for that one
ACpx prompt turn. Omit it for the 60-minute default. Request up to 4 hours
explicitly when the slice needs it. Values above 4 hours are rejected at MCP
admission and again in the broker. The requested value is what the runtime
turn receives; it is also stored on the public and persisted job. Set `SAARIUS_ACP_TIMEOUT_MS` (milliseconds, default `3600000`, integer bounds `1000..14400000`) to override the broker default timeout; invalid values fail closed at broker startup, and a per-call `timeoutMs` override wins.

That budget is not the parent conversation lifetime, the MCP session
duration, or `grok_acp_result` `waitMs`. Result wait stays a short poll
(max 5 minutes). Keep polling status/result while the turn runs. Setup, npm
install, lock reclaim, and cleanup timers are separate and stay at their
existing bounds. The historical 900 s reasoning-budget note is not this job
turn wall.

## MCP connection

Install the `ai-shed` plugin, not `saarius-skills`, to get this server; follow
[the ai-shed plugin reference](../skills/acp-delegation/references/ai-shed-plugin.md) or ai-shed's README section "Install as a
plugin". In Claude Code the server registers as `plugin:ai-shed:grok-acp` and its
tools as `mcp__plugin_ai-shed_grok-acp__<tool>`. Do not add the server to the
`saarius-skills` manifests: both plugins would register it and start two
brokers.

Installing or updating ai-shed copies source; it does not install the broker's
Node dependencies. After each install/update, prepare the persistent runtime
store from the **installed** ai-shed plugin root (`$AI_SHED_ROOT`, the harness's
plugin cache copy, not a git clone):

```bash
node "$AI_SHED_ROOT/acp-runtime/prepare.mjs" --bridge grok-acp
```

Preparation runs locked `npm ci` with lifecycle scripts disabled in a per-user,
content-addressed runtime store outside the plugin cache. The MCP launcher
reuses that store and performs no network install during MCP initialization.
`setup.mjs --check` remains a dependency/MCP health check and does not install
or send a model turn.

If the launcher reports `RUNTIME_SETUP_REQUIRED` or `prepare.mjs` reports
`RUNTIME_IDENTITY_CONFLICT`, follow the Cursor guide's
[Runtime troubleshooting](cursor-acp-delegation.md#runtime-troubleshooting).
The recovery command for this broker is:

```bash
node "$AI_SHED_ROOT/acp-runtime/prepare.mjs" --bridge grok-acp --replace-invalid
```

Reload the host or start a fresh task after repair. Verify the native
`grok_acp_readiness` call before delegating. If native tools remain absent, diagnose the
ai-shed install and reload; changing models or switching lanes does not repair
the MCP installation.

## State, proof, and rollback

Job state defaults to the plugin data directory when the host provides
`PLUGIN_DATA`, otherwise to:

```text
~/.local/state/saarius-skills/grok-acp-delegation/
```

Each job has `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` outside
the mutating workspace. Prompts are not persisted by the bridge; only a
SHA-256 and character count are recorded. The acpx session store is
memory-only. Restart never resumes a previous model session.

To roll back the app connection, remove the local `saarius-skills` plugin,
then restore the previous plugin revision. Stopping the MCP server does not
alter Grok's installation or login.

## Host hop (B)

The shared launcher honors optional `SAARIUS_ACP_HOP_ARGV` the same way as
the other local ACP bridges. ACpx stays a local child on the worker. Unset
keeps today's local L/A1 path. See the hop section in
[docs/antigravity-acp-delegation.md](antigravity-acp-delegation.md).

## Active-turn steering

The pinned acpx 0.19.4 runtime serializes turns within a session. The bridge
refuses steering with `STEERING_UNSUPPORTED` before starting another turn.
After the canonical job result, the parent can explicitly delegate a bounded
follow-up.
