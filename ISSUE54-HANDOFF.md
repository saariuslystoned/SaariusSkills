# Issue 54 / PR 55 P2 lock repair handoff

Worktree: `/Users/bobbybones/.codex/worktrees/eb45/SaariusSkills`
Branch: `codex/issue54-cursor-recovery`
HEAD: `c3f5077` (repair cycle 1 source commit)
Route: native Cursor ACP only. No alternate transport/model, credentials, auth logs, `.env`, private keys, deploy, or merge.

## Changed files

- `bridge/cursor-acp/broker.mjs` — exclusive complete lock publication, reclaim fence, token-checked release
- `bridge/cursor-acp/test/lock.test.mjs` — two-contender and interruption regressions
- `docs/cursor-acp-delegation.md` — lock publication/exclusion contract
- `skills/cursor-acp-delegation/SKILL.md` — matching operator note
- `runs/cursor-acp-issue54-runs/20260920-issue54-001/{PROOF.md,STATE.md,events.jsonl,heartbeat}`
- `ISSUE54-HANDOFF.md`

## Tests and proof

- First reproduced both audit negatives against this candidate with imports retargeted here. Original evidence left intact at `/Users/bobbybones/Developer/side-quests/x-api/runs/pr55-audit-runs/20260920/{PROOF.md,lock-race.mjs,lock-race.json,incomplete-lock.mjs,incomplete-lock.json}`.
- Candidate repro before repair: lock-race `maximumConcurrentCriticalSections=2`, `cLockRemovedByB=true`; incomplete-lock `statusAfterRecovery=running`, `JOB_LOCK_TIMEOUT`, `lockBytes=0`.
- `cd bridge/cursor-acp && npm run check`: 30 passed, 0 failed.
- Focused: `node --test test/lock.test.mjs` (4 passed), including separate-process stale reclamation and separate-process interruption.
- Repaired repros: lock-race `FIXED` / max concurrent 1; incomplete-lock `FIXED` / recovered `failed` / subsequent lock acquired in 34ms.
- Native review `89d07e37-7588-43ba-804e-5d4a3097ee00` completed canonically but ended with `PING timed out`; local-only retry `30bf36a1-1236-4edd-9950-3331deeb537e` failed at bridge startup. Independent source proof is 30/30.

## Remaining risks

- Parent owns final adjudication; source commit and PR update remain non-merge actions.
- Native installed concurrent MCP execution is still unqualified.
- Unreadable reclaim fences with unknown owners still wait out the lock timeout (fail-safe, not indiscriminate delete).
- Lock liveness still depends on owner `startTime` matching the probed process start time; synthetic mismatched start times look like PID reuse.
