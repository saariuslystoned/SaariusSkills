# Run2 failure, local image-width fix and exhausted-batch blocker

Status snapshot: 2026-10-18 UTC. Prior PR152 head 717df54 and all original
failure/correction proof are preserved. Only status/recipe/proof is authored;
canonical assertions and runtime/transport code are unchanged by this lane.

## Evidence read

Parent x-api runs/e2e-blackbox-runs/20261017-payments-release-watch/:
parent-run02-verification.json, parent-image-width-followup.json,
approved-729-merge.json and selected status fields. Runtime-owner
run-02-transfer-4770b561/PROOF.md and proposed-new-batch-after729/PLAN.md under
runs/e2e-blackbox-runs/20261017-runner-auth-caller/storefront-beta-two-runs-20261017/.
GitHub confirms PR728/729 merged; the plan's older pending-729 wording is historical.
No credential stores, auth logs, live endpoints or private raw browser state read.

## Observed outcomes

Engine39 merged cf5737a738793fd435f7df0dca021461078e0a3e and pin260 merged
2cd8419df2091ac1cc12ec3bb7a4f420b7a5d5a0 before PR728 merged
4770b561477e265d6497df1056ff84d5bcb77e64 with native/P3 passed.
Run 5e60bdb27207427fa1e93b8181beb5d0 / lease cbx_554c688acf31 is actual hosted
FAIL in 83.177s: 3 PASS / 2 photo FAIL / 2 SKIP. Parent verified 14 exported artifacts;
stop accepted/terminal observed, provider absence unverified. Enrollment was
restored; Run1/old ledger preserved. Both requests consumed, batch reservation
$1.60, actual billing unknown. This is not an unattended mission-complete result.

PR729 reviewed 9dd2a1a2bd0117f5325803947994a86f6f8e08d3 and merged
ce93c1998fa251fd3e27c3fe561a177bceba7298 after exact CI/P3/native passed.
The observed DOM and same Linux Chromium/DPR1 reproduce selecting 600 among
300/600/1200 widths, against the previous 1200-only policy. Local canonical
FAIL→PASS with 600 and unapproved 601 FAIL plus 42/15 tests support the one-line
allowlist fix. The actual denied live URL was redacted; no recovered URL or
new Cloudflare PASS is claimed.

The reviewed caller still cannot admit a fresh batch through its fixed
Storefront ledger/digest contract. New-batch source/admission is required;
no ledger reset/rotation or new live request is authorized by PR729 merge.

## Validation and boundary

31 focused tests, skill validation, links/privacy, unchanged source bytes and
diff checks passed; final exact-head CI/review is recorded on PR152 and in the
task run proof.
No runtime write, installation, merge, new PR, live request or issue715 edit.
Stop after second failed review total and return the issue/recommendation.
