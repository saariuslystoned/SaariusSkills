# Workflow contract

Treat GrillTrack as an intent-aware, typed artifact graph. A phase may consume
only the durable outputs of its predecessors plus fresh project facts. No
successful transition silently authorizes the next transition.

## Authority

- **Invocation:** Allow natural activation only when the user clearly asks to
  start, continue, resume, reopen, or close product-cycle work. Also accept
  explicit `$grilltrack`. A casual mention never activates the workflow.
- **Input:** Consume repository instructions, the real project baseline, and
  the current `.grilltrack/ledger.json` when it exists.
- **Output:** Produce an updated ledger and event history, source-linked
  implementation and proof references, and either a next-grill recommendation
  or a confirmed closeout.
- **Allowed mode:** Observe and suggest before shared-understanding
  confirmation. After confirmation, mutate only the bounded local domain the
  user confirmed.
- **Mutation owner:** Preserve the repository's active mutation owner,
  branch/worktree, and concurrency rules. GrillTrack does not create a second
  writer or hand mutation authority to a reviewer.
- **Context cost:** Prefer one complete cycle in a sharp context. At a phase
  boundary, externalize state before context pressure makes the agent
  rediscover or flatten decisions.
- **Gates:** Require shared-understanding confirmation before implementation,
  repository and safety gates for every action, and separate authorization for
  delivery.
- **Closer:** The user owns closure confirmation.
- **Stop rule:** Pause on incomplete proof, misleading fidelity, unresolved
  review findings, context loss, baseline drift, or any human/repository gate.

## Artifact graph

```text
repository facts + prior ledger
  -> focused domain and cadence
  -> proposed decisions with dependency edges
  -> confirmed shared-understanding summary
  -> implementation_ref
  -> verification_ref
  -> review_ref + immutable source identity + adjudication
  -> next-grill recommendation or confirmed closeout
```

Store artifacts where their owning project expects them. The ledger stores
stable references and lifecycle state; it does not duplicate whole specs,
proof bundles, transcripts, or credentials.

## Scope routing

Run one focused cycle when the next useful decision and bounded implementation
fit in a sharp session. If the destination is too foggy or the unresolved
decision graph spans several useful sessions, stop before inventing a
monolithic grill. Create or adopt a source-linked decision map, then use each
GrillTrack cycle to resolve one current frontier node. Research and prototypes
may clear uncertainty, but they do not acquire implementation or delivery
authority.

## Context boundaries

Treat compaction, a fresh session, a new harness, a new directory, or a new
owner as a context boundary. Cross it with durable artifacts, never assumed chat
memory.

At a phase boundary:

1. Continue when the next phase needs the current reasoning as a primary source
   and the context remains sharp.
2. Otherwise update and validate the ledger, persist the exact source-linked
   inputs and outputs, and record the next safe action.
3. Use `pause` when work will stop or another owner/harness must resume it.
4. In the new context, read the ledger first and load only the referenced
   artifacts needed for the current frontier.

Context pressure is evidence, not a universal token threshold. Warning signs
include repeated rediscovery, compaction, growing dependency fan-out, many
unresolved decisions, unexpected duration, and inability to restate the active
lock from its source. Pause and externalize before quality drifts.
