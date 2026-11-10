# DinkusKit rails for a sweep

Facts the sweep needs that the repositories do not say in one place. Check
them against the live repository before relying on one; the repositories win.

## ClawSweeper (the review gate on every DinkusKit repository)

- Ready means the `clawsweeper/review` commit status is success on the exact
  head, and the durable review comment carries
  `clawsweeper-review-state:ready` for that SHA. A pushed head needs a new pass.
- It reviews non-draft PRs whose base is `main`. In the product repositories a
  PR body edit starts a pass; a standalone `@clawsweeper review` comment always
  does.
- Fork pushes are refused at intake: start each fork PR's pass with a
  standalone `@clawsweeper review`.
- It can silently never start. Check the pickup comment and nudge once.
- "Base moved during admission": `main` moved after the head was pushed. Merge
  `main` into the PR and push. Every merge to `main` causes this for the other
  open PRs on that repository, so sequence merges.
- A `review_failed` run leaves a same-head comment the owner deletes, then a
  fresh `@clawsweeper review`. Many PRs failing in seconds is a runner outage:
  look at recent merges in the runner repository and stop retrying.
- "Owner decision: Required" only because it cannot open a cross-repository
  record: post one comment quoting the ledger entry verbatim (question, choice,
  rationale, lock time, merging PR and commit) and the test names, ending with
  `@clawsweeper review`. Never ask the owner to type it.
- Blocks the owner has overridden before because no real stores exist: proof
  for populated existing stores, and reviewer-side source access failures.
  These still go to the card's "Override?" group; they are not standing
  permission.

## Forks

- "Update branch" on a fork PR fails unless the contributor allowed edits from
  maintainers. Then the contributor merges `main` in.
- Fork CI can wait as "action_required": rerun the held run.
- A Commerce fork PR needs a changeset.

## GrillTrack

- Every product, API or data-model choice is a ledger entry the owner approves
  before it locks. Use `./scripts/grilltrack` only; never hand-edit the ledger
  or events.
- Merging `main` into a branch conflicts in `.grilltrack/ledger.json` and
  `.grilltrack/events.jsonl` almost every time. Take `main`'s two files, replay
  the branch's own decisions through the CLI with identical bodies (propose,
  lock, implement, verify), then `./scripts/grilltrack validate`.

## The owner's words

- Merge words: "merge N", "merge it", "merge them", "merge all", "go ahead and
  merge", "i auth N", "i authorize", "i pre-auth", "... once clean and green",
  "go", "lets just merge", "yes" to a plain "May I merge N now?". "agreed"
  alone means build, not merge.
- "close N": close with a note. "leave N alone": hands off. "rebase": merge
  `main` in. "defer": park it. "take it from here": own the fix end to end.
- A merge word waits for ClawSweeper ready on the final head unless the owner
  overrides that item.
- Merge with a merge commit and the expected head SHA.

## Boundaries

- Agents never comment on upstream EmDash repositories; prepare the text for
  the owner to post.
- Deploys, releases, Cut beta, secrets, permission grants and live journeys are
  outside a sweep. The shared beta store runs one journey at a time and is
  queued through the project coordinator.
- Every GitHub comment ends with the harness's attribution footer when it has
  one. Never put a model identifier in a repository artifact.
