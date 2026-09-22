# Local Antigravity ACP delegation

This repository carries an experimental local-only bridge for Codex, separate
from the Cursor ACP lane. The bridge exposes a small stdio MCP server named
`antigravity-acp` and uses pinned `acpx@0.19.0` to open an ACP session with
Google's official Antigravity runtime:

```text
antigravity-acp 1.1.1
registry revision 81bf71b55e15f630c4fb8a86d20d3088071d2071
acpx 0.19.0
acpxSourceCommit null (published package has no gitHead)
lastInspectedSourceCommit 50a47ad10a75431cbc276ec9b555d11fe1f69c84
lastInspectedSourceRelease 0.17.1
npm integrity sha512-sgG0CkhuvVxgfiksXjIPEl9hsHZW0CpxywPdQeoIP5D31gwZE4nrnddLUUqaSCLb1UIM7LFPBL5qdvy15/+B6Q==
tarball sha256 5a61820401cfed668ce3ad77a2feaebdd9e496a037ba28b2afca3224e7505c6d
runtime.js sha256 88a9799088146a191360a297bec94fb9006853a4420bef6257635a6b10520e1b
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

The requested model must be an exact advertised ACP model id. The bridge fails
closed when the runtime/helper is missing, personal OAuth is not already
configured under the explicit `GEMINI_HOME` profile, API-key or Cloud fallback
variables are present, overage is not proven disabled/never, the model id is
unknown, ambiguous, or substituted, or a fixed-choice `interaction_*` question
appears. Effort is not inferred from labels.

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
resolve the active plugin root from the installed skill location and run:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/antigravity-acp/scripts/setup.mjs" --install
```

Set `SAARIUS_PLUGIN_ROOT` to that absolute installed plugin directory, not a
development checkout. `--install` runs locked `npm ci` with lifecycle scripts
disabled, then initializes the MCP server and verifies all six tools.
`--check` does only the health check and prints the locked runtime/helper pin
plus exact repair actions. Neither opens Antigravity nor sends a model turn.
`DEPENDENCIES_MISSING` prints an exact repair command; `MCP_READY` establishes
server health, not that an existing Codex task has refreshed its tool
inventory.

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
