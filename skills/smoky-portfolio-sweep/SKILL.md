---
name: smoky-portfolio-sweep
description: Qualify and close an already-selected bounded batch of issues or pull requests using current source evidence and serial mutation ownership. Use after priorities are set.
---

# Portfolio Sweep

Read the current request and trusted repository instructions first. If they name an optional binding for this skill, read it for local targets, tools and policy. Without a binding, use the portable workflow below. A binding does not grant authority to act.

Read `references/sweep-protocol.md`. Accept a finite selected batch, its owner, the intended outcome and its mutation boundary before execution. Use `smoky-maintainer` if prioritization is still needed. Do not silently add candidates, truncate the input or create a second portfolio queue.

Qualify each item read-only: exact head/base for a PR, current acceptance criteria for an issue, required checks, review/adjudication, dependencies, duplicate or superseding work and remaining blockers. Use the authoritative current service for state; exported packets are evidence, not mutation authority.

Assign one mutation owner. Parallel read-only qualification is allowed when authorized, but comments, labels, closes, branch writes and merges are serial. Before each mutation, reread relevant live state and authority. Requalify if source identity, gates or dependencies changed.

Separate `merge-ready` from permission to merge. Clean checks never grant authority. If a required technical fix remains, report it even when an owner gate is also pending. Record the completed action's canonical receipt before moving to the next item.

Stop when every selected item has a supported disposition and next action. Return the compact batch packet from the protocol; leave unrelated work and history intact.
