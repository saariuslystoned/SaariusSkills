# Inactive caller and latest-beta readiness milestone

Observed 2026-10-18 UTC. Prior PR152 head `6018edb931f5949e4f049005757917b224417ca2`
and its proofs remain historical. This lane changes documentation only; no
canonical assertions, runner helper code, installed skill or runtime is edited.

## Source and reviewed evidence

Fresh SaariusSkills main is b80649233bd9ade9a9f5481a5ee5b0c2f13c4fca (PR159).
The clean current-main merge preserves canonical bytes and packaging. Its new
Mark as completed journey has local proof only. Existing journeys do not become
Cloudflare-qualified merely because canonical main advanced.

x-api PR724 merged `47c4937adef3016d52580e40cc4ad3680b0f0da8`, adding the inactive
fixed public-beta caller. PR725 merged `3e7ea069c7bba1c02021ccf87a923c5d22b480dd`,
reviewed head `6f64659d083c9343fcb8556efb65b2d58e5ba8a7`, updates the pin/helper
closure to canonical `b806492`, including support/storefront-page.mjs.
Storefront spec SHA-256 is `6a3b94b58bee7f4016c3d5f1943ad6844d7a0acfda5d503155ab3e668be10306`.
Five Linux cases, exact-head CI and comprehensive P3 passed. Native review found
no code defect and requested current receipts; the parent
[satisfied that evidence item](https://github.com/saari-co/x-api/pull/725#issuecomment-6244366717).
Its raw verdict is not relabeled. No live Storefront execution or runtime
promotion occurred.

## Release and installed-state evidence

Read the safe proof, first-run packet, canonical observation, publisher listing,
installed versions and review adjudication under x-api
runs/e2e-blackbox-runs/20261017-first-live-preparation/.
The complete two-page authoritative PDS listing at 01:30 UTC includes Commerce
beta 0.3.0-beta.2 and no Payments beta. Authenticated Plugins UI at 01:31 UTC shows
Commerce beta 0.3.0-beta.0 and Payments stable 0.2.8 enabled on the shared beta
store. Published/downloaded blob integrity and installed UI observations are
separate proofs. These are dated observations, not hardcoded release policy.
No screenshot, private identity, credential value or raw authenticated output
is copied into this repository.

The refreshed guidance preserves one shared-store run at a time, the same
canonical tests locally then in Cloudflare, a latest published beta pair frozen
per batch, persistent auth/connections and isolated run data. Existing records
stay untouched. Passing run data is cleaned only after proof is saved; failing
data remains until the fix is verified. After the second failed review total,
stop and return the issue and recommendation, not two extra repair cycles.

## Validation and boundary

Skill quick validation, 31 focused packaging/artifact tests, local links/privacy,
canonical byte preservation and diff checks passed before commit. Exact-head CI
and comprehensive review results are recorded on PR152 and in the task run root.
No PR152 merge/install, publication, store upgrade, credential operation,
activation, deploy or live run is part of this update. Issue715 is not edited.
