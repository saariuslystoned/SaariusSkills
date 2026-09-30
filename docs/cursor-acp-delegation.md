# Cursor ACP delegation

This is the Codex → Cursor worker lane. Host the plugin in Codex, then
delegate one bounded slice over ACP to a local Cursor agent. Live Local /
Always-on / Hop hello.mjs proof is the Antigravity worker, not this lane.
Former aliases: Local was L; Always-on was A1; Hop was B. See
[docs/antigravity-acp-delegation.md](antigravity-acp-delegation.md).
Published install is the plugin, not a hand-written `~/.cursor/mcp.json`.

The bridge exposes a small stdio MCP server and uses pinned `acpx@0.19.3`
to open an ACP session with the explicit local Cursor executable:

```text
/Users/bobbybones/.local/bin/cursor-agent acp
```

The durable worker default is the plugin alias `gpt-5.6-luna-medium`: base model
`gpt-5.6-luna` plus effort `medium`. That alias is not a live ACP model id. The
parent orchestrator model, including a Codex GPT-5.6 Luna session, is a different
selection from this Cursor worker. Pass `model` and `effort` on readiness or
delegation for one job. Supported selectors are an exact advertised id, a base
name plus effort, the plugin alias, and the older documented
`cursor-grok-4.6-low|medium|high|xhigh` selector. Other suffixes are not guessed.

`ready` matches whether that same selection can be delegated. `catalogReady`
can be true while `ready` and `selectionReady` are false. The report then
includes `MODEL_REQUIRED` or `EFFORT_UNSUPPORTED` and the full advertised
`availableModelIds` / `availableModels`. It does not treat the session's
current model as the default. Duplicate or ambiguous ids and conflicting
effort fields fail closed. The resolved id and effort are stored on the job
and checked again immediately before the prompt, including when a handle is
reused. Drift fails with no prompt and no fallback.

On 2026-09-30, Cursor agent `2026.08.11-e8db854` advertised Luna as
`gpt-5.6-luna[context=272k,reasoning=medium,fast=false]`. No Luna High id was
advertised. Session config options were `mode` and `model`; there was no
separate effort setting. Product docs name the base model GPT-5.6 Luna and a
Fast pricing slug `gpt-5.6-luna-fast`; neither slug is a live model id.
Luna Medium is the user-chosen default. Explicit per-job High requests fail
closed with `EFFORT_UNSUPPORTED` on the Medium-only live catalog; Medium is
never substituted for explicit High. The integration supports switching between
`grok-4.6`, `grok-4.7`, and `gpt-5.6-luna` as needed (effort is optional advanced;
unique advertised bases resolve without choosing effort). Finish `cleanupReady`
before switching models because one conversation owns one active worker.
This does not claim subscription or pricing savings.
The bridge fails closed when the executable is missing, the existing Cursor login cannot
open a session, there is no unique matching advertised model ID, or the selected model
is not confirmed by session status. Live `cursor_acp_delegate` refuses when selection readiness is red,
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

## Delegation examples

Pass `model` alone for any of the three supported models. One conversation owns one active worker; always await canonical completion (`taskComplete: true`) and `cleanupReady: true` before delegating the next task or switching models:

```json
// Example 1: Grok 4.6 (model base name only, effort omitted)
{
  "workspace": "/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930",
  "model": "grok-4.6",
  "prompt": "Run npm run check in bridge/cursor-acp and verify test output."
}

// Example 2: Grok 4.7 (model base name only, effort omitted)
{
  "workspace": "/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930",
  "model": "grok-4.7",
  "prompt": "Inspect packaging tests and verify zero failures."
}

// Example 3: GPT-5.6 Luna (model base name only, effort omitted; resolves to live Medium shape)
{
  "workspace": "/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930",
  "model": "gpt-5.6-luna",
  "prompt": "Verify model resolution contracts and proof artifacts."
}
```

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

Tests need a real `node_modules` in the bridge directory (`npm ci`, or a copy).
Never symlink it to a prepared runtime under
`~/.local/state/saarius-skills/acp-runtime`: the runtime-store tests mutate
their fixture's dependencies, and a linked `node_modules` carries those writes
into the prepared runtime (see [Runtime troubleshooting](#runtime-troubleshooting)).

The bounded live smoke test is opt-in:

```bash
npm run smoke
```

It uses the installed Cursor login, the exact executable and model above, a
disposable workspace, and a run directory outside that workspace. It proves
readiness/model selection, workspace binding, completion, steering refusal, and
cancellation. It does not push, deploy, send messages, change accounts, or use
an API-key fallback.

## Delegation timeout

`timeoutMs` on `cursor_acp_delegate` is the wall-clock budget for that one
ACpx prompt turn. Omit it for the 60-minute default. Request up to 4 hours
explicitly when the slice needs it. Values above 4 hours are rejected at MCP
admission and again in the broker. The requested value is what the runtime
turn receives; it is also stored on the public and persisted job.

That budget is not the parent conversation lifetime, the MCP session
duration, or `cursor_acp_result` `waitMs`. Result wait stays a short poll
(max 5 minutes). Keep polling status/result while the turn runs. Setup, npm
install, lock reclaim, and cleanup timers are separate and stay at their
existing bounds.

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

For Claude Code, the [Claude Code manifest](../.claude-plugin/plugin.json)
registers all three ACP servers through `${CLAUDE_PLUGIN_ROOT}` with no
machine-specific paths:

```bash
claude plugin marketplace add "$PWD"
claude plugin install saarius-skills@saarius-skills
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
(including GPT-5.6 Luna Medium) is independent of the Cursor worker model. If
native tools remain absent, diagnose registration/loading; changing models or
switching to Puppet does not repair the MCP installation.

## Runtime troubleshooting

This section covers all three bridges; substitute the bridge name. The launcher
never installs anything. When it cannot start a bridge it writes one JSON line
to stderr and exits 2, which MCP clients show as a failed or `CONNECTION_CLOSED`
server. To read that line, run the launcher with stdin closed:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/launcher.mjs" cursor-acp </dev/null
```

`RUNTIME_SETUP_REQUIRED` carries `details.state`:

- `missing`: nothing is prepared for this plugin source and Node runtime. Run
  the `setup` command from the same line. `details.nodeVersion` and
  `details.identity` show what the launcher looked for.
- `invalid`: a tree with this identity exists but failed integrity validation.
  `details.check`, `details.path` and `details.kind` name the first failing
  check; `path` is relative to `details.root`. Only paths and kinds are
  reported, never file contents.

`prepare.mjs` reports the same fields under `RUNTIME_IDENTITY_CONFLICT` and
stays fail-closed: it never overwrites or deletes an existing tree. After
looking at what changed, move the invalid tree aside and prepare a fresh one:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge cursor-acp --replace-invalid
```

`--replace-invalid` renames the invalid tree to
`<runtime root>/.quarantine/<bridge>/<identity>-<timestamp>-<id>/`, writes a
`.json` record of the failed check beside it, and prepares a fresh tree. It
deletes nothing; remove quarantined trees yourself once they are no longer
needed. A valid tree is reused unchanged. Restart the MCP client afterwards.

Recoveries for one runtime identity are serialized by a lock at
`<runtime root>/.locks/<bridge>-<identity>.lock/`. Each recovery re-validates
the tree while holding the lock and moves it only if it is still invalid, so a
runtime that another recovery already repaired is never taken away, even
briefly. A second recovery waits for a live holder and then reports
`RUNTIME_RECOVERY_BUSY` if the wait runs out. If the recorded holder process has
exited (for example, the recovery was killed), recovery stops with
`RUNTIME_RECOVERY_LOCK_STALE` and names the lock. Remove that directory once no
`prepare.mjs` is running, then retry. If the fresh install fails after the
invalid tree was quarantined, the identity is simply missing; rerun
`prepare.mjs`.

| `check` | Meaning |
| --- | --- |
| `runtime_root` | The identity path is a symlink (even a dangling one), not a directory, or unreadable. |
| `source_file` | A copied bridge source file is missing. |
| `dependency_root` | `node_modules` is missing, not a directory, or a symlink; a prepared tree must own its dependencies. |
| `required_import` | A module the bridge imports is missing. |
| `package_version`, `dependency_version` | The tree's bridge or pinned dependency version differs. |
| `source_integrity` | A copied bridge source file differs from the plugin source. |
| `dependency_record` | `DEPENDENCIES.json` is unreadable or does not match this identity. |
| `dependency_inventory` | A file under `node_modules` was `changed`, `added` or `removed` after preparation. |
| `ready_record` | `READY.json` is unreadable or does not match this identity or platform. |
| `unexpected` | Validation itself hit an error; `kind` is the error code. |

A known cause of `dependency_inventory` / `changed` on
`node_modules/acpx/dist/runtime.js` is a trailing
`// dependency payload drift fixture` line. That line comes from the
runtime-store test suite, run from a checkout whose `node_modules` was symlinked
into the store. Preparation now refuses a linked `node_modules`, and the tests
refuse any fixture write that resolves outside their temp directory.

### Node on PATH

The runtime identity includes the Node version and module ABI. The MCP
manifests launch `node` from PATH, so the `node` the MCP client resolves decides
which identity the launcher looks up. Changing that Node makes every prepared
runtime stale at once, and the launcher reports `state: "missing"`. This can
happen without any SaariusSkills change: for example, when OpenClaw's bundled
Node (`/Applications/OpenClaw.app/Contents/Resources/node-worker/arm64/bin/node`)
is first on PATH, an OpenClaw update changes it. Check `command -v node` and
`node -v` in the environment the MCP client uses. Then run the `setup` command
from the launcher's error line. It names the exact Node binary, so the prepared
identity matches. Trees for the previous Node stay in the store unused.

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
transport-neutral controller, a proven chat-host parent, OpenClaw gateway,
or formal ACP qualification. The shared launcher honors optional
`SAARIUS_ACP_HOP_ARGV` the same way as the Antigravity hop; ACpx still
stays a local child on the worker. Cursor-worker Hop is source-landed, not
the proven MacBook → CP-1 hello.mjs job. See the hop section in
[docs/antigravity-acp-delegation.md](antigravity-acp-delegation.md).

## Active-turn steering

The pinned acpx 0.19.3 runtime serializes turns within a session. Its `steer`
mode does not interrupt the current turn. The bridge refuses steering with
`STEERING_UNSUPPORTED` before starting another turn, so completion and
cancellation cannot lose ownership of queued work. After the canonical job
result, the parent can explicitly delegate a bounded follow-up. Historical
steering smoke evidence does not establish active-turn steering support.
