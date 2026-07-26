# SaariusSkills issue #15 Phase 3 4x4 proof

schema: smoky.swarm.route_terminal_proof.v1
result: failed
route_id: route_20260726_020509_62287_saariusskills-custom-agent-4x4
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: 479e7e5d891e8eee18b78a7602ff1e7898dbba0c
run_id: saariusskills-issue15-phase3-4x4-20260726

## Result

The first guarded width-four round exposed a strict coordination failure and
stopped the campaign.

Round A passed every structural runtime gate:

- exact parent discovery count `1`;
- four custom child result files became non-empty before profile quarantine;
- every child file matched its controller-held agent, challenge, schema,
  status, and hidden marker;
- the parent join remained empty until the controller released its OS lock;
- the join changed afterward and its mtime followed all four child files;
- all five profile hashes and the exact five-file workspace inventory passed
  postflight;
- the parent process exited `0` without timeout or raw retention.

Strict semantic verification failed. The parent join used four newly invented
role markers rather than the four markers in the qualifying child artifacts:

| Side | Child artifact marker | Parent join marker |
| --- | --- | --- |
| alpha | `alpha4-a8af5d8c23df9046` | `alpha-role-38416d860d5b4a92` |
| beta | `beta4-3817384f02e85890` | `beta-role-53b92d6e46ff8522` |
| gamma | `gamma4-7e3962c91f3a9b1c` | `gamma-role-b51f0c29f60a221f` |
| delta | `delta4-10f7edc3627e0924` | `delta-role-ffae45759ef17eb9` |

The exact join otherwise named the correct parent, challenge, children, order,
schema, and status. `success-a-mismatch.json` classifies all four child files
as correct and all four join-to-child marker comparisons as false.

This is not a race or fixture mismatch. It is a source-grounding failure
between successful child artifacts and parent coordination. Functional
width-four joining is not qualified under this fingerprint.

## Gate outcome

The contract required four-of-four successful rounds before any containment
control. The first strict failure therefore blocked:

- success rounds B, C, and D;
- join-permission denial;
- malformed delta-child containment;
- watchdog termination.

Only one parent process and four declared child branches launched. No model
launched after the failure. The unexecuted workspaces remained at their
zero-byte fixture state.

This preserves the Phase 2 result: functional two-child fan-out and join passed
two of two rounds at proof commit
`c71206a3e6a2fad71119ee8d53d06651aee1cbc5`. It does not generalize that
result to width four.

## Teamwork Preview and PR #6

The round used ordinary `invoke_subagent` custom profiles only. Teamwork
Preview and Puppet were not invoked, installed, or depended on. PR #6 remains
unchanged historical research at
`baea84b2bb0d21ff749ce65d077a76cc76f2e1de`.

The failure is not evidence that Teamwork Preview is required. It is evidence
that ordinary width-four coordination needs stronger grounding before it can
be packaged as a reusable skill, plugin, or Puppet adapter.

## Evidence

- `capability-fingerprint.json`
- `behavior-report.json`
- `runtime-preflight.json`
- `fixture-comparison.json`
- `success-a-fixture.json`
- `success-a-runtime.json`
- `success-a-verification.json`
- `success-a-postflight.json`
- `success-a-observed-join.json`
- `success-a-mismatch.json`
- prepared but unexecuted fixture reports for rounds B–D and the three
  containment controls
- `campaign-stop.json`
- `cleanup.json`
- `STATE.md`
- `events.jsonl`

The executed harness SHA-256 was
`3e268b58ca59a29eef558252c4423ade9b5c64a01ba62db11ee45ad6c9e073c5`.
It is the exact `fanout4_harness.py` copy from source head
`479e7e5d891e8eee18b78a7602ff1e7898dbba0c`.

## Verification and budget

The frozen source passed:

```text
python3 -m py_compile plans/custom-agents/scripts/fanout4_harness.py
python3 -m unittest tests.test_custom_agent_fanout4_harness -v
python3 -m unittest discover -s tests -v
```

Result: `79` repository tests passed.

- parent CLI processes: `1 / 7`;
- declared nested child branches: `4 / 28`;
- maximum agent sessions: `5 / 35`;
- strict successful rounds: `0 / 4`;
- additional model launches after failure: `0`;
- observed round duration: approximately `8.1` seconds;
- timeouts: `0`;
- raw stdout/stderr/log content retained: `false`;
- foreign state touched: `false`.

## Cleanup

After bounded reports and the 641-byte intended join artifact were copied,
eight exact remote roots were inventoried as `87` files, `79` directories,
`0` symlinks, `0` special files, and `266310` bytes. Six unexecuted workspaces
still had only zero-byte results. All eight disposable roots were removed and
verified absent. The deletion is not recoverable; committed reports retain the
bounded evidence.

## Disposition

Do not promote ordinary custom agents as a general width-four orchestration
plugin from this evidence. Preserve Phase 2 as a qualified width-two research
primitive and Phase 3 as a width-four counterexample.

Before another promotion attempt, choose one narrow next hypothesis:

1. a stricter child-return/parent-copy contract in a single calibration round;
2. an independently observable structured return channel;
3. a product-specific width-two probe that does not claim width-four
   reliability.

The frozen Phase 3 contract itself does not admit product comparisons or
containment sessions after this failure.
