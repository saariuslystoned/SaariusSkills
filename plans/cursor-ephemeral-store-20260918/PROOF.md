# Proof

Source review of pinned acpx 0.16.0 showed FileSessionStore.save serializes record.messages and title. No existing session/conversation store was opened. The prior metadata-only broker record did not cover this nested runtime persistence.

Regression uses a synthetic record with the real default runtime store. Before the fix, saving created an acpx directory. After the fix, no files are created, load/save copy isolation holds, a new runtime has no previous record, and shutdown clears records. All 11 bridge tests and 12 packaging tests pass. These are hermetic tests; live proof pending.

The runtime now stores internal records only in memory. Broker job metadata, hashes and bounded handoffs remain durable. Restart already fails in-flight jobs closed and never resumes stale backend sessions. Existing older stores are neither inspected nor migrated nor deleted.

Old active delegation was cancelled and the exact task-owned supervisor gracefully stopped before new use. No unrelated processes were touched. Parent review confirmed load/save semantics against the pinned public runtime store interface; independent Cursor review pending.
