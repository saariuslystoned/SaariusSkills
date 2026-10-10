---
name: clawjev
description: After a published ClawSweeper review, classify leftover boxes with Jev as repair, owner-gate, or do-not-patch. Not Spark doorbell, leftover recap, GrillTrack Q1, or merge.
---

# ClawJev

ClawSweeper writes the review. Jev labels what to do next. When Jev cannot
run, the agent applies the same rubric and says so; a chat model's label is
never reported as Jev's. Jev does not replace live GitHub, Spark, or Bobby's
merge yes.

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
2. Build one `choice` question per leftover box. Its `state` is only that
   box (finding, Before-merge box, or Decision needed row) plus the locked
   shop-owner line from CHARTER, FEATURE_MAP, or already-written proof limits.
   Its `criteria` are the three labels mapped to their descriptions in
   [references/rubric.md](references/rubric.md). Do not send the whole repo,
   MEMORY, or the transcript. Done when every box has one question.
3. Ask the first judge this harness has, in this order:
   - OpenClaw: the core `decision_evaluate` tool.
   - Claude, Cursor, Codex, Antigravity: `decision_evaluate` from the
     `jev-decision` MCP server ([bridge/jev-decision](../../bridge/jev-decision/README.md)),
     same request and result shape.
   - Neither tool present: the rubric by hand.
   Labels are only `repair`, `owner-gate`, and `do-not-patch`. Work out
   `next_move` from the box labels with the rubric's `next_move` rule. Done
   when every box has a label and the report names the judge: `Jev` with the
   result's provenance, or `rubric by hand` with the unavailable reason.
4. If any item is `repair`, repair that item through `dinkuskit-review-rails`
   product findings. If every item is `owner-gate`, stop and ask Bobby the
   shop-owner yes. If any item is `do-not-patch`, refuse that patch and keep the
   lock. Do not merge. Done when the next action matches those labels.

## Jev down never stops the rails

`status: unavailable` (any reason), a timeout, or a missing tool is not an
answer and not a reason to stop. Label the boxes by the rubric yourself, write
`judge: rubric by hand (Jev <reason>)` in the report, and carry on with step 4.
Do not retry Jev more than once, and never claim a Jev result that did not run.
