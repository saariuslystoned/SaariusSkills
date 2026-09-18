# Proof

Source review of pinned acpx 0.16.0 showed FileSessionStore.save serializes record.messages and title. No existing session/conversation store was opened. The prior metadata-only broker record did not cover this nested runtime persistence.

Regression uses a synthetic record with the real default runtime store. Before the fix, saving created an acpx directory. After the fix, no files are created, load/save copy isolation holds, a new runtime has no previous record, and shutdown clears records. All 11 bridge tests and 12 packaging tests pass. These are hermetic tests; live proof pending.

The runtime now stores internal records only in memory. Broker job metadata, hashes and bounded handoffs remain durable. Restart already fails in-flight jobs closed and never resumes stale backend sessions. Existing older stores are neither inspected nor migrated nor deleted.

Old active delegation was cancelled and the exact task-owned supervisor gracefully stopped before new use. No unrelated processes were touched. Parent review confirmed load/save semantics against the pinned public runtime store interface; independent Cursor review pending.

## Independent review and real-runtime proof

Independent Cursor ACP review at `c67a203304ef7a6894fa1bbba95358e7ff6cd06d` found no blockers and passed all 11 bridge tests. Accepted: public load/save interface matches, persistent session keys match record IDs, records clone safely, shutdown flushes before memory clearing, and no embedded-runtime disk-store path remains. Rejected: file-backed runtime persistence is covered by metadata-only broker records.

Parent live job `5bcf97eb-0a46-4d32-8858-76bcb56856a6` requested `cursor-grok-4.6-high` and confirmed selected/current `grok-4.6[effort=high,fast=true]` from 38 advertised models. It wrote the exact expected marker to its supplied workspace, refused active-turn steering, and completed. No nested acpx runtime directory was created. An independent review job through the same frozen supervisor also created no nested runtime store. Only directory existence was checked; no session/conversation file was opened. Broker shutdown completed for the probe.

The review ran in a separate candidate workspace and did not modify the frozen supervisor. This follow-up changes proof only; final-head Linux/macOS CI is still the merge gate.
