# Local Grok ACP delegation

This repository carries an experimental local-only bridge, separate from the
Cursor ACP lane and from Puppet's grok tmux harness. The bridge exposes a
small stdio MCP server named `grok-acp` and uses pinned `acpx@0.19.1` to
open an ACP session with ACpx's built-in `grok-build` agent:

```text
grok agent stdio
```

The plugin default model is the exact advertised id `grok-4.7`. The child
executable is `GROK_EXECUTABLE` when set, otherwise `grok` resolved from
`PATH`. Plugin manifests do not ship a machine-specific path. The bridge
fails closed when the executable is missing, the existing Grok login cannot
open a session, the selected model is not advertised, or the selected model
is not confirmed by session status. Live `grok_acp_delegate` refuses when
readiness is red, defaults to `approve-reads` plus fail on write/exec that
would prompt (`approve-all` is an explicit `SAARIUS_ACP_PERMISSION_MODE`
break-glass), and binds one parent conversation to one worker with
owner-gated rebind. It does not lock cwd and does not use one-path
`allow_once`.

This is not `cursor-agent acp`, not a Grok Bot computer, not a gateway, and
not an ACpx rebuild.

Conversation ownership is host-controlled. `hostConversationId` identifies the
parent conversation; a request `binderId` is only an assertion and must match
the host-controlled `SAARIUS_ACP_BINDER_ID` value or the broker's configured
default. Admission writes the durable job record, including exact broker
ownership, before publishing the conversation binding. Only confirmed
unstarted or released admissions can be replaced by the same owner; once
worker startup is attempted, the admission stays fenced until cleanup is
explicitly proven.

## Local development

From the repository worktree:

```bash
cd bridge/grok-acp
npm run setup
npm test
```

The package requires Node 22.13 or newer. `package-lock.json` pins the bridge's
development dependencies. `npm test` uses protocol fixtures and a fake runtime;
it does not contact Grok or run a model turn.

The bounded live smoke test is opt-in:

```bash
SAARIUS_ACP_PERMISSION_MODE=approve-all npm run smoke
```

The explicit `SAARIUS_ACP_PERMISSION_MODE=approve-all` is required as a
break-glass precondition because this smoke intentionally exercises local
`pwd`/`sleep` exec. Unset or default `approve-reads` refuses before runtime or
provider startup; the command does not automatically escalate permissions.
It uses the installed Grok login, `grok agent stdio`, plugin default
`grok-4.7`, a disposable workspace, and a run directory outside that
workspace. It proves readiness/model selection, workspace binding, completion,
steering refusal, and cancellation. It does not push, deploy, send messages,
change accounts, or use an API-key fallback.

## MCP connection

Codex `.mcp.json` and Cursor `.cursor-plugin/mcp.json` both start the shared
launcher with bridge name `grok-acp`. After each plugin install/update,
prepare the persistent runtime store from the installed plugin root:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge grok-acp
```

Set `SAARIUS_PLUGIN_ROOT` to that absolute installed plugin directory, not a
development checkout. Preparation runs locked `npm ci` with lifecycle scripts
disabled in a per-user, content-addressed runtime store. The MCP launcher
reuses that store and performs no network install during MCP initialization.
`setup.mjs --check` remains a dependency/MCP health check and does not
install or send a model turn.

Cursor, Antigravity, and Grok never reuse each other's runtime trees.

Reload the host or start a fresh task after repair. Verify the native
`grok_acp_readiness` call before delegating.

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

The pinned acpx 0.19.1 runtime serializes turns within a session. The bridge
refuses steering with `STEERING_UNSUPPORTED` before starting another turn.
After the canonical job result, the parent can explicitly delegate a bounded
follow-up.
