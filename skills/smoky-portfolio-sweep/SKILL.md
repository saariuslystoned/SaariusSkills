---
name: smoky-portfolio-sweep
description: Qualify and close an already-selected bounded batch of issues or pull requests using current source evidence and serial mutation ownership. Use after priorities are set.
---

# Portfolio Sweep

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Read `references/sweep-protocol.md`. Accept a finite selected batch, its owner, the intended outcome and its mutation boundary before execution. Use `smoky-maintainer` if prioritization is still needed. Do not silently add candidates, truncate the input or create a second portfolio queue.

Qualify each item read-only: exact head/base for a PR, current acceptance criteria for an issue, required checks, review/adjudication, dependencies, duplicate or superseding work and remaining blockers. Use the authoritative current service for state; exported packets are evidence, not mutation authority.

Assign one mutation owner. Parallel read-only qualification is allowed when authorized, but comments, labels, closes, branch writes and merges are serial. Before each mutation, reread relevant live state and authority. Requalify if source identity, gates or dependencies changed.

Separate `merge-ready` from permission to merge. Clean checks never grant authority. If a required technical fix remains, report it even when an owner gate is also pending. Record the completed action's canonical receipt before moving to the next item.

Stop when every selected item has a supported disposition and next action. Return the compact batch packet from the protocol; leave unrelated work and history intact.
