# Same-repository fork reconciliation

Use `reconcile` when independent continuations of one track need a new composed
track. It accepts three full immutable Git commit IDs in the target repository:
the common base, the snapshot matching the target's current canonical state,
and the incoming continuation. The base must be an ancestor of both forks.
Each fork must retain the base track's exact event prefix and either continue
that track or have its direct successor active. Shared historical archives must
remain byte-identical. This does not implement cross-repository orchestration
or concurrent live writers (related issues #90 and #101).

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

Apply preserves all three source ledgers, full event streams, and archives under
`.grilltrack/lineage/<plan-id>/snapshots/{base,current,incoming}/`. Competing
versions of the base track therefore remain distinct. Existing canonical
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
