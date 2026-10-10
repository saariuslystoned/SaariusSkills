# jev-decision

A local MCP server that gives Claude Code, Cursor, Codex and Antigravity the
same `decision_evaluate` tool OpenClaw has, so skills like
[clawjev](../../skills/clawjev/SKILL.md) can ask Jev from any harness.

- Same request and result shape as OpenClaw's core tool: `state`, a
  `questions` map of `boolean`, `choice` or `score` questions, and a result of
  `status: ok` with `answers` and `provenance`, or `status: unavailable` with a
  `reason`.
- No dependencies. Plain `node` (22 or later) runs it; there is nothing to
  install, so a missing `npm install` can never take the judge down.
- Never blocks. Every failure (no key, wrong key, rate limit, network, a hung
  call after `JEV_TIMEOUT_MS`, default 15 seconds) comes back as
  `status: unavailable` with guidance to apply the rubric by hand. It never
  throws and never retries on its own.

## Routes

Picked from local settings on every call, first match wins:

| Setting | Route |
| --- | --- |
| `JEV_DISABLED=1` | none (`disabled`) |
| `TYPESAFE_BASE_URL=http://127.0.0.1:<port>` | local Kev System One server, no key, loopback only |
| `TYPESAFE_API_KEY` in the server's environment | hosted Jev at `api.typesafe.ai` |
| macOS Keychain item `typesafe-jev` (or `JEV_KEYCHAIN_SERVICE`) | hosted Jev |
| none of the above | none (`credentials-unavailable`) |

`JEV_MODEL` picks the hosted model (default `jev-latest`). Hosted calls send
the supplied `state` to TypeSafe and are billed to that key.

## Set up on a Mac (once)

The Keychain route is the one that works for every app, including Cursor and
Antigravity launched from the Dock, which do not see shell variables.

```sh
security add-generic-password -s typesafe-jev -a "$USER" -w
# paste the TypeSafe key at the prompt; it is not echoed or written to a file
node bridge/jev-decision/server.mjs --check   # which route, no network, no key shown
node bridge/jev-decision/server.mjs --probe   # one tiny paid call to prove it works
```

To turn it off without deleting the key: set `JEV_DISABLED=1` in the harness's
MCP entry, or remove the Keychain item with
`security delete-generic-password -s typesafe-jev`.

## Harnesses

- **OpenClaw:** not needed. Its own `decision_evaluate` uses the agent's
  `decisionModel`; clawjev tries that first.
- **Claude Code:** the plugin manifest (`.claude-plugin/plugin.json`) and the
  repo's `.mcp.json` both start `jev-decision`. The tool shows up as
  `mcp__jev-decision__decision_evaluate` (plugin installs add a prefix).
- **Codex:** `.codex-plugin/plugin.json` points at `.mcp.json`.
- **Cursor:** `.cursor-plugin/mcp.json` starts it with `${CURSOR_PLUGIN_ROOT}`.
- **Antigravity:** add this to its MCP config with the checkout's real path:

  ```json
  { "mcpServers": { "jev-decision": { "command": "node", "args": ["/path/to/SaariusSkills/bridge/jev-decision/server.mjs"] } } }
  ```

## Tests

```sh
node --test bridge/jev-decision/test/*.test.mjs
```

The tests use no network and no key: a fake judge for every failure path, and
a real stdio round trip against a stand-in Kev server on loopback.
