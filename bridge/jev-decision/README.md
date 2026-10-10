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
  call after `JEV_TIMEOUT_MS`: 30 seconds by default like OpenClaw, at most
  60) comes back as `status: unavailable` with guidance to apply the rubric by
  hand. It never throws and never retries on its own.

## Routes

Picked from local settings on every call, first match wins:

| Setting | Route |
| --- | --- |
| `JEV_DISABLED=1` | none (`disabled`) |
| `TYPESAFE_BASE_URL=http://127.0.0.1:<port>` | local Kev System One server, no key, loopback only |
| `TYPESAFE_API_KEY` in the server's environment | hosted Jev at `api.typesafe.ai` |
| macOS Keychain item `typesafe-jev` (or `JEV_KEYCHAIN_SERVICE`) | hosted Jev |
| none of the above | none (`credentials-unavailable`) |

`JEV_MODEL` picks the hosted model. The default is pinned to `jev-1.13.0`, the
model the OpenClaw Gateway's decision picker uses, so every harness gets the
same judge; change both together. Hosted calls send the supplied `state` to
TypeSafe and are billed to that key.

## Set up on a Mac (once)

The Keychain route is the one that works for every app, including Cursor and
Antigravity launched from the Dock, which do not see shell variables.

```sh
security add-generic-password -U -s typesafe-jev -a "$USER" -w
# paste the TypeSafe key at the prompt; it is not echoed or written to a file
node bridge/jev-decision/server.mjs --check   # which route, no network, no key shown
node bridge/jev-decision/server.mjs --probe   # one tiny paid call to prove it works
```

The tests below prove the request and answer mapping with a stand-in judge;
only `--probe` proves this Mac can reach hosted Jev with this key. Run it once
after setup and again after changing the key or model.

### One key, two stores

OpenClaw keeps its own copy of the key (`TYPESAFE_API_KEY` in Settings →
Secrets), and this bridge reads the Keychain item. Apps opened from the Dock
cannot see OpenClaw's store, so the two copies can drift: rotate one and the
other keeps the old key. Either rotate both together, or point OpenClaw at the
same Keychain item with an exec secret provider (not yet tried on this
Gateway; the Gateway must run as your user to read your login Keychain):

```json5
{
  secrets: {
    providers: {
      keychain_typesafe: {
        source: "exec",
        command: "/usr/bin/security",
        trustedDirs: ["/usr/bin"],
        args: ["find-generic-password", "-s", "typesafe-jev", "-w"],
        jsonOnly: false,
      },
    },
  },
  plugins: {
    entries: {
      typesafe: {
        config: { apiKey: { source: "exec", provider: "keychain_typesafe", id: "value" } },
      },
    },
  },
}
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
