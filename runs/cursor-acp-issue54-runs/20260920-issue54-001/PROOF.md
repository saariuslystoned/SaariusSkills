# Issue #54 proof

Source repair is implemented and fixture-proved. Detailed commands and outcomes are appended to `events.jsonl`.

## Baseline

- Remote source baseline: `46ec908177bce10d8dffbdff8acab7967f43ec74`.
- Native readiness must use `/Users/bobbybones/.local/bin/cursor-agent acp` and `cursor-grok-4.6-high`.
- Shared state contained terminal jobs only; no live job was modified.
- `bridge/cursor-acp/npm test`: 13 passed at baseline.
- Disposable reproduction: two initialized brokers sharing a temporary state root changed `running` to `failed` with `BRIDGE_RESTARTED`.

## Source repair

- Uncommitted worktree changes on `codex/issue54-cursor-recovery`.
- `cd bridge/cursor-acp && npm run check`: 26 passed.
- Isolated setup fixtures only; `setup --check` was not pointed at shared real job storage.
- No commit, push, deploy, or live Cursor model turn from this worker.
- Native follow-up `78daf5de-a569-4d82-85af-2392fb4489e5` completed canonically on the exact route with 81 tool calls; review follow-up `ff1b65be-63dc-4214-8a17-df061dfd3249` completed with 111 tool calls.
- Independent `node --test test/recovery.test.mjs` passed three consecutive runs; `git diff --check` passed.

## Acceptance tracking

- [x] Live owner is preserved during second broker initialization.
- [x] Demonstrably dead owner is recovered; unknown/PID-reuse cases fail safe.
- [x] Separate-process regression and terminal-state race coverage.
- [x] Setup/readiness cannot invalidate active jobs.
- [ ] One native Cursor ACP implementation completes while another broker initializes (requires installed reload; not claimed).
- [x] Source review and tests; commit/PR preparation remains.

## Current terminal status

`SOURCE_FIXED`, not `NATIVE_QUALIFIED`: committed source and review-ready PR are next; installed plugin reload and bounded live in-flight qualification remain owner-gated.
