# Review: Cursor ACP model selection repair

- Repo: SaariusSkills
- Worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`
- Branch: `codex/cursor-luna-model-selection-20260930`
- Base: `cc4070ebd7861f07ca3e24f7744d779fb13a472f`
- Patch state: uncommitted on base `cc4070e`. Target commit HEAD will be created by parent.
- Writers: all code through native workers (native Grok CLI `c5c1f1e9-6f62-4a09-9e7b-4bb2c6d3fe08` and Antigravity `d657d1ef-872d-4516-a443-e0929a11f181` closeout; previous AGY docs `0fead6ea-f962-4487-af33-870ee2173f4f` cancelled canonically complete+cleanupReady). Cursor prompts sent: 0.

## Accepted

1. **Catalog Inspectability & Default Model Policy**:
   - `ready` strictly equals `selectionReady` and matches `delegate` for the same selector.
   - `catalogReady` can be true while `ready` is false.
   - Missing High on an advertised Luna base throws `EFFORT_UNSUPPORTED` with the full safe advertised catalog (`availableModelIds` and `availableModels`).
   - Missing base throws `MODEL_REQUIRED`.
   - The runtime's current model is not used as a substitute or default.
   - Evidence: `bridge/cursor-acp/test/model-selection.test.mjs` and candidate readiness receipt `proof/cursor-model-selection/20260930/receipts/candidate-native-readiness.json`.

2. **Advertised Catalog Exact ID Uniqueness & Coherent Effort**:
   - Exact advertised model IDs use equality counting; duplicate IDs are rejected with `MODEL_AMBIGUOUS`.
   - Repeated, conflicting, or malformed effort parameters are rejected with `EFFORT_UNSUPPORTED`.
   - Documented selectors: exact ID, base plus effort, plugin default alias `gpt-5.6-luna-high`, or legacy `cursor-grok-4.6-(low|medium|high|xhigh)`.
   - Plugin default alias `gpt-5.6-luna-high` is base `gpt-5.6-luna` plus effort `high` (`liveModelId: null`). It is not advertised as a live ID.

3. **Pre-Prompt Confirmation & Drift Guard (Source Correctness Gap Resolution)**:
   - `confirmExactCursorModel` invokes helper `assertAdvertisedSelectedModel(models, selectedModelId, selectedEffort)`, asserting the selected model ID count is exactly 1 in `models.availableModelIds` and verifying coherent advertised effort matches stored effort.
   - Fails closed with `MODEL_SELECTION_UNCONFIRMED` if persisted model is absent or ambiguous in current catalog, even if `currentModelId` already matches.
   - Does NOT re-resolve aliases/defaults or select a substitute.
   - `allowSelection` parameter controls setter invocation:
     - Initial admission / new handle (`verifyModel`, `runJob` when `!prepared.handle`) passes `allowSelection: true`. It may set the exact persisted ID if uniquely advertised.
     - Prepared pre-prompt check passes `allowSelection: false`. Prepared handle drift fails closed before prompt with zero prompts and no setter call.
   - On confirmation failure, immutable fields (`selectedModelId`, `selectedEffort`, `requestedModel`, `requestedEffort`, `selectionPolicy`) are preserved in `job.model` and `job.request`, while `job.model.currentModelId` is updated to the observed `error.details.currentModelId` so public `modelSelection`, `STATE.md`, and `PROOF.md` reflect actual observed drift.

4. **Lifecycle Proofs & Public Receipts Preserved**:
   - Original discovery receipt: `proof/cursor-model-selection/20260930/discovery-receipt.json` preserved with `cleanupReceipt.closed: false` and unsupported `session/close` error (`Agent does not support session/close`).
   - Independent parent config probe exit receipt: `proof/cursor-model-selection/20260930/receipts/config-catalog-cleanup.json` (pid 24120, exitCode 143, prompts 0, config options `mode` and `model` only).
   - Candidate MCP readiness receipt: `proof/cursor-model-selection/20260930/receipts/candidate-native-readiness.json` (`ready: false`, `catalogReady: true`, `selectionReady: false`, `EFFORT_UNSUPPORTED`, 43 IDs, `hostNativeReloaded: false`, promptsSent: 0).
   - Candidate listTools receipt: `proof/cursor-model-selection/20260930/receipts/candidate-listtools.json` (6 tools; `cursor_acp_readiness` and `cursor_acp_delegate` expose optional `model` and `effort`, promptsSent: 0, `hostNativeReloaded: false`).
   - Initial Antigravity job `852e991f-3503-4b8b-8cce-12e16ec92339` terminal receipt: `proof/cursor-model-selection/20260930/receipts/antigravity-terminal.json` (`status: "cancelled"`, `complete: true`, `cleanupReady: true`).
   - Grok repair job `c5c1f1e9-6f62-4a09-9e7b-4bb2c6d3fe08` terminal receipt: `proof/cursor-model-selection/20260930/receipts/grok-terminal.json` (`status: "completed"`, `complete: true`, `cleanupReady: true`).
   - Final Antigravity job `d657d1ef-872d-4516-a443-e0929a11f181` terminal receipt: `proof/cursor-model-selection/20260930/receipts/final-antigravity-terminal.json` (`status: "completed"`, `complete: true`, `cleanupReady: true`, cleanup observed `local_worker_terminated_backend_session_discard_unsupported`).
   - Grok docs job `0dabe14d-0ae7-4080-a62c-eaa5279bbffc` timeout receipt: `proof/cursor-model-selection/20260930/receipts/proof-grok-timeout.json` (timed out; left partial verifier; no source/test changes observed, canonical `status: "failed"`, `complete: true`, `cleanupReady: true`).
   - Previous Antigravity docs job `0fead6ea-f962-4487-af33-870ee2173f4f` cancellation receipt: `proof/cursor-model-selection/20260930/receipts/proof-antigravity-cancelled.json` (`status: "cancelled"`, `complete: true`, `cleanupReady: true`, cleanup observed `local_worker_terminated_backend_session_discard_unsupported`).
   - Proof closeout review receipt: `proof/cursor-model-selection/20260930/receipts/proof-closeout-review.json` (corrected parent finding: timed-out Grok docs job left partial verifier at `2026-09-30T19:51:35Z`; no source/test changes observed).
   - Final persisted catalog review reproducer receipt: `proof/cursor-model-selection/20260930/receipts/persisted-catalog-review-final.json` (exitCode 0, promptsSent: 0, expected and actual `MODEL_SELECTION_UNCONFIRMED`).

5. **Fixtures & Boundaries**:
   - `bridge/cursor-acp/fixtures/model-catalog.json` marked `synthetic: true`, recording the live Luna ID as the medium parameterized ID.
   - No edits to other agent lanes (`bridge/grok-acp`, `bridge/antigravity-acp`).

## Rejected

- Treating any unadvertised slug (such as `gpt-5.6-luna-fast`) as live High.
- Downgrading the durable default to Medium.
- Accepting duplicate exact IDs or missing catalog entries when `currentModelId` matches.
- Calling `setModel` or adopting drifted current models during pre-prompt prepared execution.
- Labeling base commit `cc4070e` as the patch head.
- Inventing evidence timestamps (e.g. guessed future timestamp 20:10Z).
- Sending any Cursor prompt today (Luna High absent; status: `WAITING_FOR_HUMAN`).

## Verification & Checks

All code changes were executed through native workers without sending a Cursor prompt.
Candidate `hostNativeReloaded: false`; no live High prompt was sent because only Medium is advertised.
A tiny synthetic prompt is already user-authorized, but remains strictly gated behind live High catalog advertisement and approved plugin installation/native-load verification.

- Cursor Bridge Suite:
  - Command: `cd bridge/cursor-acp && npm run check`
  - Result: 135 total: 124 pass, 11 skipped, 0 fail
  - Log: `proof/cursor-model-selection/20260930/test-suite.log`
- Shared Runtime Suite:
  - Command: `cd bridge/cursor-acp && npm run check`
  - Result: 114 pass, 0 fail
  - Log: `proof/cursor-model-selection/20260930/npm-check.log`
- Focused Model Selection Suite:
  - Command: `node --test bridge/cursor-acp/test/model-selection.test.mjs`
  - Result: 27 pass, 0 fail (includes 4 persisted model confirmation & drift guard regression tests)
  - Log: `proof/cursor-model-selection/20260930/model-selection-tests.log`
- Packaging Test Suite:
  - Command: `python3 -m unittest tests.test_packaging`
  - Result: 14 pass, 0 fail (OK)
  - Log: `proof/cursor-model-selection/20260930/packaging.log`
- Full Python Test Suite:
  - Command: `python3 -m unittest discover -s tests -q`
  - Result: 69 pass, 0 fail (OK)
  - Log: `proof/cursor-model-selection/20260930/python-suite.log`
- Git diff hygiene: `git diff --check` passes cleanly with zero output.
- Manifest and versions remain unchanged: Plugin `0.4.2`, Bridge `0.1.0`.
