---
name: smoky-deslop
description: Clean AI-style noise from staged, branch, or user-scoped code diffs while preserving behavior and repository idioms. Use before final review, not for writing-style edits or skill packaging audits.
---

# Changed-code cleanup

Read the request and trusted repository instructions first. Check them and available skill metadata for a configured profile-specific variant or optional binding; read that first unless already loaded. Do not invent a binding, search unrelated files, or bypass a configured profile. A binding supplies local choices, not permission. Without one, use this portable core.

## Establish the exact scope

Use the existing assigned writable owner and worktree. Verify repository, branch, dirty state and ownership before editing; do not provision workers or another assignment to perform cleanup. Preserve other owners' changes.

Select the requested **staged**, **branch**, or **user-scoped** diff. Record full base/head SHAs and any uncommitted scope; use [diff identity](references/diff-identity.md) to distinguish the index, working tree and branch changes. Resolve an ambiguous base or conflicting ownership before changing files.

Default to changed hunks. Read surrounding unchanged code, tests and applicable style/configuration to establish idioms, error semantics and intentional exceptions. A named file is not permission for unrelated refactoring. Expand beyond the selected hunks only for a necessary coherent edit within the user's scope; otherwise report the dependency.

## Make the smallest safe cleanup

Use [cleanup decisions](references/cleanup-decisions.md) when a suspicious pattern may carry behavior. Candidates include repetitive narration, inconsistent local naming, needless wrappers and type escapes. Appearance is a reason to investigate, not evidence that a check is redundant.

- Preserve behavior, public interfaces, security, validation, error handling and reliability. Preserve intentional logging, metrics and tracing.
- Do not mechanically delete defensive checks, casts, retries, catches or comments. Establish call-path guarantees and consumers first. Necessary rationale, warnings, compatibility notes and suppression directives stay.
- Prefer repository idioms over a new abstraction or broad formatter pass. Do not weaken types or validation to make lint pass.
- If a proposed cleanup changes behavior, separate it as an explicitly scoped change. Do not disguise a bug fix, permission change or reliability tradeoff as cleanup. If intent cannot be established, leave the code and report the uncertainty.

## Verify and hand back

Inspect the resulting diff against the selected baseline. Run the target's applicable tests, type/lint checks and focused failure/security cases. Record actual outcomes and gaps; a small diff alone does not prove behavior preservation.

Cleanup happens **before final exact-head review**. If a reviewed head changes, repeat applicable verification and review for the new source under repository policy. Do not treat earlier clean evidence as current. This skill grants no merge, install, deployment or distribution authority.

Return a concise summary of paths and cleanup, base/head plus index/working-tree scope, checks and remaining risks. A no-op is valid when the apparent noise is necessary. Keep routine findings inline; use existing task proof when required by the assignment.

## Provenance

Adapted from Vincent Koc's MIT-licensed technical-deslop at a pinned revision. See [third-party notice](THIRD_PARTY_NOTICES.md). This is a portable adaptation, not the upstream runtime or a replacement for repository policy.
