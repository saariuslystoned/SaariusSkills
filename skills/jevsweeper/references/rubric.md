# JevSweeper rubric

Use these three labels only. Each label's section below is its description in
the `choice` question's `criteria`; the box and the locked line go in `state`.
Apply this rubric only after the native publication eligibility checks in
[coordinator.md](coordinator.md) hold. Absent or stale review evidence is not a
box to label, and the rubric cannot stand in for a review.

## repair

There is a code, test, or exact-head proof change the agent can make without a
new shop-owner lock. Examples: a P1 that names a file and a fix; missing
real-behavior proof for the locked contract; a leftover fixture; a schema that
rejects an upgrade shape the current main already writes; a genuine Registry
install (`r_*` ids) still unproven while local tests used fixed plugin slugs.

Missing required proof is repair (or coordinator `needs-evidence`), not
owner-gate, when the gap is product or behavior proof in an otherwise eligible
review. Missing native review/publication evidence remains a prerequisite
mismatch. Platinum, gold, or "findings none" does not waive required proof.

## owner-gate

The code matches an already-locked shop-owner contract, required evidence for
that lock is present, and the leftover box is only maintainer acceptance of a
documented public boundary or an explicitly scoped non-goal. Examples:
checkboxes that restate "accept public guest POSTs / payment window / Stripe
not run" after that proof exists; real `sk_test` vs dry-run; ClawSweeper is
not merge authority.

Do not use owner-gate for an unmet acceptance criterion dressed as a rating.

## do-not-patch

The finding asks to reverse a locked shop-owner outcome. Examples: list
unpriced products; invent Regular or `$0`; auto-remap a shared-pool SKU;
strip public UI that FEATURE_MAP already locked; add multi-currency when USD
is locked.

## next_move

Handle every pile; one pile never cancels another. In this order:

1. Each `do-not-patch` item: refuse that change, keep the lock, and name the
   item in the report.
2. Each `repair` item: fix it, unless the fix would undo a lock from step 1.
   A refused item never stops an unrelated repair.
3. Each `owner-gate` item: after the repairs, ask the owner once about the
   items still open, unless that exact action is already authorized (see
   [coordinator.md](coordinator.md)).

`next_move` is the first of those piles that is not empty: `do-not-patch`,
then `repair`, then `owner-gate`. An empty Before merge list with findings
none is `owner-gate` only when required evidence for the lock is already in
the published review or PR proof for this head.
