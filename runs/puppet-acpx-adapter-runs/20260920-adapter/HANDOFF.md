# Puppet acpx adapter handoff

Step 2 is complete as a disabled, synthetic-only Puppet adapter for the named
local `cursor-acp` transport. This artifact is ready for review; it is not
live-qualified and does not change ordinary launch behavior.

Draft PR: https://github.com/saariuslystoned/SaariusSkills/pull/56
Implementation commit: `23eb2fd3b3e53dafcc0cad2825ccb9ccf31ba37a`
Dependency refresh commit: `88d3ba63b7e4bcdc6a9db040e3829bac88ff97ee`

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
- repaired head: `02c03c7abeee0324a71e2114e6b1b4cf7b0785ff`
- status: draft; `merged=false`; `released=false`
- qualification: `synthetic_only`
- public surface: `acpx/runtime` / `createAcpRuntime`
- integrity: `9f5d189cf0adf8151109b36814b39293a5f8b82bee38668724635f6fed652b66`
- ordinary pinned package remains `acpx@0.16.0` on the MCP broker
- upstream repair delta is test-only: reconnect/load-session support, absolute
  fixture paths, enabled/disabled control reconnect coverage, and probe path
  assertions; no runtime implementation file changed
- historical pre-repair identity remains in `events.jsonl`

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
