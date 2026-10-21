# JevSweeper rail alignment proof

This is documentation and packaging proof. It does not establish deployed
queue behavior, live review success, or Jev inference quality.

## Source and scope

- Repository: `saariuslystoned/SaariusSkills`
- Branch: `codex/jevsweeper-rail-refresh-20261020`
- Worktree: `/Users/bobbybones/Developer/worktrees/SaariusSkills-codex-jevsweeper-rail-refresh-20261020`
- Starting source: `74c13e997555911a803281742c8fbd7637d84fbf`
- Changed skill: `skills/jevsweeper/` only
- Evidence and provenance: this directory and [SOURCES.md](SOURCES.md)
- Paired dependency: [SmokySkills PR #33](https://github.com/saari-co/SmokySkills/pull/33),
  canonical `smoky-openclaw-autoreview` commit
  `ad244204a2a6331b9b58f2aad2f36d4a2bfa57d9`

## Validation

- Canonical skill validator: passed under `/usr/bin/python3`;
  [log](skill-validation-system-python.log). The default `python3` initially
  lacked PyYAML; [diagnostic](skill-validation.log). No package was installed.
- YAML frontmatter also passed the existing Ruby stdlib parser and field
  checks; [log](frontmatter-validation.log).
- Local Markdown links: 17 resolved; [log](local-links.log).
- Original implementation's full Python suite, including existing packaging checks:
  `python3 -m unittest discover -s tests -v` passed all 157 tests in 152.372
  seconds in one run at `ab1f07f368c258653ba6d9d95b71303fd8952378`;
  [preserved log](python-tests.log).
- Diff whitespace and assigned-scope checks: passed;
  [log](scope-check.log). Packaging manifests, test implementation, and PStack
  files are unchanged.

## Review repair: pin the operational dependency

- Review: comprehensive OpenClaw request
  `req-20261020T134758Z-215397226633` on
  `ab1f07f368c258653ba6d9d95b71303fd8952378`.
- Finding: P2 at `skills/jevsweeper/SKILL.md:23`; the operational fallback
  followed mutable `main`, while the evaluated dependency was SmokySkills
  `ad244204a2a6331b9b58f2aad2f36d4a2bfa57d9`.
- Disposition: `required_fix`, accepted. Pin that fallback to the exact
  reviewed revision and explicitly require a reviewed dependency refresh.
  The target contract still takes precedence; no runbook was copied.
- Validation: canonical quick skill validation, exact pinned source and native
  reference existence, local Markdown links, whitespace, and scoped diff;
  [repair log](review-repair-validation.log). The original 157-test log remains
  unchanged; no full-suite rerun was needed for this Markdown-only repair.
- Handoff: the dependency remains [SmokySkills PR #33](https://github.com/saari-co/SmokySkills/pull/33)
  at the same exact head. No push, review trigger, or merge by this worker.

## Source review

- Accepted: replace the two nonexistent dependency names with the canonical
  external review contract; separate review eligibility from missing product
  proof; keep queue states and coordinator status outside Jev's three labels.
- Accepted: publication readback, replacement identity, single waiting owner,
  existing authorization, and separate required-review gates.
- Accepted: valid native leftovers may be classified while CI/comprehensive
  review is pending; those gates block promotion independently, without
  serializing Jev behind them.
- Rejected: invalidating review solely because default-branch SHA advances;
  the source correction in [SOURCES.md](SOURCES.md) does not support that rule.
- Retained boundaries: no additional skill installation prerequisite, no
  automatic dispatch, no fourth label, no new evaluation framework.

## Acceptance boundaries

The scenario file records expected outcomes for absent/stale review,
unpublished completion, failed executor, terminal admission rejection,
replacement identity, default-branch advance, optional metadata, independent
review gates, and Jev unavailability. These are source-level contract checks,
not results from invoking a model or live queue.

No real Jev call, review dispatch, live queue change, installation, service
change, push, PR, or merge was performed. The containing commit is the handoff
artifact; the coordinating owner receives its exact hash and closes the lane.
