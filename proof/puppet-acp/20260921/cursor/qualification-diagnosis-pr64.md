# Cursor ACP PR64 Qualification Diagnosis

Date: 2026-09-21

## Result

The one authorized live turn was useful and completed the fixture change, but qualification is not accepted. The blocker is cleanup/session-close semantics, not route execution:

- Receipt: `live-outcome-pr64/live-outcome.json`
- Receipt SHA-256: `a940d5425bd21c04e6542bb754e7cd01ad0d0e473bd933e79f4bb2f68e42fe33`
- Fixture result: `normalize-lines.mjs` changed; protected test remained unchanged; 3/3 tests passed.
- Cleanup fence: retained in the qualifier-owned run; replacement is blocked.
- Cleanup error: `Agent does not support session/close for cursor-proof-v3-live-pr64-20260921.`
- Allocation: one session and one prompt consumed; retry is not authorized.

## Exact cleanup path

The failure propagates through the following path:

1. `skills/puppet/scripts/puppet_lib/acp_consumer.py:233-241` calls `runner.finish()` and records its exception as `finish_error`.
2. `skills/puppet/scripts/puppet_lib/acp_consumer.py:243-264` still calls `shutdown_task_owned_runtime(runtime)`, but only treats the returned helper `exited: true` as proven local release.
3. `skills/puppet/scripts/puppet_lib/cursor_acp.py:1845-1866` calls `_owned_close()`.
4. `skills/puppet/scripts/puppet_lib/cursor_acp.py:1605-1634` sends the public runtime `close` RPC and fences cleanup on any exception.
5. `bridge/cursor-acp/test/controller-runtime-driver.mjs:138-140` forwards that RPC to `current.close(...)`; its separate `shutdown` operation is at `:142-146`.
6. The pinned `acpx` runtime is exact merged-unreleased source `2e05de525dd1ab62e9e74bf02d91e3638920fcf3`, artifact SHA-256 `5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614`. Its `dist/runtime.js:2186-2194` checks `supportsCloseSession()` and throws `ACP_BACKEND_UNSUPPORTED_CONTROL` when the agent does not advertise `session/close`.

The owner therefore attempts close, fences the owned state, then shuts down the local Node controller. The failure is re-raised from `acp_consumer.py:278-283`. This is an intentional fail-closed result, not evidence that the worker survived.

## What is and is not proven

The runtime error proves only that backend session close/discard is unsupported by the selected ACP backend. It does not prove backend termination, and it does not establish an upstream defect by itself.

The recorded helper PID was `59286`; it was absent when checked after the failure. That is only a local observation. The helper is the Node `controller-runtime-driver` process (`cursor_acp.py:1434-1462`), not automatically the Cursor backend process. The qualification driver explicitly treats helper exit as insufficient (`cursor_live_capable_proof_driver.py:650-674`), so `backend_termination_verified` remains false and `helper_exit_sufficient` remains false. No owned backend spawn/exit lifecycle record was available in the retained sanitized evidence.

## Why model attribution is incomplete

The reviewed driver does perform independent model selection and remapping in `skills/puppet/scripts/puppet_lib/cursor_acp.py:1149-1201`, and `_run_turn()` passes `mapped["current_model"]` into the observation at `:1710-1777`. However, the observation/receipt is not durably committed before owner cleanup. Because `owner.finish()` raised, the retained ownership/event records contain session ownership and cleanup state but no selected/current model. The receipt therefore correctly records both observed model fields as `null`; no model PASS is claimed.

## Prior accepted pattern

Merged PR58 (`9c8178f`, implementation `08f3788`) provides the relevant cleanup pattern in `bridge/antigravity-acp/broker.mjs:123-220` and `:887-918`:

- classify `ACP_BACKEND_UNSUPPORTED_CONTROL` for `session/close`;
- track exact owned worker start and exit identities through `processLifecycle`;
- wait for the owned worker exit;
- record `backendSessionDiscard: "unsupported"` separately from worker termination;
- admit replacement only after the exact worker exit proof; otherwise remain uncertain and fenced.

Its regression coverage in `bridge/antigravity-acp/test/cleanup-compatibility.test.mjs:88-200` proves the completed-worker case, while `:202-240` keeps a surviving worker uncertain and fenced. PR59 (`faa332c`, implementation `a7e77ad`) supplies the complementary candidate ownership binding: `bridge/cursor-acp/puppet-adapter.mjs:842-860`, `:914-936`, and `:1179-1212` validate ownership/handle identity and fence cleanup failures. PR64 fixed the route identity mismatch, but did not add the PR58-style matched lifecycle proof for Cursor.

## Smallest likely fix boundary

The smallest safe source-side fix is in the Cursor runtime adapter/consumer boundary, not in the fixture driver:

1. Pass the pinned runtime's `processLifecycle` hooks through the Cursor runtime construction and record the exact session-scoped worker identity.
2. In the owned-close path, recognize unsupported backend `session/close` as a distinct discard result.
3. Admit cleanup only after an exact matching owned-worker exit proof; otherwise preserve the existing cleanup-unknown fence and block replacement.
4. Persist the bounded cleanup result, worker identity, and backend-discard status before the owner can re-raise the close error.

Do not simply swallow the unsupported-close exception, and do not convert helper exit into backend termination. A proof-driver-only fix is still needed to persist the model observation and lifecycle metadata before `owner.finish()` can fail, but it cannot substitute for source-side cleanup semantics.

## Offline regression required before another live allocation

Add a synthetic unsupported-close regression with two cases:

1. A fake/public runtime raises `ACP_BACKEND_UNSUPPORTED_CONTROL` for `close`, while the exact owned worker emits matching start/exit identities. Expected result: useful turn retained, backend discard marked unsupported, worker termination proven, cleanup admitted, replacement allowed.
2. The same close error with a surviving worker, no matched backend exit, or helper-only exit. Expected result: cleanup remains unknown, fence is retained, replacement is blocked, and no PASS is emitted.

The regression must also assert that selected/current model metadata and bounded lifecycle metadata are persisted even when final close raises. The existing accepted PR58 tests are the reference behavior; no further live/provider attempt should occur until the Cursor path meets the same distinction and proof standard.
