# Cursor ACP Safe Model Selection Proof

> **Current Superseding Status (Model Switching Scope)**: The earlier Luna High blocker is historical and superseded by user-selected Luna Medium default (`gpt-5.6-luna-medium`) and optional effort/model-only switching among `grok-4.6`, `grok-4.7`, and `gpt-5.6-luna`. See current acceptance proof in [model-switching/PROOF.md](model-switching/PROOF.md). The current scope is not blocked by the absence of Luna High. The current pending gate is maintainer-approved installation and native host reload, followed by the previously authorized tiny Luna Medium smoke turn; zero real Cursor prompts have been sent so far (`modelPromptsSent: 0`, `hostNativeReloaded: false`). All earlier historical evidence below remains intact.

- Worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`
- Branch: `codex/cursor-luna-model-selection-20260930`
- Base commit: `cc4070ebd7861f07ca3e24f7744d779fb13a472f`
- Patch status: uncommitted on base `cc4070e`. Target commit HEAD will be created by parent.
- Writers: all code through native workers (native Grok CLI `c5c1f1e9-6f62-4a09-9e7b-4bb2c6d3fe08` and Antigravity `d657d1ef-872d-4516-a443-e0929a11f181` closeout; previous AGY docs `0fead6ea-f962-4487-af33-870ee2173f4f` cancelled canonically complete+cleanupReady).
- Cursor agent: `2026.08.11-e8db854`
- Cursor prompts sent: 0

## Live Discovery & Receipts

- Advertised Luna model in live catalog: `gpt-5.6-luna[context=272k,reasoning=medium,fast=false]` (43 advertised IDs total).
- Luna High advertised in live catalog: false.
- Original discovery receipt: [discovery-receipt.json](discovery-receipt.json) (`cleanupReceipt.closed: false`, unsupported backend close error: `Agent does not support session/close`, promptsSent: 0).
- Independent parent config probe exit receipt: [config-catalog-cleanup.json](receipts/config-catalog-cleanup.json) (pid 24120, exitCode 143, promptsSent: 0, config options `mode` and `model` only).
- Initial Antigravity job `852e991f-3503-4b8b-8cce-12e16ec92339` terminal receipt: [antigravity-terminal.json](receipts/antigravity-terminal.json) (`status: "cancelled"`, `complete: true`, `cleanupReady: true`).
- Grok repair job `c5c1f1e9-6f62-4a09-9e7b-4bb2c6d3fe08` terminal receipt: [grok-terminal.json](receipts/grok-terminal.json) (`status: "completed"`, `complete: true`, `cleanupReady: true`).
- Final Antigravity job `d657d1ef-872d-4516-a443-e0929a11f181` terminal receipt: [final-antigravity-terminal.json](receipts/final-antigravity-terminal.json) (`status: "completed"`, `complete: true`, `cleanupReady: true`, cleanup observed `local_worker_terminated_backend_session_discard_unsupported`).
- Grok docs job `0dabe14d-0ae7-4080-a62c-eaa5279bbffc` timeout receipt: [proof-grok-timeout.json](receipts/proof-grok-timeout.json) (timed out; left partial verifier; no source/test changes observed, canonical `status: "failed"`, `complete: true`, `cleanupReady: true`).
- Previous Antigravity docs job `0fead6ea-f962-4487-af33-870ee2173f4f` cancellation receipt: [proof-antigravity-cancelled.json](receipts/proof-antigravity-cancelled.json) (`status: "cancelled"`, `complete: true`, `cleanupReady: true`, cleanup observed `local_worker_terminated_backend_session_discard_unsupported`).
- Proof closeout review receipt: [proof-closeout-review.json](receipts/proof-closeout-review.json) (corrected parent finding: timed-out Grok docs job left partial verifier at `2026-09-30T19:51:35Z`; no source/test changes observed).
- Persisted catalog review reproducer receipt: [persisted-catalog-review-final.json](receipts/persisted-catalog-review-final.json) (exitCode 0, promptsSent: 0, expected and actual `MODEL_SELECTION_UNCONFIRMED`).
- Candidate native readiness receipt: [candidate-native-readiness.json](receipts/candidate-native-readiness.json) (`ready: false`, `catalogReady: true`, `selectionReady: false`, `EFFORT_UNSUPPORTED`, 43 IDs, `hostNativeReloaded: false`, promptsSent: 0).
- Candidate listTools receipt: [candidate-listtools.json](receipts/candidate-listtools.json) (6 tools; `cursor_acp_readiness` and `cursor_acp_delegate` expose optional `model` and `effort`, promptsSent: 0, `hostNativeReloaded: false`).

## Verification & Checks

All code execution performed through native workers without sending a Cursor prompt. Candidate `hostNativeReloaded: false`.

| Suite | Command | Result | Evidence Log |
| --- | --- | --- | --- |
| Cursor Bridge | `cd bridge/cursor-acp && npm run check` | 135 total: 124 pass, 11 skipped, 0 fail | [test-suite.log](test-suite.log) |
| Shared Runtime | `cd bridge/cursor-acp && npm run check` | 114 pass, 0 fail | [npm-check.log](npm-check.log) |
| Focused Model Selection | `node --test bridge/cursor-acp/test/model-selection.test.mjs` | 27 pass, 0 fail | [model-selection-tests.log](model-selection-tests.log) |
| Packaging | `python3 -m unittest tests.test_packaging` | 14 pass, 0 fail (OK) | [packaging.log](packaging.log) |
| Full Python Suite | `python3 -m unittest discover -s tests -q` | 69 pass, 0 fail (OK) | [python-suite.log](python-suite.log) |
| Git Diff Hygiene | `git diff --check` | exit 0, no trailing whitespace or conflicts | clean |

## Persisted Model Confirmation & Drift Guard Proofs

Four specific regression tests in `bridge/cursor-acp/test/model-selection.test.mjs`:
1. `current=stored High` but catalog missing High -> fails closed with zero prompts (`MODEL_SELECTION_UNCONFIRMED`).
2. Exact High duplicated after admission in advertised catalog -> fails closed with zero prompts (`MODEL_SELECTION_UNCONFIRMED`).
3. Prepared current drift with working setter -> fails closed with zero prompts and no setter call (`MODEL_SELECTION_UNCONFIRMED`).
4. Failed confirmation exposes latest observed current model in `job.model.currentModelId`, `STATE.md`, and `PROOF.md` while immutable selected fields (`selectedModelId`, `selectedEffort`, `selectionPolicy`) remain preserved.

## Documentation & Reload Plan

- Comprehensive Review: [REVIEW.md](REVIEW.md)
- Install & Reload Plan: [install-reload-plan.md](install-reload-plan.md)
- Read-only Source Verifier: [compare-installed-source.py](compare-installed-source.py)
- Model Switching Proof: [model-switching/PROOF.md](model-switching/PROOF.md)

## Blocker (Historical - Superseded by model-switching/PROOF.md)

Native Luna High prompt stays `WAITING_FOR_HUMAN`.
1. Luna High is absent from the live Cursor ACP catalog today (only Medium is advertised: `gpt-5.6-luna[context=272k,reasoning=medium,fast=false]`). No fallback or downgrade to Medium is permitted.
2. The installed host has not loaded this reviewed worktree schema (`hostNativeReloaded: false`).
3. A tiny synthetic prompt is already user-authorized, but strictly gated behind:
   - Live High catalog advertisement (`models.availableModelIds`).
   - Approved plugin installation and native-load verification against reviewed commit.
   - Reloaded schema active with matching `selectedModelId` and `currentModelId`.
   - Effective `approve-all` permission policy.
