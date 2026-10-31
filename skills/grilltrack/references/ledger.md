# Durable ledger

Use `.grilltrack/ledger.json` as the single current projection and
`.grilltrack/events.jsonl` as append-only history. The ledger is
project-local, human-readable JSON, and machine-validatable.

## Directory contract

```text
.grilltrack/
  .gitignore        # ignores work/
  ledger.json       # canonical current projection
  events.jsonl      # append-only transition records
  archive/           # immutable closed ledger and event-log snapshots
  lineage/           # immutable fork inputs, plans, projections, apply receipts
  proof/             # curated evidence suitable for retention
  work/              # ignored candidates and renderer artifacts
    gates/           # human-guided checklists when needed
```

Do not auto-delete `work/`. If a referenced working artifact is unavailable,
mark that limitation and regenerate it from durable input or begin a new round.
Never claim to reproduce missing pixels exactly.

See [reconciliation.md](reconciliation.md) for the same-repository fork join.
An interrupted join leaves `work/reconcile-transaction.json`; ordinary commands
refuse that mixed state until the exact approved apply is retried.

## Core fields

The ledger records:

- `schema_version`, `track_id`, title, status, and timestamps;
- current focus, cadence, confirmation, and summary;
- stable decision identifiers and dependency links;
- accepted value, rationale, context, baseline, and candidate references;
- implementation and verification references;
- review reference, immutable source identity, result, classifications, and
  review history;
- active pause reason, context-boundary artifact references, next safe action,
  and last completed pause;
- delivery references recorded only after separate authorization;
- lifecycle status and immutable transition history;
- next-grill recommendation and alternatives;
- closeout facts.

Decision states are:

- `proposed`
- `locked`
- `implemented`
- `verified`
- `reopened`
- `superseded`
- `needs_reverification`
- `deferred`

## CLI transitions

Run `python3 scripts/grilltrack_ledger.py --help` for the exact flags.

Typical sequence:

```bash
python3 scripts/grilltrack_ledger.py --project "$ROOT" init \
  --title "Product direction"
python3 scripts/grilltrack_ledger.py --project "$ROOT" focus \
  --domain "product direction" --cadence sequential
python3 scripts/grilltrack_ledger.py --project "$ROOT" propose \
  --id direction-001 --scope durable \
  --question "Who is this for?" --choice "Operators"
python3 scripts/grilltrack_ledger.py --project "$ROOT" lock \
  --id direction-001 --user-reply "yes, operators first"
python3 scripts/grilltrack_ledger.py --project "$ROOT" confirm \
  --summary "Build the operator-first slice and verify its primary flow."
python3 scripts/grilltrack_ledger.py --project "$ROOT" implement \
  --id direction-001 --ref "file:src/product.ts"
python3 scripts/grilltrack_ledger.py --project "$ROOT" verify \
  --id direction-001 --ref "test:product-flow"
python3 scripts/grilltrack_ledger.py --project "$ROOT" review \
  --id direction-001 --source-identity "git:<full-commit-sha>" \
  --ref ".grilltrack/proof/review/PROOF.md" --result clean
python3 scripts/grilltrack_ledger.py --project "$ROOT" compact --output summary
```

### Decision scopes, live gatekeeper, and compaction

- **Scopes (`--scope durable | slice | deferral`)**:
  - `durable`: Permanent architectural or product invariants retained in the
    active ledger projection.
  - `slice`: Single-PR or tactical decisions that archive out of active
    `ledger.json` once `verified` and `compact` runs.
  - `deferral`: Parked work requiring `--revisit-when "<condition>"`. Locking a
    `deferral` transitions status to `deferred` with `deferred_reason` populated
    so future agents see an explicit revisit trigger instead of a permanent ban.
- **Live Lock Gatekeeper (`lock --user-reply` and `gate`)**:
  - Evaluates whether the proposed `choice` and `rationale` overlock beyond the
    user's reply, routing to TypeSafe Jev (`jev-1.13.0`) first and falling back
    automatically to the OpenAI Responses Decision API (`gpt-6.1-sol`) when Jev
    credits are exhausted, or to the deterministic local rubric offline.
- **Ledger Compaction (`compact`)**:
  - Moves `superseded` decisions, `verified` `slice` decisions, and prior
    per-decision `history[]` snapshots out of active `.grilltrack/ledger.json`
    into `.grilltrack/archive/compacted-<track-id>.json` (while keeping the
    append-only `.grilltrack/events.jsonl` log intact) and records
    `compacted_decision_ids` so active dependency links remain valid.

For a review with findings, pass one or more adjudicated classifications:

```bash
python3 scripts/grilltrack_ledger.py --project "$ROOT" review \
  --id direction-001 --source-identity "git:<full-commit-sha>" \
  --ref ".grilltrack/proof/review/PROOF.md" --result findings \
  --classification required_fix
```

Allowed classifications are `required_fix`, `reject_false_positive`, `defer`,
and `human_gate`. Recording `required_fix` marks the decision
`needs_reverification`; repair it through `implement`, `verify`, and a fresh
review bound to the new source identity.

Use `pause` at a session boundary and attach each source-linked artifact needed
to resume:

```bash
python3 scripts/grilltrack_ledger.py --project "$ROOT" pause \
  --reason "Waiting for attended setup" \
  --next-safe-action "Resume verification after the sanitized receipt exists" \
  --artifact-ref ".grilltrack/work/gates/setup.md"
```

Use `resume` when work naturally continues. It moves the active pause record to
`last_pause` and records the new activation mechanism.

Use `reopen` to revisit a prior decision; the tool marks transitive dependents
for re-verification. The optional `--activation '$grilltrack'` records an
explicit invocation; omission records natural implicit activation.

After closeout, start another track with:

```bash
python3 scripts/grilltrack_ledger.py --project "$ROOT" new \
  --title "Next product direction"
```

`new` accepts only a valid closed predecessor. It snapshots the closed ledger
and event log under `.grilltrack/archive/<track-id>/`, leaves curated proof in
place so references remain valid, and records `predecessor_track_id` on the new
active ledger. Existing archives are never overwritten.

## Invariants

- Track IDs and decision IDs are stable and unique.
- Dependencies must reference existing decisions and may not form cycles.
- Implementation requires confirmed shared understanding.
- Verification requires an implemented or re-verification-needed decision.
- Review requires a verified decision, an immutable source identity, and an
  adjudicated clean result or finding classifications.
- A review classified `required_fix` returns the decision to
  `needs_reverification`.
- A paused projection records its reason, next safe action, and artifact refs.
- Closed tracks are immutable.
- Clean closeout rejects decisions still proposed, locked, implemented,
  reopened, or needing re-verification.
- Reopening and superseding preserve history.
- No ledger command invokes Git, a forge, deployment, or another delivery
  system.

Use `validate` before verification handoff and closeout. Do not bypass a
validation failure by hand-editing the projection.
