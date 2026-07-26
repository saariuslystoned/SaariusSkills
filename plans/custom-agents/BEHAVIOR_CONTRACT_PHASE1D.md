# Behavior contract: documented print-argument identity oracle

Version: `2026-07-26.phase1d`

## Normative contract

`BEHAVIOR_CONTRACT_PHASE1C.md` remains normative in full except for the prompt
transport override below.

The Phase 1C exact head remains failed: it invoked a bare `--print`, AGY exited
`2` before model use, the result remained unchanged, and external postflight
passed.

## Prompt transport override

AGY 1.1.7 receives the prompt as the value of its documented print flag:

```text
agy ... --print "<challenge-only prompt>"
```

The value is limited to:

```text
Identity calibration challenge: <random-safe-token>. Follow the active
profile's calibration contract.
```

The argument contains no agent name, role marker, result schema, result path,
plugin name, harness path, credential, account data, product data, or user
content. The controller records its SHA-256, never its text. It exists in the
exact owned AGY child argv only for that bounded process lifetime.

All hidden-identity properties remain unchanged:

- the unpredictable agent name and role marker exist only in the runtime
  profile and controller control record;
- the profile is quarantined 350 ms after launch and before any qualifying
  result mutation;
- the selected agent exposes only `write_to_file`;
- the result must change after quarantine;
- exact result validation and complete scoped filesystem postflight remain
  mandatory;
- raw stdout, stderr, and CLI log content remains unobserved and is
  digest-then-unlinked.

## C1–C8, budget, and gates

C1–C8, the four positive roles, negative controls, seven-session ceiling,
fourteen-invocation ceiling, deadlines, cleanup requirements, and Phase 2 gate
are identical to Phase 1C.

Phase 1C consumed no model session, so the issue-level budget remains one
session used and seven available.

