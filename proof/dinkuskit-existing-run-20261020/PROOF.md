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

## Fixed-pair behavior comparison

The frozen comparison used upstream Harness2
`1cfe254e8d25b15f37048c3730134686abe60335` through its custom adapter and actual
`judge_one` API. Six Codex CLI calls used the existing ChatGPT subscription,
with no retries or observed tool actions. Each arm received the full skill
and the same complete pinned runner README. No variant meaning or private
rubric was given to the solver. A separate judge scored neutral IDs against
nine prewritten criteria per case.

| Fictional case | Baseline | Candidate |
| --- | ---: | ---: |
| Matching full run and misleading subset | 9/9 | 9/9 |
| Active matching run | 8/9 | 9/9 |
| Completed but unusable evidence | 9/9 | 8/9 |
| Total | 26/27 | 26/27 |

**No measured efficiency gain.** The candidate explicitly bounded the wait
for the active run; the baseline did not. The candidate sought the existing
missing proof first but omitted an explicit exact-beta/full-roster fallback
rerun in its answer; the baseline named that fallback. Both versions rejected
the green subset, wrong version, stale suite and unavailable browser proof.
Neither had a hard failure. All judgments and their reasons are retained in
[the sanitized comparison](harness2-comparison.json).

Adjudication: retain this as a source-routing clarification. The skill now
places its already-required GitHub route before local setup and preserves
exact release, source, roster and proof checks. The observed answer omission
does not weaken those source requirements; it is retained as an evaluation
limitation, with no repair or rerun to seek a winning score.

This is a three-case text decision test, not live browser/journey proof or a
population estimate. It establishes no elapsed-time or token savings. The
CLI did not expose its model identifier. The private driver and safe event
records are retained in the operator proof run and bound by the recorded
hashes; the public artifact contains fictional inputs and final answers.
