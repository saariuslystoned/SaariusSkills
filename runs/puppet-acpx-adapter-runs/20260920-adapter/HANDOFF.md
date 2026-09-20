# Puppet acpx adapter handoff

Step 2 is complete as a disabled, synthetic-only Puppet adapter for the named
local `cursor-acp` transport. This artifact is ready for review; it is not
live-qualified and does not change ordinary launch behavior.

## Changed files

- `skills/puppet/scripts/cursor_acpx.py` — disabled adapter outside the
  existing `puppet_lib/*.py` census glob, so ordinary adapter fingerprints and
  qualification source scopes remain unchanged
- `tests/test_puppet_cursor_acpx.py`
- `bridge/cursor-acp/puppet-adapter.mjs` — explicit disabled surface
- `bridge/cursor-acp/test/puppet-adapter.test.mjs`
- `bridge/cursor-acp/package.json` — `node --check puppet-adapter.mjs` only

Ordinary `cursor_acp.py`, transport/session/qualification modules, native
defaults, `broker.mjs`, and `server.mjs` are unchanged.

## Dependency tuple

- source: `https://github.com/openclaw/acpx/pull/648`
- head: `2b7627a6b91b4c94c8a83ad0cc4863f72e8f14de`
- status: draft; `merged=false`; `released=false`
- qualification: `synthetic_only`
- public surface: `acpx/runtime` / `createAcpRuntime`
- integrity: `cad05ead9a4cae01e0cc612e43a16ea647323a69d14c172700c790c333e4b0fd`
- ordinary pinned package remains `acpx@0.16.0` on the MCP broker

## Proof

- focused Python adapter suite — 10 passed
- bridge `npm run check` — 23 passed; syntax checks passed
- no provider prompt, live Cursor ACP launch, or qualification action
- worker delegation and one bounded retry both ended canonically with
  `BRIDGE_RESTARTED`; parent completed and independently reviewed the bounded
  implementation after explicit user authorization

Covered: completion ≠ controller acceptance; reconnect/load exact session
identity; cancel ≠ observed halt; unsupported question human/cancel, no
invented answer; forbidden fs/read/write/terminal with no local side effect;
body-free durable artifacts; missing proof fail-closed; process-query failure
→ cleanup unknown + replacement blocked; duplicate isolated-root ownership
rejected.

## Limitations

- Synthetic fixtures only. Not merged, released, or live-qualified.
- Ordinary launch/`available()` remain false; leases stay `not_admitted`.
- Approve-all / MCP broker policy is not imported.
- Does not solve #54 / `BRIDGE_RESTARTED`.
- No provider launch, no live Cursor ACP, no qualification promotion.

The next slice may inspect this draft PR and proof, but must not treat it as
live qualification or production readiness.
