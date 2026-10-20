# Existing Live journeys evidence before beta setup

## Source and scope

- Repository: `saariuslystoned/SaariusSkills`
- Branch: `codex/dinkuskit-existing-proof-20261020`
- Base: `76c6b7bad6ef1c83ea9bcff281bc8074bc1cd80d`
- Changed source: `skills/dinkuskit-live-test/SKILL.md` only.
- Inspected contracts: the skill, `CONTRIBUTING.md`, the runner README's roster
  and GitHub route, `.github/workflows/live-journeys.yml`, and the existing
  public-summary implementation in `runner/scripts/run-summary.mjs`.

The workflow accepts a journey selection, serializes beta-store runs, and may
replace a queued run on another dispatch. Its summary reports recorded journey
results and plugin versions; it does not establish the complete current roster
by itself. These source facts support checking an existing matching execution
before requesting another.

The skill now routes beta release proof before local setup. Reuse requires
applicable source, exact run/attempt and release identity, selected and actually
passed current journeys, and required detailed proof. Active matching runs
retain one execution identity; missing or mismatched evidence remains a gap.
The release section references this route instead of repeating local beta
instructions. Existing observations are not asserted as current deployment.

## Validation and limitations

- Quick skill validation passed; [output](skill-validation.log).
- Existing packaging/mail-boundary test passed:
  `python3 -m unittest tests.test_packaging.PackagingTests.test_dinkuskit_live_test_is_packaged_and_reads_mail_only -v`;
  [output](packaging-test.log).
- Local links and anchors, exact allowed diff, unchanged existing rules/local
  procedure, runner/workflow identity, and proof privacy are recorded in
  [source checks](source-checks.log).
- No wording-matching test was added, and the unchanged full suite was not
  rerun.

This is source-only proof. No live test, setup, authentication, store mutation,
workflow dispatch, installation, deployment, push, PR, merge, or model behavior
evaluation was performed. The coordinator owns separate behavior testing.
No private case, rubric, or transcript is included.
