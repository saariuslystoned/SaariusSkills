# Native Grok model selection proof

Fresh origin/main b2ec4896d0532e6c9a149c114cf3054433be5e7e. Isolated branch codex/grok-model-selection-20261001. Source and docs only in this worktree. No commit, push, PR, install, or live provider prompt.

Native Cursor readiness recorded before implementation remains in implementation-receipt.json. This implementation did not call Grok or Cursor again.

Provider-free verification on 2026-10-01:
- `node --check` of broker.mjs, server.mjs, and test/model-selection.test.mjs passed.
- `node --test bridge/grok-acp/test/*.test.mjs`: 96 passed, 0 failed, 0 skipped. Log: grok-tests.log.
- `python3 -m unittest tests.test_packaging -q`: 14 passed. Log: packaging-tests.log.

Dependencies: this worktree has no `bridge/grok-acp/node_modules`. The Grok suite imported preexisting acpx 0.19.4, zod 4.6.5, and MCP SDK 1.30.0 from runtime store `1bc2f751d791b81bf192419c3dac4e13df7248dad217451bea7f989329e52904` through a temporary symlink that was removed afterward. No package install.

The preexisting setup test prepared an isolated temp runtime root via `SAARIUS_ACP_RUNTIME_ROOT` and deleted it in `test.after`. It did not target the user runtime store.

Covered: omitted default grok-4.7; default alternative grok-4.6 when only grok-4.6 and grok-4.5 are advertised, without keeping the session current model; ordered fallbackModels; empty strict list; explicit grok-4.6 and grok-4.7-build-fast; explicit grok-4.7 absent with zero prompts; missing allowed models, invalid model-plus-fallbacks, and auth failure with zero prompts; concurrent and sequential per-job isolation; receipts, persisted job, STATE, and PROOF; catalog drift before prompt with zero prompts and no model switch. Existing strict pin tests still refuse an explicit grok-4.7 when it is not advertised.

## Parent independent verification

Native implementation job ef0ec142-9f2f-471c-8136-6c7fd569d384 completed with taskComplete=true, cleanupReady=true, complete=true. Canonical result is implementation-result.json. Implementation model was Grok4.7 through Cursor ACP, not an OpenAI worker model.

Parent reran all Grok tests:96pass/0fail; impacted packaging:14pass; shared host-policy and plugin-manifest parity:20pass. parent-test-summary.json records exact argv, exit codes, raw stdout/stderr paths and hashes. Dependencies were linked read-only from the preexisting prepared0.19.4 tree into this worktree and the task-created symlink was removed in finally; no shared installation was changed. Existing setup tests prepare only their isolated temp runtime. Python full discovery exceeded a90s diagnostic cap; its outcome is retained, not claimed passing. The impacted packaging suite passed directly. No Python source changed.

Parent reviewed model policy/receipt/persistence, per-session isolation, strict pins, pre-prompt catalog membership and ownership boundaries. Accepted P3 contradictory empty-list comment was fixed without semantic changes. Rejected weakening concern: old strict constructor-pin test now expressly pins4.7 and asserts zero prompts, while default behavior is independently covered. See independent-review.json. No source/runtime dependency pins or installed plugin files changed. Native Grok inference on new source remains unperformed. PR111 startup fixture race is separate and remains outside this change.

SSH review preflight: <USER_HOST> -> spark-2; effective <REVIEW_ACCOUNT>@spark-2:22, identitiesonly=no, one identityfile. Bounded BatchMode/ConnectTimeout10/StrictHostKeyChecking=yes hostname/id probe returned spark-2 and <REVIEW_ACCOUNT>, exit0. No secrets or proxy-command output inspected.
