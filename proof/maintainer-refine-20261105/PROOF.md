# Maintainer assessment refinement

## Source and scope

- Base: `7594b58ec25b91ad7749604b62580d534e12c313`.
- Skill source commit: `49d217a724949cf30648f4a549694c2a520e2813`.
- Branch: `ridge/maintainer-refine-20261105`.
- Observation: 2026-11-05, Python 3.14.6 on macOS.
- Assignment: refine only `skills/smoky-maintainer/` and dedicated proof. No other skill, manifest, installer, runtime or global configuration change.

Accepted authoring decisions: assessment and recommendations are separate from execution; rank against the user's goal with evidence and explained tradeoffs; support both one repository and a selected portfolio without scope expansion. Preserve existing commitments, identify authority and evidence gaps, and allow no new work as a valid result. The task's private decision record retains original approval pointers; no private operational context is exported here.

## Changes and fidelity

- Activation metadata now includes single-repository maintenance assessment and triage.
- The core explicitly bounds discovery, uses established priorities when no new goal is supplied, and distinguishes facts, assumptions and freshness.
- Ranking considers goal fit, impact, supported urgency, dependencies and effort without invented scores or age-based urgency.
- `already_authorized` means eligible for a separate execution handoff, not automatic implementation. Owner decisions, missing evidence and deferral remain distinct.
- No worker launch, silent maintenance, recurring monitor, new ledger or particular harness/service is required by this skill.
- Small questions can receive short answers rather than a mandatory form.
- Public source comparisons are pinned and credited in [source-comparisons.md](../../skills/smoky-maintainer/references/source-comparisons.md). No upstream text, code or templates were copied. Personal portfolio, worker, host and release policies were not imported.
- The applicable private binding required no change: it already supplies private priorities/discovery and routes execution under owning contracts. No private-binding PR or duplicated public business policy was manufactured.

## Checks

- `git diff --check`: passed before source commit.
- `python3 -m unittest discover -s tests -q`: **205 tests passed**, 98.589 seconds. This includes existing portable-skill metadata/local-reference/license/privacy checks and package/discovery checks. No dependency installation and no new prose-matching tests.
- YAML parsed with Ruby's standard `Psych.safe_load`: two required skill frontmatter fields and agent metadata passed.
- Local and pinned-link validation: **9 references passed**, local targets present, external comparison links pinned to full 40-character revisions. Referenced upstream source files were retrieved at those revisions and inspected; this is not a claim that every historical link in the repository was audited.
- Public-core privacy check and manual diff review: no private paths, business priorities, identities, fleet topology or runtime routing added. Existing skill license remains byte-identical to the repository license.
- [Eight synthetic decision walkthroughs](SCENARIOS.md): manually checked scope, ranking, absent goal, external blockers, authorized handoff, no-work result, committed-priority protection and untrusted instructions.

## Result limits and review gates

This is documentation/skill-authoring proof, not runtime proof. The walkthroughs were authored and checked by the writer, not independent harness executions. No trigger accuracy, comparative model performance or production behavior is claimed.

CI and required exact-head reviews must be read from the final PR and existing task record. Local tests and queued reviews do not establish review-clean status or merge authorization. The native review route needs a target-supported trigger and enrollment; absent wiring is an external integration blocker, not a clean verdict and not permission to install it. No merge, release, deploy, account change or runtime refresh is authorized by this proof.

## Source hashes

```text
a480be6d9712084a5395a7605815a10378558a1c122cd370fa762d7f8df75eca  skills/smoky-maintainer/SKILL.md
a067b8c54ddb355c2b9dad09eb38d1574f240ab166a4a31abb6fa1b4097a5d0f  skills/smoky-maintainer/agents/openai.yaml
5ed928f8c9d791992a1989672afeae58a399d158e7b4dc4ea015af9cbf411a09  skills/smoky-maintainer/references/portfolio-loop.md
b36556e31825c54dade05cf743392a1e755abc796697c8ce8f9e96ef58c8ba65  skills/smoky-maintainer/references/source-comparisons.md
```
