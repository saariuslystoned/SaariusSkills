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

Repair cycle 2 was dispatched to exactly one native Cursor ACP worker,
`f3b870e8-94af-42da-a9e9-fe9819ce335c`, with exact
`grok-4.6[effort=high,fast=true]`. Its uncommitted delta carries caller task
text, public `setModel` selection, persistent next-turn/final-close behavior,
explicit candidate-vs-synthetic runtime configuration, and the AGY
clean-checkout optional-artifact skip.

Independent evidence for the delta: 58 focused Python tests passed; supplied
artifact bridge checks passed with Cursor 30/30 and Antigravity 33/33; a clean
git-archive checkout passed Cursor 23/30 with 7 explicit optional-artifact
skips and Antigravity with 1 explicit optional-artifact skip. The decisive
remaining mismatch is normal candidate construction: both structured launch
callers invoke the default candidate factory without passing the trusted
manifest executable. Reproductions through the two structured launch
functions fail before runtime creation with `ValidationError: cursor-acp
candidate executable is missing` and `ValidationError: antigravity-acp
candidate executable is missing`. The worker source remains uncommitted for
parent adjudication; no extra worker, pin refresh, live qualification, or
provider action was performed.

The parent-rescoped lifecycle worker was native Cursor ACP job
`faeec797-3fa7-4893-a0d0-f5c6d289267c`. It binds each named route through the
existing official resolver policy, returns a process-local owner plus
body-free continuation from the default factory, and proves two useful turns
plus exact synthetic child exit without private runner injection. The native
AGY manifest executable is not used as the ACP server. Ordinary availability
stays false. No pin refresh, live qualification, publication, or merge.

This release/env repair started from exact
`83935f3ad55e1f2f51a154f948d7d25f63cf26e4`. Finish failure now still shuts
down the task-owned runtime; uncertain cleanup keeps ownership and refuses
another turn. Official AGY candidate launch starts the driver/child from the
validated allowed environment only, or fails closed. Focused checks: 119
Python, 65 Cursor bridge, 34 Antigravity bridge. No pin refresh, live
qualification, publication, or merge.

The authorized upstream refresh started from accepted
`e999f88092ef8e07c7dd1736b31c69bfeacb738b`. Both Cursor and AGY consumers now
materialize exact acpx `2e05de525dd1ab62e9e74bf02d91e3638920fcf3` / tree
`c612e764ead5d8eaa409956fb1b11c008a7579ed` from
`runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz`
(SHA-256 `5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614`).
The old f888 artifact remains in place as a rejected fence. Focused checks:
121 Python, 66 Cursor bridge, 34 Antigravity bridge, including two-turn
non-default-model cleanup and owned-child retirement/reconnect with recorded
backend mapping. `#687` was not cherry-picked. No live qualification,
publication, merge, or PR.
