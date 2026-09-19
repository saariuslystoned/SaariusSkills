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
