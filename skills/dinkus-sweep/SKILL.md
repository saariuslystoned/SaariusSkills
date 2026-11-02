---
name: dinkus-sweep
description: Sweep every open issue and pull request across the core DinkusKit repositories, compare each feature with Shopify, WooCommerce and BigCommerce, and bring the owner one numbered batch card to answer once. Use when the owner says "sweep", "dinkus sweep", or asks to clear open issues or PRs across the DinkusKit stack.
---

# Dinkus Sweep

This is the DinkusKit profile of `smoky-portfolio-sweep`. Read that core skill
and its `references/sweep-protocol.md` first: its dispositions, serial mutation
owner, pre-mutation reread and batch packet all apply here. This profile adds
the scope, discovery, the giants check, the batch card and the DinkusKit rails
in `references/dinkus-rails.md`. A profile grants no authority: only the
owner's own words merge, close, override or publish.

## Scope

Sweep these repositories, nothing else unless the owner names it:

- `dinkuskit/commerce`, `dinkuskit/payments`, `dinkuskit/ship`
- `dinkuskit/template-store`, `dinkuskit/dinkuskit`, `dinkuskit/live-journeys`
- `dinkuskit/coupons`, `dinkuskit/inventory`, `dinkuskit/books`

Read each repository's `AGENTS.md` (or `CLAUDE.md`) from its default branch
before touching it. Read the project's current plan and scope rules where the
harness keeps them (project memory, the plan file it names). Two rules shape
most verdicts: there are no real stores yet, so never ask for or build
fallbacks for existing stores; and scope does not grow without the owner.

## 1. Recover

Read the sweep's decision ledger (see **Ledger** below). Terminal decisions
(merged, closed, explicitly skipped) never re-enter. An older open item
re-enters only when its head SHA, its review state or its linked plan changed.
Check that no other thread or agent already owns an item: the owner's other
agents merge on their own, so fetch first and stay hands off unless told.

## 2. Discover

List every open pull request and every open issue in scope from live GitHub.
Do not pad and do not truncate: the batch is whatever is open. Sort each item
into one lane:

- **Contributor PRs** from forks (today: Dad, GitHub `saarius`). Discuss first,
  compare with the giants, then review.
- **The owner's agents' PRs** (Codex, Cursor and others). Qualify, but stay
  hands off unless the owner says take over.
- **Bot PRs** (version pin bumps). Close when a merged or open change already
  carries the same pins.
- **Issues.**
- **Drafts.** Status `keep`, no review.

## 3. Qualify (read-only)

For each PR record the core packet fields plus: mergeable state, CI on the
exact head, the `clawsweeper/review` commit status and the durable ClawSweeper
comment's verdict for that head, whether a product, API or data-model choice
needs a GrillTrack entry (and whether one is locked), overlap with other open
PRs, and whether current `main` already has the fix.

For each issue pick one outcome and gather its proof:

- **Fixed on main:** close it, citing the merge commit or PR and the line that
  fixes it. A linked merged PR alone is not proof.
- **Not scoped or planned:** close it with a note naming the plan or scope rule.
- **Relevant and in scope:** open a PR for it and drive that PR to the merge
  gate (CI green and ClawSweeper ready on the final head), recording any
  product decision in GrillTrack first.

## 4. Giants check

Run it whenever the feature in question has a counterpart at Shopify,
WooCommerce or BigCommerce, not only for visible or data changes. Use
`emdash-commerce` and official documentation, note the date checked, and say
plainly whether the change leaves the feature reachable by agents as well as
people: Shopify leads on agentic commerce and DinkusKit means to compete there.
Include Shopify's agent catalog and carts-and-checkout docs, and the project's
locked UCP scope, when an agent could use the feature. Skip it only for pure
CI, tooling or typo work. Each card line carries the verdict (aligned,
diverges, or n/a) with one source.

## 5. Classify ClawSweeper blocks

- **Code findings** it raised on the exact head make the PR `required-fix`.
- **Blocks that are not code** go to the card's "Override?" group with the
  reason. Typical ones: proof for populated existing stores (none exist yet),
  a reviewer-side source or blob it could not read, a stale-base admission
  failure, or a decision it could not open (post the quoted ledger entry
  yourself, per the rails, before calling it an override).
- Never override on your own. Ticking an item in "Override?" is the owner's
  call, every time.

## 6. Contributor fixes

If the PR allows edits from maintainers, fix it on the contributor's branch
yourself: merge `main` in, push the fix, keep their commits and credit, never
rebase or force-push. If it does not, post one review comment in the owner's
style (what is wrong, why, then "Please ...") or, only on the owner's word,
open a credited follow-up PR and close the original with thanks.

## 7. The batch card

Post one numbered card, each line: `repo#N`, a plain-shop-terms title, status,
a one-line reason, and the giants verdict. Group the lines:

1. Ready to merge (CI green, ClawSweeper ready on the exact head)
2. Override? (only a non-code ClawSweeper block remains)
3. Needs a fix (say who fixes it: this sweep, the contributor, or an agent)
4. Close (with the proof or the scope rule)
5. Needs the owner's decision (with a recommended answer)
6. Keep (drafts, waiting on something named)

The owner answers once, for example "merge 1, 3 and 4 once clean and green,
override 6, close 2". Read the answer against the merge words in the rails;
ask once, plainly, when a line is ambiguous.

## 8. Execute serially

One mutation owner, one item at a time. Before each action reread the live PR
or issue and stop on drift. Merge with a merge commit and the expected head
SHA. Without a ticked override, merge only after ClawSweeper is ready on the
final head. After an override merge leave one note on the PR quoting the
owner's words. Order merges so later PRs on the same repository pick up `main`
once: merge `main` into your own branches yourself; ask a contributor for one
main merge after the last of yours lands. Record each receipt (merge SHA,
closing comment link) before the next item.

## Ledger

Keep the sweep's decision ledger in project memory when the harness has one
(one file, `dinkus-sweep-ledger`); otherwise ask the owner where it lives.
Record terminal outcomes only: repository and number, outcome, merge SHA or
comment link, the owner's words, and the date. Keep it short; it is how the
next sweep skips what is settled.

## Report

End with one post: a line per item with its outcome and link, then what is
left and who owns it. Never deploy, release, press Cut beta, change secrets,
start a live journey or comment on an upstream EmDash repository as part of a
sweep; name those as next steps for the owner instead.
