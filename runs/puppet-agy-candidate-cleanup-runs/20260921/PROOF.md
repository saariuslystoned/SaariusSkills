# AGY Candidate Cleanup Implementation Proof

## Scope

This checkpoint repairs only the official `antigravity-acp` candidate driver
and adapter boundary. It consumes the accepted PR68 lifecycle/model-receipt
interface and does not modify the Cursor implementation or the native AGY
plugin route.

Changed surfaces:

- `bridge/antigravity-acp/test/controller-runtime-driver.mjs`
- `bridge/antigravity-acp/test/controller-runtime-driver.test.mjs`
- `bridge/antigravity-acp/test/unsupported-close-peer.mjs`
- `skills/puppet/scripts/antigravity_acpx.py`
- `skills/puppet/scripts/puppet_lib/antigravity_acp.py`
- `tests/test_puppet_antigravity_acp_runtime.py`

## Cleanup contract

The driver now passes the shared process lifecycle tracker into the pinned
public runtime and exposes session-scoped `waitForOwnedExit` and lifecycle
snapshot operations. Unsupported `session/close` is returned to the adapter;
it is never converted to completed merely by an environment flag.

The adapter admits cleanup only after an exact worker identity match on PID,
launch ID, start timestamp, and runtime-session scope. It records
`backendSessionDiscard: unsupported` separately from worker termination. A
matched worker is locally released, but unsupported backend discard leaves
`persistent_state: unknown` and `final_discard: false`; it does not claim
persistent state was discarded. Missing, mismatched, helper-only, or surviving
worker evidence fences replacement.

Requested and current exact model IDs are persisted before finish/cleanup. The
receipt remains body-free and includes lifecycle, model, cleanup, and discard
fields only.

## Provenance

- Accepted shared base: `6a9140f81b1850a0b39935bb8cd3e58b9ca0f0e2`
- Base tree: `2c4a2142266a6f7eaa80873a609935d0e6736e38`
- Candidate artifact: `runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz`
- Candidate artifact SHA-256: `5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614`
- Local setup: `npm ci --ignore-scripts` in `bridge/antigravity-acp`
- No provider job, OAuth flow, shared install/reset, VM, or account action was performed.

## Test proof

Python command:
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_puppet_antigravity_acp tests.test_puppet_antigravity_acp_runtime tests.test_puppet_antigravity_acpx tests.test_puppet_transport -v`

Result: 41 passed. This includes actual pinned public-runtime tests using the
repository synthetic unsupported-close peer:

- matched owned worker exit => cleanup completed, exact model receipt, local
  release, backend discard unsupported, persistent state unknown;
- surviving owned worker with injected unsupported close => cleanup uncertain,
  replacement blocked, exact model receipt, zero worker exits.

Bridge command:
`npm test` from `bridge/antigravity-acp/`

Result: 34 passed, 0 skipped.

Additional checks:

- `node --test bridge/antigravity-acp/test/controller-runtime-driver.test.mjs`:
  2 passed;
- `python3 -m py_compile skills/puppet/scripts/antigravity_acpx.py skills/puppet/scripts/puppet_lib/antigravity_acp.py`:
  passed;
- `git diff --check`: passed.

## Next gate

Parent must review this exact implementation head before the single authorized
stacked draft PR. Formal AGY provider qualification remains a separate later
allocation with exact `gemini-3.8-flash-high`, omitted effort, one prompt,
timeout no greater than 600000 ms, no fallback/retry, and canonical job receipt
recorded before result/cleanup.
