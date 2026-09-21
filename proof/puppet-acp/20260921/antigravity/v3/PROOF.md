# Antigravity live-driver v3 repair proof

Status: `OFFLINE_LIFECYCLE_REPAIR_STAGED_NOT_RUN`.

This is one bounded task-only lifecycle repair over v2. Product source was
not edited. No official Antigravity provider turn was authorized or launched.
v1/v2 and historical job `2ac39aae` remain untouched.

## Frozen inputs

```text
HEAD   d5e33f67f6b42384f6feec1d15be3b69b4525eb8
TREE   938ef948a6a1218ad055a17d5d297c633b936167
BRANCH codex/puppet-antigravity-controller-proof-20260921
route  antigravity-acp
model  gemini-3.8-flash-high
effort unset
```

Product `skills/`, `bridge/`, `tests/`, and package manifests are unchanged.

## v3 hashes

| path | SHA-256 |
| --- | --- |
| `runs/puppet-controller-proof-runs/20260921/v3/driver/agy_live_capable_proof_driver.py` | `1bf2c9b22be3561f0e3461edc8b191e61de8e1067aa20cbbeb48c6e7d0a89ba8` |
| `runs/puppet-controller-proof-runs/20260921/v3/tests/test_agy_live_capable_proof_driver.py` | `00e5a7ea624ab19ecb9ece3702bfa9bb2bcfd58123c98a8b69ac74912a50ed93` |
| `runs/puppet-controller-proof-runs/20260921/v3/staged/live-invocation.json` | `949ee8ce35619f46cc9ea2d86296281ca27bde9b8985fc6a5dbe395a44f766cf` |
| `runs/puppet-controller-proof-runs/20260921/v3/staged/launch-input.contract.json` | `b78a5b1d3d1d30811e92eba331712fa52e3135474436f819f8b7be5d399d484c` |

Preserved v2 identities, not rewritten:

```text
v2 driver 04575383754a61c6ba938de1bd66f8a7aae442e14dd8d70349ba44efd851d2fe
v2 tests  fcc142b9c1dfb2bf65ae6bf78d5085912b27743cbad33be022ab173114ea864e
v2 launch-input b78a5b1d3d1d30811e92eba331712fa52e3135474436f819f8b7be5d399d484c
```

## Lifecycle delta

- Helper PID remains `runtime.child_process_identity` / `node_driver_helper` only.
- Actual owned backend incarnation is captured with PID, PPID, executable
  name, and start/birth identity. No argv, env, or secrets.
- After canonical `owner.finish`, that same incarnation is re-observed.
  Helper exit never counts as backend proof.
- Real post-finish observation is fed into `accept_unsupported_backend_discard`.
- Unsupported-close plus an actual owned `localharness_external` peer exit is
  accepted. That local peer is not an AGY backend claim.
- Unknown or surviving backend writes a durable fence with owner/continuation
  identity, retains fixture/state, blocks replacement, and keeps the primary
  error. A generic `node` child is not labeled as an AGY backend.
- First turn is `_antigravity_acp_structured_launch.require_observation`.
  `owner.next_turn` is a same-owner continuation, not automatically first task.
- Existing product runtime cap remains 30000ms from
  `controller-runtime-driver.mjs`. No timeout feature was added.
- Product `live_antigravity_acp_claimed:false` remains candidate-only.

## Offline commands and results

```text
PYTHONDONTWRITEBYTECODE=1 python3 runs/puppet-controller-proof-runs/20260921/v3/tests/test_agy_live_capable_proof_driver.py -v
Ran 14 tests in 21.411s
OK

python3 -m unittest tests.test_puppet_antigravity_acp_runtime.AntigravityAcpRuntimeControllerTests.test_default_consumer_owner_lifecycle_uses_public_runtime_and_synthetic_peer
Ran 1 test in 2.802s
OK

--mode lifecycle                         exit 0; offline synthetic; two turns; helper 15504 exited; backend unobserved; accept=false; fence=null; first_turn=require_observation
--mode fixture-baseline                  1 pass / 1 expected missing --check failure; tree 3f34ef57c245222c998be421dc9aaec998e47c18
--mode fixture-after                     2 passes; OK/NON_NORMALIZED; exact {bin/normalize-lines.mjs}
--mode reject-live                       exit 2
--live --mode lifecycle                  exit 2; missing launch-input rejected before process start
unsupported-close + owned local peer     accepted; backend_discard=unsupported_local_cleanup_proved; terminated; no fence
unknown/surviving backend                fenced; primary retained; replacement blocked
```

## Official live path: staged but not run

Exact command, not executed:

```text
/opt/homebrew/opt/python@3.14/bin/python3.14 \
  /Users/bobbybones/Developer/worktrees/puppet-antigravity-controller-proof-20260921/runs/puppet-controller-proof-runs/20260921/v2/driver/agy_live_capable_proof_driver.py \
  --live \
  --launch-input \
  /Users/bobbybones/Developer/worktrees/puppet-antigravity-controller-proof-20260921/runs/puppet-controller-proof-runs/20260921/v2/staged/launch-input.contract.json \
  --mode lifecycle
```

## Cleanup

- Task-owned helper `15504` started and later exited; death was not inferred
  from driver exit.
- Owned local `localharness_external` peers used only in offline tests exited
  via sentinel stop, not a broad process kill.
- No leftover `controller-runtime-driver.mjs`, `candidate-peer.mjs`, or
  `localharness_external`.
- Proved-finish disposable `v3/workspaces` and `v3/state` removed after
  cleanup was known; staged receipts retained.
- Driver/test `__pycache__` removed.
- v1/v2 and historical job `2ac39aae` were not touched.

## Remaining live blocker

This is not live AGY acceptance. Official useful-edit proof remains pending
parent release of the already-authorized one-session / two-prompt
`<=300000ms` staged command. No merge, default availability, or production
claim.
