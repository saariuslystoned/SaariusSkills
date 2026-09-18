# Proof packet

Status: implementation complete; local app connection pending.

This packet records deterministic tests and one bounded local Cursor ACP smoke
run. It must distinguish fixture evidence from live evidence and must not carry
credentials, raw transcripts, thought streams, or authentication logs.

## Paths

- Canonical repository: `/Users/bobbybones/Developer/SaariusSkills`
- Worker worktree: `/Users/bobbybones/.codex/worktrees/328f/SaariusSkills`
- Branch: `codex/cursor-acp-delegation-20260918`
- Run root: `/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918`

## Evidence ledger

| Evidence | Status | Location |
| --- | --- | --- |
| Protocol fixtures and broker tests | PASS | `bridge/cursor-acp/test/`; `cd bridge/cursor-acp && npm run check` — 9 tests |
| Plugin and skill validation | PASS | `validate_plugin.py .`; `quick_validate.py skills/cursor-acp-delegation`; `git diff --check` |
| Full repository regression suite | PASS | `root-unittest.log` — 1,112 tests |
| Live Cursor ACP readiness/model proof | PASS | `live/PROOF.md` — selected `grok-4.6[effort=high,fast=true]` |
| Live steering/completion proof | PASS | `live/PROOF.md` |
| Live cancellation proof | PASS | `live/PROOF.md` |

## Limitations

- No OpenClaw gateway, CP-1 route, remote host, SwarmHerdr transport, or
  Puppet ACP qualification is part of this run.
- The live proof uses the already installed Cursor login and a disposable
  workspace; it does not create accounts, alter global configuration, or push
  changes.
- The installed ACP catalog uses a parameterized opaque model ID; the bridge
  maps the explicit `cursor-grok-4.6-high` selector only when that mapping is
  unique and then verifies the selected ID through session status.
- The plugin has not been installed or activated in the Codex app by this run.
  The app currently reports the prior `saarius-skills` snapshot enabled from
  `/Users/bobbybones/.codex/.tmp/marketplaces/saarius-skills`; setup for this
  worktree is documented in `docs/cursor-acp-delegation.md`.
