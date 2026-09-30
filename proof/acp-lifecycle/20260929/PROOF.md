# ACP lifecycle repair proof

Repository: `saariuslystoned/SaariusSkills`
Branch: `codex/acp-lifecycle-recovery`
Base: `ec8995eae9a326c4ed26157d81f4b36db19a064d`
Reviewed source head: `38fcf2d189eedcbf070e5e02c9fb9cd8ce82e65d`.
The subsequent proof-only commit leaves reviewed code unchanged.

## Scope and provenance

Preserves merged unified discovery (#103), lock-reclaim hardening (#100),
and one-hour/four-hour timeout policy (#104). Installed source inspection
confirmed random default binders for Antigravity/Cursor and an existing stable
state-root binder for Grok. Recovery never supplies an old binder as the new
host identity, edits canonical live jobs, or sends process signals.

Reference inspected at exact upstream OpenClaw commit
`b725cc7b27f64ae1b1cf72eccc0bd5959d982839`: session-resource, session-owner,
runtime closeSession, runtime-process-cleanup, runtime-generations and ACP setup
guide. Adaptations and limits are in `docs/acp-lifecycle-recovery.md`.

## Reproducible verification

Use Node >=22.13 and each bridge's locked `npm ci --ignore-scripts --no-audit --no-fund`.
No provider or credential setup is needed.

- `node --test bridge/acp-runtime/test/lifecycle.test.mjs`: 48 passed.
- `node --test bridge/acp-runtime/test/local-lifecycle-smoke.test.mjs`: 1 passed.
- `node --test bridge/acp-runtime/test/*.test.mjs`: 107 passed in the worker run; independently 110 passed at the
  initial review head. Final exact-head lifecycle + native smoke: 49 passed,
  including the three newly added successor recovery regressions.
- `npm test --prefix bridge/grok-acp`: 85 passed, no skips.
- `npm test --prefix bridge/cursor-acp`: 97 passed, 11 explicit historical candidate/native opt-in skips.
- `npm test --prefix bridge/antigravity-acp`: 66 passed, 12 explicit historical candidate/native opt-in skips.
- `python3 -m unittest discover -s tests -q`: 60 passed.
- Shared utility syntax checks and `git diff --check`: passed.

Deterministic cases cover cleaned restart/follow-up, foreign owner rejection,
live/unknown/missing worker rejection, lease and session mismatches, active-job
rejection, exact launch exits for unsupported close, missing close refusal,
legacy proven-clean binding migration, history-preserving cleanup recovery,
interrupted publication and idempotent retry, and unchanged successor binding.
The native smoke runs pinned published ACpx against a real local synthetic
child twice across broker replacement. It observes exact child disappearance,
unsupported backend discard and fresh follow-up admission.

## Findings and delivery state

Accepted: process-random logical binders strand legitimate follow-ups; Cursor
lacks the observed-exit compatibility path; Cursor/Grok conflate terminal task
status with canonical cleanup completion. Addressed by this patch and focused
regressions.

Rejected as root cause: permissions and the current task timeout default.
Those policies remain independent and their regressions pass.

Required independent review: Bobby explicitly assigned a Codex subagent as a
bounded alternate route because current Conductor enrollment/capability evidence
is unavailable to this worker. Final source head `38fcf2d189eedcbf070e5e02c9fb9cd8ce82e65d`
has no remaining actionable findings. One independently reproduced P2 successor
provenance bug was accepted, repaired after a failing regression in all three
lanes, and independently re-verified. Accepted/rejected findings and test
receipts are preserved in `REVIEW-initial.md` and `REVIEW.md`. No Conductor/legacy
clean rail is claimed. No self-merge is authorized.

## Limits

All proof is deterministic or from a local synthetic peer. No production
stranded binding/job was recovered. No plugin install/reload, provider call,
external send, unrelated configuration edit or product-worktree mutation was
performed. Existing uncertain jobs without exact persisted worker receipts stay
fenced. Local-child exit does not prove backend history discard or cleanup of
detached descendants. Recovery requires approval of an exact live plan before
`--apply`; it only observes ownership and never kills workers.
