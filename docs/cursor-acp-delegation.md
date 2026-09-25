# Local Cursor ACP delegation

This repository now carries an experimental local-only bridge for Codex. The
bridge exposes a small stdio MCP server and uses the pinned `acpx@0.19.1`
runtime to open an ACP session with the explicit local Cursor executable:

```text
/Users/bobbybones/.local/bin/cursor-agent acp
```

The requested route selector is `cursor-grok-4.6-high`. Cursor ACP may expose
an opaque parameterized ID instead of that CLI-facing selector; on this live
install the unique matching ACP ID is
`grok-4.6[effort=high,fast=true]`. The bridge fails closed when the executable
is missing, the existing Cursor login cannot open a session, there is no unique
matching advertised model ID, or the selected model is not confirmed by
session status. Live `cursor_acp_delegate` refuses when readiness is red,
defaults to `approve-reads` plus fail on write/exec that would prompt
(`approve-all` is an explicit `SAARIUS_ACP_PERMISSION_MODE` break-glass), and
binds one parent conversation to one worker with owner-gated rebind. It does
not lock cwd and does not use one-path `allow_once`.

Conversation ownership is host-controlled. `hostConversationId` identifies the
parent conversation; a request `binderId` is only an assertion and must match
the host-controlled `SAARIUS_ACP_BINDER_ID` value or the broker's configured
default. It cannot select an arbitrary owner or use `system` as an exemption.
When no stable binder is configured, the broker uses its generated process
identity, so a restart is a new owner and cannot rebind an old conversation
binding; set `SAARIUS_ACP_BINDER_ID` consistently when continuity across
processes or restarts is required. Concurrent claims, active prior jobs, and
prior jobs without proven cleanup are rejected fail-closed.
Admission writes the durable job record, including exact broker ownership,
before publishing the conversation binding. A crash at that boundary leaves a
readable job. Only confirmed unstarted or released admissions can be replaced
by the same owner; once worker startup is attempted, the admission stays
fenced until cleanup is explicitly proven. A binding whose job cannot be read
remains fail-closed. There is no automatic retry or
deletion of uncertain ownership.
When `SAARIUS_ACP_HOST_CONVERSATION_ID` or a broker default is configured, an
explicit request label must match it; with no trusted host context, the explicit
label is required but is only an identity label, not an authentication proof.
Conversation-claim locks carry broker PID/start-time metadata. A crashed lock is
reclaimed only when that exact owner is proven missing or its PID is proven reused;
live or uncertain locks remain busy. An existing reclaim fence is preserved and
returns a recovery-required error; it is never auto-deleted after an interrupted
recovery attempt.

## Local development

From the repository worktree:

```bash
cd bridge/cursor-acp
npm run setup
npm test
```

The package requires Node 22.13 or newer. `package-lock.json` pins the bridge's
development dependencies. `npm test` uses protocol fixtures and a fake runtime;
it does not contact Cursor or run a model turn.

The bounded live smoke test is opt-in:

```bash
npm run smoke
```

It uses the installed Cursor login, the exact executable and model above, a
disposable workspace, and a run directory outside that workspace. It proves
readiness/model selection, workspace binding, completion, steering refusal, and
cancellation. It does not push, deploy, send messages, change accounts, or use
an API-key fallback.

## MCP connection

The root `.codex-plugin/plugin.json` declares `.mcp.json`, whose stdio server
command uses `cwd: "."`, which Codex resolves against the installed plugin
root, with a relative server argument. This legacy `.codex-plugin` format does
not expand `${PLUGIN_ROOT}` in arguments. The plugin's MCP server
does not accept arbitrary shell commands or credentials in tool arguments.

After reviewing the package, connect it to Codex from the repository worktree:

```bash
codex plugin marketplace add "$PWD/.agents/plugins"
codex plugin add saarius-skills@saarius-skills
```

Installing/updating the plugin copies source; it does not install this bridge's
Node dependencies. After each install/update, resolve the active plugin root
from the installed skill location and prepare the persistent runtime store:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge cursor-acp
```

Set `SAARIUS_PLUGIN_ROOT` to that absolute installed plugin directory, not a
development checkout. Preparation runs locked `npm ci` with lifecycle scripts
disabled in a per-user, content-addressed runtime store outside the ephemeral
plugin cache. The MCP launcher reuses that store and performs no network install
during MCP initialization. Run the analogous Antigravity command when that lane
is enabled. `setup.mjs --check` remains a dependency/MCP health check and does
not install or send a model turn.

The shared store is keyed by bridge source, package lock, OS/architecture, and
Node compatibility. Cursor and Antigravity never reuse each other's runtime
trees. A failed or incomplete preparation never becomes launchable; diagnostics
are emitted on stderr so MCP stdout remains protocol-only.

Reload Codex or start a fresh task after repair. Verify the native
`cursor_acp_readiness` call before delegating. The Codex orchestrator model
(including GPT-5.6 Luna High) is independent of the Cursor worker model. If
native tools remain absent, diagnose registration/loading; changing models or
switching to Puppet does not repair the MCP installation.

## State, proof, and rollback

Job state defaults to the plugin data directory when Codex provides
`PLUGIN_DATA`, otherwise to:

```text
~/.local/state/saarius-skills/cursor-acp-delegation/
```

Each job has `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` outside the
mutating workspace. Prompts are not persisted by the bridge; only a SHA-256 and character
count are recorded. The acpx session store is memory-only because its records
contain conversation messages. Shutdown clears that store; restart never
resumes a previous model session. A later broker initialization, or a later `status`/`result` observation of a
non-terminal job, fails that job only when its exact owner identity is
demonstrably gone: the recorded owner is missing/dead, or a complete matching
job and lease identity plus a definite process start-time mismatch proves PID
reuse. Owner death during a bounded result wait is observed within that wait.
There is no generic periodic recovery service. Jobs owned by another live
broker, and jobs whose ownership is unknown, incomplete, missing a matching
lease, or probed without a definitive start time, are left unchanged. Proven
PID reuse is recovered; ambiguous identity is not.
Job mutation uses a sibling lock file whose complete owner metadata is published
atomically. Stale-lock takeover is serialized by an exclusive reclaim fence and
token-checked release, so two reclaimers cannot enter a critical section
together or unlink another live holder. An interrupted acquire must not leave an
empty or partial lock at the canonical path; unreadable leftovers are reclaimed
only through that fence, not deleted on sight.
Bare PID existence is not treated as proof of liveness or of reuse. Existing stores from
older bridge versions are not read, migrated or deleted. Final handoffs are bounded and redacted.

To roll back the app connection, remove the local `saarius-skills` plugin from
Codex, then restore the previous plugin revision in the repository. Stopping
the MCP server does not alter Cursor's installation or login. Job state may be
left for audit or removed only as an explicitly approved, exact-path cleanup;
the bridge never deletes it automatically.

This slice is distinct from Puppet issues #35 and #37. It does not claim a
transport-neutral controller, a second gateway, OpenClaw gateway, or formal
ACP qualification. The shared launcher honors optional `SAARIUS_ACP_HOP_ARGV`
the same way as the Antigravity hop; ACpx still stays a local child on the
worker. See the hop section in
[docs/antigravity-acp-delegation.md](antigravity-acp-delegation.md).

## Active-turn steering

The pinned acpx 0.19.1 runtime serializes turns within a session. Its `steer`
mode does not interrupt the current turn. The bridge refuses steering with
`STEERING_UNSUPPORTED` before starting another turn, so completion and
cancellation cannot lose ownership of queued work. After the canonical job
result, the parent can explicitly delegate a bounded follow-up. Historical
steering smoke evidence does not establish active-turn steering support.
