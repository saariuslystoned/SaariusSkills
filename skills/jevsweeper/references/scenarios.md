# JevSweeper acceptance cases

These are the coordinator outcomes. Jev still only returns the three labels.

1. Clean review text, but required real Registry proof is absent → Jev
   `repair`, status `needs-evidence`. Not owner acceptance of the gap.
2. Only owner_merge_authority remains and Bobby already authorized merge of
   this PR after reviews pass → do not re-ask; finish checks; only that
   action.
3. Review names an old head or obsolete base → not this skill; revalidate
   before routing.
4. Dependency PR merged with identical reviewed content → clear the
   dependency hold; do not churn consumer source or rerun unrelated reviews.
5. One requested change contradicts a lock and another is a valid mechanical
   repair → `do-not-patch` the first, `repair` the second; both run.
6. Review is queued or Jev is unavailable → keep real review gates; no
   duplicate dispatch; `judge: rubric by hand (Jev <reason>)`.
7. Required evidence cannot be inferred from supplied inputs → report exactly
   what is missing; do not manufacture confidence or an owner-gate.
