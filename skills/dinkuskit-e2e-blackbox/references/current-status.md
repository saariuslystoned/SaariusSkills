# Current route and evidence

Observed **2026-10-17**. This is a dated snapshot, not evergreen admission.
Refresh linked source, PR state, enrolled profile/policy and evidence before
dispatch. The canonical test owns assertions; x-api owns the runner and its
activation. PR152 owns this routing skill.

## Canonical journey source

Use [`dinkuskit-live-test`](https://github.com/saariuslystoned/SaariusSkills/blob/949091838e55b3861968ebf12f403cda48f86b48/skills/dinkuskit-live-test/SKILL.md),
its [runner README](https://github.com/saariuslystoned/SaariusSkills/blob/949091838e55b3861968ebf12f403cda48f86b48/skills/dinkuskit-live-test/runner/README.md)
and [status](https://github.com/saariuslystoned/SaariusSkills/blob/949091838e55b3861968ebf12f403cda48f86b48/skills/dinkuskit-live-test/references/status.md).
PR135 is historical proposal context, no longer the primary owner.

| Source/case | Observed result and boundary |
| --- | --- |
| [PR156](https://github.com/saariuslystoned/SaariusSkills/pull/156), merged `0a078332432c079cf628dbaa2e795648fa84218b` | Journey split, Storefront and Buy and ship. Canonical status records prior unattended live Buy and ship/finish evidence, but the new thank-you confirmation step has not passed. This does not qualify Cloudflare execution or every current assertion. |
| [PR157](https://github.com/saariuslystoned/SaariusSkills/pull/157), merged/main `949091838e55b3861968ebf12f403cda48f86b48` | Adds Cart; local proof only, no live Cart pass. Canonical Storefront previously ran live and found page/content failures. |
| [PR158](https://github.com/saariuslystoned/SaariusSkills/pull/158), OPEN `7e923c68f83d1f0c3effc92c97af8a6803b91c2b` | Manage products: ten local steps pass against Template Store `7b96c7e` and Commerce `0.3.0-beta.2`; not live or merged. The stated minimum is beta.2 or later, not proof of later versions. Its [candidate status](https://github.com/saariuslystoned/SaariusSkills/blob/7e923c68f83d1f0c3effc92c97af8a6803b91c2b/skills/dinkuskit-live-test/references/status.md) also records updated local Cart proof. |

The broader seven-journey plan is not seven implemented/passing journeys.
Preserve the selected spec's original assertions/hashes; do not silently pull
an open PR into the merged baseline.

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
  `25b2a1865d55673537778c2955c52777e67c4412`: security trial5 passed:
  stale-credential readiness/native create401, zero instances, cleanup404.
  Scoped refusal proof, not hosted journey proof.
- [PR722](https://github.com/saari-co/x-api/pull/722), OPEN, source
  `f3075215452f70bc6410d3191fd09d4fbcf4876d`: active fixed CP-1 consumer.
  [Public closeout](https://github.com/saari-co/x-api/pull/722#issuecomment-6242647497)
  links the bounded evidence.

First routine request `issue715-routine-acceptance-20261017-01` passed in
741.694s including preparation: smoke206.492s, two isolated synthetic merchant
stage526.717s, actual journey intervals192.756s. All29 artifact hashes were
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
$0.80 over30days, expiring `2026-11-16T22:40:01.490312Z`; one used/six remained.
Global reservation cap was$25, prior reservations$5.717104. Read fresh policy
and ledger; these historical numbers grant no new spend or capability.

Authoritative private evidence is located by repo-relative paths (no private
outputs copied into this skill):

- x-api coordinator: `runs/e2e-blackbox-runs/20261015/routine-policy-proposal-20261017/f307-activation-admitted/PROOF.md`,
  `parent-verification.json`, `independent-validator/report.final.md`.
- x-api runtime-owner checkout: `runs/e2e-blackbox-runs/20261017-runner-auth-caller/routine-activation-plan/f307-candidate/first-request/`;
  read its safe `PROOF.md`, `INVOCATION.md`, verification and timing diagnosis.

Managed Browser Run remains optional/deferred; the October15 missing-consumer
preflight did not prove unavailable account entitlement. Hetzner and the bundled
public probes remain [historical qualification](qualification.md).

## Prepared Storefront versus real hosted targets

[PR723](https://github.com/saari-co/x-api/pull/723) is OPEN at
`8ba255dae698208fa3cc78ecc0c264978c71d28f`. Its
[proof](https://github.com/saari-co/x-api/blob/8ba255dae698208fa3cc78ecc0c264978c71d28f/proof/storefront-port-20261017/PROOF.md)
records seven unchanged canonical Storefront steps passing offline on
Linux/x64 headless Chromium, plus expected failures for missing photo,
developer notice, external redirect and Access refusal. Canonical spec SHA-256:
`0d3ad71eb67739e96be0504215849c0df8aa4265dacd4dfc161f47bb53a683af`;
lock SHA-256:
`51a538a6154719d5bebb4393b607303a175be28d18518b605e3dfaa47637f397`.
The package is inactive: no active CP-1 Storefront capability or live Cloudflare
Storefront run. Consult current PR review status separately from offline proof.

| Explicit target | Worker | Observation and remaining gate |
| --- | --- | --- |
| `https://e2e-v2.sm0ky.dev` | `sm0ky-registry-test-store-v2-20261013` | Real hosted report target; anonymous root302 to Access. Qualified inbox consumer needed when Access applies. |
| `https://e2e-beta-20261014.sm0ky.dev` | `sm0ky-registry-test-store-beta-20261014` | Separate real store; anonymous root200. Automatic main builds were pinned at old `0b39b431…` and owner-disabled; data untouched. Root200 proves neither all required public routes nor full journey acceptance. |

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
