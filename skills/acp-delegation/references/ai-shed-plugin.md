# ACP servers come from the `ai-shed` plugin

The `cursor-acp`, `antigravity-acp`, `grok-acp`, `muse-acp` and
`jev-decision` MCP servers ship in the separate **`ai-shed`** plugin
([saari-co/ai-shed](https://github.com/saari-co/ai-shed)). The
`saarius-skills` plugin ships skills and instructions only: the
`*-acp-delegation` skills, `jevsweeper`, and this entry skill describe how to
use those servers. Do not bundle, copy, or re-add the servers in
`saarius-skills`. Both plugins would register the same server names and every
broker would start twice.

## Tool names

Claude Code registers plugin servers as `plugin:ai-shed:<server>` and exposes
their tools as `mcp__plugin_ai-shed_<server>__<tool>`, for example
`mcp__plugin_ai-shed_cursor-acp__cursor_acp_readiness` or
`mcp__plugin_ai-shed_jev-decision__decision_evaluate`. Codex and Cursor apply
their own prefixes. Search the available and deferred tool catalog for the
bare tool name (`cursor_acp_readiness`, `decision_evaluate`, ...) before
concluding a route is unavailable.

## Install

Follow ai-shed's README section "Install as a plugin" for the current steps.
In short:

| Harness | Install | Servers |
| --- | --- | --- |
| Claude Code | `claude plugin marketplace add saari-co/ai-shed` then `claude plugin install ai-shed@ai-shed` (or the `/plugin` equivalents in a session) | all five |
| Codex | From a reviewed ai-shed checkout: `codex plugin marketplace add "$PWD/.agents/plugins"` then `codex plugin add ai-shed@ai-shed` | all five |
| Cursor | Clone ai-shed into `~/.cursor/plugins/local/ai-shed` (a real directory, not a symlink), then **Developer: Reload Window** | all but `cursor-acp` |

The ai-shed repository is private: installs use your existing git credentials.

## Prepare each broker

The ACP brokers run from a persistent dependency store outside the plugin
cache; the launcher never installs during MCP startup. After installing, after
each ai-shed update and after a Node upgrade, prepare each broker from the
**installed** ai-shed plugin root (`<ai-shed root>`: the harness's plugin cache
copy, not a git clone), with the same `node` the harness puts on `PATH`:

```bash
npm run setup-runtime --prefix "<ai-shed root>/<server>"
```

An unprepared broker exits with `RUNTIME_SETUP_REQUIRED` and prints its exact
setup command with the installed path filled in. The non-mutating package check
for one broker is:

```bash
node "<ai-shed root>/<server>/scripts/setup.mjs" --check
```

`DEPENDENCIES_MISSING` includes an exact repair command; run it with
`--install` only when local setup is authorized. `jev-decision` has no
dependencies and needs no setup.

## Reload and verify

After an install, update or repair, reload the host (a fresh Claude Code
session, confirmed with `/mcp`; a restarted Codex app or fresh task; a reloaded
Cursor window) so the native tool inventory is rebuilt. `MCP_READY` from a
setup check proves server startup, not that the current task has reloaded it.
Verify with a native readiness call. If tools are still absent, report
`MCP_UNAVAILABLE` with the setup result and the exact install or reload action
still needed.

If an older `saarius-skills` install still declares these servers (its entries
fail with "Connection closed" or start duplicate brokers), update
`saarius-skills` to a version that ships skills only.
