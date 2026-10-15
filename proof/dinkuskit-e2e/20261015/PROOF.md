# Interim isolated beta checkpoint — 2026-10-15

Documentation fidelity checkpoint, not runtime execution by this writer. The prior [payment/order checkpoint](../20261014/PROOF.md) remains historical. Current facts derive from selected coordinator STATE/PROOF records and the release owner’s qualified publication receipt; raw private records and account/resource IDs are not copied here.

## Qualified publication

- Package: `dinkus-commerce-beta` version `0.3.0-beta.0`.
- Source: `93af4fec2f33f43463d5917972cce574180446d1` on main.
- Original workflow: [38772132019, attempt 1](https://github.com/dinkuskit/commerce/actions/runs/38772132019/attempts/1).
- Archive: 45,642 bytes; SHA-256 `8bff911fababa6a909519ae06bceee5824fd6bc093883f022b417d97985b9a49`.
- Release record CID: `bafyreic3to6o4zexhg3eap7w5a5a5lr7yqby7n7bk6krkg5ult34qkbwfu`.
- Verified source/workflow/invocation provenance and public Registry record/index. Original workflow FAILURE remains explicit: approval wait timed out, same original intent independently reconciled. No republish or workflow retry. Stable 0.2.2 unchanged.

## Prepared versus observed

Four fresh store resources exist; reviewed template real-ID local build passed. The new isolated Ship Worker/domain/audience are assigned and closed deployment approved, with execution handoff pending. Neither actual Ship/store deployment nor admission, merchant activation, provider shipment, rendered PDF, tracking/completion or email delivery is established by this checkpoint. The original paid order, key and shared credentials remain preserved. No beta installation is inferred from publication.

Portable guidance now prefers qualified CLI/API and permits authorized browser fallback. It distinguishes one-time isolated resource setup from routine plugin-update/unique-TEST-fixture checks and retains a separate fresh-install case. This is guidance for subsequent proof, not evidence that those repeatable checks already passed.

## Validation and limits

Local reference links, privacy and diff checks are performed for this docs update. Packaging: 19 tests passed via `python3 -m unittest discover -s tests -p test_packaging.py -q`. Local file links and privacy-pattern checks passed; `git diff --check` passed. Root has no `package.json` or npm skills-check script. The skill-creator quick validator remains unavailable in default Python because PyYAML is missing; no successful run is claimed. No runtime/account/browser actions, credential reads or infrastructure writes were performed by this writer. Required exact-head review and CI remain coordinator-owned. Full E2E remains unverified and requires a final skill update after actual proof.
