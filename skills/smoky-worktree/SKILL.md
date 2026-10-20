---
name: smoky-worktree
description: Prepare or verify an isolated Git worktree from a fresh trusted base, with one writer and explicit source identity. Use before source changes or exact-revision review.
---

# Worktree Setup

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Read `references/worktree-policy.md` before choosing a base or creating a checkout. Identify the repository, current branch, dirty state and assigned source revision. Preserve existing operator checkouts and other tasks' work.

Prefer a repository-owned helper. Otherwise fetch the intended remote, resolve its default branch, and create a separate branch/worktree from the verified base. An explicitly assigned revision wins over a default; record it rather than silently substituting another branch. Do not change the branch of an operator's landing checkout.

Assign one writable owner per source slice. Keep review checkouts read-only unless ownership is explicitly transferred. Before replacing a writer, establish termination or cancellation and preserve partial work. Creating a worktree is source preparation, not permission to merge, deploy or clean other worktrees.

Return repository, worktree, branch, full base SHA, status, command used, proof path and next owner/action. Stop on ambiguous source identity, dirty-state overlap, conflicting ownership or missing required access. Do not inspect credential stores or authentication-bearing history to diagnose a Git route.
