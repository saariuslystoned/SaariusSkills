# Status and promotion criteria

As of 2026-10-12 this is an **unverified scaffold**. Historical observations are readiness context, not reusable credentials, a target assignment, or current deployment proof.

| Capability | Evidence state | Required proof |
| --- | --- | --- |
| Isolated EmDash admin authentication | Observed native Cloudflare Access path | Fresh authorized session for the assigned run; automated merchant auth unverified |
| Registry installation | Commerce 0.1.0 and Payments 0.1.0 observed enabled | Fresh disposable store, Registry installation receipts, package digests and store deployment identity |
| New merchant connection | UNVERIFIED; Payments observed unconnected | Merchant identity, TEST connection, safe account identity and visible success |
| Storefront checkout | UNVERIFIED; checkout observed unavailable | Catalog/config authority, authorized checkout, completed Stripe TEST payment |
| Commerce paid order | UNVERIFIED | Visible paid TEST order joined to that payment |
| Hosted Ship fulfillment | UNVERIFIED | Exact hosted deployment, PB sandbox shipment and order join |
| Provider PDF | UNVERIFIED | Provider-origin PDF, safe hash/provenance, rendered visual inspection |
| Tracking/completed | UNVERIFIED | Matching shipment/tracking evidence and observed terminal state under current sandbox semantics |
| Practice label | Separate required case; UNVERIFIED | Explicit practice-mode result and provider/runtime provenance |
| Returning merchant | Separate required case; UNVERIFIED | Existing connection reused with correct identity and successful authorized flow |

Historical readiness found unresolved service deployment identities and a checkout integration gap involving catalog/config authority. Service root/health responses did not resolve either. Read the current source and deployment evidence rather than assuming that a setting fixes the gap. Readiness mitigation work was in progress; no timing or implementation choice is locked here.

Promotion requires all required rows to have fresh, inspectable evidence for the declared versions and environments, adjudicated failures, and a bounded repeatable procedure. Keep source, local-test, deployment and observed-behavior claims distinct. A later version change requires requalification of affected boundaries; retain prior evidence as historical.
