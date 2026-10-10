# JevSweeper coordinator state

Jev emits only `repair`, `owner-gate`, and `do-not-patch`. Everything below is
the agent's report beside those labels. Do not send this file to Jev.

## Bind

Every classification is valid only for:

- `dinkuskit/<repo>#<n>`
- live `baseRefOid` and `headRefOid`
- the published review comment URL whose body contains
  `<!-- clawsweeper-review item=<n> -->` and that head SHA
- the CHARTER / FEATURE_MAP / proof-limit line used as the lock

If any of those change, classify again. A pickup comment or a green review /
relay check is not this bind.

## Authorization

Keep classification and owner authority separate. Record whether an
`owner-gate` is already authorized, the exact action, and the user instruction
that granted it.

If Bobby already said merge after reviews pass, and the leftover is only
maintainer look / owner_merge_authority for that same PR and head, do not ask
again. Finish the required checks, then only that authorized action. New
scope, a revoked yes, or an unsupported action still needs a decision.

## Execution status

Attach one status per leftover item, never as a Jev label:

- `actionable` — the agent can repair, refuse, or ask now
- `waiting-on-dependency` — Spark still queued, a sibling PR, or merged
  content that must be compared first. Name the owner and the resume
  condition. Do not dispatch a second review. An identical merged tree can
  clear a pin/dependency hold without rewriting consumer source.
- `needs-evidence` — required proof for the locked outcome is absent
  (Registry installer path, exact-head browser/terminal transcript). That is
  also `repair` for Jev. Do not force it into `owner-gate` to produce a label.

A queued reviewer is not a product decision. Missing deployment config is not
automatically a code defect.
