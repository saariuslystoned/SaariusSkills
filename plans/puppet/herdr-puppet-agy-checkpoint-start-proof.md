# Herdr-Puppet AGY checkpoint-start proof

## Verdict

`keep` the checkpoint-driven AGY start flow at source
`e104773919097d0cf3e070ee350d906de762a8dc`.

One fresh, explicitly owned Herdr row launched AGY with the bound
`gemini-3.7-flash-high` selector, sent the wrapped initial message exactly
once without asking the operator whether AGY was ready, and advanced
`unverified -> checkpoint_pending -> checkpoint_verified` only after the
matching sequence and nonce STATUS checkpoint. A later device-proof steering
turn returned ACTION_REQUIRED and the controller preserved the exact row; it
did not resend or infer success.

## Private evidence

- Run ID: `pr28-phone-proof-20260814-a4`
- Private controller root:
  `~/Developer/_machine-runs/herdr-puppet-pr28-phone-proof-20260814-a4`
- Exact run-owned identity: tab `w2:t6`, pane `w2:p6`, terminal
  `term_65905303b8aff18`
- Herdr: `0.7.3`, protocol `16`
- Harness binding fingerprint:
  `354f7d56daeaaa6e913548234dbc79f985fef7658c32110278646add55d9785f`
- Bound remote source intent: repository `saari-co/swarmpocket`, worktree
  `<remote-home>/Developer/worktrees/swarmpocket-pr28-phone-proof-20260814-a3`

The private packet retains `plan.json`, `lease.json`, and `events.jsonl`.
Its generated `STATE.md` and `PROOF.md` remain initialization snapshots
(`planned` / `Pending`) and are not terminal truth; the final lease plus
append-only event journal are authoritative for the transitions below. The
packet contains local machine paths and is not a public transcript artifact.
No pane text, SSH target, process ID, credential, account identifier, prompt
body, or device identifier is copied into this curated proof.

A separate read-only SSH check immediately before the row observed the remote
worktree at `b8ce4e43941e61c915ca7993418caf76c8c38d5a` with an empty
`git status --porcelain=v1`. That check corroborates the bound path but is not
derived from the controller lease.

## Observed transition

The controller recorded this exact order:

1. Shell STATUS preflight at sequence 1 matched on its first wait.
2. The create-only in-row census at sequence 2 revalidated the stable
   controller-attested executable, profile, source, model, and launch-vector
   facts; only its observation time advanced.
3. `qualification-harness-launch` acknowledged the only harness launch at
   sequence 3 at `2026-08-14T17:32:52.224775Z`.
4. `qualification-send.v2` acknowledged one wrapped initial pane input at
   sequence 4 at `2026-08-14T17:33:41.136567Z`, 48.912 seconds after launch.
   The receipt remained scoped to `herdr_pane_input_only`, reported
   `harness_acceptance: unverified`, and moved readiness only to
   `checkpoint_pending`.
5. The first sequence-4 `qualification-beacon-wait.v2` observed STATUS at
   `2026-08-14T17:33:50.554317Z`, no more than 9.418 seconds after the send,
   with nonce hash
   `d0dd96e2a15a106ff284a6d2dbb00489c7a233c81fc53fe64a2bb6f9388b34f1`.
   Only then did readiness become `checkpoint_verified`.

The journal contains zero `qualification.harness-ready` events, zero startup
gate events, and exactly one successful initial send at sequence 4. The
controller never asked the operator to confirm a ready input surface.

## Downstream steering check

After readiness was checkpoint-verified, one separately sequenced steering
message asked the same visible AGY row to attempt registered-Pixel PR #28
proof through Pixel Use. The first bounded terminal wait did not match. The
same-sequence, same-nonce second wait observed ACTION_REQUIRED and atomically
preserved the row. There was no second steering input.

The controller proof makes no claim about the device task beyond the exact
ACTION_REQUIRED checkpoint class and preserved lease. The worker wrote a
separate private device packet outside the controller journal; those artifacts
require their own source, image, APK, and route audit before promotion. They
are not evidence for this Herdr-Puppet change and are not a PR #28
merge-readiness claim.

## Source validation

Exact source `e104773919097d0cf3e070ee350d906de762a8dc` passed:

- `python3 -m unittest discover -s tests -p 'test_*.py'` — 254 tests;
- `python3 -m compileall -q skills/herdr-puppet/scripts`;
- JSON parsing for active lease-v3 and frozen lease-v1/v2 schemas;
- external `jsonschema.Draft202012Validator` alignment over 22 generated valid
  states and 8 forged invalid states;
- the skill quick validator and plugin validator;
- the 500-line `SKILL.md` packaging cap;
- `git diff --check` and a clean exact-source worktree.

Independent code and contract audits found no remaining required fix. The
frozen lease-v2 schema is included in the controller adapter fingerprint and
keeps its pinned canonical digest. Generic v1/v2 migration and the historical
v1-only alias retain distinct, tested receipt schemas.

## Boundaries and remaining proof

- This run proves the ordinary live no-confirmation checkpoint path. It does
  not claim an artificially delayed or sub-second startup injection; retain a
  future slow-start row as liveness hardening rather than a source blocker.
- A Herdr acknowledgement remains transport-only. The STATUS checkpoint is the
  first harness-acceptance evidence.
- The local Agents sidebar is not remote-harness authority.
- The controller retains no ordinary transcript and emits no surrounding pane
  text from its bounded watcher.
- The tab remains visible and preserved. Cleanup, merge, release, device
  security changes, and production mutation remain separate gates.
