# Antigravity failure-receipt v4 proof

Status: `OFFLINE_FAILURE_RECEIPT_REPAIR_COMPLETE`. Canonical implementation
result: `completed/end_turn`. This is one bounded proof-artifact repair over
v3. Product source, pins, ordinary availability, and v3 bytes are unchanged.
No official Antigravity provider turn was authorized or launched.

## Frozen identities

```text
frozen execution HEAD d5e33f67f6b42384f6feec1d15be3b69b4525eb8
frozen execution TREE 938ef948a6a1218ad055a17d5d297c633b936167
publication HEAD      18c438a058407ef08bfc02e8397f039eb8ae0ff6
route                 antigravity-acp
model                 gemini-3.8-flash-high
effort                unset
acpx commit           2e05de525dd1ab62e9e74bf02d91e3638920fcf3
acpx artifact         5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614
runtime.js            ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683
```

Implementation job `12791074-59c9-454e-a446-6ca5c7d14214`, native Cursor ACP,
exact Grok 4.6 High, timeout 600000ms. No AGY provider job.

## v4 authored hashes

| path | SHA-256 |
| --- | --- |
| `v4/driver/agy_live_capable_proof_driver.py` | `bf5fda87ff9dbfb001bd4603662e00b52c25e75fdd5c63b511c7db17b00176b5` |
| `v4/tests/test_agy_live_capable_proof_driver.py` | `242d3cc965b4d842edb4b3e99e5e39dba02179fa1ac953d2b1a5575638e17c75` |
| `v4/staged/live-invocation.json` | `4b2713cd6e64afda6023f97eee86c2b0c9572fd3e4b013c2e71a5a8766cc7d60` |
| `v4/staged/launch-input.contract.json` | `0b0bb275478a24aad9d929548818eb5cf3a577b7109c050900d3ea3fb5119859` |
| `v4/.gitignore` | `c603c47175aa05ae21cd0218309ab9bb204db9485119efcd95df1beed793851b` |

Preserved v3 identities, not rewritten:

```text
v3 driver 1bf2c9b22be3561f0e3461edc8b191e61de8e1067aa20cbbeb48c6e7d0a89ba8
v3 tests  00e5a7ea624ab19ecb9ece3702bfa9bb2bcfd58123c98a8b69ac74912a50ed93
v3 invocation 949ee8ce35619f46cc9ea2d86296281ca27bde9b8985fc6a5dbe395a44f766cf
v3 launch-input b78a5b1d3d1d30811e92eba331712fa52e3135474436f819f8b7be5d399d484c
v3 STATE  fdfc9d4bf38a0f2b8a9a2a5495fe2c5cb1a61eb674dc1325c8d0bff9e665b336
v3 PROOF  8cca51695d3e1bb883fb354b94be4dfed4b51b743c953223b59a8b3a87923c19
```

## Repair delta

- Ordinary public-runtime + local synthetic-peer fixture failure now persists a
  fresh allowlisted body-free receipt. The v3 fixture assertion no longer sits
  outside the evidence path.
- Receipt captures incrementally available route/source/artifact identities,
  requested and observed model, first/second request IDs and stop reasons,
  same-owner continuation, owner.finish result, backend incarnation and
  matched post-finish termination, and independent fixture outcome. Missing
  observations stay `unknown`.
- Primary and cleanup errors stay separate. Fixture failure remains nonzero,
  cannot become PASS, and cannot imply a provider was never contacted.
- Fresh receipt destination on every run; overwrite of an existing receipt or
  any v3 path is rejected.
- Failure before owner/handle exists still writes a receipt with unknowns and
  cleanup uncertainty. Existing owned cleanup/fences remain; no broad process
  kill.
- Live mode cannot invoke `apply_intended_implementation`. Legitimate identical
  bytes are no longer rejected merely by hash equality. Independent
  changed-path / protected-file / test checks still run.
- Staged invocation names the exact v4 driver and v4 contract. The old
  v3-to-v2 command remains historical/quarantined and was not executed.

## Offline commands and results

```text
PYTHONDONTWRITEBYTECODE=1 python3 proof/puppet-acp/20260921/antigravity/v4/tests/test_agy_live_capable_proof_driver.py -v
Ran 18 tests in 37.430s
OK

--mode reject-live                       exit 2; live turn not authorized
--mode fixture-baseline                  1 pass / 1 expected missing --check; tree 3f34ef57c245222c998be421dc9aaec998e47c18
--mode fixture-after                     2 passes; OK/NON_NORMALIZED; exact {bin/normalize-lines.mjs}
--mode ordinary-fixture-failure          exit 2; see receipt below
--live --mode lifecycle                  exit 2; missing launch-input rejected before process start
--mode stage-live                        executed=false; v4 driver + v4 contract only
```

## Ordinary failure receipt

Command used the pinned public runtime and local synthetic peer, not an
injected special-exception branch. Host known-answer was not applied.

```text
exit 2
ok=false live=false live_claimed=false qualifying_pass=false
mode=ordinary_fixture_failure
runtime_contacted=true official_agy_provider_contacted=false
provider_never_contacted_implied=false synthetic_peer_used=true
requested/observed model=gemini-3.8-flash-high effort=unset
first request=agy-proof-v4-offline-turn-1 stop=end_turn
second request=agy-proof-v4-offline-turn-2 stop=end_turn
same_owner_continuation=true owner_handle_existed=true
finish final_discard=true backend_discard=closed cleanup_fence=null
backend after finish unmatched/unobserved; helper exit not backend proof
fixture independent fail; bin absent; changed_paths=[]
primary=ValidationError fixture after tests did not pass independently
cleanup_error=null
body sentinels absent
receipt schema=puppet.antigravity-failure-receipt/v4
receipt file=v4/receipts/receipt-20260921T162629-51db4f975123.json
receipt sha256=aaab6bc707bd2ca3a1f5821ca2207d2cf720d01edc276b6e4145cc87637bfb86
fresh_destination=true overwrote=false
```

Generated receipt/state/workspace bytes stay under v4 gitignore or task-owned
runs. No prompt, model-output, tool body, credential, config, env, or argv
fields were persisted.

## Remaining limits

This is not live AGY acceptance. Useful-edit ability remains unproven. Both
previous live attempts remain consumed. This packet authorizes zero new
candidate provider turns. Independent review of this v4 delta is required
before any new one-session proof is considered.
