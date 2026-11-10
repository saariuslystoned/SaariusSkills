---
name: smoky-worktree
description: Prepare or verify an isolated Git worktree from a fresh trusted base, with one writer and explicit source identity. Use before source changes or exact-revision review.
---

# Worktree Setup

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Read `references/worktree-policy.md` before choosing a base or creating a checkout. Identify the repository, current branch, dirty state and assigned source revision. Preserve existing operator checkouts and other tasks' work.

Check for an assigned workspace or existing task session before provisioning. A worker uses the supplied checkout, branch and repository mounts after verifying them; it does not create a duplicate top-level assignment or extra writable workspace to repeat setup. This preserves the same assignment across follow-ups and harness recovery; it does not prohibit bounded specialists permitted under the same lead. If a workspace contains several repositories, read its manifest and each repository's contract, and keep Git changes and verification inside the owning repository.

Prefer a repository-owned helper. Otherwise fetch the intended remote, resolve its default branch, and create a separate branch/worktree from the verified base. An explicitly assigned revision wins over a default; record it rather than silently substituting another branch. Do not change the branch of an operator's landing checkout.

Assign one writable owner per conflicting source slice. Give any permitted specialist explicit scope, permissions and source identity, and tie its identity, results and proof to the parent assignment. The lead retains integration and final verification; scope or writable-workspace expansion returns to the coordinator. Verify child status, cancellation and stopped-writer evidence across parent interruption, exit or failure before relying on unattended child writers; keep children supervised or read-only if lifecycle support is unproved. Keep review checkouts read-only unless ownership is explicitly transferred. Before replacing a writer, prove that it and any conflicting child writers stopped, then preserve partial work and transfer ownership within the same assignment. Creating a worktree is source preparation, not permission to merge, deploy or clean other worktrees.

Return repository, worktree, branch, full base SHA, status, command used, proof path and next owner/action. Stop on ambiguous source identity, dirty-state overlap, conflicting ownership or missing required access. Do not inspect credential stores or authentication-bearing history to diagnose a Git route.
