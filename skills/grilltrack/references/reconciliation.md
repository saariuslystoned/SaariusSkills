# Same-repository fork reconciliation

Use `reconcile` when independent continuations need a new composed track. The
command requires three full immutable Git commit IDs in the target repository:
the common base, the current snapshot, and the incoming snapshot. The base
must be an ancestor of both forks. Two base modes are supported: a
shared-ledger base, where both forks retain the base track's exact event prefix
and either continue that track or have its direct successor active; and a
no-ledger base, where the Git ancestor contains neither canonical ledger nor
event stream and the two complete fork histories are reconciled independently.
Shared-ledger forks may also be later canonical joins that retain the exact
base ledger and event stream through their applied immutable lineage. The base
can appear in a reachable input snapshot or an earlier join's exact recomputed
projection. The CLI
recomputes retained plans from their Git inputs and checks plan identities,
source bytes, projections, receipts, and the live join's event prefix. Newly
introduced joins must name source commits ancestral to their retaining fork.
Older joins inherited from the common base are bound to that base's exact
artifact bytes, accommodating earlier squash or ordinary single-parent commits.
New roots must be reachable through validated live source joins. Historical
roots can be seeded only through matching common-base records and exact inherited
artifacts; an unrelated fork archive cannot establish reachability by naming a
plan ID. Embedded prior lineage remains usable without duplicate top-level roots.
Missing or changed inherited artifacts and unrelated retained joins fail closed.
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
history or proof fields, is a conflict requiring explicit adjudication. Supply
a strict JSON adjudication file when the human has selected one retained role:

```json
{
  "schema": "grilltrack/adjudication/v1",
  "refs": {
    "base": "<full-base-commit>",
    "current": "<full-current-commit>",
    "incoming": "<full-incoming-commit>"
  },
  "decisions": {
    "decision-id": {
      "role": "incoming",
      "reason": "The incoming record is completed and has the newer lifecycle."
    }
  }
}
```

The refs must exactly match the command, every conflicting decision must be
selected, and the role must name an unambiguous body present in the live or
base-track archive source. A nested joined fork contributes its live decision
body; retained older base bodies are ancestry evidence, not competing bodies
for that role. Unknown fields, duplicate JSON keys, malformed
values, unnecessary selections, and blank reasons fail closed. The selection
and reason are part of the plan digest. The tool never chooses a winning fork.
Invalid archives, event identities, missing
streams, unrelated commits, and a target differing from the current snapshot
also block the plan.

For an adjudicated plan, use the file with the exact refs and title used for
the plan:

```bash
ADJUDICATION_FILE="$PROJECT_ROOT/adjudication.json"
python3 scripts/grilltrack_ledger.py --project "$PROJECT_ROOT" reconcile \
  --base-ref "$BASE_COMMIT" --current-ref "$CURRENT_COMMIT" \
  --incoming-ref "$INCOMING_COMMIT" --title "Composed integration" \
  --adjudication-file "$ADJUDICATION_FILE" > adjudicated-plan.json
```

After the operator approves that concrete plan, set `APPROVED_PLAN_SHA256` to
its `plan_id` and repeat the same inputs and title:

```bash
python3 scripts/grilltrack_ledger.py --project "$PROJECT_ROOT" reconcile \
  --base-ref "$BASE_COMMIT" --current-ref "$CURRENT_COMMIT" \
  --incoming-ref "$INCOMING_COMMIT" --title "Composed integration" \
  --apply "$APPROVED_PLAN_SHA256"
python3 scripts/grilltrack_ledger.py --project "$PROJECT_ROOT" validate
```

For the adjudicated plan, set `APPROVED_PLAN_SHA256` to its `plan_id` and
repeat the same adjudication file, refs, title, and plan digest exactly:

```bash
python3 scripts/grilltrack_ledger.py --project "$PROJECT_ROOT" reconcile \
  --base-ref "$BASE_COMMIT" --current-ref "$CURRENT_COMMIT" \
  --incoming-ref "$INCOMING_COMMIT" --title "Composed integration" \
  --adjudication-file "$ADJUDICATION_FILE" \
  --apply "$APPROVED_PLAN_SHA256"
```

The adjudication file path is not bound; its validated contents are bound.
Changed selections, reasons, or refs therefore reject the old approval, even
when the file is supplied at the same path.

New plans use `grilltrack/reconcile/v2`. Apply stores each distinct historical
byte sequence once under `.grilltrack/lineage/objects/sha256/<digest>` and
shares identical directory subtrees through a canonical Merkle DAG. Each
`.grilltrack/lineage/<plan-id>/retention.json` references its logical root; its
`applied.json` reference marker is published only after the canonical ledger
and event transaction succeeds. Exact byte hashes, safe paths, complete object
closure, source commits, plan identities, projections, receipts and live event
prefixes are validated before history is accepted. A hash-valid foreign body
still fails when it differs from the recomputed source history.

The logical root preserves the original role ledgers, complete event streams,
archives, plan, projection and receipt. Its `snapshots/<role>/lineage.json`
references the source's immutable lineage tree instead of copying old lineage
inside another snapshot. Source definitions are reconstructed once per root;
new joins never create backups of earlier snapshots. The plan binds compact
per-role lineage-tree hashes in `retention.lineage`, as well as the exact refs,
role file hashes, provenance and explicit adjudication. Inspect source bodies
through these references, not by expecting physical snapshot directories.

In no-ledger-base mode, the plan retains the base commit ref and empty base
snapshot map; no canonical base files are fabricated. Existing canonical
archives remain unchanged. Only validated ledger/event data and immutable join
artifacts enter the reference graph; source work directories, private proof
and unrelated project files remain excluded. Unreferenced source objects are
not imported. Referenced objects, including prior source-index edges, must exist
and match their addresses; missing or corrupt data fails closed.

### Compatibility and migration boundary

The storage-aware CLI reads existing v1 raw snapshots without changing or
removing them. A later v2 reconciliation can reference their exact contents
while retaining the existing files unchanged. This additive transition can
leave historical v1 copies alongside the new shared store; it does not claim
to compact already committed history or authorize deleting those originals.
New storage growth shares contents and subtrees instead of making further raw
snapshot copies. Destructive compaction of existing history is a separate,
reviewed migration, outside this command.

New plans always bind the v2 format in their digest. An unapplied v1 approval
cannot silently authorize a v2 apply: regenerate and approve a fresh plan.
Completed v1 retries and interrupted v1 transactions with their original journal
continue under the original v1 digest, bytes and recovery contract. Old
pre-journal staging remains preserved; replan with the storage-aware CLI and
obtain the new approval rather than removing its artifacts or assuming the old
digest authorizes a different representation.

Earlier reconciler versions cannot read v2 references and must not be used for
reconciliation or recovery once a project has v2 lineage. Install and verify
the storage-aware version through the normal owner-approved plugin workflow
before using it in a product. Never hot-edit installed bytes, rewrite a product
ledger, or treat a source PR as permission to migrate or resume paused work.

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

Adjudication is currently supported only for shared-ledger-base composition.
No-ledger-base histories fail closed on any cross-fork decision-body conflict;
they do not invent a common adjudication source or synthetic base projection.
