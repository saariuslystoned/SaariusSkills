# Affirmative recommendation-question wording

## Source and bounded change

- Repository: `saariuslystoned/SaariusSkills`
- Branch: `codex/grilltrack-affirmative-20261020`
- Base: `08be4a68150b826f05c427726f31cd2373776f52`
- Changed instruction: `skills/grilltrack/references/protocol.md`, in the
  existing Grill paragraph. When a question recommends a direction, its
  affirmative answer clearly accepts that direction.
- Exact upstream influence:
  [Matt Pocock grilling skill at 5beb35b](https://github.com/mattpocock/skills/blob/5beb35b040e3de97e54fa9e386d7e42d15c295c2/skills/productivity/grilling/SKILL.md),
  read at that revision. Only the recommendation-question wording rule is
  borrowed; both existing third-party notice copies record the narrow credit.

The neutral visual-choice rules, existing shared-understanding confirmation,
and separate delivery authority remain unchanged. No rule was added to the
root skill, and no new confirmation stage, cadence, or picker behavior was
introduced.

## Validation

- Quick skill validation: passed; [output](skill-validation.log).
- Existing `tests.test_packaging.PackagingTests.test_legal_copies_match`:
  passed; [output](packaging-test.log). The notices remain identical.
- Local links, unchanged root skill/workflow boundary files, assigned scope,
  proof privacy, and diff whitespace: [checks](scope-and-links.log).
- The full unchanged suite was not rerun, and no wording-matching test was
  added.

This is source/provenance proof only. No live or model behavior evaluation,
installation, push, PR, merge, or review trigger was performed by this worker.
The coordinator owns the separate blind behavior tests. No private transcript
or raw evaluation fixture is included here.

## Paired behavior check

The coordinator ran a fixed two-task comparison using the actual Harness2
`BenchmarkAdapter` and `core.judge.judge_one` APIs at upstream commit
`1cfe254e8d25b15f37048c3730134686abe60335`. A private custom backend used the
installed Codex CLI 0.161.0 through its existing ChatGPT session, with read-only
sandboxing, ephemeral sessions, the same argv/context, and no tools observed.
This was not the built-in Responses executor or full recursive optimization.
No package install, API credential setup, or production operation was needed.

[Evaluation evidence](evaluation.json) contains both synthetic task contexts,
all four agent-authored outputs, hashes, safe usage/timing, and each blinded
criterion judgment. Criteria were frozen before any output. Variant identity
and source diff were withheld from the judge. The private original conversation
records and evaluator runtime paths are not published.

| Check | Baseline | Candidate |
| --- | --- | --- |
| Two-task live comparison | 6/7 criteria | 7/7 criteria |
| Avoidable clarifications in those outputs | 1 | 0 |
| Unsupported authority expansion | 0 | 0 |
| Separate five-case response probes | 14/14 criteria | 14/14 criteria |

The observed difference is narrow: for admin-only setup, the baseline asked
whether to pause or allow a developer fallback; the candidate asked directly
whether to adopt the recommended admin-only requirement. Both preserved the
unproved feasibility boundary. The separate Save case preserved the existing
overall-summary confirmation instead of reopening the settled yes.

All four new solver calls completed without retries, within a 120-second limit
per call (27.374 seconds aggregate). Model identity was not exposed by the CLI;
no exact-model, population-level, latency, or token-saving claim is made. The
five-case probes tied, so they establish only no observed regression in those
responses. This is evidence for one explicit wording rule, not a claim that
GrillTrack has been broadly optimized.

The source instruction tested is commit `17b63f34769e52d9cd820cc30a97a811a42d35fb`.
The subsequent proof-only commit adds this report and JSON; the skill bytes
remain unchanged. No installed skill copy, product ledger, or runtime changed.
