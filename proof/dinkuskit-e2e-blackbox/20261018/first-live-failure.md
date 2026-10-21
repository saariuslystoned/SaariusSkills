# First live Storefront failure and held remaining slot

Dated snapshot: 2026-10-18 UTC. Starting PR152 head
85ee721dec0d54d93e2c8ad9b67635cf80aef1a0; fresh canonical main
76fe3316cc3a85ea031473bdc1060093b409a3c0. Only status/recipe/proof is authored
here; canonical assertions and helpers remain unchanged from current main.
The executed Storefront source remains selected b806492, not an automatic
upgrade to later canonical main.

## Evidence read

Parent x-api proof root: runs/e2e-blackbox-runs/20261017-payments-release-watch/.
Read STATE.md, last-observed.json, PROOF.md, BUILD-PIN-FINDING.md,
parent-installed-pair-verification.json and parent-live-run01-verification.json.
Read the assigned PR728 proof/storefront-final-slot-20261017/PROOF.md and
GitHub PR726/728 metadata. Subsequent parent runtime handoff reports the failed
38s build and rollback; no deployment or publication success is inferred.
No credential store, auth log, provider or live store operation was accessed.

## Observed result and limits

Parent verified Commerce beta 0.3.0-beta.2 and Payments beta 0.2.9-beta.1 installed
and enabled, with stable Payments 0.2.8 retained disabled. First hosted Storefront
request issue715-storefront-beta-pair-20261017-01 genuinely failed in 56.55s:
homepage 200/no notices passed, missing parcel photo/product-page checks failed,
category/checkout skipped. Parent verified 21 artifact hashes and terminal lease
cbx_fe2aa0c77a74; native stop accepted, provider absence unverified. This is
separate from the earlier two synthetic merchant fixture passes.

One approved $0.80 request of two consumed; cumulative reservation $7.317104/$25,
actual billing unknown. No second live lease. Approved photo now loads, saved
page still unpublished. Old effective build pin 0b39 differs from displayed
trigger 8aa; merged Template Store PR95 supplies the nested-ID fix. Approved
pin-correction build failed before deployment after 38s, old pin restored,
automatic builds disabled, old 068de13d-c257-4c92-8d0b-82a8c9ebeaee at 100%.
PR728 observed 7e5e808 remains open, with native input hold and explicit
new-generation transfer/new exact-head review required. No candidate promotion.

This update adds bounded judgment: preserve failed-run evidence; distinguish
SKIP/product FAIL/runner outcome; verify effective build source before a new
fix; never reset or silently transfer the remaining request across generations.
Existing shared-store, frozen-pair, data-retention and second-failed-review-total
stop rules remain. Prior proof is not rewritten.

## Verification

31 focused packaging/artifact tests, skill validation, local links/privacy,
canonical-byte preservation and diff checks passed. Final exact-head review/CI belongs
in the PR and owned run record. No PR merge, install, activation, deploy,
request02, issue715 edit or additional external dispatch is performed here.
