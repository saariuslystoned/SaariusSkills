# Cursor ACP delegation implementation

Status: implementation complete; app connection intentionally pending

## Ownership

- Canonical repository: `/Users/bobbybones/Developer/SaariusSkills`
- GitHub: `saariuslystoned/SaariusSkills`
- Worker worktree: `/Users/bobbybones/.codex/worktrees/328f/SaariusSkills`
- Branch: `codex/cursor-acp-delegation-20260918`
- Baseline: `a7befa0`
- Proof root: `/Users/bobbybones/.codex/worktrees/328f/SaariusSkills/runs/cursor-acp-delegation-20260918`

## Scope

Add an experimental local stdio MCP bridge and delegation skill that routes
bounded implementation work through the pinned `acpx@0.16.0` runtime to the
explicit local Cursor ACP executable. This slice is separate from Puppet's
transport-neutral controller and does not claim issues #35/#37 complete.

## Current checkpoint

- Repository and plugin contracts inspected.
- `plugin-creator` and `skill-creator` instructions read.
- Upstream `acpx@0.16.0` runtime and Cursor route inspected.
- Local MCP bridge, delegation skill, docs, fixtures, and package lock implemented.
- Fixture tests, plugin validation, skill validation, and live Cursor ACP smoke passed.
- Codex app connection was not installed or activated by this run.

Connection status: the Codex app currently reports the prior `saarius-skills`
snapshot enabled from `/Users/bobbybones/.codex/.tmp/marketplaces/saarius-skills`;
this worktree's updated Cursor ACP bridge has not been installed or activated.
