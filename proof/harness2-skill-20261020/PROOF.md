# Harness² skill clarification proof

Status: bounded clarification pass complete; no final forward retest is
claimed.

## Preserved first attempt

The independent Grok forward evaluation tested source `8832bc315e923b12bb64a0ac41cc4953ad67707b` and
handled six of eight scenarios cleanly:

- clean: `auth_expired`, `product_preference`, `duplicate_trial`,
  `vague_optimization`, `higher_judge_failed_check`, `judge_unavailable`;
- clarification required: `handoff_repeat`, `blocked_protocol`.

The first-attempt private cases, responses, and parent assessment remain
preserved outside this repository. This public record contains no private
filesystem paths, secrets, host identifiers, or unfiltered transcripts.

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
