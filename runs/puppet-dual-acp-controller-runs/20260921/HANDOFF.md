# Dual ACP controller handoff

The first Cursor ACP controller slice is complete in this isolated
worktree. SaariusSkills main remains frozen at
`d0f0644f4ef4c84286d5307966514cf52cededc8`; upstream acpx remains frozen
at `f8883645c261e07b2df7f9c3b4ad243b62d8168a` (`#678`). Worker job
`59754615-f2c0-41b9-a2e8-d41d999ba4cb` connected the pinned public
runtime to Puppet's existing `cursor-acp` controller/caller path.

Repair cycle 1 was implemented by the single native Cursor worker
`35e20824-58e5-46b9-bb14-402098b36b69` with exact
`grok-4.6[effort=high,fast=true]`. It restored the committed `Contract`
API, fixed AGY imports and typed blockers, and wired the explicit
`antigravity-acp` candidate through the existing session/caller dispatch.
The prior AGY source delta was repaired in place; the prior Cursor commit
was not amended or reset.

Independent checks passed: 96 focused Python tests, 30 Cursor bridge tests,
33 Antigravity bridge tests, and 1309 repository unittest-discovery tests.
The bridge dependencies were task-local locked installs with lifecycle
scripts disabled and no lockfile changes. No live qualification, publication,
merge, or ordinary route promotion has been performed. Source acceptance and
the subsequent pinned-source refresh remain parent gates.
