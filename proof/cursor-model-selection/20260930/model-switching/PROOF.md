# Cursor ACP Model-Switching Acceptance Proof

- Worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`
- Branch: `codex/cursor-luna-model-selection-20260930`
- Base commit: `cc4070ebd7861f07ca3e24f7744d779fb13a472f`
- Scope: Model-only switching among `grok-4.6`, `grok-4.7`, and `gpt-5.6-luna`; effort optional; Luna Medium default (`gpt-5.6-luna-medium`).
- Host Native Reloaded: `false`
- Real Cursor prompts sent: 0
- Historical reference: [../PROOF.md](../PROOF.md) and [../REVIEW.md](../REVIEW.md)

## Current Acceptance & Scope

The user requested model-only switching across the three advertised base models (`grok-4.6`, `grok-4.7`, and `gpt-5.6-luna`), with effort being optional and `gpt-5.6-luna-medium` as default. The earlier Luna High blocker is historical and superseded by user-selected Luna Medium default and model-only switching.

All implementation and test files were authored exclusively through native ACP workers and parent-reviewed.

### Acceptance Evidence:

1. **Candidate Switching Readiness ([candidate-switching-readiness.json](candidate-switching-readiness.json))**:
   - `ready: true` and `selectionReady: true` for all three model-only inputs:
     - `grok-4.6`: resolves to `grok-4.6[effort=high,fast=true]`, `ready: true`, `selectionReady: true`.
     - `grok-4.7`: resolves to `grok-4.7[context=256k,reasoning_effort=high,fast=true]`, `ready: true`, `selectionReady: true`.
     - `gpt-5.6-luna`: resolves to `gpt-5.6-luna[context=272k,reasoning=medium,fast=false]`, `ready: true`, `selectionReady: true`.
   - `defaultMediumReadiness`: `ready: true`, `selectionReady: true` (`preferredDefaultAlias: "gpt-5.6-luna-medium"`).
   - Explicit High (`explicitHighReadiness`): `ready: false`, `selectionReady: false` (`EFFORT_UNSUPPORTED`), confirming fail-closed behavior without silent fallback.
   - `allThreeSuccess: true`.
   - `hostNativeReloaded: false`.
   - `modelPromptsSent: 0`.
   - Probe transport observed clean exit 0 (`observedExit: { exitCode: 0, signalCode: null }`).
   - Probe backend session discard observed as `unsupported` (`Agent does not support session/close`), matching Cursor agent transport contract.

2. **Exposed Tools & Optional Schema ([candidate-listtools.json](candidate-listtools.json))**:
   - 6 tools advertised (`cursor_acp_readiness`, `cursor_acp_delegate`, `cursor_acp_status`, `cursor_acp_result`, `cursor_acp_steer`, `cursor_acp_cancel`).
   - `cursor_acp_readiness` and `cursor_acp_delegate` expose `model` (string) and `effort` (string) as optional fields.

3. **Focused Model Selection & Packaging Tests**:
   - `bridge/cursor-acp/test/model-selection.test.mjs`: 30 passed, 0 failed. Log: [model-selection-tests.log](model-selection-tests.log). Includes sequential delegation loop: Grok 4.6 -> Grok 4.7 -> Luna -> Grok 4.6.
   - Packaging tests (`tests.test_packaging`): 14 passed, 0 failed (OK). Log: [packaging.log](packaging.log).

4. **Parent Verification Checks ([parent-verification.json](parent-verification.json))**:
   - Cursor bridge suite: 138 total: 127 pass, 11 skipped, 0 fail.
   - Shared runtime suite: 114 total: 112 pass, 2 fixture setup 30s timeouts repeated in narrow retry (`spawnSync setup returned status null at the 30-second fixture preparation timeout`).
   - Do NOT claim local full check passed; reliance is placed on exact-head CI.

5. **Native Worker Terminal Receipt ([native-worker-terminal.json](native-worker-terminal.json))**:
   - Native job ID: `60138a26-a3d1-4ff3-b5ce-2ede5fa2c15d`.
   - Terminal status: `failed` with error code `TIMEOUT` (exceeded bounded job timeout).
   - Canonical flags: `complete: true`, `taskComplete: true`, `cleanupReady: true`.
   - Cleanup observed: `local_worker_terminated_backend_session_discard_unsupported`.
   - Honest status preserved.

6. **Upstream OpenClaw Review ([upstream-openclaw-review.json](upstream-openclaw-review.json))**:
   - Parent read-only inspection against pinned upstream `openclaw/openclaw` commit `3bc0356e6a6af17ba6a993435629900f50f21f36`.
   - Verified that no missing transport change is required; model selection utilizes advertised catalog controls and acpx runtime setModel directly.

## Install Gate & Verification Sequence

Zero real Cursor model turns or prompts have been sent. Execution remains gated behind:
1. Parent staging and updating existing draft PR #108.
2. Exact-head CI validation on GitHub Actions.
3. Maintainer-approved plugin installation and native host reload (`hostNativeReloaded: true`).
4. Previously authorized tiny synthetic Luna Medium smoke turn under effective `approve-all` permission policy.
