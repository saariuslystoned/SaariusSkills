# Proof packet

Status: follow-up MCP lane implemented and fixture-verified; live ACP remains blocked.

## Worktree proof

- Worktree: `/Users/bobbybones/.codex/worktrees/3ca4/SaariusSkills`
- Branch: `codex/antigravity-acp-plugin-followup`
- Dependency / PR #51 head: `7bb31bb2bf83d83910f80b2690d403d6ee13e78d`
- `origin/main` observed, not merged: `5fc4a9158f4c454f2c0e2deee7642f79f4a584f8`
- Dependent branch `codex/acpx-antigravity-decision` was not modified
- No secret, credential store, `.env`, token, private key, auth log, or raw ACP body read

## Evidence ledger

| Claim | Result | Evidence |
| --- | --- | --- |
| Separate MCP server named `antigravity-acp` | PASS | `.mcp.json` keeps `cursor-acp` and adds `bridge/antigravity-acp/server.mjs` |
| Cursor six-tool catalog unchanged | PASS | Cursor setup `--check` listed all six `cursor_acp_*` tools; 13 Cursor tests passed |
| Official runtime pin reused | PASS | Setup report pin `antigravity-acp` `1.1.1`, registry `81bf71b…`, acpx `0.17.1` / `50a47ad…` |
| Exact model handling | PASS | Fixture tests reject unknown, ambiguous, and substituted IDs; effort is unsupported |
| Auth fallback fail-closed | PASS | API-key and Cloud env names, plus non-`oauth-personal` settings, return setup/input errors |
| Question refusal | PASS | `interaction_*` permission requests become `needs-input` / cancelled; options are not persisted |
| Cancellation and result semantics | PASS | Cancel returns `cancellation-requested` then `cancelled`; completed jobs return bounded handoff |
| Restart stale jobs | PASS | Re-init of the same state root marks in-flight jobs `failed` / `BRIDGE_RESTARTED` |
| Workspace binding | PASS | Delegate requires an absolute directory and passes that cwd into `ensureSession` |
| No raw body persistence | PASS | Job JSON omits the prompt body; session store stays memory-only |
| Setup does not install Google runtime | PASS | `--check` reports `silentlyInstalled: false` and exact archive/helper repair |
| Live Antigravity smoke | BLOCKED | `RUNTIME_MISSING` for `agy_acp_server.par`; no login or request attempted |
| AI Ultra attribution | NOT CLAIMED | Setup/auth diagnosis records `ultraAttribution: unclaimed` |
| Native agy-print / Puppet qualification | UNCHANGED | Candidate contract tests still pass; no Puppet transport registration added |

## Commands and checks

- `npm install --ignore-scripts --no-audit --no-fund` in `bridge/antigravity-acp` created the locked `acpx@0.17.1` tree.
- `npm ci --ignore-scripts --no-audit --no-fund` in `bridge/cursor-acp` restored missing local Node modules for regression only.
- `node --test test/*.test.mjs` in `bridge/antigravity-acp` → 15 passed.
- `node --test test/*.test.mjs` in `bridge/cursor-acp` → 13 passed.
- `node scripts/setup.mjs --check` in `bridge/antigravity-acp` → `MCP_READY`, six `antigravity_acp_*` tools, runtime absent, live check false.
- `node scripts/setup.mjs --check` in `bridge/cursor-acp` → `MCP_READY`, six `cursor_acp_*` tools.
- Independent `npm ci --ignore-scripts --no-audit --no-fund` in `bridge/antigravity-acp` → locked install succeeded; follow-up `npm run doctor` → `MCP_READY`.
- Independent second `npm test` in `bridge/antigravity-acp` → 15 passed after locked install.
- `python3 -m unittest tests.test_packaging tests.test_puppet_antigravity_acp -q` → 19 passed.
- `git diff --check` → passed.
- `quick_validate.py` and `validate_plugin.py` were attempted but could not start because this host Python lacks the `yaml` module; no global dependency was installed.
- `python3 -m unittest -q` was stopped at 7 minutes 21 seconds after hanging in the pre-existing `tests/test_puppet_session.py::test_concurrent_duplicate_launch_cannot_switch_state_root` join; no affected test had failed.
- `node scripts/live-smoke.mjs` → outcome `blocked`, code `RUNTIME_MISSING`; proof at `live/PROOF.md`.

## Source set

- `bridge/antigravity-acp/`
- `skills/antigravity-acp-delegation/`
- `docs/antigravity-acp-delegation.md`
- `.mcp.json`, `.codex-plugin/plugin.json`, `README.md`, `tests/test_packaging.py`
- Candidate contract unchanged: `skills/puppet/scripts/puppet_lib/antigravity_acp.py`

## Limitations

The official `agy_acp_server` 1.1.1 binary and helper are not present in this
worktree. Live personal OAuth and overage-disabled controls were therefore not
demonstrable without installing a runtime or inspecting an existing account
profile. This packet does not claim macOS provider-auth qualification, Ultra
quota attribution, active-turn steering, or Puppet transport ownership.
Native-tool discovery still requires a Codex reload after plugin install.
