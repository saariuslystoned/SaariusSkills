# Diff identity

Choose one baseline and target deliberately. Commands below are read-only examples; substitute the verified full commit IDs and literal pathspecs, not guessed refs. Run inside the assigned repository. Never reset, stash or switch another task's checkout to make the diff easier to read.

## Common identity

```sh
git status --short --branch
git rev-parse --show-toplevel
git branch --show-current
git rev-parse --verify HEAD
```

Record the repository and branch plus full HEAD. A commit ID does not identify uncommitted content. Capture the relevant diff and status before/after in the existing task record when durable evidence is required. Do not publish sensitive code or private paths.

## Staged cleanup

The baseline is HEAD; the target is the index, not the working-tree copy.

```sh
git diff --cached --name-status
git diff --cached -- <selected-paths>
git diff -- <selected-paths>
```

The last command reveals unstaged overlap. If a path is partially staged, inspect the index version as well as the working tree. Do not silently stage unrelated hunks, overwrite unstaged work, or claim that a working-tree edit changed the index. Agree how selected edits reach the index; stage only owned, intended hunks and inspect the cached diff again. An unborn branch has no HEAD baseline; stop to establish an explicit empty-tree or other user-approved baseline rather than inventing commit identity.

## Branch cleanup

Resolve the base from the requested PR or user-supplied revision. Otherwise verify the repository's default branch and fresh remote identity; never assume `origin/main` or trust stale local refs. Fetch only the intended remote when permitted. Record both the full selected base and the actual merge base.

```sh
git rev-parse --verify '<base>^{commit}'
git merge-base <base-sha> <head-sha>
git diff <merge-base-sha> <head-sha> -- <selected-paths>
```

This is the branch-introduced diff (the meaning of a three-dot comparison), not necessarily the direct base-to-head snapshot diff. If the requested review uses a different comparison, retain that contract and label it. Dirty work is separate: establish which owned uncommitted changes are included before touching it. New cleanup edits are not part of the recorded head until committed.

## User-scoped cleanup

For named paths, a patch or a line range, record those limits **and** the baseline/target: commits, index, or working-tree content. If no Git history exists, use supplied before/after artifacts and state that commit identity is unavailable. Do not label such work a verified branch diff.

Quote literal paths and use `--` before pathspecs. Confirm untracked files separately; ordinary `git diff` omits them. Exclude unrelated hunks even when they share a file. At closeout, resolve the final HEAD and account for remaining staged/unstaged changes so review evidence describes the actual target.
