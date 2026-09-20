# Issue #54 proof

Source repair is implemented and fixture-proved. Detailed commands and outcomes are appended to `events.jsonl`.

## Baseline

- Remote source baseline: `46ec908177bce10d8dffbdff8acab7967f43ec74`.
- Native readiness must use `/Users/bobbybones/.local/bin/cursor-agent acp` and `cursor-grok-4.6-high`.
- Shared state contained terminal jobs only; no live job was modified.
- `bridge/cursor-acp/npm test`: 13 passed at baseline.
- Disposable reproduction: two initialized brokers sharing a temporary state root changed `running` to `failed` with `BRIDGE_RESTARTED`.

## Source repair

- Committed candidate `a821c6c` on `codex/issue54-cursor-recovery`.
- Branch HEAD at start of P2 lock repair: `9d1e5c8b2a3bc333ae0667bb97856cce526776dd`; repair commit: `c3f5077`.
- Isolated setup fixtures only; `setup --check` was not pointed at shared real job storage.
- No commit, push, deploy, or live Cursor model turn from this worker.
- Native follow-up `78daf5de-a569-4d82-85af-2392fb4489e5` completed canonically on the exact route with 81 tool calls; review follow-up `ff1b65be-63dc-4214-8a17-df061dfd3249` completed with 111 tool calls.

## PR #55 P2 lock defects

Audit negatives (preserved, not overwritten):

- `/Users/bobbybones/Developer/side-quests/x-api/runs/pr55-audit-runs/20260920/PROOF.md`
- `/Users/bobbybones/Developer/side-quests/x-api/runs/pr55-audit-runs/20260920/lock-race.json` — `maximumConcurrentCriticalSections=2`, `cLockRemovedByB=true`
- `/Users/bobbybones/Developer/side-quests/x-api/runs/pr55-audit-runs/20260920/incomplete-lock.json` — `statusAfterRecovery=running`, `subsequentLockAttempt=JOB_LOCK_TIMEOUT`, `lockBytes=0`

Candidate reproduction (imports pointed at this worktree, same scripts):

- lock-race: `REPRODUCED`, `maximumConcurrentCriticalSections=2`, `cLockRemovedByB=true`
- incomplete-lock: `REPRODUCED`, `statusAfterRecovery=running`, `initializationMs=5126`, `JOB_LOCK_TIMEOUT`, `lockBytes=0`

Repair: exclusive complete lock publication (`write`+`fsync`+`link`), reclaim fence, token-checked release, and live unique-ticket exclusion. Unreadable leftovers are reclaimed only through the fence.

Repaired verification (adapted scripts; original negatives left intact):

- lock-race: `FIXED`, `maximumConcurrentCriticalSections=1`, C did not enter while B held, B release left C's lock
- incomplete-lock: `FIXED`, `statusAfterRecovery=failed`, subsequent lock `acquired`, `initializationMs=34`
- Original incomplete-lock script now fails its `running` assertion (`actual=failed`)
- Original lock-race script now probes the replacement holder instead of unlinking it

`cd bridge/cursor-acp && npm run check`: 30 passed, 0 failed.

## Acceptance tracking

- [x] Live owner is preserved during second broker initialization.
- [x] Demonstrably dead owner is recovered; unknown/incomplete identity and probes without a definitive start time fail safe.
- [x] Proven PID reuse (complete matching job/lease plus definite start-time mismatch) is recovered like missing/dead; bare PID existence is not treated as reuse.
- [x] Separate-process regression and terminal-state race coverage.
- [x] Setup/readiness cannot invalidate active jobs; eligible dead-owner fixture now has a matching lease and a direct-init negative control.
- [x] Two stale-lock reclaimers keep mutual exclusion, including separate OS processes.
- [x] Incomplete/interrupted lock publication does not pin a dead-owner job or loop into `JOB_LOCK_TIMEOUT`.
- [ ] One native Cursor ACP implementation completes while another broker initializes (requires installed reload; not claimed).
- [x] Source review, commit, non-force push, and PR update completed for repair cycle 1; merge/adjudication remains external.
- [ ] Repair cycle 2 commit/push/PR update and exact-head review remain with the parent.

## Repair cycle 2

Canonical review `saariusskills-pr55-2efafae-repair1-p3` against head `2efafae2bd1e336a27e482b0ed375a83404fea34` found two required fixes. Official proof: `/Users/bobbybones/Developer/side-quests/x-api/runs/spark-openclaw-autoreview-runs/spark-openclaw-autoreview-20260920T185532Z-81856/PROOF.md`. Local adjudication: `/Users/bobbybones/Developer/side-quests/x-api/runs/pr55-audit-runs/20260920/repair1/PROOF.md`.

Implemented on the native Cursor ACP route only (`/Users/bobbybones/.local/bin/cursor-agent acp`, `cursor-grok-4.6-high`) in this worktree. Native job `29036f29-bb4c-4731-b098-0314c6a99bcb` completed canonically with 150 tool calls. Repair-cycle-1 locking is preserved. No install/reload, shared job-store pointer, commit, push, or merge.

- P2: `shouldRecoverOwnedJob` recovers `dead` and `reused` after matching job/lease identities. Ambiguous identity stays unrecovered.
- P3: setup fixture writes `owners/<brokerId>.json`. `setup --check` leaves that eligible fixture `running`; an equivalent disposable fixture is recovered when a broker initializes directly.

Targeted before: `node --test test/broker.test.mjs test/recovery.test.mjs test/setup.test.mjs` — 26 passed (including the two tests that encoded the rejected behavior).
Targeted after: same plus `test/lock.test.mjs` — 31 passed.
`cd bridge/cursor-acp && npm run check`: 31 passed, 0 failed, independently rerun after the native handoff.

## Current terminal status

`SOURCE_FIXED`, not `NATIVE_QUALIFIED`: repair cycle 2 source is implemented and fixture-proved against reviewed head `2efafae`, committed as `d4fb178`, and pushed to the PR branch. Native job `29036f29-bb4c-4731-b098-0314c6a99bcb` completed, and independent `npm run check` is 31/31. Parent owns PR update, exact-head review, and final adjudication. Installed plugin reload and bounded live in-flight qualification remain owner-gated.

Review PR: https://github.com/saariuslystoned/SaariusSkills/pull/55
