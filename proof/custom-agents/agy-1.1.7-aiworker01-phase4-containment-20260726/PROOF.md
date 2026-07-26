# SaariusSkills issue #15 Phase 4 containment proof

schema: smoky.swarm.route_terminal_proof.v1
result: passed
route_id: route_20260726_021410_64760_saariusskills-custom-agent-containment
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: 44fae4dea019a1f205e0a43a9978ff2b80a4839d
run_id: saariusskills-issue15-phase4-containment-20260726

## Result

All three characterization-only controls passed:

### Denied join

- exact parent discovery count `1`;
- four grounded child artifacts before profile quarantine;
- the join was never unlocked and remained zero bytes;
- the parent terminated with exit `0` without a watchdog;
- exact five-profile and five-result postflight passed.

This proves the OS permission boundary contained the join. The parent profile
requested one retry after a denied write, but no transcript or tool trace was
retained. Attempted-write count is therefore not observed or claimed.

### Malformed child

- alpha, beta, and gamma produced exact grounded artifacts;
- the delta-only fault profile returned a non-qualifying response and left its
  result at zero bytes;
- the parent wrote no join and terminated with exit `0`;
- exact fault-profile hash and scoped postflight passed.

This proves one malformed child prevented a joined result without suppressing
the three valid sibling artifacts.

### Watchdog

- exact parent discovery count `1`;
- the one-second child deadline fired before any child artifact;
- the controller terminated the exact process group;
- the process exited `1`;
- all four child files and the locked join remained zero bytes;
- raw artifacts were digested and unlinked;
- exact five-profile and five-result postflight passed.

This proves bounded controller termination and zero-join containment.

## Scope boundary

This route did not rerun or repair successful width-four joining. Phase 3
remains failed because its parent join substituted all four child markers.
Passing containment does not qualify width-four success or admit product
promotion.

Teamwork Preview and Puppet were not invoked, installed, or depended on.
PR #6 remains unchanged historical research at
`baea84b2bb0d21ff749ce65d077a76cc76f2e1de`.

## Evidence

- `capability-fingerprint.json`
- `behavior-report.json`
- `runtime-preflight.json`
- `fixture-comparison.json`
- `control-summary.json`
- `deny-join-fixture.json`
- `deny-join-runtime.json`
- `deny-join-verification.json`
- `deny-join-postflight.json`
- `child-failure-fixture.json`
- `child-failure-runtime.json`
- `child-failure-verification.json`
- `child-failure-postflight.json`
- `watchdog-fixture.json`
- `watchdog-runtime.json`
- `watchdog-verification.json`
- `watchdog-postflight.json`
- `cleanup.json`
- `STATE.md`
- `events.jsonl`

The executed harness SHA-256 was
`3e268b58ca59a29eef558252c4423ade9b5c64a01ba62db11ee45ad6c9e073c5`.
It is the exact `fanout4_harness.py` copy referenced by source head
`44fae4dea019a1f205e0a43a9978ff2b80a4839d`.

## Verification and budget

The frozen source passed:

```text
python3 -m py_compile plans/custom-agents/scripts/fanout4_harness.py
python3 -m unittest tests.test_custom_agent_fanout4_harness -v
python3 -m unittest discover -s tests -v
```

Result: `79` repository tests passed.

- parent CLI processes: `3 / 3`;
- declared nested child branches: `12 / 12`;
- maximum agent sessions: `15 / 15`;
- containment controls: `3 / 3`;
- observed process durations: approximately `13.9`, `9.5`, and `1.0`
  seconds;
- unexpected timeouts: `0`;
- intentional watchdog deadlines: `1 / 1`;
- raw stdout/stderr/log content retained: `false`;
- foreign state touched: `false`.

## Cleanup

After all twelve bounded reports were copied, four exact remote roots were
inventoried as `47` files, `35` directories, `0` symlinks, `0` special files,
and `237079` bytes. All four disposable roots were removed and verified
absent. The deletion is not recoverable; committed reports retain the bounded
evidence.

## Disposition

Keep the result split:

- width-two functional fan-out/join: qualified by Phase 2;
- width-four child execution plus semantic join: failed by Phase 3;
- width-four denial, malformed-child, and watchdog containment:
  characterized as passing here;
- retry-attempt count: unobserved;
- general reusable orchestration plugin: not justified;
- Teamwork Preview dependency: not required by any qualified or containment
  surface.

A product comparison requires a new explicit decision about whether the
qualified width-two primitive is independently useful despite the width-four
promotion failure.
