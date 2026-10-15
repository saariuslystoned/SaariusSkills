# Status and promotion criteria

As of **2026-10-15**, this remains a **draft with partial observed runtime proof**. The full E2E, practice-label and returning-merchant cases are not certified. This dated checkpoint reports the assigned isolated run; it does not assign a target or make historical deployment evidence current.

| Capability | Observed checkpoint | Remaining qualification |
| --- | --- | --- |
| Isolated store/admin | Registry store deployed; native Cloudflare Access session and exact manifest-derived public path exceptions observed | Reverify assigned host, session, deployment and exceptions for a new run; unattended authentication unverified |
| Registry installation | Commerce 0.2.2 and Payments 0.2.8 installed; existing runtime identities preserved through updates | Retain exact archive/provenance, discovery, installed-runtime and deployment evidence; version labels alone are insufficient |
| New merchant connection | Stripe TEST connected account ready after human authentication/MFA/passkey setup | Reverify exact TEST binding for another run; human authentication is not automated sandbox fixture setup |
| Checkout/payment | One actual Stripe TEST payment for a USD 12 test parcel succeeded | Return-page confirmation failed; investigate separately without repeating payment |
| Commerce paid order | One durable provider-paid TEST order observed in Processing, joined to the payment as `paid-order-A` | Preserve this order and its key; payment success does not prove fulfillment |
| Hosted Ship handoff | Ship enabled with explicit approval; nonsecret settings saved without replacing the Store key; top-level Orders page synced the existing order | Hosted order and freshly verified PB sandbox environment establish handoff, not a shipment |
| PB sandbox shipment | BLOCKED: first service refused as not trackable; qualified Priority Mail/DelCon attempt had an eligible $13.82 sandbox quote, then failed for insufficient funds | No shipment/label saved in the visible UI; provider-side outcome must be qualified before another creation attempt |
| Provider PDF | UNVERIFIED; no provider PDF created | Provider-origin PDF, hash/provenance and rendered visual inspection |
| Tracking/completed | UNVERIFIED; no shipment tracking or terminal completion achieved | Join actual tracking and observed completion to `paid-order-A` |
| TEST shipped email | Specific automatic send to the dedicated test mailbox authorized, but not achieved | Authorization is not delivery proof; no customer send authorized |
| Practice label | Separate required case; UNVERIFIED | Explicit practice-mode result and provider/runtime provenance |
| Returning merchant | Separate required case; UNVERIFIED | Existing connection reused with correct identity and successful authorized flow |

The earlier shared-account switch was not applied and remains superseded by isolated deployment preparation. The original paid order, Store key and shared credentials are preserved. Old deployed PB credential ownership remains unresolved; the intended agent-associated sandbox showed $400 (currency code absent), which does not resolve the shared Worker’s insufficient-funds refusal.

A new isolated Ship target is approved for a **closed, inactive deployment**: Worker `dinkuskit-ship-sandbox`, host `ship.sm0ky.dev`, runtime audience `dinkus-ship-sandbox`, in the assigned agent Cloudflare account. Execution handoff is pending; no deployed-service or merchant-activation proof is claimed. The latest coordinator state also records an exact CLI-consumer capability gap. CLI/API is preferred; an authorized, correctly targeted browser fallback remains available under owner steering. No provider operation follows from closed-resource approval alone.

For the separate fresh beta store, four resources (Worker placeholder, D1, private R2 and session KV) have been created. The template’s real-resource-ID local build passed at reviewed source `e2ad5273fbd0ec46e9947a96bc37b9aeb7b913d4`. Admin protection, actual deployment, exact admission/generation, plugin installation and merchant activation still require their own observed proof. A local build is not a deployed store.

Commerce **0.3.0-beta.0** (`dinkus-commerce-beta`) is independently qualified as published; stable **0.2.2** is unchanged. Source `93af4fec2f33f43463d5917972cce574180446d1` and [original release run 38772132019](https://github.com/dinkuskit/commerce/actions/runs/38772132019) are tied to the public archive by verified provenance. That original workflow remains **FAILURE** because its approval wait timed out. The same original publish intent was independently reconciled after approval; no new publication or workflow retry is claimed. Publication does not prove installation or full beta E2E.

Official Registry release workflows reported `RELEASE_CONFLICT`; separately inspected public archives and provenance tied the packages to the approved release source/run, and Registry discovery and installation were subsequently observed. Do not describe those workflows as successful or infer publication from a workflow label alone.

This checkpoint is based on the coordinator’s selected runtime records, not new runtime execution by the documentation writer. The [sanitized checkpoint proof](../../../proof/dinkuskit-e2e/20261015/PROOF.md) records scope and evidence limits. Private screenshots, raw account/order/provider identifiers and authentication material remain outside this reusable skill.

Promotion requires fresh, inspectable evidence for the complete main flow and both separate cases, adjudicated failures, and a bounded repeatable procedure. Keep prepared, locally tested, deployed and observed claims distinct. Requalify affected boundaries after a version or account change; retain prior evidence as historical.
