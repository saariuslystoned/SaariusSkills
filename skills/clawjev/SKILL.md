---
name: clawjev
description: After a published ClawSweeper review, classify leftover boxes with Jev as repair, owner-gate, or do-not-patch. Not Spark doorbell, leftover recap, GrillTrack Q1, or merge.
---

# ClawJev

ClawSweeper writes the review. Jev labels what to do next. Chat models do not
stand in for Jev. Jev does not replace live GitHub, Spark, or Bobby's merge yes.

Use after a published `<!-- clawsweeper-review item=<n> -->` comment on the live
`headRefOid`, when leftover Before-merge boxes, findings, or a Decision needed
table remain, or when the heading says blocked but findings are none. Stop and
follow `dinkuskit-review-rails` for Spark wait vs miss, stacked bases, pickup,
or dispatch. Follow `dinkuskit-leftover-recap` for leftover vs `main`. Follow
`grilltrack` for shop-owner Q1. Do not merge.

## Classify

1. Confirm the published review marker names this PR and the live `headRefOid`.
   A pickup comment or a review on an older SHA is not this skill. Done when
   those two ids match.
2. Copy three piles into `decision_evaluate` `state`: the findings, Before-merge
   boxes, and Decision needed table; the locked shop-owner line from CHARTER,
   FEATURE_MAP, or already-written proof limits; and [references/rubric.md](references/rubric.md).
   Do not send the whole repo, MEMORY, or the transcript. Done when `state` is
   only those piles.
3. Ask Jev one `choice` per leftover box, plus `next_move` for the whole PR.
   Labels are only `repair`, `owner-gate`, and `do-not-patch`. Criteria are the
   rubric file. Done when `decision_evaluate` returns `status: ok` with those
   labels, or `unavailable` is reported as Jev-down and this skill stops.
4. If any item is `repair`, repair that item through `dinkuskit-review-rails`
   product findings. If every item is `owner-gate`, stop and ask Bobby the
   shop-owner yes. If any item is `do-not-patch`, refuse that patch and keep the
   lock. Do not merge. Done when the next action matches those labels.

If `decision_evaluate` is missing or `credentials-unavailable`, say Jev did not
run and apply the same three labels by the rubric without claiming a Jev result.
