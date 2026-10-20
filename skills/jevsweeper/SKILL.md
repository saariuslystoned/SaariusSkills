---
name: jevsweeper
description: After a published ClawSweeper review, classify leftover boxes with Jev as repair, owner-gate, or do-not-patch. Not Spark doorbell, leftover recap, GrillTrack Q1, or merge.
---

# JevSweeper

ClawSweeper writes the review. Jev labels what to do next. When Jev cannot
run, the agent applies the same rubric and says so; a chat model's label is
never reported as Jev's. Jev does not replace required reviews, proof, or
Bobby's authorization.

Use after a current published `<!-- clawsweeper-review item=<n> -->` comment,
when leftover Before-merge boxes, findings, or a Decision needed table remain,
or when the heading says blocked but findings are none. Prove the native
review's source binding and valid publication under the target contract before
asking Jev. Missing or stale native review evidence is a prerequisite
mismatch, not a clean review and not a Jev label. CI and comprehensive OpenClaw
may still be pending while Jev classifies valid published leftovers; retain
their independent merge/promotion gates. A pickup comment, green relay check,
or queue `completed` state does not prove a published verdict or successful
executor.

For admission, publication, retries, waits, and dependency reconciliation,
follow the exact target contract or the readable canonical
[smoky-openclaw-autoreview contract](https://github.com/saari-co/SmokySkills/blob/main/skills/smoky-openclaw-autoreview/SKILL.md),
including its conditional native-queue reference when applicable. An optional
skill installation is not a prerequisite when that contract is supplied.
JevSweeper does not dispatch or retry reviews. Follow
[grilltrack](../grilltrack/SKILL.md) for shop-owner Q1. Do not merge.

## Classify

1. Record the source and publication bind from
   [references/coordinator.md](references/coordinator.md). The published review
   must apply to this PR and live `headRefOid` under the target contract.
   Preserve its captured base; a default-branch advance alone does not require
   rebasing, retriggering, or classifying again. If native publication is absent
   or inapplicable, report the mismatch and return to the review owner without
   evaluating boxes. Required product or behavior proof missing from an
   otherwise eligible review is different: classify that gap with the rubric.
2. Build one `choice` question per leftover box. Its `state` is only that
   box (finding, Before-merge box, or Decision needed row) plus the locked
   shop-owner line from CHARTER, FEATURE_MAP, or already-written proof limits.
   Its `criteria` are the three labels mapped to their descriptions in
   [references/rubric.md](references/rubric.md). Do not send the whole repo,
   MEMORY, or the transcript. Done when every box has one question.
3. Ask the first judge this harness has, in this order:
   - OpenClaw: the core `decision_evaluate` tool.
   - Claude, Cursor, Codex, Antigravity: `decision_evaluate` from the
     `jev-decision` MCP server, same request and result shape. That server ships
     in the separate `ai-shed` plugin
     ([saari-co/ai-shed](https://github.com/saari-co/ai-shed), see its
     `jev-decision/README.md`), not in `saarius-skills`; in Claude Code the tool
     is `mcp__plugin_ai-shed_jev-decision__decision_evaluate`.
   - Neither tool present: the rubric by hand.
   Labels are only `repair`, `owner-gate`, and `do-not-patch`. Work out
   `next_move` from the box labels with the rubric's `next_move` rule. Done
   when every box has a label and the report names the judge: `Jev` with the
   result's provenance, or `rubric by hand` with the unavailable reason.
4. Attach coordinator status from the coordinator file (`actionable`,
   `waiting-on-dependency`, or `needs-evidence`). Jev never emits those.
   Then work the piles in the rubric's `next_move` order: refuse each
   `do-not-patch`; repair each `repair`; ask Bobby once for remaining
   `owner-gate` items unless that exact action is already authorized. Do not
   merge. Done when every pile has its action and the bind is in the report.

## Jev down never stops the rails

For eligible review inputs, `status: unavailable` (any reason), a timeout, or a
missing Jev tool is not an answer and not a reason to stop. Label the boxes by
the rubric yourself, write `judge: rubric by hand (Jev <reason>)` in the report,
and carry on with step 4. This fallback cannot replace an absent or stale
review. Do not retry Jev more than once, and never claim a Jev result that did
not run.

Acceptance cases: [references/scenarios.md](references/scenarios.md).
