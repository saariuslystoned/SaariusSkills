# Goal Packet: Four-harness live Puppet dogfood

Status: active Codex goal, 2026-07-25

This goal deliberately reopens SaariusSkills PR #5 after the standalone
tmux/core closeout at
`23c1c3d2f151324b20e33122d31e2d71dc75b4b8`. It replaces
`codex-goal-regular-qualification.md` as the active execution packet while
preserving that document as the broader qualification contract.

The purpose is evidence, not another speculative framework pass: make Codex
CLI, Claude Code, Cursor Agent, and Grok Build perform real bounded work through
Puppet, learn from their actual behavior, and land only the repairs and curated
proof that those runs justify.

## Objective

Run a real subscription-backed Puppet campaign for Codex CLI, Claude Code,
Cursor Agent, and Grok Build using each harness's current default model and
ordinary regular session.

For each harness, complete:

1. one mutating implementation session entered directly from an isolated
   SaariusSkills worktree; and
2. one read-only cross-review session entered from the cockpit with the exact
   target repository supplied explicitly.

The live launch authority remains with the root controller. A delegated worker
may inspect code, run tests, or review a bounded packet, but it may not launch,
authenticate, adopt, steer, halt, or claim ownership of a live harness
session.

## What counts as real use

An implementation session counts only when all of these are proved:

- the exact current executable, version, adapter/protocol, launch mapping,
  default-model observation, host, and isolated profile/config route are bound;
- the actual subscription-backed model starts inside a newly created
  Puppet-owned tmux server/session and native TUI;
- the target receives one non-trivial Puppet-related source task outside argv;
- at least one later ordinary, sequenced steering message is consumed by the
  same exact session;
- the target produces a source handoff and candidate commit in its own
  worktree;
- the controller independently reruns the claimed tests and evaluates the
  checkpoint against the task contract;
- a human can attach to and detach from the exact native TUI through Puppet's
  read-only viewer path without affecting the target; and
- exact halt stops only the leased Puppet target and preserves proof.

A cross-review counts only when the real harness inspects another harness's
exact candidate commit without mutation and returns a bounded finding set or
clean verdict that the controller independently adjudicates.

Doctor-only, parser-only, mocked, unauthenticated, launcher-only, static-census,
or target-self-reported evidence does not count as live use.

## Review ring

| Harness | Implementation entry | Read-only cross-review |
| --- | --- | --- |
| Codex CLI | direct repository | reviews Grok |
| Claude Code | direct repository | reviews Codex |
| Cursor Agent | direct repository | reviews Claude |
| Grok Build | direct repository | reviews Cursor |

Each implementation slice must own disjoint source files or wait behind the
current mutation owner. Cross-review sessions are no-edit lanes.

## Controller and source boundaries

- Start from the exact remote PR #5 head above in a fresh isolated campaign
  worktree.
- Keep the supervising Puppet release immutable during every live session.
  The target receives a different candidate worktree and never supervises
  itself.
- One target, one lease, one private tmux socket/session, one worktree, one
  profile namespace, and one proof root.
- The root controller launches every live harness itself. Do not delegate live
  launch through Codex subagents.
- Select the exact execution host from current subscription, launcher, and
  isolation evidence. Record the host; do not assume CP-1 or the operator Mac
  is suitable for every harness.
- Safe subscription reuse requires a qualified auth-only selector or broker.
  Never inherit an ordinary harness home merely because it is logged in.
- If a lane-owned profile needs first enrollment, preserve one exact
  human-present handoff and continue the other lanes. Puppet never performs the
  login or reads, copies, hashes, or exposes credential material.
- Use the safest already-implemented additive instruction path needed for the
  bounded run. Do not require a three-plane comparison before dogfood. Record
  the selected plane and treat any behavior-driven repair as new evidence.

## Work sequence

### Phase 1: admit the campaign

- Create the campaign worktree, private campaign journal, and four lane route
  stubs.
- Re-census the installed executable/version/help and zero-agent population on
  candidate hosts.
- Classify subscription/profile readiness without inspecting auth stores.
- Select one exact host and launcher surface per harness.

### Phase 2: unblock real launch

- Run only source-only plans, onboarding/status classifiers, and deterministic
  tests until a lane has exact launch authority.
- Repair the smallest concrete controller or adapter gap that blocks real use.
- Commit every accepted repair with a regression test and push bounded
  checkpoints to PR #5.
- A human enrollment handoff is a waiting lane, not permission to weaken
  isolation or count a doctor receipt as success.

### Phase 3: implementation dogfood

- Launch each harness through Puppet in current-default regular mode.
- Give it one disjoint, non-trivial Puppet source slice with executable
  acceptance criteria and a hard stop before push or merge.
- Require one useful mid-run steering turn and one terminal structured
  checkpoint.
- Keep the human read-only native TUI view available throughout the useful
  portion of the run.
- Independently test, adjudicate, and either accept, repair, or reject the
  candidate before integration.

### Phase 4: cross-review

- Run the review ring above from cockpit entry.
- Bind each review to the exact candidate SHA and real diff.
- Classify findings as `required_fix`, `reject_false_positive`, `defer`, or
  `human_gate`.
- Allow at most two review-triggered repair cycles per source slice.

### Phase 5: reconcile PR #5

- Commit curated transcript-free receipts and the four-harness matrix.
- Re-run every affected deterministic test after each accepted integration.
- Push periodic bounded checkpoints to the existing PR #5 head branch.
- At the final integrated head, run the complete suite, packaging tests, skill
  validation, exact live lifecycle checks, and independent exact-head review.
- Leave PR #5 open and unmerged.

## Required proof

Maintain one private campaign root and one proof root per lane with current:

```text
STATE.md
events.jsonl
heartbeat
PROOF.md
```

Committed proof may contain only curated, bounded facts:

- exact source and controller SHAs;
- harness executable/version and non-secret adapter/model observations;
- profile/instruction fingerprints and classification;
- tmux socket/session/pane and process birth hashes or sanitized identities;
- prompt and checkpoint hashes, never bodies;
- candidate commit, changed-file list, test commands/results, and controller
  verdict;
- read-only viewer admission and detach result;
- exact halt result and protected-population comparison;
- cross-review verdict and adjudication; and
- limitations or exact blockers.

Do not commit or persist prompts, responses, pane text, transcripts, arbitrary
logs, account identifiers, machine-global configuration contents, credentials,
cookies, session stores, auth logs, or secrets.

## Acceptance

The goal is complete only when all four harnesses have:

- one accepted real implementation session;
- one accepted real cross-review session;
- at least one consumed follow-up steering turn;
- controller-validated task evidence;
- native read-only TUI attach/detach proof;
- exact halt proof;
- curated committed proof at one final PR #5 head; and
- no unresolved `required_fix` at that head.

The final PR head must be clean and pushed, the full controlled test suite and
skill/package validation must pass, and an independent exact-head review must
be adjudicated.

An authenticated or live result for one harness never substitutes for another.
Continue independent lanes while one waits. If an exact irreducible blocker
repeats under the Codex goal blocked-status rules, preserve it honestly; never
weaken a hard gate or label non-live evidence as dogfood completion.

## Exclusions

Do not enable `/goal`, `/loop`, `/teamwork-preview`, automatic routing, or Pi.
Do not touch a non-Puppet session, replace a vendor system prompt, edit live
operator-global harness configuration, inspect/copy auth stores, merge, deploy,
release, publish, send externally, alter accounts/security, weaken security,
spend, or perform destructive cleanup.

Herdr-Puppet AGY evidence remains valuable convergence input for issue #11, but
this campaign neither reruns nor claims AGY tmux qualification.
