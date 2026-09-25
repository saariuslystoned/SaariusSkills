# Antigravity ACP delegation

Host this plugin in Codex or Cursor, then delegate one bounded slice over
ACP to Google's official Antigravity runtime. The bridge is a stdio MCP
server named `antigravity-acp`. ACpx is the local client. SaariusSkills is
the host policy. Published install is the plugin, not a hand-written
`~/.cursor/mcp.json`.

This lane is separate from the Cursor worker (`cursor-acp`) and from native
`agy --print` / Puppet qualification. It uses pinned `acpx@0.19.1`:

```text
antigravity-acp 1.1.1
registry revision 81bf71b55e15f630c4fb8a86d20d3088071d2071
acpx 0.19.1
acpxSourceCommit null (published package has no gitHead)
lastInspectedSourceCommit 50a47ad10a75431cbc276ec9b555d11fe1f69c84
lastInspectedSourceRelease 0.17.1
OpenClaw main 482a4b2c499a053b173c5d36d78cf67b9137e013 depends on acpx 0.19.1
@openclaw/acpx 2026.9.7
npm integrity sha512-zKVZVM6tHGXmdXU+sC30jdFLzz0ZpNLMorYKH+it3XcuEcvFl20sLbHPqfdjfsLfV+PmhRDEm1b9Np5KxgFHow==
tarball sha256 f99d74e81085121563c917f4509758fb78bf1fa30424e469193c09837592bbf0
runtime.js sha256 5dfd93c5345bd039f9ab8f50afdf1b621e7ba46c41575d07c2637aa31dea546e
agent-registry.js sha256 bbc57d4f195f93ceb93b4a71fa9c0d51e9717867d728623e97c8e8f81c18f48c
```

The runtime binary and matching `localharness_external` helper are a separate
download. This package does not install or update them. Native `agy --print`
and Puppet qualification stay on their own routes.

## Placements (L / A1 / B)

The same six tools run in three proven placements. **A2** (a SaariusSkills
chat gateway that owns phone or browser chat and spawns ACP) stays off.

| Id | Parent | Worker | What it is | Proven |
| --- | --- | --- | --- | --- |
| **L** | This machine | This machine | Parent and worker are local children of the plugin host. | MacBook desktop Agent chat: readiness plus `proof/l-live-dogfood/hello.mjs` (job `38a1c9e7`). After [#80](https://github.com/saariuslystoned/SaariusSkills/pull/80), job `a8c3cbbf` admitted then fail-closed write/exec that would prompt. |
| **A1** | Always-on box | Same box | L pointed at a different machine. Attach to that box; the plugin, ACpx, and Antigravity stay local there. | CP-1: readiness plus `proof/a1-live-dogfood/hello.mjs` (job `9028cc7a`). First live job `43190be6` fail-closed on `approve-reads`. |
| **B** | Carry laptop | Another machine | Parent hops stdio with `SAARIUS_ACP_HOP_ARGV` before ACpx starts. ACpx stays a local child on the worker. | MacBook → CP-1 job `69b134e9` wrote `proof/b-live-dogfood/hello.mjs` after [#83](https://github.com/saariuslystoned/SaariusSkills/pull/83). |

Those hello.mjs jobs used the Antigravity worker. A cloud Cursor Project
chat still cannot call `antigravity_acp_*`.

Host policy on `main` ([#80](https://github.com/saariuslystoned/SaariusSkills/pull/80),
[#82](https://github.com/saariuslystoned/SaariusSkills/pull/82)): readiness
gates `delegate`; everyday permission is `approve-reads` plus fail;
`approve-all` is break-glass; one parent conversation owns one worker.

When the pinned runtime is installed at the documented default location,
native MCP readiness discovers it without shell-only environment overrides:

```text
~/.local/share/saarius-skills/antigravity-acp/<version>-<platform-archive>
```

`ANTIGRAVITY_ACP_RUNTIME_DIR`, `ANTIGRAVITY_ACP_SERVER`, and
`ANTIGRAVITY_HARNESS_PATH` remain explicit overrides for non-default layouts.

When the caller omits `model`, the plugin default is the exact advertised id
`gemini-3.8-flash-high`. That default is defined in the plugin contract
(`PREFERRED_DEFAULT_MODEL_ID` in `bridge/antigravity-acp/contract.mjs`) and
applied by readiness and delegate. It is not a `GEMINI_HOME` setting, not a
machine `settings.json` field, and not a Bobby-only MCP env. If that id is not
advertised, omit-model fails closed and an exact advertised id is required. The
bridge never treats runtime `currentModelId` or `gemini-3.7-flash-high` as the
wished default. An explicit requested model must still be an exact advertised
ACP id. The bridge fails closed when the runtime/helper is missing, personal
OAuth is not already configured under the explicit `GEMINI_HOME` profile,
API-key or Cloud fallback variables are present, overage is not proven
disabled/never, the model id is unknown, ambiguous, or substituted, or a
fixed-choice `interaction_*` question appears. Effort is not inferred from
labels. Live `antigravity_acp_delegate` refuses when readiness is red, defaults
to `approve-reads` plus fail on write/exec that would prompt (`approve-all` is
an explicit `SAARIUS_ACP_PERMISSION_MODE` break-glass), and binds one parent
conversation to one worker with owner-gated rebind. It does not lock cwd and
does not use one-path `allow_once`. The candidate Puppet controller contract
stays separate.

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
cd bridge/antigravity-acp
npm run setup
npm test
```

The package requires Node 22.13 or newer. `package-lock.json` pins the
bridge's development dependencies. `npm test` uses protocol fixtures and a
fake runtime; it does not contact Antigravity or run a model turn.

The bounded live smoke test is opt-in and stays blocked unless
already-authorized personal OAuth and overage-disabled controls are
demonstrably available without account switching or billing changes:

```bash
npm run smoke
```

It will not start a login or send a live request from this follow-up worker.

## MCP connection

The root `.codex-plugin/plugin.json` declares `.mcp.json`, which now has two
separately named stdio servers: `cursor-acp` and `antigravity-acp`. Both use
`cwd: "."`, which Codex resolves against the installed plugin root. This
legacy `.codex-plugin` format does not expand `${PLUGIN_ROOT}` in arguments.

After reviewing the package, connect it to Codex from the repository worktree:

```bash
codex plugin marketplace add "$PWD/.agents/plugins"
codex plugin add saarius-skills@saarius-skills
```

Published install is the Codex or Cursor plugin. A machine-local
`~/.cursor/mcp.json` attach is operator config, not the product install.

Installing/updating the plugin copies source; it does not install this
bridge's Node dependencies or the Google runtime. After each install/update,
resolve the active plugin root from the installed skill location and prepare
the persistent runtime store:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge antigravity-acp
```

Set `SAARIUS_PLUGIN_ROOT` to that absolute installed plugin directory, not a
development checkout. Preparation runs locked `npm ci` with lifecycle scripts
disabled in a per-user, content-addressed runtime store outside the ephemeral
plugin cache. The MCP launcher reuses that store and performs no network install
during MCP initialization. Run the analogous Cursor command when that lane is
enabled. `setup.mjs --check` remains a dependency/MCP health check and does not
install, download the Google runtime, or send a model turn.

The shared store is keyed by bridge source, package lock, OS/architecture, and
Node compatibility. Cursor and Antigravity never reuse each other's runtime
trees. A failed or incomplete preparation never becomes launchable; diagnostics
are emitted on stderr so MCP stdout remains protocol-only.

Reload Codex or start a fresh task after repair. Verify the native
`antigravity_acp_readiness` call before delegating. The Codex orchestrator
model is independent of the Antigravity worker model. If native tools remain
absent, diagnose registration/loading; changing models or switching to Cursor
ACP, Puppet, or native `agy-print` does not repair this MCP installation.

## Auth and profile

The MCP server uses an explicit `GEMINI_HOME` profile, defaulting to:

```text
~/.local/state/saarius-skills/antigravity-acp/gemini-home
```

Complete personal Google OAuth in an interactive ACP client that uses that
exact profile, then keep:

```json
{ "auth": { "type": "oauth-personal" }, "useG1Credits": false }
```

in `<GEMINI_HOME>/antigravity-acp/settings.json`. Missing login or overage
proof is a `needs-input`/setup result. Do not add API keys, Cloud project
variables, alternate accounts, or paid-credit fallback. This route does not
claim Google AI Ultra quota attribution.

## State, proof, and rollback

Job state defaults to the plugin data directory when Codex provides
`PLUGIN_DATA`, otherwise to:

```text
~/.local/state/saarius-skills/antigravity-acp-delegation/
```

Each job has `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` outside
the mutating workspace. Prompts, outputs, questions, and transcripts are not
persisted; only hashes, counts, status, IDs, and redacted handoff metadata are
recorded. The acpx session store is memory-only because its records contain
conversation messages. Shutdown clears that store; restart never resumes a
previous model session and fails in-flight jobs closed as `BRIDGE_RESTARTED`.
Final handoffs are bounded and redacted.

To roll back the app connection, remove the local `saarius-skills` plugin from
Codex, then restore the previous plugin revision in the repository. Stopping
the MCP server does not alter Antigravity's installation or login. Job state
may be left for audit or removed only as an explicitly approved, exact-path
cleanup.

This slice is distinct from Puppet issues #35, #37, and #38. It does not claim
a transport-neutral controller, A2, a second gateway, or formal ACP
qualification.

## Host hop (B)

B is proven. The parent launcher places the same six-tool server on another
machine without changing tool names or turning ACpx into an SSH client.
Live proof: MacBook parent → CP-1 worker, job `69b134e9`,
`proof/b-live-dogfood/hello.mjs` (`B_READY`, exit 0), after
[#83](https://github.com/saariuslystoned/SaariusSkills/pull/83). ACpx stayed
a local child on CP-1. Workspace was worker-absolute.

Set `SAARIUS_ACP_HOP_ARGV` on the **parent** attach to a JSON array that
execs the worker launcher over stdio (`ssh -T …`, `docker exec -i …`). The
worker launcher command must include the explicit `--worker` entry flag, for
example:

```json
["ssh", "-T", "worker.example", "node", "/opt/saarius-skills/bridge/acp-runtime/launcher.mjs", "antigravity-acp", "--worker"]
```

That example is the shape, not a published hostname. Hop argv is operator
config. Do not put a Bobby hostname in the plugin manifests. Do not treat
bare `ssh` as the laptop login user as the proven hop identity. Do not hop
with `acpx --agent ssh`.

Unset keeps the local L/A1 path. A set-but-invalid value fails closed and
does not spawn a local ACpx child.

The launcher uses `--worker` to establish worker mode inside the worker's own
environment; this is the transport contract and does not depend on SSH or
Docker forwarding arbitrary environment variables. The local child is also
started with the hop env stripped and `SAARIUS_ACP_HOP_ROLE=worker` as
defense-in-depth. Nested hop argv is refused. `acpx` or
`--agent` in the hop argv is refused. Token-shaped argv entries are
refused. Published plugin manifests stay hop-free.

`workspace` is an absolute path on the worker. Prepare, the official
1.1.1 runtime, `GEMINI_HOME`, and job state stay on that box. The laptop
does not need a local AGY runtime for a hopped job. Hop-process exit is
transport death, not proof the remote worker is gone. The hop command
must die with the parent (no `ssh -f`, no `ControlPersist`).

A later B turn still needs an isolated worktree, one intended path, and a
stated budget. This document does not authorize a new model turn.

## Not claimed

- A cloud Cursor Project chat can call `antigravity_acp_*`.
- Google AI Ultra / quota entitlement.
- A2, a second gateway, Parallels, or `acpx --agent ssh`.
- Bare `ssh` as the laptop login user to the always-on box.
- `~/.cursor/mcp.json` as the published install.
- Cursor-worker hello.mjs jobs (L/A1/B live proof is this Antigravity lane).

## Active-turn steering

Active-turn steering is unproved for this runtime. The bridge refuses
steering with `STEERING_UNSUPPORTED` before starting another turn. After the
canonical job result, the parent can explicitly delegate a bounded follow-up.
