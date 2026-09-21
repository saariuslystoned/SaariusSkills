# AGY Candidate Cleanup Implementation

status: `IMPLEMENTATION_CHECKPOINT_READY_FOR_PARENT_REVIEW`
updated_at: `2026-09-21`
worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-agy-candidate-cleanup-20260921`
branch: `codex/puppet-agy-candidate-cleanup-20260921`
base_commit: `6a9140f81b1850a0b39935bb8cd3e58b9ca0f0e2`
base_tree: `2c4a2142266a6f7eaa80873a609935d0e6736e38`
canonical_provider_job: `not_allocated`

This is the bounded AGY candidate driver/adapter repair checkpoint. It is not
formal provider qualification and does not claim OAuth, live AGY account, or
production model readiness.

## Gates

- [x] Fresh isolated checkout from accepted PR68 shared interface.
- [x] AGY-only driver/adapter/test changes; Cursor sources untouched.
- [x] Exact pinned `acpx-0.18.0.tgz` materialized task-locally and hash verified.
- [x] Unsupported close no longer swallowed by the AGY controller driver.
- [x] Exact process lifecycle wait/snapshot reaches the AGY Python adapter.
- [x] Requested/current model receipt persists before cleanup can fail.
- [x] Matched worker exit admits local cleanup without claiming backend discard.
- [x] Surviving worker fences replacement and preserves model evidence.
- [x] Offline and actual public-runtime synthetic-peer regressions pass.
- [ ] Parent review and exact source-head acceptance.
- [ ] One authorized stacked draft PR.
- [ ] Separate formal AGY provider qualification.
