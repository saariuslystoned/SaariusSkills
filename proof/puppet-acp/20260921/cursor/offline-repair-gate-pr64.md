# Cursor ACP Offline Repair Gate

Date: 2026-09-21

## Decision

The reviewed proof driver's existing helper-vs-backend checks are directionally correct and should be preserved. A bounded driver change is still required for the exception path: the current `consume()` flow raises after `owner.finish()` and therefore loses the model observation, close classification, child-exit result, and any lifecycle snapshot needed for a useful sanitized receipt.

The source repair must expose the missing Cursor-owned worker lifecycle and backend-discard classification first. The proof driver should then consume those public bounded fields; it must not infer backend termination from the Node helper PID.

## Existing contracts to preserve

- `acpx` `2e05de525dd1ab62e9e74bf02d91e3638920fcf3` defines `AcpProcessStarted` as `launchId`, `scope`, `command`, `args`, `cwd`, `pid`, `startedAt`, and `AcpProcessExit` as the same identity plus `exitCode`, `signal`, `exitedAt` (`node_modules/acpx/dist/session-options-Dp6mzNSy.d.ts:98-125`).
- `createVerifiedCandidateAcpRuntime` already admits the public `processLifecycle` option (`bridge/cursor-acp/puppet-adapter.mjs:119-128`, `:670-717`); the current controller driver does not provide a cross-process lifecycle collector (`bridge/cursor-acp/test/controller-runtime-driver.mjs:68-93`).
- PR58's accepted pattern requires exact owned start/exit matching before cleanup admission (`bridge/antigravity-acp/broker.mjs:123-220`, `:887-918`).
- PR59's accepted pattern validates the owned handle and fences cleanup uncertainty (`bridge/cursor-acp/puppet-adapter.mjs:842-860`, `:914-936`, `:1179-1212`).

## Required source-facing output contract

The Cursor controller runtime must return bounded lifecycle metadata from the same Node process that owns `processLifecycle`. A protocol response or equivalent public runtime method must provide exact owned start/exit records with the `acpx` fields above. The snapshot must be available after runtime shutdown settles. The Python `child_process_identity()` helper remains local-controller evidence only.

The owner/runner cleanup result must distinguish:

- `backend_discard: "unsupported"` when the pinned runtime reports `ACP_BACKEND_UNSUPPORTED_CONTROL` for `session/close`;
- `worker_termination: "proven"` only when the exact owned lifecycle start has a matching exit;
- `cleanup_uncertain: true` and `replacement_blocked: true` for a missing, mismatched, or surviving backend worker.

The source path must retain the completed turn observation before applying final close. That observation must carry the selected/current model fields produced by `select_and_map_runtime_models` and `_run_turn`, even if final close later reports unsupported control.

## Proof-driver changes after the source contract exists

The smallest driver diff is limited to:

1. Capture a bounded `finish_error` object and the owner-returned cleanup/lifecycle snapshot in `attempt_owner_finish()` instead of raising before receipt construction.
2. Persist the pre-cleanup observation/model summary and runtime IDs before invoking final cleanup.
3. Replace process-tree heuristics with exact lifecycle matching on `launchId`, `scope`, `pid`, and `startedAt`; retain the current helper-only negative behavior.
4. Emit a useful-turn cleanup outcome when backend discard is unsupported but exact worker exit is proven; emit a fenced uncertain outcome otherwise.
5. Keep fixture/state/fence retention and `replacement_blocked` unchanged for uncertainty. No driver path may delete or replace the live session after an uncertain result.

## Required offline assertions

Add a synthetic regression against the real public shape with these cases:

### Matched exit

The fake runtime raises `ACP_BACKEND_UNSUPPORTED_CONTROL` for `close`, returns a completed turn, and reports one exact owned start/exit pair. Assert useful fixture output, selected/current model equality, `backend_discard == "unsupported"`, `worker_termination == "proven"`, no fence, and replacement allowed.

### No matched exit

Use the same close error with no backend lifecycle pair, a mismatched PID/start identity, or only helper exit. Assert no PASS, cleanup uncertainty, retained fence, replacement blocked, retained fixture/state, `helper_exit_sufficient == false`, and backend termination unknown.

### Model-before-cleanup

Make final close fail after the first turn has completed. Assert the bounded receipt still contains requested, selected, and current model fields plus runtime identity and cleanup classification. This is the regression that the current live receipt failed.

## Dependency

Do not launch another provider session until the source owner has a parent-accepted repair head exposing the lifecycle/cleanup contract, the proof-driver assertions pass offline on that exact head, and the parent issues a fresh one-session allocation. The existing PR64 live allocation remains consumed.

## Proof-driver reconciliation completed

The checkpoint driver now consumes the source contract through `source_cleanup_contract()` and `evaluate_backend_after_finish(..., cleanup=...)`. It validates `launchId`, `scope`, `pid`, and `startedAt` across worker/start/exit records, preserves selected/current model fields on cleanup errors, and records bounded finish-error/source-contract fields. Helper PID evidence remains non-authoritative.

- Checkpoint driver SHA-256: `34b9885102eb84cd52ddb14b22678168cdc9da74b307dc25305ca82db75ec4d8`
- Focused proof tests SHA-256: `47732b81ae1cb9829507efa8854666419cc544645d6c150a0e655d9a4543dc75`
- Offline result: 11 tests passed, 6 skipped by the archival source guard, 0 failed.
- The new contract test is data-only; it does not claim the unmerged source repair is live-qualified.
