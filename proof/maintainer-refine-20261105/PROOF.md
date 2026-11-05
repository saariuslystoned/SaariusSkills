# Maintainer assessment refinement

## Source and scope

- Original base: `7594b58ec25b91ad7749604b62580d534e12c313`; refreshed base after integrating merged PR #215: `19a31ea47001323ff39dea9d6dfd621f4d9c68f0`.
- Original skill source: `49d217a724949cf30648f4a549694c2a520e2813`.
- Authorization-repaired skill source: `3f9f89fe788e12d1cdb34c502cbdb8ba848ca4ff`; its later provenance-only correction was `fbe9eadad23f871fd50aeb8d76eb6b87de871afc`.
- Handoff-publication-repaired skill source: `5778be346b0bb916fb4a1c2f131f64ac764af8df`. The hashes below describe this latest skill source. Later proof changes do not change those skill files; live PR head/review identities remain in the delivery record and PR.
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

## Initial checks — original source `49d217a`

These checks belong to the original source, not the later authorization repair.

- `git diff --check`: passed before source commit.
- `python3 -m unittest discover -s tests -q`: **205 tests passed**, 98.589 seconds. This includes existing portable-skill metadata/local-reference/license/privacy checks and package/discovery checks. No dependency installation and no new prose-matching tests.
- YAML parsed with Ruby's standard `Psych.safe_load`: two required skill frontmatter fields and agent metadata passed.
- Local and pinned-link validation: **9 references passed**, local targets present, external comparison links pinned to full 40-character revisions. Referenced upstream source files were retrieved at those revisions and inspected; this is not a claim that every historical link in the repository was audited.
- Public-core privacy check and manual diff review: no private paths, business priorities, identities, fleet topology or runtime routing added. Existing skill license remains byte-identical to the repository license.
- [Eight synthetic decision walkthroughs](SCENARIOS.md): manually checked scope, ranking, absent goal, external blockers, authorized handoff, no-work result, committed-priority protection and untrusted instructions.

## Result limits and review gates

This is documentation/skill-authoring proof, not runtime proof. The walkthroughs were authored and checked by the writer, not independent harness executions. No trigger accuracy, comparative model performance or production behavior is claimed.

CI and required exact-head reviews must be read from the final PR and existing task record. Local tests and queued reviews do not establish review-clean status or merge authorization. Native review intake is unavailable: no native clean verdict is claimed and no enrollment is authorized. The owner subsequently selected Copilot plus comprehensive P3 and CI for this PR; native absence alone is not a blocker under that per-PR instruction. Merge authority remains separate and with the coordinator, not this worker. No merge, release, deploy, account change or runtime refresh is authorized by this proof.

## Review repair — conditional dependency ordering

Copilot review `5786984498`, inline comment `4482027721`, identified a supported low-severity finding in walkthrough 2: its input described a planned prerequisite, but the assessment called it verified. Disposition: `required_fix`, repaired in `SCENARIOS.md`. The sequence now depends on confirming whether Atlas's repair requires Beacon's item; confirmed-required, not-required and unknown cases were manually checked. Only confirmed-required supports Beacon-first ordering. No skill/runtime behavior changed, and these remain author walkthroughs rather than independent execution proof. Fresh current-head review and CI evidence is retained in the delivery task record.

## Review repair — authorization coverage and progress record

Copilot review `5787326237` confirmed the dependency fix resolved and raised two supported low findings: inline `4482290777` identified stale publication/initial-request next steps in `STATE.md`; inline `4482290861` identified incomplete authorization definitions. Both dispositions: `required_fix`, repaired. State now separates completed publication/repairs from live review evidence kept in the delivery record. Authorization covers an applicable assignment, explicit approval or standing repository policy; routine fixes without such authority are `needs_owner`. Separate execution handoff and no-repeat-approval rules remain intact. Scenario 1 now explicitly lacks authorization; scenario 5 manually checks assignment, approval, standing-policy and missing-authorization variants. These remain writer checks, not independent harness runs.

## Post-repair validation and provenance correction

For repaired skill source `3f9f89fe788e12d1cdb34c502cbdb8ba848ca4ff`, the existing suite passed **208 tests in 97.295 seconds**, and `git diff --check` and same-diff proof-media placement passed. The expanded authorization variants in walkthrough 5 check this repaired source, not the original `49d217a`; walkthrough 2's conditional ordering was introduced in `3a54f4ff7ba6d36aaf9d5ebd6cd49633dfdc882f`. No independent harness behavior is claimed.

Copilot review `5787504372`, inline comments `4482431103` and `4482431192`, identified ambiguous original-versus-repaired provenance and stale PR-description source claims. Both dispositions: `required_fix`. This proof and the scenario header now distinguish the revisions and their checks. The PR description is maintained separately with current source/review identities; original proof-only publication is not described as the final repaired head. Current-head CI/review clearance still requires terminal evidence in the delivery record and PR.

## Review repair — handoff destination authority

Copilot review `5787648171` raised a publication-authorization concern in its summary while linking the outdated provenance thread `4482431103`; it did not publish a new inline comment for that concern. The original provenance repair remains present, and scenario-provenance thread `4482431192` was confirmed resolved. Disposition of the summary concern: `required_fix`, made explicit in source `5778be346b0bb916fb4a1c2f131f64ac764af8df`. A durable task/PR handoff now requires authorization for its destination and audience; otherwise return the assessment in the authorized conversation and describe, but do not post, the handoff. Sensitive owner information is not automatically publishable.

Existing portable-skill/packaging checks passed: **37 tests in 0.668 seconds** before that skill commit; diff check passed. Three manual author reasoning variants were checked: authorized audience-appropriate persistence; conversation-only authority with no posting; and an authorized record that still excludes audience-inappropriate sensitive detail. No external publication or independent harness execution was performed for those variants. Final full CI and independent review evidence belong to the live head's delivery record, not this source-only check.

## Latest repaired skill source hashes — `5778be3`

```text
a480be6d9712084a5395a7605815a10378558a1c122cd370fa762d7f8df75eca  skills/smoky-maintainer/SKILL.md
a067b8c54ddb355c2b9dad09eb38d1574f240ab166a4a31abb6fa1b4097a5d0f  skills/smoky-maintainer/agents/openai.yaml
44faf2242ff52786946a6c3dfddbd519dd3d5199d5a0b6a7aca90d71078f02e0  skills/smoky-maintainer/references/portfolio-loop.md
b36556e31825c54dade05cf743392a1e755abc796697c8ce8f9e96ef58c8ba65  skills/smoky-maintainer/references/source-comparisons.md
```
