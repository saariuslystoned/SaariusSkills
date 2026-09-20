# Issue 54 / PR 55 repair-cycle-2 handoff

Worktree: `/Users/bobbybones/.codex/worktrees/eb45/SaariusSkills`
Branch: `codex/issue54-cursor-recovery`
HEAD: `d4fb178` (repair-cycle-2 source fix, pushed)
Route: native Cursor ACP only — `/Users/bobbybones/.local/bin/cursor-agent acp` with `cursor-grok-4.6-high`. No alternate transport/model, credentials, auth logs, `.env`, private keys, install/reload, deploy, or merge.

## Repair-cycle-2 dispositions

Canonical review `saariusskills-pr55-2efafae-repair1-p3` (PROOF at `/Users/bobbybones/Developer/side-quests/x-api/runs/spark-openclaw-autoreview-runs/spark-openclaw-autoreview-20260920T185532Z-81856/PROOF.md`; local adjudication at `/Users/bobbybones/Developer/side-quests/x-api/runs/pr55-audit-runs/20260920/repair1/PROOF.md`) returned 2 required fixes. Both implemented here. Repair-cycle-1 locking (`write`+`fsync`+`link`, reclaim fence, token-checked release) is unchanged.

Native Cursor job `29036f29-bb4c-4731-b098-0314c6a99bcb` completed canonically on the exact route with 150 tool calls. Independent post-handoff verification is 31/31. Source commit `d4fb178` is pushed to the PR branch. This remains `SOURCE_FIXED`; no install/reload or `NATIVE_QUALIFIED` claim.

- P2 PID reuse: `required_fix` implemented. After complete matching job-owner and lease identities, `shouldRecoverOwnedJob` now recovers `classifyOwnerIdentity === "reused"` exactly like missing/dead. Unknown/incomplete identity and probes without a definitive start time stay unrecovered. Bare-PID safety is unchanged.
- P3 setup isolation fixture: `required_fix` implemented. The dead-owner fixture now writes `owners/<brokerId>.json`. An equivalent disposable control is recovered when a broker initializes directly; `setup --check` leaves the original fixture `running`.

## Changed files

- `bridge/cursor-acp/broker.mjs` — recover proven PID reuse after matching job/lease identities
- `bridge/cursor-acp/test/broker.test.mjs` — distinguish proven reuse from ambiguous identity
- `bridge/cursor-acp/test/recovery.test.mjs` — recover proven reuse; keep bare-PID and no-lease fail-safe
- `bridge/cursor-acp/test/setup.test.mjs` — matching lease plus direct-init negative control
- `docs/cursor-acp-delegation.md` — proven reuse vs ambiguous identity
- `skills/cursor-acp-delegation/SKILL.md` — matching operator wording
- `runs/cursor-acp-issue54-runs/20260920-issue54-001/{PROOF.md,STATE.md,events.jsonl,heartbeat}`
- `ISSUE54-HANDOFF.md`

## Tests and proof

- Targeted before: `node --test test/broker.test.mjs test/recovery.test.mjs test/setup.test.mjs` — 26 passed, including the two tests that encoded the rejected behavior (`PID reuse ... is not reaped`; setup fixture without a lease).
- Targeted after: same files plus `test/lock.test.mjs` — 31 passed, 0 failed. New/updated: proven reuse recovers `BRIDGE_RESTARTED`; no-lease reuse and bare-PID stay `running`; setup `--check` isolation plus direct-init recovery control.
- `cd bridge/cursor-acp && npm run check`: 31 passed, 0 failed.
- Lock suite unchanged and still passing (4/4).
- No native model turn, shared job-store pointer, install/reload, or merge from this worker. Source commit `d4fb178` was committed and pushed after verification.

## Remaining risks

- Parent owns PR update, exact-head review, and final adjudication. No `NATIVE_QUALIFIED` claim.
- Native installed concurrent MCP execution is still unqualified.
- Unreadable reclaim fences with unknown owners still wait out the lock timeout (fail-safe, not indiscriminate delete).
- Ambiguous probes (`alive` without start time, incomplete identity, missing/mismatched lease) remain unrecovered by design.
