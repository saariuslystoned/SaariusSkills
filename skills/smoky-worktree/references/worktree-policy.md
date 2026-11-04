# Worktree policy

Use a trusted assigned revision, or fetch and verify the intended remote's default branch. Do not infer freshness from a stale local main branch. Preserve the operator's landing branch and unrelated dirty work.

Prefer the repo-owned helper. A plain Git setup can use:

```sh
git rev-parse --show-toplevel
git status --short --branch
git fetch origin
git symbolic-ref --quiet --short refs/remotes/origin/HEAD
# Resolve the verified ref to a full commit before using it.
git worktree add -b task-branch ../task-worktree <verified-base-sha>
```

Use the repository's branch naming and location convention. If origin/HEAD is absent, verify the intended main/master ref or ask only for the missing identity. Do not print a remote URL containing embedded credentials.

Before creation, inspect the task's existing session/workspace and `git worktree list --porcelain`. Reuse a matching assigned checkout after checking repository, branch, base/head and writable ownership. A name match alone is not sufficient. Conflicting ownership or a mismatched manifest is a blocker, not a reason to invent a new task name.

For a new single-repository task, verify whether the helper fetches or merely branches from local HEAD; pass the verified full base SHA explicitly when needed. For a new multi-repository task, use the configured workspace provisioner once for the selected repository set. Keep each repository's commits, tests and pull requests separate. A task runtime's start, attach and resume operations may have different provisioning semantics: read the current command contract before choosing one. An existing workspace without an attached runtime is not evidence that an arbitrary start command can adopt it.

Record repository, branch, full base SHA, worktree, owner, allowed mode, proof path and stop condition. Verify that the checkout and assignment agree before editing. Review another task read-only unless writable ownership is handed over explicitly.

Worktree setup does not authorize cleanup. Do not reset, stash, prune, remove or switch another task's checkout to make room. Stop on conflicting ownership, untrusted source identity or a missing required dependency, and report a concrete recovery step.
