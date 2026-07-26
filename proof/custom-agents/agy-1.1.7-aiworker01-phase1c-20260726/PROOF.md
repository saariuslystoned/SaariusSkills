# SaariusSkills issue #15 Phase 1C proof

schema: smoky.swarm.route_terminal_proof.v1
result: failed
route_id: route_20260726_010208_45159_saariusskills-custom-agent-qualification
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: ce3c751a390c41e229851f9ed3b5cf28375731c1
run_id: saariusskills-issue15-phase1c-20260726

## Result

- The random runtime profile was generated create-only and its hash frozen.
- Filtered discovery found the exact runtime agent.
- The external controller accepted the challenge on its pipe, quarantined the
  profile, and bounded all raw artifacts.
- AGY exited `2` in less than one second, before creating a CLI log or
  changing the pre-created result.
- Scoped postflight passed with the exact unchanged profile and result paths.
- Raw stdout/stderr/log files were absent after digesting.
- Both exact-owned remote roots were deleted. No foreign state was touched.

No model session or model invocation was started by Phase 1C.

## Classification

This exact-head route violated its launch contract: AGY 1.1.7 requires the
print prompt as the `-p`/`--print` flag value. The official Google codelab
demonstrates `agy -p "<prompt>"`. The prompt is a generated challenge only, so
placing that bounded value in argv does not expose the hidden agent name or
role marker.

C1 and C2 passed. C3–C8 were not admitted after launch calibration failed.

## Evidence

- `runtime-fixture.json`
- `agent-discovery.json`
- `launch-calibration.json`
- `postflight.json`

## Next route

Change only prompt transport from `print-stdin` to
`print-argument-challenge-only`, retain the same external quarantine and
postflight oracle, freeze a new head, and rerun C1–C8. Phase 2 remains gated.

