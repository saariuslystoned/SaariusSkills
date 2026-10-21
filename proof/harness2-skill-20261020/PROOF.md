# Harness² skill clarification proof

Status: clarification and targeted forward recheck complete. This is skill
routing evidence; it does not establish product-performance improvement.

## Preserved first attempt

The independent Grok forward evaluation tested source `8832bc315e923b12bb64a0ac41cc4953ad67707b` and
handled six of eight scenarios cleanly:

- clean: `auth_expired`, `product_preference`, `duplicate_trial`,
  `vague_optimization`, `higher_judge_failed_check`, `judge_unavailable`;
- clarification required: `handoff_repeat`, `blocked_protocol`.

Complete private execution records remain outside this repository. Curated
case inputs and resulting decisions are included here for inspection, without
private filesystem paths, secrets, host identifiers, or unfiltered transcripts.

## Clarifications applied

- Immutable sections are preserved and must not be modified or overridden;
  mandatory policy is kept in authoritative sources.
- Authorized private execution packets may contain minimal routing IDs and
  sanitized excerpts actually needed for execution. Secrets and unfiltered
  transcripts remain prohibited; public/hosted evidence minimizes private
  identifiers.
- If Jev is unavailable, an explicitly labeled independent manual evaluation
  using the same fixed criteria is allowed. Jev is not a new delivery gate;
  without comparative evidence the result remains inconclusive.
- An inline H2 experiment still requires a qualified runtime and the complete
  bounded loop. Ordinary authorized repair may proceed separately and must not
  be represented as Harness² evidence.

## Verification

Actual repository test run:

```text
python3 -m unittest tests.test_packaging tests.test_portable_skills
..............................
----------------------------------------------------------------------
Ran 30 tests in 0.383s

OK
```

Result: 30 passed, 0 failed.

## Independent forward recheck

Grok 4.7 evaluated the corrected skill at `d78d27bde803ef3bc11f23113b8cd7d3d596a30f` in a separate frozen workspace. All three narrow cases behaved as intended: a qualified blocking experiment stays a full inline loop; independent manual evidence can support a source PR when Jev is unavailable; and the A/B mapping stays outside Jev input. These are simulated planning cases, not real product completion or a population estimate.

The later packaging-only repair left the tested skill files unchanged. Initial cases and responses are in `initial-evaluation.json`; recheck inputs/results are in `recheck-cases.json` and `recheck-responses.json`. Earlier failures remain visible. No model result was regenerated to obtain a favorable score.

Both targeted packaging and portable-profile modules now pass: 30 tests, zero failures. The temporary portable test failure was introduced by adding this new general skill to the list of eight profile-compatible migrated cores; it was corrected by removing that misclassification. It was not a pre-existing failure. The full local suite is tracked separately; this document does not claim an unobserved result.

## Independent review correction

The independent review of `18575495a1acc10112cff283e61a440c1aab7b8b`
identified one accepted P2: including hypothesis wording in the deduplication
key could automatically launch another experiment for an already-owned
failure. The skill and packet now deduplicate the same task/source/failure
regardless of hypothesis wording. Alternative hypotheses are candidates in
the same bounded experiment. A completed failure requires material new
evidence or source and an explicitly admitted remaining budget to restart.

This is a narrow instruction correction. The 30 targeted packaging and
portable-profile tests pass under Python 3.12.9, and `git diff --check` passes.
No model-backed forward case was rerun; the prior forward-recheck results
remain evidence for their recorded revision, not a claim about this edit.

## Executor limits and manual-evaluation clarification

Comprehensive review of `e18ab6d879268d1d6a5c4ddea598e93ef21678be`
identified two accepted instruction gaps. The skill and packet now explicitly
reject upstream unrestricted executor defaults on ordinary/private workspaces
and require demonstrated effective filesystem/sandbox and egress limits with
isolated task copies and inaccessible held-out material. AI Shed response-only
event rejection is explicitly not isolation proof; unproven qualification
blocks the experiment while independent product work continues.

Source fidelity: pinned upstream `1cfe254e8d25b15f37048c3730134686abe60335`
README, Web access section, states unrestricted network access and disabled
Codex sandboxing; `harness2/substrate/codex.py` includes the approval/sandbox
and hook-trust bypass flags. This clarification changes no runtime capability
or readiness claim.

Independent manual fallback now explicitly uses the same blinded, neutral A/B
evidence and fixed criteria, excludes arm identity and optimizer preference,
and maps the answer only in the record. All existing dedupe, budget, authority,
and hard-check rules remain intact. The 30 targeted packaging/portable tests
and diff check pass under Python 3.12.9. No new model experiment was run.
