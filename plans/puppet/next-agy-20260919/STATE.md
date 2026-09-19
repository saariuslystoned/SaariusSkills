# State

- repository: `<worktree>/SaariusSkills`
- branch: `codex/puppet-next-agy-20260919`
- base: `89846223be4d900108a5f7c4a9c8f1faa662eae9`
- owner: parent implementation/review lane; no main/other-worktree writes
- scope: native `agy-print` process-backed transport + public controller lifecycle + AGY-scoped qualification tests
- live AGY native process proof: passed; public CLI launch/qualification receipt remains separate
- external writes: none

## Current phase

Source slice implemented and independently repaired in this worktree. Native
runtime tests, nested AGY protocol parsing, transport-specific qualification
invalidation tests, and installed native process proof passed. Full discovery
now passes all 1,247 tests on this host after the bounded Darwin doctor census
guard. The existing PR remains open and unmerged.
PR #49 is open at
`https://github.com/saariuslystoned/SaariusSkills/pull/49`; it is not merged.

## Repair pass closeout

- repair commit: `89fd495902c163c60c0e63b34ef422b5e0139e5a`
- public AGY checkpoint import now reaches the shared handoff validator; review and acceptance use shared identity, actor, verdict, and terminal-criteria records
- native AGY launch/send/resume/checkpoint/review/accept/halt now use the shared operation lock, durable lease admission/activation, current process identity, and crash-safe request ledger
- owned-child halt preserves recorded birth-bound descendants across reparenting and treats ambiguous identity as non-gone
- selected transport is carried through census and checked against qualification scope at doctor/launch
- public CLI qualification receipt/live proof remains pending; no such receipt was available for this pass

## Repair pass 2 closeout (2026-09-19)

- repair commits: `4da746d`, `ecff5fc`
- delegated checkpoint-admission slice: Cursor ACP job `e7692e33-c502-4e8e-bbc2-204b8b23957c`, selected `grok-4.6[effort=high,fast=true]`; focused worker tests passed and the diff was independently inspected
- public AGY checkpoint import/review/accept now share runtime, protocol, conformance-fixture, source-identity, and state-admission gates
- parent-gone halt uses the lease-bound identity and preserves retryable owned-child cleanup; resume refreshes executable/worktree identity before lease admission and reconciles failed admissions
- refused sends do not create delivery intent; historical request IDs are retained without silent eviction
- Linux `/proc` disappearance is typed as `ProcessVanished`; blocked doctor transports skip unrelated live PID census
- focused repair tests: 72 passed; probe/qualification batch: 164 passed; full discovery: 1,247 passed in 349.622s
- exact-head CI run `35426959846` passed on Ubuntu 24.04 and macOS 26, including test, compile, and smoke steps
- exact public CLI qualification receipt/live proof remains pending; no external sends, deploys, merges, or account changes were performed

## Repair pass 3 closeout (2026-09-19)

- Cursor ACP worker job `54d7aa3c-f71a-4ed7-a336-e89985625f51` completed on the exact worktree with selected `grok-4.6[effort=high,fast=true]`; selected-transport qualification slice was independently inspected
- qualification probe now fails closed before execution for unsupported selected transports; no AGY-print receipt is stamped from tmux execution
- public AGY continuation now uses the shared follow-up/proof-assignment envelopes, preserves source review protocol phases, and replays submitted receipts without reactivating old process identity
- resume cleanup now proves owned-tree halt before releasing a post-start lease; failed terminal leases are haltable only with a HALTED observation
- focused repair suite: 110 passed; worker qualification batch: 144 passed
- full discovery: 1,258 tests; 1 unrelated timing-sensitive Codex doctor-child assertion failed in the aggregate run and passed on exact isolated rerun
- exact public CLI AGY qualification receipt/live proof remains pending; no external sends, deploys, merges, or account changes were performed
- corrected exact-head CI run `35445828955` passed on Ubuntu 24.04 and macOS 26 after redacting machine-local proof paths

## Repair pass 4 closeout (2026-09-19)

- authoritative packet `/audit-packet/20260919-pr49-repair4-review/` reproduced the real-start persistence, source admission, cleanup recovery, and proof-path defects before edits
- Cursor ACP job `99d9be46-cd4d-4dd7-9aa0-7c22fe7c5ca4` completed on the exact worktree with selected `grok-4.6[effort=high,fast=true]`; protocol-state slice independently inspected
- real AGY start/persistence now commits the admitted continuation transition; HALTED source sessions can resume proof assignment and restore SOURCE_ACCEPTED after start
- failed resumed cleanup binds the runtime's exact process identity before cleanup and public halt can recover an active/launching fenced generation; ambiguous identity remains unreleased
- focused repair suite: 113 passed; public recovery regression exercises first cleanup failure followed by successful public halt
- proof note no longer contains machine-local home-directory literals
- full discovery: `python3 -m unittest discover -s tests -q` → 1,261 passed in 227.191s
- exact-head CI run `35452109013` for `ff197b71bd6e546728175011aa9cd1cf7ae137d5` passed on Ubuntu 24.04 and macOS 26, including test, compile, and smoke steps
- PR #49 remains open and unmerged; public AGY qualification receipt/live proof remains pending

## Repair pass 5 closeout (2026-09-19)

- authoritative review packet `<audit-packet>/20260919-pr49-repair5-review/` reproduced two remaining source-flow defects: reviewed source HEAD was not rebound for resume, and exact source proof-assignment replay reconstructed a different envelope
- Cursor ACP readiness passed on the exact worktree using the native `<cursor-agent> acp` route; selector `cursor-grok-4.6-high` resolved to `grok-4.6[effort=high,fast=true]`
- source-identity worker job `5732d1e4-2a28-404c-9e01-e8d5beafab05` completed; reviewed `source_accept` now binds the current clean source workspace while preserving exact path/branch and ancestry checks; real commit-A → commit-B resume regression added
- replay worker job `5ad545b4-6b42-4668-ae21-9345f1785b04` failed closed with `BRIDGE_RESTARTED` before canonical handoff; its bounded partial replay diff was independently inspected and verified in the parent lane, with no replacement worker dispatched
- focused verification: 125 passed; `py_compile` and `git diff --check` passed
- full discovery: 1,264 passed in 270.995s
- adapted review probe now passes the source identity boundary and reaches the expected unsupported native transport; its mocked lease fixture lacks a real authority root for cleanup after that boundary
- packaging guard initially caught one literal home-directory path in this state file; the path was redacted in `d7a5306`, and the rerun passed
- source repair head `d7a5306398c2c49fb64d223d06544de5d6330bb9`; final proof closeout head `bae47d450bbd79a4d6dba9fe35608fd647b21d1e`; hosted CI run `35456997885` passed on Ubuntu 24.04 and macOS 26, including test, compile, and smoke steps
- public AGY qualification receipt/live proof remains pending; PR remains open and unmerged
