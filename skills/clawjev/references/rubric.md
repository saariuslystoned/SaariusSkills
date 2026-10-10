# ClawJev rubric

Use these three labels only. Each label's section below is its description in
the `choice` question's `criteria`; the box and the locked line go in `state`.

## repair

There is a code, test, or exact-head proof change the agent can make without a
new shop-owner lock. Examples: a P1 that names a file and a fix; missing
real-behavior proof for the locked contract; a leftover fixture; a schema that
rejects an upgrade shape the current main already writes.

## owner-gate

The code matches an already-locked shop-owner contract, or the leftover box is
only maintainer acceptance of a documented public boundary or proof limit.
Examples: platinum/gold with findings none; checkboxes that restate "accept
public guest POSTs / payment window / Stripe not run"; real `sk_test` vs
dry-run; ClawSweeper is not merge authority.

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
   items still open.

`next_move` is the first of those piles that is not empty: `do-not-patch`,
then `repair`, then `owner-gate`. An empty Before merge list with findings
none is `owner-gate`.
