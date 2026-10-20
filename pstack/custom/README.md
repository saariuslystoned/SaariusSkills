# Local PStack sources

`skills/bobby-mode/` and `skills/pstack-playbooks/` are the hand-maintained
Saarius sources. They are not from `cursor/plugins` and are never replaced by
an upstream refresh. Their license is in `LICENSE`.

Edit these files when changing local behavior, then run
`python3 scripts/sync-pstack-skills --package` from the repository root.
The matching `pstack/skills/` trees are generated compatibility/distribution
paths; `--check` detects drift between those copies and these sources.
