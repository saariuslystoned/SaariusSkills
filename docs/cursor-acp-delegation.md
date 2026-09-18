# Local Cursor ACP delegation

This repository now carries an experimental local-only bridge for Codex. The
bridge exposes a small stdio MCP server and uses the pinned `acpx@0.16.0`
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
session status.

## Local development

From the repository worktree:

```bash
cd bridge/cursor-acp
npm ci
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
command resolves the bridge through `${PLUGIN_ROOT}`. The plugin's MCP server
does not accept arbitrary shell commands or credentials in tool arguments.

The local repository marketplace is:

```text
/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/.agents/plugins/marketplace.json
```

After reviewing the package, connect it to the local Codex app with the
repository's marketplace flow:

```bash
codex plugin marketplace add /Users/bobbybones/.codex/worktrees/328f/SaariusSkills/.agents/plugins
codex plugin add saarius-skills@saarius-skills
```

Start a new Codex task after reinstalling so the skill and MCP inventory are
loaded together. This implementation run does not install or activate the
plugin in the app; the concrete connection status is therefore **not yet
installed/activated**.

## State, proof, and rollback

Job state defaults to the plugin data directory when Codex provides
`PLUGIN_DATA`, otherwise to:

```text
~/.local/state/saarius-skills/cursor-acp-delegation/
```

Each job has `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` outside the
mutating workspace. Prompts are not persisted; only a SHA-256 and character
count are recorded. Final handoffs are bounded and redacted.

To roll back the app connection, remove the local `saarius-skills` plugin from
Codex, then restore the previous plugin revision in the repository. Stopping
the MCP server does not alter Cursor's installation or login. Job state may be
left for audit or removed only as an explicitly approved, exact-path cleanup;
the bridge never deletes it automatically.

This slice is distinct from Puppet issues #35 and #37. It does not claim a
transport-neutral controller, remote swarm route, OpenClaw gateway, or formal
ACP qualification.

## Active-turn steering

The pinned acpx 0.16.0 runtime serializes turns within a session. Its `steer`
mode does not interrupt the current turn. The bridge refuses steering with
`STEERING_UNSUPPORTED` before starting another turn, so completion and
cancellation cannot lose ownership of queued work. After the canonical job
result, the parent can explicitly delegate a bounded follow-up. Historical
steering smoke evidence does not establish active-turn steering support.
