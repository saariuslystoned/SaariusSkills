# GrillTrack nested-lineage compatibility

Baseline: `b82f88af478bd3831885ad17029628b0be6bcf11`.
Reconciliation script SHA-256: `e5386fe87cbda9df22e1f108755abef2e4cf1b9d7c84809c2b8bdafab0e34111`.

A later canonical join starts a new event stream. Treating it as an ordinary
continuation incorrectly rejects a common base preserved in its immutable
source snapshots. The repair validates that retained proof, preserves its full
closure, and keeps historical records out of a nested fork's live-role selection.

Validation recomputes each retained plan and projection from exact Git commits,
checks source snapshot bytes, receipts, plan hashes and live event prefixes,
and rejects orphaned roots. Inherited common-base artifacts must match that
base byte-for-byte. New roots must connect through validated live source joins;
historical roots are seeded only by matching common-base ledger records and
projections. Recursively validated embedded source lineage supplies prior roots
without requiring duplicate top-level directories. This supports earlier single-parent or squashed joins whose
original source commits no longer appear in current ancestry. New roots still
require their source commits to be ancestors of their retaining fork. Event
identity checks cover retained history as well as canonical/archive streams.
Reachable prior join projections can also supply the exact common base; their
source metadata and event prefix must match the validated join.
Existing direct/no-ledger plan digests and strict adjudication remain unchanged.

The one authorized Cursor Luna Medium implementation turn completed and released
its workspace. Parent qualification rejected its incomplete nested retention.
The owning Codex fallback repaired and qualified the candidate; the worker patch
and rejected-output evidence remain in the local run packet.

Local verification commands:

- `python3 -m unittest tests.test_nested_reconcile -v`: 11 tests passed, including
  exact retention, deterministic planning, a fourth join, a reachable prior-join
  projection as the common base, inherited single-parent
  history, new foreign-ref rejection, missing/tampered artifacts, conflicting
  retained event IDs, event-prefix mismatch, archive-based orphan laundering rejection, crash recovery
  and retry integrity.
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

Independent Spark/OpenClaw review of the first frozen revision identified two
findings. The enumeration finding was rejected: combined Git `-rz` includes
recursive `-r`, proved by Git blob enumeration and functional CLI tests. The
prior-projection finding was accepted: a new neutral regression failed before
the reachable projection check and passed after it. Both dispositions and
reviewer-native artifacts are preserved in the local packet. The first two
revisions' four CI checks passed. A second native comprehensive review found
archive-based orphan laundering; that finding was accepted and reproduced by a
neutral source-ancestral join spliced through unrelated archive metadata. The
repair restricts reachability to validated live chains and inherited common-base
records, while preserving embedded prior proof. The revised eleven-test suite
includes both the attack and another subsequent join. Each changed revision
requires fresh exact-head CI and review.

Exact-head CI and independent review qualification are recorded in the PR and
local run proof. This artifact does not claim review completion. Product apply,
merge and global plugin installation require their own concrete owner gate.
