# Behavior-validator refinement — authoring proof

## Acknowledged assignment and provenance

The task owner's approved 2026-11-05 brief retains this skill and requires a concise portable black-box workflow usable directly in supported harnesses or by an assigned worker. This is a curated interpretation of that decision, not a transcript or a claim of live product validation.

One lead/writer owns `skills/smoky-behavior-validator/` and genuinely affected authoring checks/docs/proof on branch `ridge/behavior-validator-refine-20261105`. Other skills, runtime/configuration, installation, credentials and accounts are excluded. The coordinator retains acceptance and closeout; no merge or rollout is authorized.

Acceptance: start with assigned observable criteria; permit target-owned published specs, fixtures and external state, not implementation/diffs/internal tests/developer explanations; add proportionate edge cases without inventing rules; cover web, CLI, API, registered test devices and artifacts; preserve permissions, privacy, reproducibility and pass/fail/blocked/out-of-scope reporting. Source-aware repair/review stays separate. Synthetic guidance checks must not be represented as live behavior proof.

## Exact source and proof root

- Repository: `saariuslystoned/SaariusSkills`.
- Assigned base: `7594b58ec25b91ad7749604b62580d534e12c313`.
- Branch: `ridge/behavior-validator-refine-20261105`; supplied isolated workspace verified clean before authoring.
- Proof root: `proof/behavior-validator-refine-20261105/` (this record).
- Existing private binding and current coordinator/worktree portable-core patterns inspected read-only. Binding disposition will be recorded without publishing private topology or revisions.

## Implementation and source fidelity

- Kept metadata, profile/binding discovery, black-box separation, focused post-repair probes and optional report fields. Clarified direct-harness/assigned-worker use without runtime dependencies.
- Added acceptance/spec provenance, explicit expectation gaps, source-contamination handling, scoped web/CLI/API/registered-device/artifact checks and proportionate inline reporting. Missing observations cannot justify a pass or an invented product defect.
- Compared only the directly relevant upstream behavior-validator and device-lab guidance; [pinned sources and credit](../../skills/smoky-behavior-validator/references/sources.md) distinguish the symlink from its resolved canonical source. No upstream executable, shell recipe or unrelated process imported; existing licenses preserved.
- Existing private binding reviewed: **no change needed**. It already supplies authorized test targets/identities, action/privacy gates, target-owned proof and separate code-aware review. No private binding source or operating topology is published here; no companion repository PR is needed.
- No other skills, manifests, runtime, profiles or installed copies changed. No new exact-prose tests added.

## Validation

- `python3 -m unittest tests.test_packaging tests.test_portable_skills -q`: **PASS, 36 tests**; [output](package-checks.txt).
- `python3 -m unittest discover -s tests -q`: **PASS, 205 tests**, 100.773 seconds; [output](all-tests.txt). Negative-fixture EmDash drift/refusal diagnostics are expected test output, not working-tree failures.
- Skill Creator `quick_validate.py skills/smoky-behavior-validator`: **PASS** using the existing system Python/PyYAML, no installation; [output](skill-validation.txt).
- One-off structural check: local backtick references and relative Markdown links resolve; report JSON parses; skill files contain no absolute host paths or operator-binding fields. `git diff --check`: **PASS**.
- Manual source-fidelity/privacy review: contract and report references agree with the core, preserve source blindness and permissions, and distinguish observed failures from missing expectations/access; pinned public upstream URLs were read at their exact commits. Changed public source/proof contains no private topology, account/device identifiers, credentials, auth URLs or transcript excerpts. Public Git source identity and synthetic examples only.
- [Twelve synthetic guidance walkthroughs](sanity-cases.md): narrow pass, real-state failure despite success text, persistence, API semantics, missing expectations, unavailable exact device, artifact content, source contamination, mock/live separation, action exclusions, mixed verdicts and repair handoff. These are manual semantic sanity checks, **not live product behavior proof or an independent harness evaluation**.

## Initial publication state and remaining gates (historical)

Scope was acknowledged before implementation. Source authoring and local checks are complete. Next: commit/non-force push, open the scoped PR, and request exact-head CI, native ClawSweeper and comprehensive review. External evidence must bind the published head; submission/queue receipts are not clean review. Worker output is not coordinator acceptance. No merge, installation, deployment or product validation is claimed.

## Review repair continuation — 2026-11-05

Read the actual published [Copilot review 5786977430](https://github.com/saariuslystoned/SaariusSkills/pull/216#pullrequestreview-5786977430) and all three inline findings on the initial head. All three are `required_fix` and repaired:

- [4482022103](https://github.com/saariuslystoned/SaariusSkills/pull/216#discussion_r4482022103): require shared verdict rules for every report, including inline; only JSON formatting remains optional.
- [4482022186](https://github.com/saariuslystoned/SaariusSkills/pull/216#discussion_r4482022186): distinguish display/status-only acceptance from additional promised work, content or persistence; no new product requirement is inferred.
- [4482022255](https://github.com/saariuslystoned/SaariusSkills/pull/216#discussion_r4482022255): explicitly mark undecidable clauses `blocked` for missing/inconclusive evidence; reserve `fail` for observed violations and name the next evidence action.

Integrated current main `19a31ea47001323ff39dea9d6dfd621f4d9c68f0` non-destructively before fresh review. Changes already merged by PR #215 are inherited, not authored or revised in this task. No unrelated skill edits, private binding change or companion PR.

Checks after integration and repair: packaging/portable tests **37 passed**; full suite **208 passed** (108.106 seconds); existing Skill Creator validator **valid**. Seven additional manual synthetic walkthroughs cover inline mixed/all-excluded results, narrow web/API signals and missing/inconclusive evidence. These supplement the initial twelve, not live behavior proof. No prose-matching tests, new upstream material or tool installation. Reference/JSON structure, privacy/source-fidelity and diff checks are repeated before publication; detailed outputs retained in the existing machine-run proof root, not copied as private operating context here.

Current owner instruction conditionally authorizes merge after clean reviews, with Copilot selected for this PR and native absence explicitly disclosed; the worker must still return readiness to the coordinator, **not self-merge**. Historical native absence is not a claimed clean review. Old exact-head CI/comprehensive evidence remains historical; fresh current-head CI, Copilot and comprehensive P3 evidence are required. No acceptance, installation, deployment or rollout is claimed.
