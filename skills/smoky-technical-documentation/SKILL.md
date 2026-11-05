---
name: smoky-technical-documentation
description: Build, review, audit, or rewrite human and agent technical documentation against current source truth. Use for operational accuracy, commands, paths, policy and release claims, not merely writing-style cleanup.
---

# Source-truth technical documentation

Read the request and trusted repository instructions first. Check them and available skill metadata for a configured profile-specific variant or optional binding; read that first unless already loaded. Do not invent a binding, search unrelated files, or bypass a configured profile. A binding supplies local choices, not permission. Without one, use this portable core.

## Scope and authority before prose

Identify the mode (`build`, `review`, `audit`, `rewrite`), intended reader (human, agent or both), reader task, and requested files/directory/diff. Use the assigned owner/worktree for edits. Review/audit is report-only unless remediation is authorized. Repository size or a single stale link does not authorize a repository-wide audit, new orchestration or additional writers.

Read current implementation, applicable contracts and relevant tests before polishing language. For commands, paths, links and release claims, use [source fidelity checks](references/source-fidelity.md). Source can establish implementation; it cannot alone establish deployment or observed runtime health. Mark planned, implemented, tested, deployed and observed claims distinctly, with version/date and evidence where relevant. Resolve conflicting sources or state the uncertainty; do not silently promote a plan into a capability.

For agent/contributor instructions, read [policy and alias checks](references/policy-and-aliases.md). Preserve policy meaning, scope, authority, precedence and approval gates. A wording edit is not permission to change the policy or normalize aliases.

## Apply only the requested mode

- **Build:** define prerequisites and the successful reader outcome. Add the smallest useful procedure, reference or explanation in the existing information architecture. Match the repository's framework, components, terminology and release state rather than migrating platforms.
- **Review:** inspect the scoped diff plus necessary source/context. Report concrete incorrect claims and reader-impacting omissions with locations and evidence. Separate required fixes from optional wording preferences.
- **Audit:** inventory the requested surface, including governance/product/framework files when they are in scope. Read every page claimed as covered. Run existing native validators; verify findings against current source and deduplicate. Report coverage and unread/unverified gaps. If too large to finish, checkpoint at an honest boundary; do not claim exhaustive coverage from sampling.
- **Rewrite:** establish what must remain true, then simplify wording. Preserve literal commands, names, paths, numbers, conditions, exceptions, warnings and modality. If source contradicts the text, distinguish an evidenced factual correction from a meaning-preserving rewrite. Do not silently fix facts by guessing.

Write plain English with clear actors and consistent terms. Keep safety conditions beside the action. Simplified Technical English may inform wording when requested or useful; it is optional, not a blanket compliance, sentence-cap or lint requirement. Precision wins over brevity. Do not alter code/CLI literals to satisfy prose style.

## Validate and report proportionately

Check each introduced or changed command/flag/path/link/alias against its owning source, safe help or native validation. Verify prerequisites, working directory, expected outputs and failure behavior. Do not run gated commands to prove documentation; static verification and safe dry-run/help are sufficient where execution is unauthorized, with the limit stated.

Preserve existing headings/anchors, navigation, redirects, generated-source ownership and locale policy. Check filesystem paths separately from published routes. Run the repository's applicable documentation/build/link checks without triggering deployment or installing new infrastructure. Record which checks actually ran and what they establish.

Return the requested draft/edit/findings plus concise validation notes, coverage and unresolved questions. Routine scoped findings stay inline. Create durable evidence only for a requested deliverable or concrete audit/resumption/handoff need; name its consumer/purpose and reuse the existing task location. This skill does not authorize merge, publication, installation or rollout, and source edits do not prove any of those occurred.

## Provenance

Adapted from Vincent Koc's MIT-licensed technical-documentation at a pinned revision. See [third-party notice](THIRD_PARTY_NOTICES.md). Model rosters, workflow runtime, STE reference trees and lint scripts are not bundled.
