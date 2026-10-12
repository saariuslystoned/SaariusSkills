# Run contract

## Prepare

Record a run ID, owner, case, allowed mode/actions, closer, exact repos/revisions, disposable resource aliases, proof root, stop condition and human gates. Name the assigned Registry, store, Payments, Commerce, hosted Ship, Stripe TEST and PB sandbox environments. Capture fresh runtime identities separately from source and local tests. Resolve missing authority or environment identity before a mutating boundary.

Use an authorized new merchant for the main case, an independently identified returning merchant for that case, and a distinct DinkusKit admin identity for privileged setup. Do not publish raw emails or credentials. Use native authentication; an unattended login method must be proven before describing the run as automated.

## Cases

1. **New merchant:** create the authorized disposable Registry store; install Commerce and Payments via Registry; prove TEST connection and storefront catalog/config readiness; purchase a test product through actual Stripe TEST checkout; inspect paid order in Commerce admin; fulfill that same order through hosted Ship with PB sandbox; obtain and render the provider PDF; inspect matching tracking/completed state.
2. **Practice label:** independently exercise the declared practice-label path. Label it practice and record its provider/environment behavior. It cannot stand in for a paid order or production-like hosted sandbox shipment.
3. **Returning merchant:** start from an existing authorized merchant connection; prove identity/connection reuse and the required checkout/fulfillment behavior. Reconnection or duplicate resource creation must be recorded as a deviation, not hidden as success.

At every failure, preserve the last successful boundary and stop dependent actions. Use only the current contract's bounded readiness/retry behavior, with an idempotency record before retrying actions that create payments or shipments. Do not substitute mocks or local execution when the case requires the hosted path.

## Evidence

Maintain a safe join table containing run ID and stable aliases for merchant, store, checkout, payment, Commerce order, shipment, PDF and tracking. Keep raw identifiers only in an approved private proof record when needed; publish a consistent redacted mapping. Never retain auth-bearing URL queries or session data.

Capture:

- Registry installation receipt plus package versions/digests; store source and deployment identity.
- Independent Payments, Ship and other participating service source, deployment and observed environment identities; unresolved fields remain explicit.
- TEST payment success and paid Commerce order screenshots/state, joined to the same checkout.
- PB sandbox request/result provenance without sensitive payloads; shipment and tracking join.
- Provider PDF provenance and SHA-256, rendered page evidence, and inspection result. An HTTP success or PDF extension alone is insufficient.
- Tracking transitions, final observed status, timestamps and any sandbox limitations. Do not synthesize completed status if the provider does not supply the necessary evidence.

`PROOF.md` reports each case as PASS, FAIL, BLOCKED or UNVERIFIED with artifact links. `STATE.md` gives the current boundary, next action and gate; `events.jsonl` records safe transitions and idempotency; `heartbeat` records progress freshness. Public proof contains no local absolute paths or private identities.

## Retention and teardown

Preserve the intended 14-day evidence window in the run plan, identifying its start and retention owner. Do not automatically delete evidence at expiry. Inventory exact disposable resources and dependencies, obtain applicable teardown authority, then remove only the run's approved resources. Keep sanitized terminal evidence and record remaining resources; never broaden teardown to shared merchant accounts, stores or service configuration.
