# Commerce Behavior Proof

Use this reference only for commerce-connected EmDash work. Follow the product's
current contracts and launch decisions; optional inventory and shipping features
are not requirements for every site.

## Keep authority in one place

Record which component owns catalog price/sellability, checkout orchestration,
orders, physical stock, payment settlement and shipment state. UI adapters must
not introduce a second ledger or silently switch providers. Optional inventory
or future automation must not become an invented launch prerequisite. Preserve
explicit unavailable states until the capability is actually supported.

## Guest checkout acceptance

Use a synthetic product and an authorized provider TEST account through the
real storefront. Capture:

1. Guest browse/cart, quantity and price totals; coupon apply/remove if in scope.
2. Actual provider test checkout with the verified merchant/site binding.
3. Confirmation and exactly one correct durable order, including discount and
   shipping/tax treatment under the agreed rules.
4. Applicable retry, cancellation/failure, and closed-browser recovery proof.

Dashboard setup, a rejected provider request, a fixture payment, and unit tests
do not establish this purchase. Provider success also does not establish an
order saved by Commerce. Report each achieved milestone separately.

Where completion crosses services, preserve stable idempotency identities and
the agreed durable delivery/acknowledgment contract. A consumer must not discard
an event before its own order result is durably committed. Exercise replay and
the relevant interruption boundary, including overlapping consumers when the
deployment permits them. Do not infer success solely from a browser return URL.

Keep authoritative payment-session deadlines and discount snapshots intact.
An unknown provider outcome needs reconciliation, not a new purchase identity
or a time-only stock release. Apply the product's specific coupon reservation,
failure and refund policy rather than inventing one in the UI layer.

## Inventory acceptance

After an actual packaged plugin connects, view stock by location. Make one
reasoned synthetic adjustment and verify its immutable receipt and new balance.
Restart the relevant runtime without reseeding and confirm both the displayed
balance and authoritative receipt. Stock-engine tests alone are not installed
plugin proof. Separate this from full merchant consent/hosted service proof.

## Shipping acceptance

Separate quote, label request, confirmed label creation, downloadable document,
printing, carrier handoff and delivery. A sandbox provider portal label does not
prove label purchase inside the EmDash plugin. An unresolved in-app operation
with no document remains unresolved; reconcile its original identity before any
retry. Sandbox and live postage are different authorizations.

Place the reviewed shipment details, service/price and explicit purchase action
inside the supported admin surface. Keep package/fulfillment contracts compatible
with future inventory and printer events without implementing premature automatic
purchases. Provider onboarding delays need not block local UI, packaging or
contract work; label synthetic evidence clearly and retain the live dependency.
