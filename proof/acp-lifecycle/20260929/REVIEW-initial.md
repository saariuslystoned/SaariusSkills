# Independent ACP lifecycle review

Repository: saariuslystoned/SaariusSkills
Head: b7ec8653ea513da30aec92d76835cf6a3c69afa0
Base: ec8995eae9a326c4ed26157d81f4b36db19a064d
Route: Bobby-authorized Codex subagent alternate independent review. No Conductor/legacy rail claim.

## Accepted finding

**[P2] Scope migration binder provenance to its exact job.** `bridge/acp-runtime/recovery.mjs:44` compares a job's binding binder against `existing.recoveries.at(-1).fromBinderId` even when that recovery belongs to an older job. `bridge/cursor-acp/host-policy.mjs:395` (and the equivalent two lanes) intentionally carries recovery history into normal successor bindings. After one legacy migration and one normally admitted successor, the successor job records the current stable binder but the last historical recovery records the old random binder. If that successor becomes interrupted with exact dead-owner/dead-worker proof, recovery fails `binding_job_mismatch` permanently. Use only a recovery entry scoped to this exact job when validating the original binder, and add a migrated-predecessor -> successor -> interrupted-successor recovery regression. Shared implementation affects all three lanes.

Reproduction: `node runs/acp-lifecycle-review-runs/20260929/successor-recovery-repro.mjs` (exit 0 confirms expected buggy refusal); output in `successor-recovery-output.txt`. Fixture uses a real normal binding replacement, persisted matching lease/session identity, synthetic missing-process observations, no providers or live state.

## Rejected concerns

- Async worker capture racing ordinary startup saves: pinned ACpx 0.19.3 awaits `onSpawned` at `dist/runtime.js:1025` and physical client admission at `dist/queue-owner-runtime-Dhr4gxNE.js:2844`, before session startup can return. No demonstrated race in this contract.
- Broker death being treated as worker cleanup: Cursor/Grok now require canonical cleanup completion; recovery independently observes every persisted worker when cleanup is uncertain. Owner disappearance alone is rejected.
- Unsupported protocol close automatically unlocking admission: fallback requires all exact launch identities to have matching exit observations; foreign launch exit, absent callback evidence and unavailable close remain fenced.
- Recovery mutating a successor: compare-and-swap preconditions reject changed job/binder; existing tests check unchanged successor bytes. Above finding is a false refusal, not an ownership bypass.
- Shared utility packaging omitted: runtime source digest includes lifecycle/recovery modules, and clean snapshot fixtures include them. Packaging verification recorded separately.

## Proof and limits

Read CONTRIBUTING.md and supplied Swarm AGENTS policy. Reviewed full diff, shared recovery/lifecycle implementations, broker admission/cleanup paths, conversation bind locking, native ACpx callback-await semantics, docs and proof claims. Local dependencies installed with `npm ci --ignore-scripts --no-audit --no-fund` in this isolated checkout.

Focused lifecycle + synthetic native smoke: 46 passed, zero failures/skips (`test-output.txt`). Shared and packaging tests recorded in PROOF.md after completion. Existing tests do not cover the confirmed successor-history failure. No source edits, commits, provider calls, installed-state changes, process killing, live recovery or production claims.

Disposition: request changes for P2 above. No other actionable issue demonstrated within this bounded review.

Public snapshot: detailed command outputs and standalone reproductions are retained in the isolated local review run; they are not included in this public text snapshot.
