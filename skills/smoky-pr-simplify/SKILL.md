---
name: smoky-pr-simplify
description: Simplify an implementation to its smallest complete change before PR review or after substantial repairs. Reconsider responsibilities, state, compatibility paths and test value across the selected diff.
---

# Simplify a proposed change

Use this pass when preparing or shrinking a PR, or when implementation has
accumulated machinery during repairs. It complements independent review.
For a request limited to local style and code noise, use `smoky-deslop`.

Read the request, current scope and applicable repository instructions. Use
the existing assigned worktree and writer. A review-only assignment produces
findings. Edit only with the task's existing authority, and preserve other
owners' changes. Honor a configured repository profile when one is supplied.

## Re-derive the necessary change

Establish the selected base, candidate head and any included staged or working
tree changes. Inspect the complete selected diff and retained evidence. State
the requested outcome and the invariant the change must establish. Then ask
what implementation would achieve them starting from the base.

Trace each changed area to that outcome. Identify work that serves a different
goal and propose moving it out of the PR. For an oversized change, find a
coherent independently useful stage with its own proof. Line count can guide
inspection but does not determine correctness or force a split.

Read direct callers, existing owners, relevant tests and history before
removing behavior. Preserve contracts for supported inputs and existing data,
including justified migration, upgrade, error and lifecycle paths. If their
purpose remains unclear, retain them and report the uncertainty.

## Reduce machinery at its owner

Start with additions that create lasting maintenance work.

- Give each decision one owner. Callers should consume its result without
  repeating its policy. Preserve distinct transport and lifecycle contracts.
- Challenge additional stored state, managers, caches, representations and
  adapters. Prefer an existing owner when its authority, lifetime, atomicity
  and cleanup fit. Derive values when synchronization would duplicate truth.
- Remove superseded paths and forwarding-only layers when their consumers can
  migrate within the selected scope. Complete an intended cutover rather than
  accumulating parallel implementations.
- Keep compatibility code tied to a supported contract. Preserve necessary
  validation, retries, recovery, telemetry and error semantics. Apparent
  redundancy alone is insufficient reason to delete them.

Keep required growth when it is the smallest complete way to satisfy the
outcome. A deletion target must never replace reasoning about behavior.
Surface new product choices, broken contracts or unrelated cleanup for the
owner instead of folding them into this pass.

## Keep proof for distinct failures

For each added or changed test group, name the observable failure or independent
contract it protects and why existing proof misses it. Preserve distinct
ordering, cancellation, restart, rejection, upgrade and consumer risks.

Consolidate duplicated setup and same-contract assertions into an existing
suite where possible. Challenge tests that repeat a mock's supplied behavior,
assert incidental implementation shape or require production hooks with no
production caller. Static and slow tests can protect real contracts. Before
consolidating or removing tests, briefly map each affected distinct failure
contract to its retained test or other proof in the existing task or PR
evidence. Preserve the strength of the assertions that remain.

## Verify and hand back

Reinspect the full selected diff after editing. Rerun the reproduction and
checks for changed contracts and affected consumers. Reuse proof only while
its inputs and coverage remain valid. Repository policy owns broader checks,
independent review, publication and merge. A changed reviewed head needs the
applicable new verification and review.

Report the outcome, responsibility or state removed, supported behavior still
protected, source scope, checks and remaining uncertainty. Distinguish a
reduction from an earlier proposal from the final diff against the base.
Finish when the change is complete and each remaining addition has a reason.
Keeping the existing design is a valid result when evidence justifies it.

## Provenance

Adapted from OpenClaw's `pr-simplify` skill. The portable scope, source identity,
proof and authority choices here follow the consuming repository. See the
[source and license notice](THIRD_PARTY_NOTICES.md).
