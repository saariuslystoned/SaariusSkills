# Antigravity ACP plugin follow-up

Status: implementation complete; live smoke blocked on missing pinned runtime.

## Ownership

- Repository: `saariuslystoned/SaariusSkills`
- Worktree: `/Users/bobbybones/.codex/worktrees/3ca4/SaariusSkills`
- Branch: `codex/antigravity-acp-plugin-followup`
- Dependency head / PR #51: `7bb31bb2bf83d83910f80b2690d403d6ee13e78d`
- This branch started at that exact head; the dependent PR branch was not modified
- `origin/main` at start: `5fc4a9158f4c454f2c0e2deee7642f79f4a584f8` (not merged)
- Merge-base with `origin/main`: `72934effc7db18be0c95a773cd841dbd7b52283e`
- Proof root: `/Users/bobbybones/.codex/worktrees/3ca4/SaariusSkills/runs/puppet-roadmap-runs/20260920-acpx-antigravity-plugin-followup`

## Scope

Add a separately named experimental `antigravity-acp` MCP lane in the same
Codex plugin, analogous to `bridge/cursor-acp`, using official Google
Antigravity ACP through `acpx@0.17.1` and the pinned runtime/helper contract
from `skills/puppet/scripts/puppet_lib/antigravity_acp.py`. Keep the Cursor
lane working. Native `agy-print` and Puppet qualification stay unchanged.

## Current checkpoint

- Plugin manifests, Cursor ACP bridge, PR #51 candidate contract/tests, and
  the 20260920 decision packet were inspected first.
- Focused `bridge/antigravity-acp` package, MCP server, skill, docs, and
  fixture tests are in this worktree.
- Focused Node tests: 15 passed. Cursor bridge regressions: 13 passed.
  Packaging/candidate contract tests: 19 passed.
- Setup `--check` reports `MCP_READY` plus locked runtime/helper repair.
- Live smoke blocked on `RUNTIME_MISSING`; no login or model request attempted.
- No secrets, tokens, credential stores, auth logs, `.env` files, or raw ACP
  transcripts inspected.
- No merge, push, or dependent-branch edit.
- Independent review completed: locked install, Antigravity tests, Cursor
  regressions, packaging/contract tests, setup catalogs, live smoke gate, and
  diff checks passed. Skill/plugin validators are unavailable because Python
  `yaml` is not installed; the full legacy suite was stopped after a hang in a
  pre-existing session test.
