# Puppet acpx adapter run state

- status: step2_complete_synthetic_only; draft_pr_ready
- step: 2 — disabled synthetic-only Puppet adapter
- repo: `/Users/bobbybones/.codex/worktrees/1b4d/SaariusSkills`
- branch: `codex/puppet-acpx-adapter-20260920`
- proof_root: `runs/puppet-acpx-adapter-runs/20260920-adapter`
- commit: `23eb2fd3b3e53dafcc0cad2825ccb9ccf31ba37a`
- draft_pr: https://github.com/saariuslystoned/SaariusSkills/pull/56
- worker: native Cursor ACP job and bounded retry both ended canonically with `BRIDGE_RESTARTED`; parent completed the bounded finish after explicit user authorization
- available: false
- ordinary_launch: unavailable
- qualification: synthetic_only
- live_or_provider_action: none
- full_suite: 1281 tests; one unrelated pre-existing doctor-child timing failure, task-focused suites pass

Dependency: openclaw/acpx draft PR #648 at repaired head
`02c03c7abeee0324a71e2114e6b1b4cf7b0785ff`
(`9f5d189cf0adf8151109b36814b39293a5f8b82bee38668724635f6fed652b66`).
Historical pre-repair identity remains in `events.jsonl`; current synthetic
development evidence uses the repaired head. Not merged or released.
