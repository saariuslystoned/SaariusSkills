# Bounded sweep protocol

Record a selected finite batch, capacity, read-only qualifiers, one mutation owner and the intended stop condition. Batch size and tool/review policy come from the assignment. If selection or capacity is missing, prepare a proposal; do not silently expand or truncate the batch.

For each PR capture exact head, base ref/SHA, current state, checks, accepted review findings, dependencies/overlap, blockers and authority. For an issue capture acceptance criteria, current state, linked work and proof for each claimed completed criterion. A linked merged PR alone does not establish that the whole issue is resolved.

Use one disposition in this precedence: superseded (proven terminal replacement); required-fix (accepted defect remains); merge-ready (technical readiness only); human-gate (only authority remains); defer (outside this batch); keep (valid and open). Record uncertainty as a blocker rather than manufacturing readiness.

Before a mutation, reread the authoritative service and confirm the exact source, gates, dependencies, overlap and authorization still match. Stop and requalify on drift. Only the mutation owner performs comments, labels, closes, branch writes or merges, serially, recording each canonical receipt before the next action. Qualifiers do not mutate.

```text
sweep id:
scope: <approved repositories>
selection authority:
batch size: <finite selected count>
qualifiers: <read-only owners>
mutation owner: <one owner or none>
candidates:
  - repo/item and canonical URL:
    kind: <pull-request|issue>
    exact head: <SHA or n/a>
    exact base ref: <ref or n/a>
    exact base SHA: <SHA or n/a>
    status: <disposition>
    evidence:
    dependencies/overlap:
    blocker/gate:
    next action:
proposed serial mutations:
  - action, order, preconditions, authorization, stop condition:
completed serial mutations:
  - action, order, pre-mutation reread, receipt:
residuals:
next: <owner/action>
```

The packet is evidence and handoff, not a competing queue. Implementation or review fixes go to the repository's assigned owner; do not widen the sweep role to patch unrelated source.
