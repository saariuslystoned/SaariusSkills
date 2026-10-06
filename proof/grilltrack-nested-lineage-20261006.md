# GrillTrack nested-lineage compatibility

Baseline: `b82f88af478bd3831885ad17029628b0be6bcf11`.
Reconciliation script SHA-256: `913ce10ed19f10f13362fb75902b8f85fa4bb8478f97e7a3d45b1a4902b24e6f`.

A later canonical join starts a new event stream. Treating it as an ordinary
continuation incorrectly rejects a common base preserved in its immutable
source snapshots. The repair validates that retained proof, preserves its full
closure, and keeps historical records out of a nested fork's live-role selection.

Validation recomputes each retained plan and projection from exact Git commits,
checks source snapshot bytes, receipts, plan hashes and live event prefixes,
and rejects orphaned roots. Inherited common-base artifacts must match that
base byte-for-byte. This supports earlier single-parent or squashed joins whose
original source commits no longer appear in current ancestry. New roots still
require their source commits to be ancestors of their retaining fork. Event
identity checks cover retained history as well as canonical/archive streams.
Existing direct/no-ledger plan digests and strict adjudication remain unchanged.

The one authorized Cursor Luna Medium implementation turn completed and released
its workspace. Parent qualification rejected its incomplete nested retention.
The owning Codex fallback repaired and qualified the candidate; the worker patch
and rejected-output evidence remain in the local run packet.

Local verification commands:

- `python3 -m unittest tests.test_nested_reconcile -v`: 9 tests passed, including
  exact retention, deterministic planning, a fourth join, inherited single-parent
  history, new foreign-ref rejection, missing/tampered artifacts, conflicting
  retained event IDs, event-prefix mismatch, crash recovery and retry integrity.
- `python3 -m unittest tests.test_reconcile -v`: 30 tests passed, covering compatibility,
  adjudication, graph validation and transactions.
- CLI help, syntax parsing and `git diff --check` passed.

A separate read-only exact-input plan check retained 30 live decisions, preserved
27 explicitly proposed current-role conflict bodies and histories, and produced
a repeat-identical digest without changing product state. Its proposed plan,
manifest, input/output hashes and source identity remain in the local sealed
packet; no foreign ledgers or raw histories are committed here.

The first full-suite run exposed the changed legacy prefix diagnostic. That was
corrected before freezing source, and its targeted regression passes. Printed
ACP/policy mismatch messages belong to expected negative fixtures; they are not
unrelated suite failures.

Exact-head CI and independent review qualification are recorded in the PR and
local run proof. This artifact does not claim review completion. Product apply,
merge and global plugin installation require their own concrete owner gate.
