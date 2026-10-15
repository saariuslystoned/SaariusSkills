# Run contract

## Prepare

Record a run ID, owner, case, allowed mode/actions, closer, exact repos/revisions, disposable resource aliases, proof root, stop condition and human gates. Name the assigned Registry, store, Payments, Commerce, hosted Ship, Stripe TEST and PB sandbox environments. Capture fresh runtime identities separately from source and local tests. Resolve missing authority or environment identity before a mutating boundary.

Use an authorized new merchant for the main case, an independently identified returning merchant for that case, and a distinct DinkusKit admin identity for privileged setup. Do not publish raw emails or credentials. Use native authentication; an unattended login method must be proven before describing the run as automated.

## Reusable isolation and release checks

Provision the isolated sandbox service and disposable store resources once under their exact approved account, host, namespace and audience. Routine release checks should update the plugin in that isolated environment and use unique TEST fixture identities for each run; they should not recreate infrastructure or replace shared service credentials on every release. A new-install/onboarding case remains separate and requires its own fresh store and admission proof.

Keep service resource creation, closed deployment, issuer routing/site generation, merchant activation and provider operation as distinct transitions. Approval for an inactive deployment does not authorize credential entry, email bindings, provider calls or activation. Preserve existing paid orders, keys and shared-service configuration when qualifying a new isolated target. The deployment hostname and runtime audience are distinct configuration fields; verify both rather than deriving one from the other.

## Cases

1. **New merchant:** create the authorized disposable Registry store; install Commerce and Payments via Registry; prove TEST connection and storefront catalog/config readiness; purchase a test product through actual Stripe TEST checkout; inspect paid order in Commerce admin; fulfill that same order through hosted Ship with PB sandbox; obtain and render the provider PDF; inspect matching tracking/completed state.
2. **Practice label:** independently exercise the declared practice-label path. Label it practice and record its provider/environment behavior. It cannot stand in for a paid order or production-like hosted sandbox shipment.
3. **Returning merchant:** start from an existing authorized merchant connection; prove identity/connection reuse and the required checkout/fulfillment behavior. Reconnection or duplicate resource creation must be recorded as a deviation, not hidden as success.

At every failure, preserve the last successful boundary and stop dependent actions. Use only the current contract's bounded readiness/retry behavior, with an idempotency record before retrying actions that create payments or shipments. Do not substitute mocks or local execution when the case requires the hosted path.

## Boundary recovery

### Browser, authentication and key handoff

Use one browser owner and rediscover the exact assigned Chrome profile/extension after an app restart or connector reset. Numeric browser IDs are not durable identity. Do not substitute another signed-in profile or an untargeted native window. Respect browser redaction; missing account metadata is not permission to bypass it.

Human account login, MFA and passkey bootstrap are separate from public synthetic payment/shipping fixtures. A Store key handoff must name the exact fresh site before the human copies it directly into the intended secret field. Preserve existing keys and orders during repairs; do not rotate or read credentials to diagnose a configuration error.

### Installed checkout and hosted boundary

Verify the actual installed package and real wire response, not only source tests or version labels. Country, selling-country and shipping-country configuration must match the authorized merchant and delivery. Preserve the same checkout binding, capability and idempotency identity during a qualified recovery; missing status confirmation does not authorize a new payment. Inspect the durable Commerce order first.

For Registry publication, qualify official archive digest, release provenance, discovery and installation independently of workflow status. An artifact can require investigation even when a workflow reports a conflict; never bypass the official publisher or blindly repeat a release.

Test template changes at the native Worker boundary. Mocked fetches can miss redirect-mode compatibility, subrequest limits or same-Worker HTTP timeouts. Where the installed EmDash contract provides it, use the public-only local plugin dispatcher with its original-origin, public-route, method and sandbox guards. A private/kernel/native implementation substitute does not prove the hosted public contract. Record the deployed budget; do not turn one run’s limit into a universal setting.

### Existing paid order to Ship

After enabling Ship under applicable authority, regenerate the issued nonsecret checkout settings; do not guess service audience values. Save only those settings and leave the existing secret key field untouched. Verify the installed admin form’s unchanged-secret preservation behavior before relying on it.

Under the observed Commerce contract, reopening the **top-level Orders page** syncs an existing addressed Processing order to Ship; opening its detail alone does not. A shipping link is not proof the service accepted the order. Do not manually complete the order or create a duplicate order to force a handoff. Check the current contract before reusing this procedure after an update.

### PB refusal and automatic email

Before a sandbox label, freshly verify the deployed PB environment and order’s TEST mode. Use an eligible sandbox quote and the qualified trackable service/special-service mapping. A validation refusal or insufficient-funds response is not a label/PDF. Qualify persistence and provider-side uncertainty before any bounded retry; do not blindly retry shipment creation or fund an unverified account.

A Developer Hub balance belongs to the observed account, not necessarily the Worker’s deployed credential bindings. Display name or a configured developer ID alone does not prove credential ownership or TEST postage routing. Use authorized nonsecret provenance; unavailable login access does not authorize account recovery, rebinding, a diagnostic endpoint, or secret inspection. Prepare a concrete scoped remedy and obtain the actual account/deployment authority before executing it.

The observed TEST flow can automatically email the store’s configured reply-to after tracking sync, including background sync; it has no normal per-order skip-email control. Verify that recipient and obtain the applicable send authorization **before creating the label**. Waiting to reopen Orders does not prevent the automatic send. Do not change global email configuration as a workaround. Record authorization separately from observed delivery.

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
