# ClawJev rubric

Use these three labels only. Pass this file in `decision_evaluate` `state`.

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

- `repair` if any leftover item is repair.
- `owner-gate` if every leftover item is owner-gate, including an empty Before
  merge list with findings none.
- `do-not-patch` if any leftover item is do-not-patch. Report that item; still
  repair other mechanical items.
