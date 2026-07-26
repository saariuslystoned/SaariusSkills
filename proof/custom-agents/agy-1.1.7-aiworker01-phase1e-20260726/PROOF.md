# SaariusSkills issue #15 Phase 1E guard proof

schema: smoky.swarm.route_terminal_proof.v1
result: passed
route_id: route_20260726_013330_53752_saariusskills-custom-agent-guard
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: 65f09f8625499de95b6f8d8e9ccbfee2bcec131b
run_id: saariusskills-issue15-phase1e-20260726

## Result

The discovery-gated selection surface passed:

- absent requested name with one unrelated valid catalog profile:
  exact-name count `0`, guarded exit `2`, model launch `false`, result unchanged;
- duplicate declared name in two byte-identical profiles:
  exact-name count `2`, guarded exit `2`, model launch `false`, result unchanged;
- one exact `subagent: false` profile:
  exact-name count `1`, admitted, one fresh model launch, runtime exit `0`,
  result changed after quarantine, exact identity verified, scoped postflight
  passed.

The two rejected controls created no quarantine or raw process artifact and
left every profile hash and zero-byte result unchanged. Discovery stdout and
stderr were held only in controller memory long enough to record bounded
counts and SHA-256 digests.

## Evidence composition

This route does not rewrite the Phase 1D failure. Raw direct
`agy --agent <absent-name>` remains unqualified because it produced a
nonqualifying structured fallback when another profile existed.

The qualified surface is `guarded-run-print`, which admits only exactly one
workspace discovery occurrence before calling the unchanged Phase 1D runtime
oracle. Its fingerprint binds:

- frozen guard source head:
  `65f09f8625499de95b6f8d8e9ccbfee2bcec131b`;
- executed harness SHA-256:
  `3d0f4ec11f0d6d5d1f60663e43946e073d96f868896b06ed71b1600994e8f0ee`;
- Phase 1D proof commit:
  `b2e7dbab204408b7933dcc66df9e74cefedd9063`;
- unchanged AGY `1.1.7` binary, worker, model, sandbox, prompt transport,
  isolation, and four definition hashes.

Phase 1D remains the four-role diversity proof. Phase 1E adds the deterministic
preflight and one live positive delegation proof.

## Teamwork Preview conclusion

Teamwork Preview is not required for the qualified ordinary custom-agent
surface. The positive guard profile explicitly set `subagent: false` and still
passed exact primary discovery and execution. This qualifies primary custom
agents, not nested fan-out.

## Evidence

- `capability-fingerprint.json`
- `guard-evidence.json`
- `behavior-report.json`
- predecessor:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase1d-20260726/PROOF.md`

## Verification and budget

- repository suite at the frozen source head: `72` tests passed;
- negative live guard invocations: `2`, both no-model;
- positive live guard sessions: `1 / 1`;
- issue-level Phase 1 model sessions: `8 / 8`;
- timeouts: `0`;
- raw transcript/catalog/process content retained: `false`;
- foreign state touched: `false`.

After the packet was committed locally, the exact Phase 1E controller and
workspace roots were removed from `aiworker-01` and both paths were verified
absent. Cleanup covered 8 controlled files totaling 56 KiB. No predecessor
root or foreign state was touched.

The proof commit adds only evidence plus the previously omitted optional
fingerprint fields for the harness hash and predecessor proof commit. The
executed source head and copied harness remain exactly the values above.

## Next gate

Guarded ordinary selection is qualified and may feed a separately admitted
2x2 fan-out route with its own bounded budget and behavior contract. Nested
delegation, joins, retries, timeouts, 4x4 reliability, Puppet transport, and
product value remain unproven until those later routes pass.
