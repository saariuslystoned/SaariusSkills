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
  proof/             # curated evidence suitable for retention
  work/              # ignored candidates and renderer artifacts
    gates/           # human-guided checklists when needed
```

Do not auto-delete `work/`. If a referenced working artifact is unavailable,
mark that limitation and regenerate it from durable input or begin a new round.
Never claim to reproduce missing pixels exactly.

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
  --id direction-001 --question "Who is this for?" --choice "Operators"
python3 scripts/grilltrack_ledger.py --project "$ROOT" lock --id direction-001
python3 scripts/grilltrack_ledger.py --project "$ROOT" confirm \
  --summary "Build the operator-first slice and verify its primary flow."
python3 scripts/grilltrack_ledger.py --project "$ROOT" implement \
  --id direction-001 --ref "file:src/product.ts"
python3 scripts/grilltrack_ledger.py --project "$ROOT" verify \
  --id direction-001 --ref "test:product-flow"
python3 scripts/grilltrack_ledger.py --project "$ROOT" review \
  --id direction-001 --source-identity "git:<full-commit-sha>" \
  --ref ".grilltrack/proof/review/PROOF.md" --result clean
```

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
