# JevSweeper coordinator state

Jev emits only `repair`, `owner-gate`, and `do-not-patch`. Everything below is
the agent's report beside those labels. Do not send this file to Jev.

## Bind

Every classification is valid only for:

- the target `owner/repo#<n>`
- the live `headRefOid`, the captured reviewed base/head, and the current base
  context needed by the target contract
- the published review comment URL whose body contains
  `<!-- clawsweeper-review item=<n> -->`, with authoritative evidence binding
  that publication to the reviewed source
- request identity and queue item/generation when exposed by that evidence
- the target contract, native publication evidence, and product-proof links
- the CHARTER / FEATURE_MAP / proof-limit line used as the lock

Use the publication or its authoritative bound receipt for reviewed base/head;
do not demand optional metadata that the current review does not expose. Do
not infer identity from the newest timestamp. A pickup comment, a green relay
check, or a queue row is not the published review bind. Read back the actual
verdict: `completed` can include a failed executor and cannot establish clean.

A changed head or a review rendered inapplicable by the target contract needs
current review evidence before classification. Preserve the captured immutable
base for interpreting findings. A default-branch advance alone does not
invalidate admission or a still-applicable published review, and does not
justify merge-main, rebase, or retrigger. Reclassify affected boxes when their
applicable reviewed source or locked outcome changes.

When a superseded queue item names a replacement, follow that recorded identity
and prove the replacement publication's bind. Otherwise report its retirement
or refusal reason. Neither the superseded row nor a newer-looking comment
proves current review. An intake rejection may terminate as `superseded` /
`intake_rejected` without any review.

Missing or stale native review/publication evidence means the inputs are not
yet eligible. Report the exact prerequisite mismatch without assigning a Jev
label; resume when the review owner supplies applicable native evidence. Keep
the target contract's CI, Spark-2 comprehensive OpenClaw (including required
exact-tuple/P3 evidence), and native ClawSweeper gates separate. A native
verdict does not waive another required gate. CI or comprehensive review still
pending does not block classification of valid published native leftovers.
Report those gate statuses alongside the classification; do not claim merge
or promotion readiness until the target contract's gates pass.

## Authorization

Keep classification and owner authority separate. Record whether an
`owner-gate` is already authorized, the exact action, and the user instruction
that granted it.

If Bobby already said merge after reviews pass, and the leftover is only
maintainer look / owner_merge_authority for that same PR and head, do not ask
again. Preserve that exact authorization for the actor responsible for the
action, after the required checks pass; Jev grants no authority and this skill
does not perform the merge. New scope, a revoked yes, or an unsupported action
still needs a decision.

## Execution status

Attach one status per leftover item, never as a Jev label:

- `actionable` — the agent can repair, refuse, or ask now
- `waiting-on-dependency` — a native publication prerequisite, sibling PR, or
  merged content must be resolved or compared first. Name one waiting owner,
  the source identity, and the resume condition. A wait status does not make
  missing native review inputs eligible for Jev. An identical merged tree can
  clear a pin/dependency hold when the target contract permits, without
  rewriting consumer source.
- `needs-evidence` — required proof for the locked outcome is absent
  (Registry installer path, exact-head browser/terminal transcript). That is
  also `repair` for Jev. Do not force it into `owner-gate` to produce a label.

A queued reviewer is not a product decision. Missing deployment config is not
automatically a code defect.

For the native rail, `pending` (including deferred work), `leased`, `parked`,
`superseded`, and `completed` describe execution, never Jev labels. Deferred
work is stored as `pending` with a future eligibility time. The review owner
uses the canonical review contract for signed intake and metadata-only per-PR
inspection through the approved adapter. Preserve its generation-aware retry
rules; do not issue a duplicate dispatch. Prefer a supported notification or
bounded long wait, with one owner and a recorded resume condition. Do not run
a repeated timer-check loop. If no supported wait is available, hand back the
waiting record and stop rather than inventing a new watcher.
