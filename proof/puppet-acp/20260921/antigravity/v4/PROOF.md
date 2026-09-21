# Antigravity failure-receipt v4 proof

Status: `BIRTH_MARKER_GUARD_REPAIR_COMPLETE`. Canonical implementation result:
`completed/end_turn`, with `taskComplete=true` and `cleanupReady=true`. This is
one bounded birth-marker guard repair on the existing v4 artifact. Product
source, pins, ordinary availability, v3 bytes, the successful native pilot,
and earlier receipt bytes are unchanged. No Puppet candidate qualification
turn was authorized or launched.

## Frozen identities

```text
frozen execution HEAD d5e33f67f6b42384f6feec1d15be3b69b4525eb8
frozen execution TREE 938ef948a6a1218ad055a17d5d297c633b936167
publication baseline  18c438a058407ef08bfc02e8397f039eb8ae0ff6
                      (pre-v4 publication tree; not current HEAD)
route                 antigravity-acp
model                 gemini-3.8-flash-high
effort                unset
acpx commit           2e05de525dd1ab62e9e74bf02d91e3638920fcf3
acpx artifact         5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614
runtime.js            ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683
```

Initial receipt-repair job `12791074-59c9-454e-a446-6ca5c7d14214` and bounded
cleanup-repair job `39633833-5036-4d16-b8bf-6d7d27d33b10` used native Cursor
ACP, exact Grok 4.6 High, timeout 600000ms. The follow-up birth-marker guard
job `2c7e313d-5c52-4571-b188-de772d627bf5` used native Antigravity ACP,
exact `gemini-3.8-flash-high`, effort unset, and timeout 300000ms. It completed
with `taskComplete=true` and `cleanupReady=true`. No Cursor fallback, direct
CLI, or candidate qualification turn was used for this follow-up.

## v4 authored hashes

| path | SHA-256 |
| --- | --- |
| `v4/driver/agy_live_capable_proof_driver.py` | `39d5c6e78bcfce79603e317246723e9342e87d83898e45639fcbc4b301398c01` |
| `v4/tests/test_agy_live_capable_proof_driver.py` | `c74ff122ec1db5a278b096fdda19e77219ad3f3bc6f4cee13cdbd0ea17853729` |
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
- Official/live or otherwise provider-capable missing or unobservable backend
  cleanup now sets `cleanup_uncertain` and writes the existing
  replacement-blocking fence. Helper exit and backend-discard acknowledgement
  are not backend proof.
- `evaluate_backend_after_finish` no longer treats a captured incarnation as
  terminated when process metadata lookup is missing or failed, even if a
  liveness probe would say alive. Missing, denied, or malformed metadata or
  liveness stays `cleanup_uncertain`.
- `pid_is_alive` returns True if reachable, False for positive ESRCH absence,
  and None for permission or other lookup uncertainty.
- Explicit synthetic no-backend proof remains non-qualifying and may keep
  `cleanup_fence=null` only because it records test_only/synthetic, no
  backend claim, no provider contact, and no backend acceptance. Actual
  task-owned local peer exit is accepted only with positive absence evidence.

## Birth-marker guard delta

- `evaluate_backend_after_finish` now requires a meaningful non-empty string
  birth marker on both the captured and current process identities before
  treating a marker mismatch as a distinct incarnation.
- Missing, null, empty, or non-string current metadata stays uncertain for both
  alive and absent liveness results; it cannot claim termination or release the
  replacement block.
- Focused regressions cover current null/missing/empty/malformed markers,
  malformed captured markers, a distinct valid marker termination control, and
  same-incarnation survival. Existing positive absence, owned-local-peer,
  official empty-capture, and synthetic-boundary checks remain intact.

## Offline commands and results

```text
PYTHONDONTWRITEBYTECODE=1 python3 proof/puppet-acp/20260921/antigravity/v4/tests/test_agy_live_capable_proof_driver.py -v
Ran 23 tests in 28.134s
OK

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  test_official_empty_capture_after_helper_exit_discard_is_fenced \
  test_failed_metadata_query_with_alive_or_unknown_liveness_is_not_terminated \
  test_task_owned_local_peer_exit_is_accepted_with_positive_evidence \
  test_synthetic_no_backend_empty_capture_remains_non_qualifying -v
Ran 4 tests in 0.217s
OK

--mode reject-live                       exit 2; live turn not authorized
--mode fixture-baseline                  1 pass / 1 expected missing --check; tree 3f34ef57c245222c998be421dc9aaec998e47c18
--mode fixture-after                     2 passes; OK/NON_NORMALIZED; exact {bin/normalize-lines.mjs}
--mode ordinary-fixture-failure          exit 2; see receipt below; not rerun
--live --mode lifecycle                  exit 2; missing launch-input rejected before process start
--mode stage-live                        executed=false; v4 driver + v4 contract only
```

Existing 22 tests continue to pass. One offline birth-marker guard regression
group was added. Ordinary no-edit receipt behavior is unchanged.

## Ordinary failure receipt

Command used the pinned public runtime and local synthetic peer, not an
injected special-exception branch. Host known-answer was not applied. This
receipt was not rewritten by the cleanup-uncertainty repair.

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

This is not Puppet candidate qualification. Useful-edit ability for the
candidate transport remains unproven, and the prior candidate attempt remains
consumed. The separate native installed-plugin pilot is recorded under
`native-plugin-38-pilot/`. Missing official/live backend cleanup is explicitly
fenced, but that fence is offline policy evidence only. Independent
repaired-delta review is required before any new one-session proof is
considered.
