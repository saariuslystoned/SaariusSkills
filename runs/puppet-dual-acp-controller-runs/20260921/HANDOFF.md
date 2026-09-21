# Dual ACP controller handoff

The first Cursor ACP controller slice is complete in this isolated
worktree. SaariusSkills main remains frozen at
`d0f0644f4ef4c84286d5307966514cf52cededc8`; upstream acpx remains frozen
at `f8883645c261e07b2df7f9c3b4ad243b62d8168a` (`#678`). Worker job
`59754615-f2c0-41b9-a2e8-d41d999ba4cb` connected the pinned public
runtime to Puppet's existing `cursor-acp` controller/caller path.

Next is canonical cleanup release, then one Antigravity ACP worker for
the distinct AGY route/tests. No live qualification, publication, merge,
or ordinary route promotion has been performed.
