# Current route and evidence

Execution observations: **2026-10-17**; source-landing update: **2026-10-18 UTC**.
This is a dated snapshot, not evergreen admission.
Refresh linked source, PR state, enrolled profile/policy and evidence before
dispatch. The canonical test owns assertions; x-api owns the runner and its
activation. PR152 owns this routing skill.

## Canonical journey source

Use [`dinkuskit-live-test`](https://github.com/saariuslystoned/SaariusSkills/blob/53ac7f49b5d2f403ca7b52c0656080c388cd4720/skills/dinkuskit-live-test/SKILL.md),
its [runner README](https://github.com/saariuslystoned/SaariusSkills/blob/53ac7f49b5d2f403ca7b52c0656080c388cd4720/skills/dinkuskit-live-test/runner/README.md)
and [status](https://github.com/saariuslystoned/SaariusSkills/blob/53ac7f49b5d2f403ca7b52c0656080c388cd4720/skills/dinkuskit-live-test/references/status.md).
PR135 is historical proposal context, no longer the primary owner.

| Source/case | Observed result and boundary |
| --- | --- |
| [PR156](https://github.com/saariuslystoned/SaariusSkills/pull/156), merged `0a078332432c079cf628dbaa2e795648fa84218b` | Journey split, Storefront and Buy and ship. Canonical status records prior unattended live Buy and ship/finish evidence, but the new thank-you confirmation step has not passed. This does not qualify Cloudflare execution or every current assertion. |
| [PR157](https://github.com/saariuslystoned/SaariusSkills/pull/157), merged `949091838e55b3861968ebf12f403cda48f86b48` | Adds Cart; local proof only, no live Cart pass. Canonical Storefront previously ran live and found page/content failures. |
| [PR158](https://github.com/saariuslystoned/SaariusSkills/pull/158), merged/current main `53ac7f49b5d2f403ca7b52c0656080c388cd4720`, head `1401ea47421720d7f7cbce0dde52b52497684df9` | Manage products has ten local steps passing with Commerce `0.3.0-beta.2`; it has not run live. The stated minimum is beta.2 or later, not proof of later versions. Current [status](https://github.com/saariuslystoned/SaariusSkills/blob/53ac7f49b5d2f403ca7b52c0656080c388cd4720/skills/dinkuskit-live-test/references/status.md) also records local Cart proof. |

The broader seven-journey plan is not seven implemented/passing journeys.
Preserve the selected spec's original assertions/hashes. PR723's reviewed
Storefront port remains pinned to canonical `949091838e55b3861968ebf12f403cda48f86b48`;
current main includes later Storefront changes. Updating the canonical skill or
merging PR158 does not silently upgrade that prepared payload or its proof.

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
At the landing milestone, the reservation total remains $5.717104 against the
$25 project cap, with six routine fixture requests remaining. No additional
runtime activation, lease or reservation occurred. Read fresh policy and ledger;
these observed numbers grant no new spend or Storefront capability.

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
Canonical spec SHA-256:
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

The merged helper remains inactive preparation/offline proof under the owned
Smoky CLI. SaariusSkills owns canonical assertions; upstream Crabbox owns
lifecycle. There is no active CP-1 Storefront capability and hosted Storefront
has **not run**. Source integration, review and merge do not activate it.

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

The next source-only assignment implements one fixed public-beta Storefront
operation from fresh x-api main `f720f1903f2f5542be5fff59944365d0b4a32da2`
on `codex/issue715-storefront-live-caller-20261017`, reusing the existing
consumer, Crabbox lifecycle and exporter. Only source, local proof and review
are assigned; no completed or admitted hosted capability is claimed. Bind account/Worker/version/origin and canonical
source/browser/payload; internal `site_id` is optional because the Storefront
journey does not read it. Preserve configured-pin versus deployment-trigger
provenance and report unknowns. No generic executor, new credential consumer,
fixture allowance transfer or hosted run follows from this plan.

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
