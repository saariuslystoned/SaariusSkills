# Local Antigravity ACP delegation

This repository carries an experimental local-only bridge for Codex, separate
from the Cursor ACP lane. The bridge exposes a small stdio MCP server named
`antigravity-acp` and uses pinned `acpx@0.19.1` to open an ACP session with
Google's official Antigravity runtime:

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
When `SAARIUS_ACP_HOST_CONVERSATION_ID` or a broker default is configured, an
explicit request label must match it; with no trusted host context, the explicit
label is required but is only an identity label, not an authentication proof.
Conversation-claim locks carry broker PID/start-time metadata. A crashed lock is
reclaimed only when that exact owner is proven missing or its PID is proven reused;
live or uncertain locks remain busy.

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
a transport-neutral controller, remote swarm route, or formal ACP
qualification.

## Active-turn steering

Active-turn steering is unproved for this runtime. The bridge refuses
steering with `STEERING_UNSUPPORTED` before starting another turn. After the
canonical job result, the parent can explicitly delegate a bounded follow-up.
