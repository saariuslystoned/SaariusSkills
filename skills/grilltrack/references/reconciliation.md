# Same-repository fork reconciliation

Use `reconcile` when independent continuations need a new composed track. The
command requires three full immutable Git commit IDs in the target repository:
the common base, the current snapshot, and the incoming snapshot. The base
must be an ancestor of both forks. Two base modes are supported: a
shared-ledger base, where both forks retain the base track's exact event prefix
and either continue that track or have its direct successor active; and a
no-ledger base, where the Git ancestor contains neither canonical ledger nor
event stream and the two complete fork histories are reconciled independently.
In both modes, shared historical archives must remain byte-identical where
applicable. This does not implement cross-repository orchestration or
concurrent live writers (related issues #90 and #101).

Operate in an isolated integration checkout with one owner. Fetch and reread
the final source heads after author repairs. Earlier rehearsal pins are fixture
evidence; regenerate the plan before any real apply. Do not run this against an
author's active product checkout or reuse an approval digest after inputs change.

From this skill directory, with `PROJECT_ROOT` and the full `BASE_COMMIT`,
`CURRENT_COMMIT`, and `INCOMING_COMMIT` assigned to the reviewed final inputs:

```bash
python3 scripts/grilltrack_ledger.py --project "$PROJECT_ROOT" reconcile \
  --base-ref "$BASE_COMMIT" --current-ref "$CURRENT_COMMIT" \
  --incoming-ref "$INCOMING_COMMIT" --title "Composed integration" > plan.json
```

Planning writes no project state. Inspect `plan.json`: exact refs, file hashes,
source provenance for every decision, decision union, and decisions requiring
new verification. A shared decision ID with any different body, including
history or proof fields, is a conflict requiring explicit adjudication. The
tool never chooses a winning fork. Invalid archives, event identities, missing
streams, unrelated commits, and a target differing from the current snapshot
also block the plan.

After the operator approves that concrete plan, set `APPROVED_PLAN_SHA256` to
its `plan_id` and repeat the same inputs and title:

```bash
python3 scripts/grilltrack_ledger.py --project "$PROJECT_ROOT" reconcile \
  --base-ref "$BASE_COMMIT" --current-ref "$CURRENT_COMMIT" \
  --incoming-ref "$INCOMING_COMMIT" --title "Composed integration" \
  --apply "$APPROVED_PLAN_SHA256"
python3 scripts/grilltrack_ledger.py --project "$PROJECT_ROOT" validate
```

In shared-ledger-base mode, apply preserves all three source ledgers, full
event streams, and archives under
`.grilltrack/lineage/<plan-id>/snapshots/{base,current,incoming}/`. Competing
versions of the base track therefore remain distinct. In no-ledger-base mode,
apply retains only the current and incoming fork snapshots; the plan retains
the base commit ref and an empty base snapshot hash map to prove the absence
of canonical state, and no base files are fabricated. Existing canonical
archives remain unchanged. Only ledger/event files are imported; source work
directories, private artifacts, and unrelated project files are excluded.

The new canonical track retains original decision IDs and source provenance.
Locked, implemented, verified, and already invalidated decisions become
`needs_reverification`; current verification/review claims are cleared. Prior
history and implementation references remain, with exact original bodies in
the snapshots. Proposed, reopened, deferred, and superseded decisions keep
their states. Focus, pause, recommendation, and closeout start empty. The
canonical event stream starts with `track_reconciled`, referring to the retained
streams rather than flattening competing histories. Timestamps come from the
latest source ledger timestamp to keep plans and retry artifacts deterministic.

Run composed acceptance tests and obtain an independent review against the
exact integration source before recording verification/review and closure.
Source fork proof does not establish composed behavior.

The plan digest binds exact inputs and title. Repeating a completed apply is a
no-op that preserves later progress and checks retained source integrity.
Caught publication failures restore both canonical files. A process interruption
leaves a journal, and ordinary ledger commands refuse mixed canonical state.
Retry the exact approved command to recover; recovery refuses a target altered
outside the known old/new projections. Do not delete the journal to bypass this
guard. This is process interruption recovery, not a guarantee against storage
loss or concurrent writers.

Interruption can leave temporary staging files inside lineage directories;
exact retry does not require deleting them. Final immutable paths expose only
complete bytes and never replace different retained history.

If the immutable Git base is a shared repository ancestor but contains neither
canonical ledger nor canonical event stream, the plan records
`base_provenance: "no-ledger-base"`. The current and incoming snapshots are
then independent complete histories: their live decision composition and event
identities are reconciled without inventing a base ledger or event prefix.
Decision bodies are also compared across every current and archived ledger in
the two complete fork snapshots; a differing body under the same ID requires
explicit adjudication, while an identical body is accepted. Archived
decisions remain historical: they are retained byte-for-byte in the lineage
snapshots but are excluded from the composed live projection. A base containing
only one canonical file, or any malformed/one-sided current or incoming pair,
remains invalid. Shared-ledger-base reconciliation keeps the exact-prefix,
archive, plan, digest, and projection semantics above.
