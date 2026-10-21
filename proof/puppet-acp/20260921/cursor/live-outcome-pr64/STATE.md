# Cursor PR64 candidate qualification state

- status: LIVE_ATTEMPT_CLEANUP_UNCERTAIN
- source_head: `84a6dad7110ed97722b35ff1d7c102671312ec80`
- source_tree: `c923dfc6fc698d14d2e5c3fcdfdce3f156226b39`
- driver_sha256: `2292f0f39220b214fa561ff413d162e812b668a8ccdc86013ed1b645c0cb682f`
- session: `cursor-proof-v3-live-pr64-20260921`
- allocation: one session / one useful prompt <=300000ms / no retry
- mode: official Cursor ACP candidate qualification
- live_provider_call: first task turn completed; qualification not accepted
- provider_turns_completed: 1
- useful_fixture_edit: true
- protected_tests_unchanged: true
- owner_finish_attempted: true
- owner_finish_error: `ValidationError: Agent does not support session/close for cursor-proof-v3-live-pr64-20260921.`
- cleanup_fence: retained; replacement blocked
- backend_termination_verified: false
- model_attribution: requested selector and expected current are recorded; observed selected/current model was not durably retained before cleanup failure
- retry: forbidden and not attempted
- historical_failure_preserved: true
