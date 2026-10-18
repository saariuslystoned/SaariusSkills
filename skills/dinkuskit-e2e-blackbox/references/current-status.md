# Current route and evidence

Status snapshot: **2026-10-18 UTC**. Earlier observations retain their dates.
This is a dated snapshot, not evergreen admission.
Refresh linked source, PR state, enrolled profile/policy and evidence before
dispatch. The canonical test owns assertions; x-api owns the runner and its
activation. PR152 owns this routing skill.

## Canonical journey source

Use [`dinkuskit-live-test`](https://github.com/saariuslystoned/SaariusSkills/blob/76fe3316cc3a85ea031473bdc1060093b409a3c0/skills/dinkuskit-live-test/SKILL.md),
its [runner README](https://github.com/saariuslystoned/SaariusSkills/blob/76fe3316cc3a85ea031473bdc1060093b409a3c0/skills/dinkuskit-live-test/runner/README.md)
and [status](https://github.com/saariuslystoned/SaariusSkills/blob/76fe3316cc3a85ea031473bdc1060093b409a3c0/skills/dinkuskit-live-test/references/status.md).
PR135 is historical proposal context, no longer the primary owner.

| Source/case | Observed result and boundary |
| --- | --- |
| [PR156](https://github.com/saariuslystoned/SaariusSkills/pull/156), merged `0a078332432c079cf628dbaa2e795648fa84218b` | Journey split, Storefront and Buy and ship. Canonical status records prior unattended live Buy and ship/finish evidence, but the new thank-you confirmation step has not passed. This does not qualify Cloudflare execution or every current assertion. |
| [PR157](https://github.com/saariuslystoned/SaariusSkills/pull/157), merged `949091838e55b3861968ebf12f403cda48f86b48` | Adds Cart; local proof only, no live Cart pass. Canonical Storefront previously ran live and found page/content failures. |
| [PR158](https://github.com/saariuslystoned/SaariusSkills/pull/158), merged `53ac7f49b5d2f403ca7b52c0656080c388cd4720`, head `1401ea47421720d7f7cbce0dde52b52497684df9` | Manage products has ten local steps passing with Commerce `0.3.0-beta.2`; it has not run live. The stated minimum is beta.2 or later, not proof of later versions. Current [status](https://github.com/saariuslystoned/SaariusSkills/blob/76fe3316cc3a85ea031473bdc1060093b409a3c0/skills/dinkuskit-live-test/references/status.md) also records local Cart proof. |
| [PR159](https://github.com/saariuslystoned/SaariusSkills/pull/159), merged `b80649233bd9ade9a9f5481a5ee5b0c2f13c4fca` | Adds Mark as completed: nine local steps passed using TEST orders; it has not run live. This does not qualify that journey on Cloudflare. |
| [PR160](https://github.com/saariuslystoned/SaariusSkills/pull/160), merged/current main `76fe3316cc3a85ea031473bdc1060093b409a3c0` | Adds Problems with local stand-in Stripe/Commerce proof; not live qualified. This does not change the earlier Cloudflare Storefront run's selected `b806492` source. |

The broader seven-journey plan is not seven implemented/passing journeys.
Preserve the selected spec's original assertions/hashes. PR723's original
Storefront package used canonical `949091838e55b3861968ebf12f403cda48f86b48`.
PR725 refreshed the caller to selected canonical `b806492`,
including `support/storefront-page.mjs`; source refresh is not runtime promotion.
Do not silently mix assertions, helper closures or proof from different pins.

## Runner evidence, separate from hosted acceptance

Selected execution: Chromium/Playwright inside upstream Crabbox Cloudflare.
Nonsecret operational identity at observation:

- Agent account `4e8679e964d3d1808d6226b7150b13c0`;
  protected runner `crabbox-cloudflare-container-runner` at
  `https://crabbox-cloudflare-container-runner.agent-4e8.workers.dev`.
- Worker version `04ccef3c-c5f0-42c2-8092-7464954d16fc`;
  Crabbox `0.78.0`, upstream `2bd85693b5fdea67d352516e082b90f8cacfe07b`;
  image SHA-256 `74481895d8863cc2983e2d8ee491dd332dbeb7f4d0382198608c2ef657d4aea4`.
- [PR721](https://github.com/saari-co/x-api/pull/721), OPEN at
  `25b2a1865d55673537778c2955c52777e67c4412`: security trial 5 passed:
  stale-credential readiness/native create 401, zero instances, cleanup 404.
  Scoped refusal proof, not hosted journey proof.
- [PR718](https://github.com/saari-co/x-api/pull/718), MERGED as
  `c5759a8970dc3ad3412e6503ed112147d13f0f81`, reviewed at
  `6135558db7c04a3fbadd0f9e5896f0c106072c40`.
- [PR722](https://github.com/saari-co/x-api/pull/722), MERGED as
  `fff986f007c575747fd0ef527b98a1a57f91e86b`, reviewed at
  `093dcee86e1e303e78f29c114f89cf45e0045fd0`.
  Both landed with exact-head CI, comprehensive P3 and native review clean.
  The final PR722 correction changed copied-proof Markdown whitespace only;
  exercised runtime bytes remain equivalent to active CP-1 source
  `f3075215452f70bc6410d3191fd09d4fbcf4876d`. A merged source revision is not
  evidence of a new runtime activation. [Routine closeout](https://github.com/saari-co/x-api/pull/722#issuecomment-6242647497)
  links the bounded execution evidence.

First routine request `issue715-routine-acceptance-20261017-01` passed in
741.694s including preparation: smoke 206.492s, two isolated synthetic merchant
stage 526.717s, actual journey intervals 192.756s. All 29 artifact hashes were
verified and six screenshots inspected by an independent source-blind
validator, which returned bounded PASS. No human login or environment
intervention was observed during this invocation; prior enrollment is separate.

Exact lease `cbx_f8323201c1a5` reached stopped;
`provider_absence_verified=false`. Identical sequential redelivery produced a
byte-identical receipt and unchanged one-reservation ledger. A new ID with
revoked binding refused before credential/provider use; authorized metadata
was restored. These are bounded observations, not arbitrary-concurrency proof.

This is a **synthetic developer fixture**, not hosted Stripe, Ship, Pitney
Bowes, email, Registry install/upgrade or full-stack certification. Actual
billing is unknown. The observed policy allowed seven routine reservations at
$0.80 over 30 days, expiring `2026-11-16T22:40:01.490312Z`; one used/six remained.
At that historical landing milestone, the reservation total was $5.717104
against the $25 project cap, with six routine fixture requests remaining. The
later live Storefront batch is recorded below. Read fresh policy and ledger;
historical allowance does not grant new spend or another capability.

Authoritative private evidence is located by repo-relative paths (no private
outputs copied into this skill):

- x-api landing/adjudication: `runs/e2e-blackbox-runs/20261017-approved-landing/`,
  including `issue715-after722.md`, `pr723-adjudication.md` and source-equivalence evidence.
- x-api coordinator: `runs/e2e-blackbox-runs/20261015/routine-policy-proposal-20261017/f307-activation-admitted/PROOF.md`,
  `parent-verification.json`, `independent-validator/report.final.md`.
- x-api runtime-owner checkout: `runs/e2e-blackbox-runs/20261017-runner-auth-caller/routine-activation-plan/f307-candidate/first-request/`;
  read its safe `PROOF.md`, `INVOCATION.md`, verification and timing diagnosis.

Managed Browser Run remains optional/deferred; the October 15 missing-consumer
preflight did not prove unavailable account entitlement. Hetzner and the bundled
public probes remain [historical qualification](qualification.md).

## Prepared Storefront versus real hosted targets

[PR723](https://github.com/saari-co/x-api/pull/723) MERGED as
`f720f1903f2f5542be5fff59944365d0b4a32da2` at `2026-10-18T00:36:49Z`,
from reviewed head `519afb5c60cc47b0c9cc7bc9db6d17ba1fa10e01` against
`fff986f007c575747fd0ef527b98a1a57f91e86b`. Its
[proof](https://github.com/saari-co/x-api/blob/519afb5c60cc47b0c9cc7bc9db6d17ba1fa10e01/proof/storefront-port-20261017/PROOF.md)
records 15 focused tests and five fresh Linux cases after the hardlink repair:
seven unchanged canonical Storefront steps pass on the healthy fixture; missing
photo, developer notice, external redirect and Access cases fail as expected.
At that historical pin, spec SHA-256 was
`0d3ad71eb67739e96be0504215849c0df8aa4265dacd4dfc161f47bb53a683af`;
lock SHA-256:
`51a538a6154719d5bebb4393b607303a175be28d18518b605e3dfaa47637f397`.

CI core `39082909236` and lint `39082909233` passed. Comprehensive P3 review
`req-20261018T003011Z-246749524761` was clean for that exact tuple. Native run
`39082917042` found no actionable code/security finding, but its raw verdict
remained needs-human solely for the then-missing current OpenClaw receipt.
The parent independently verified that receipt and
[satisfied the evidence item](https://github.com/saari-co/x-api/pull/723#issuecomment-6243796719)
before the owner-approved merge; it was not waived or a raw native-ready
verdict. Same-head native re-review `39083350019` was already dispatched; no
additional dispatch is required by this skill.

The merged preparation helper remains offline-only under the owned Smoky CLI.
SaariusSkills owns canonical assertions; upstream Crabbox owns lifecycle. The
later fixed caller and actual hosted run are recorded below; source review and
merge alone never prove activation or a passing product.

| Explicit target | Worker | Observation and remaining gate |
| --- | --- | --- |
| `https://e2e-v2.sm0ky.dev` | `sm0ky-registry-test-store-v2-20261013` | Real hosted report target; anonymous root 302 to Access. Qualified inbox consumer needed when Access applies. |
| `https://e2e-beta-20261014.sm0ky.dev` | `sm0ky-registry-test-store-beta-20261014` | Separate real store; anonymous root 200. Automatic builds are owner-disabled; data untouched. The configured source pin and observed deployment trigger are separate provenance, not proof of compiled source. Root 200 proves neither all required public routes nor full journey acceptance. |

The existing beta deployment observation records active version prefix
`068de13d` at 100% traffic and trigger commit
`8aa5ce3d96f5979cd49241470fe7984beef6b958`; the configured build pin is
`0b39b43159abaafcfa116cd243fb24881f5a9512`. Full version ID and compiled-source
identity were not verified. Keep these fields distinct; do not infer the pin
was the deployed trigger or compiled source. Evidence:
`runs/e2e-blackbox-runs/20261017-approved-landing/beta-deployment-observation.json`.

[PR724](https://github.com/saari-co/x-api/pull/724) merged as
`47c4937adef3016d52580e40cc4ad3680b0f0da8`: the fixed public-beta Storefront
caller was qualified as **inactive source**, reusing the existing consumer,
Crabbox lifecycle and exporter. [PR725](https://github.com/saari-co/x-api/pull/725)
merged as `3e7ea069c7bba1c02021ccf87a923c5d22b480dd`, reviewed head
`6f64659d083c9343fcb8556efb65b2d58e5ba8a7`. It pins canonical
`b80649233bd9ade9a9f5481a5ee5b0c2f13c4fca` plus `support/storefront-page.mjs`;
Storefront spec SHA-256 is
`6a3b94b58bee7f4016c3d5f1943ad6844d7a0acfda5d503155ab3e668be10306`.
Five Linux cases, current-head CI and comprehensive P3 passed. Native review
found no code defect; its request for current review/CI receipts was
[satisfied by the parent](https://github.com/saari-co/x-api/pull/725#issuecomment-6244366717),
not waived or relabeled as a raw native-ready verdict. Neither merge promotes
the runtime or proves hosted Storefront execution.

Bind account/Worker/version/origin and canonical source/browser/payload before
any separately admitted run; internal `site_id` is optional because Storefront
does not read it. Preserve configured-pin versus deployment-trigger provenance
and report unknowns. No generic executor, new credential consumer, fixture
allowance transfer or hosted run follows from this source qualification.

### First actual live Storefront batch — 2026-10-18

The earlier 01:30–01:31 UTC Payments-publication/installed-pair gap was resolved.
Parent-verified publisher and authenticated shared-store evidence now records
Commerce beta `0.3.0-beta.2` and Payments beta `0.2.9-beta.1` published and
enabled on `https://e2e-beta-20261014.sm0ky.dev`; stable Payments `0.2.8` is
retained disabled. The pair is frozen for this batch, not an evergreen latest
version rule. [PR726](https://github.com/saari-co/x-api/pull/726) merged as
`6364e9339979179374223dc7c11a1506ba3cc995` and supplied the executed caller;
selected Storefront source remains canonical `b806492`.

Request `issue715-storefront-beta-pair-20261017-01` is a **real hosted
Storefront FAIL**, distinct from the earlier two synthetic merchant fixture
passes. Total time was 56.55s. Homepage HTTP200 and no-developer-notices checks
passed; the synthetic parcel product lacked a photo and linked product page,
so those canonical checks failed. Category and checkout were SKIP, not PASS.
Parent independently verified all 21 artifact sizes/hashes and inspected the
failure screenshot. Exact lease `cbx_fe2aa0c77a74` reached terminal state with
native stop accepted; `provider_absence_verified=false` remains explicit.

After Run1, one $0.80 request of the two-request batch was consumed and
request02 was held. The then-reported cumulative reservation was $7.317104
against $25; actual billing was unknown. The later Run2 outcome and exhausted
batch are recorded below; this historical checkpoint grants no spare request.

After the first run, the approved parcel photo was added, but the saved page
remained unpublished. The build dashboard displayed trigger `8aa5ce3…` while
the actual build command checked out `0b39b431…`; the old flat-ID reader rejected
the observed nested draft. Merged Template Store PR95 already supplied the fix
in `8aa5ce3…`. The first approved correction build failed before deployment
after 38s; its rollback and the original Storefront failure remain preserved.

The later matched correction **succeeded**, as verified by the parent's
2026-10-18 03:52 UTC record: build
`2ae6e77b-1721-4d01-9fd0-1396d8b7573a`, active version
`6777343c-03ba-4504-a8fc-cae0c686b398` at 100% traffic, automatic builds disabled.
Both the build pin and named nonsecret `DINKUS_EXPECTED_COMMIT` matched
`8aa5ce3d96f5979cd49241470fe7984beef6b958`. Successful provenance enforcement
supports that checkout; live compiled hook bytes were not downloaded or
compared. The frozen beta pair and existing connections were unchanged.

Only saved parcel page `01M56GSK05R6K6XD5ZHP8RYQPV` was published. The parent's
authorized-browser inspection showed the correct product association, loaded
600×600 parcel image, $12 price and In stock. Twelve evidence files have recorded
hashes. Checkout-unavailable text remained visible; no cart or purchase action
was performed. That page observation alone was not a second E2E run, anonymous
access proof or full Storefront PASS; the subsequent Run2 is separate below.

The earlier native-input hold was resolved after engine39 merged
`cf5737a738793fd435f7df0dca021461078e0a3e` and
[Spark-DGX pin260](https://github.com/saari-co/spark-dgx/pull/260) merged
`2cd8419df2091ac1cc12ec3bb7a4f420b7a5d5a0`.
[PR728](https://github.com/saari-co/x-api/pull/728) then merged as
`4770b561477e265d6497df1056ff84d5bcb77e64` after native/comprehensive P3 passed.
The explicitly bound generation transfer supplied Run2; the old target binding
was not silently reused. Do not infer an earlier transport denial was the
beacon: the first run did not retain that blocked URL.

### Run2 and local width repair — 2026-10-18

Request `issue715-storefront-beta-pair-20261017-02-transfer`, run
`5e60bdb27207427fa1e93b8181beb5d0`, executed the selected canonical Storefront
journey through merged caller `4770b561…` against the frozen beta pair and new
version `6777343c-03ba-4504-a8fc-cae0c686b398`. Result: **FAIL in 83.177s —
3 PASS, 2 image FAIL, 2 SKIP**. Homepage, no developer notices and product link
passed; catalog/product-detail photos failed; category and checkout skipped.
No checkout or product-record mutation occurred.

Parent verified 14 exported artifacts and the exact terminal lease
`cbx_554c688acf31`; native stop accepted and terminal state observed,
`provider_absence_verified=false`. Original enrollment was restored, and Run1,
its ledger row, policy history and both receipts remain preserved. Both slots
are consumed: $1.60 batch reservations, zero remaining runs. Reservations are
not measured billing and do not authorize a third request.

The denied URL is redacted in the live receipt. Independent observed DOM plus
the same Linux Chromium at DPR1 showed selection of the 600px image from the
300/600/1200 candidates; the old policy allowed only 1200. Controlled local
canonical proof went FAIL→PASS with 600, while unapproved 601 remained FAIL.
[PR729](https://github.com/saari-co/x-api/pull/729), reviewed head
`9dd2a1a2bd0117f5325803947994a86f6f8e08d3`, merged as
`ce93c1998fa251fd3e27c3fe561a177bceba7298` after exact-head CI/comprehensive
P3/native passed. It only changes the allowed image widths to 300/600/1200;
42 Storefront and 15 port tests passed. This is local repair proof, not recovery
of the omitted historical URL and **not a new Cloudflare PASS**.

The current caller's fixed Storefront ledger/policy-digest contract cannot
admit a fresh batch after exhaustion. The runtime's
`proposed-new-batch-after729/PLAN.md` describes that source requirement; its
older pending-merge wording predates PR729's merge. A new reviewed, explicitly
approved batch-admission route is needed. Do not bypass the refusal by resetting,
rotating, relocating or editing the old ledger, replacing its policy digest,
or reusing a consumed ID. PR729's merge authorized no new live request, and
none has started. The unattended end-to-end mission is not complete.

Authoritative safe evidence: x-api
`runs/e2e-blackbox-runs/20261017-payments-release-watch/{STATE.md,last-observed.json,PROOF.md,parent-installed-pair-verification.json,parent-live-run01-verification.json,BUILD-PIN-FINDING.md}`;
source candidate: `proof/storefront-final-slot-20261017/` in the assigned PR728
worktree. Correction proof: runtime-owner
`runs/e2e-blackbox-runs/20261017-runner-auth-caller/storefront-beta-two-runs-20261017/MATCHED-CORRECTION-RESULT.md`
and parent `parent-parcel-publication-proof.json` in the payments-release-watch
root. Run2/repair evidence: parent `parent-run02-verification.json`,
`parent-image-width-followup.json`, `approved-729-merge.json` in that same root;
runtime-owner `run-02-transfer-4770b561/PROOF.md` and
`proposed-new-batch-after729/PLAN.md` under the Storefront runtime proof root.
These are dated observations; neither correction nor source merge proves a
later hosted pass or resets the exhausted batch.

No silent target switch. The prepared mail adapter fails closed. Public beta
may avoid mail only after all required routes are proved public; v2 cannot
borrow beta's observation. Linux PDF rendering is a later Buy and ship gate,
irrelevant to Storefront. No hosted full-stack PASS is claimed here.

## Next closeout

Any runner-profile/authentication, journey revision, proof or activation change
must update this dated reference and [PR152](https://github.com/saariuslystoned/SaariusSkills/pull/152)'s
description in the same closeout. Record exact source, observed result, proof
and remaining gates; preserve prior evidence. Future assignments must carry
this synchronization responsibility. Do not create a cron/automation for it.
