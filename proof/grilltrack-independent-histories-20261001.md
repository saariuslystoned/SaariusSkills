# Independent same-repository GrillTrack histories

Reproduction on the original implementation: the synthetic no-ledger-base
regression exited 2 with `snapshot requires ledger and events`. Both tips held
valid independent histories after a shared Git ancestor without canonical state.

The supported plan now records `base_provenance: "no-ledger-base"`, binds exact
immutable inputs and title, and retains both complete source ledgers, event
streams, and archives. The absent base is recorded in the manifest; no base
ledger or events are fabricated. Different bodies under one decision ID still
require explicit adjudication, and unrelated Git inputs are rejected.

Validation:

- `python3 -m unittest tests.test_reconcile`: 16 tests passed.
- `python3 -m unittest discover -s tests`: 97 tests passed.
- `git diff --check`: passed.
- Original-CLI synthetic completed apply: exit 0; updated-CLI exact retry:
  exit 0 and valid state. Original-CLI interrupted apply: exit 86; updated-CLI
  exact recovery: exit 0 and valid state. Existing shared-base plan/digest and
  projection shape remain unchanged.
- Empty or unterminated no-ledger-base canonical/archive streams on either tip
  reproduced failure before the guard; all eight regression cases pass after it.
- A private immutable-tuple rehearsal produced identical reviewable plans in
  two dry runs with unchanged disposable canonical files. No apply was run.
  Raw histories, tuple identities, and plans are excluded from this public proof.

Implementation used the native Cursor ACP lane with advertised GPT-5.6 Luna
Medium and effective `approve-all`. Terminal task and child cleanup were
confirmed before each replacement job. One interrupted broker required an
explicitly operator-approved, history-preserving recovery; the recovery
signalled no processes. No plugin release, global installation, product
integration, or merge was performed. Separate review and CI results belong to
the exact candidate revision and are recorded in the pull request.
