# Reviews, Decisions And Agent Environments

Use this reference when an EmDash change moves through an automated review bot,
a decision ledger, or a cloud agent session. Repository instructions win where
they differ.

## Review-bot gates

These apply to review bots that keep one durable review comment per pull
request, such as ClawSweeper.

- A review clears one exact head commit. A green relay or delivery check, a
  pickup comment and a "review started" placeholder only prove the request
  arrived. Wait for the final review on the live head (ClawSweeper marks it
  `<!-- clawsweeper-review item=N -->`); a review naming an older commit is not
  clearance.
- When the repository's review dispatch workflow is already on the default
  branch, do not comment a review command to start the first review; it starts
  by itself. Do not edit the pull request body while a review is queued or
  running: that cancels and restarts it.
- A stacked pull request whose base is not the default branch may be skipped on
  purpose. Merge the parent with a merge commit so the child can retarget.
- Do not send two open pull requests that still change the same user-facing
  outcome against the default branch for review together; pick an order.
- When the review rates the change well, no mechanical finding remains, and
  only "accept this contract / proof limits" items are left, stop patching and
  give the owner a yes-or-no decision.
- Use obviously fake fixtures: no credential-shaped strings or `user:pass@`
  URLs. Review triggers posted by bots may be ignored; a human comment counts.

## Decisions and leftover work

- Source leftover work from the live forge plus the repository's charter,
  feature map and decision ledger, not from agent memory or a stale checkout.
- Change ledger decisions only through the ledger's CLI (for GrillTrack,
  `./scripts/grilltrack`), never by hand-editing the ledger file.

## Agent environments

- Cloud and gateway agents do not inherit the operator's shell. Configure tool
  denylists and API keys per agent; an OAuth chat login is not an API key for
  another service such as embeddings.
- Prove UI in a real browser tab on the loopback host, not inside an embedded
  portal iframe.
- Launch single-repository work against that repository; a multi-repository
  launcher can open pull requests in an unexpected repository.
- Attempt one push before promising a pull request. Forge app installations are
  per organization or account, so access to one does not imply another.

## Cloud sessions

- Use the repository's `.nvmrc` Node. Cursor cloud agents switch with nvm;
  Claude Code cloud sessions get Node from the environment, and a repository
  SessionStart hook (`.claude/hooks/session-start.sh`) can verify it, install
  from the lockfile and report anything missing.
- Install this skill pack pinned to a commit. In Claude Code cloud environments
  the environment setup script installs it into `~/.claude/skills`; Cursor
  projects may install into `.cursor/skills`. List the loaded skills in the pull
  request body.
- In Claude Code cloud sessions, `github:` dependency tarballs download only for
  repositories attached to the session; attach them before installing.
- Node's built-in `fetch` ignores the session proxy unless
  `NODE_USE_ENV_PROXY=1` is set; set it in the environment for scripts that
  fetch over HTTPS.
- A tool the CI image provides may be missing from a cloud image (for example
  the `sqlite3` CLI). Install it in the session hook rather than changing tests.
