# JevSweeper acceptance cases

These are expected coordinator outcomes for the skill's contract. They are
scenario acceptance criteria, not claims that live Jev or the review rail has
been exercised. Jev still only returns the three labels; an ineligible input
does not receive a fourth label.

1. Eligible published review says findings none, but required real Registry
   proof is absent → Jev `repair`, status `needs-evidence`. Not owner acceptance
   of the gap.
2. Only owner_merge_authority remains and Bobby already authorized merge of
   this PR after reviews pass → do not re-ask; finish checks; preserve that
   scoped authorization for the actor responsible for the action.
3. Review names an old head, wrong PR/request, or a base that makes it
   inapplicable under the target contract → report the prerequisite mismatch;
   no Jev or manual-rubric evaluation until current review evidence exists.
4. Dependency PR merged with identical reviewed content → clear the
   dependency hold; do not churn consumer source or rerun unrelated reviews.
5. One requested change contradicts a lock and another is a valid mechanical
   repair → `do-not-patch` the first, `repair` the second; both run.
6. Current published review is eligible, but Jev is unavailable → keep real
   review gates; classify by the rubric with
   `judge: rubric by hand (Jev <reason>)`. The same fallback is forbidden when
   the review itself is missing or stale.
7. Required evidence cannot be inferred from supplied inputs → report exactly
   what is missing; do not manufacture confidence or an owner-gate.
8. Native item is `pending` (including a deferred item), `leased`, or `parked`,
   with no current publication → no Jev evaluation. Record
   `waiting-on-dependency`, one waiting owner, source identity, and resume
   condition. Use a supported notification or bounded long wait; do not
   timer-poll or dispatch another review.
9. Native item is `completed`, but its executor failed or no applicable
   published verdict can be read back → no clean claim and no Jev evaluation.
   Return the missing prerequisite to the review owner.
10. Item is `superseded` / `intake_rejected` after deterministic admission
    rejection and no review was produced → report that result, not a clean
    review. No Jev label or generic retry; the review owner follows the
    canonical intake/generation contract.
11. Old item is superseded and a replacement has a published review → follow
    the recorded replacement identity and prove the current PR/head and
    captured reviewed base bind. A newer timestamp alone cannot select it.
12. Default branch advanced after a valid captured review, while the PR head
    and applicable contract remain unchanged → preserve the captured base;
    do not rebase, merge-main, retrigger, or classify again solely for that
    advance.
13. A valid publication exposes reviewed base/head but no optional request or
    generation field → use its authoritative source bind; do not invent a
    missing-metadata gate. Record request/generation when exposed.
14. Native ClawSweeper has a valid current publication with leftover boxes,
    while CI or comprehensive OpenClaw/P3 is pending → classify the legitimate
    leftovers now and report the other gates separately. Do not wait for those
    gates before classifying, claim merge/promotion readiness, or use Jev to
    waive them.
