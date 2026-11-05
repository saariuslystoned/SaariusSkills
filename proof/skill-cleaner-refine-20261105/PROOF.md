# Skill cleaner refinement

## Assignment and source

- Owner: sole Pi lead/writer; Blaze coordinates and accepts separately.
- Task: `skill-cleaner-refine-20261105`; branch `ridge/skill-cleaner-refine-20261105`.
- Repository: `saariuslystoned/SaariusSkills`; immutable starting base `19a31ea47001323ff39dea9d6dfd621f4d9c68f0`.
- Acknowledged scope: `skills/smoky-skill-cleaner/`, dedicated tests and this proof only. No shared manifests/docs, other skills, private binding, installed copies or runtime changes.
- Product direction supplied by coordinator: Ryan agreed the two-part packaging/usefulness audit in Skill Refinery (recommendation `1567935499463692432`, confirmation following `1567936430511095959`). These are assignment evidence, not independently inspected messages.
- Read local `CONTRIBUTING.md`, `docs/portable-skills.md`, cleaner source/helper/UI/license, `.github/workflows/tests.yml`, `tests/test_portable_skills.py`, and current portable technical-documentation/worktree/coordinator metadata as pattern/role context, not a re-audit.
- Actual source consumers: `tests/test_portable_skills.py` invokes `--root … --json` and checks count/duplicates/missing refs/read-only hashes; `docs/portable-skills.md` advertises packaging; plugin manifests discover the existing skill (no new/renamed package). No usage telemetry supplied: usage is **unknown**.

## Decisions

1. Two separately evidenced sections: deterministic packaging vs human usefulness assessment. Findings yield keep/update/consolidate/retire recommendations, never automatic source edits/deletion/install.
2. Require explicit helper selection (`--root` or named `--skill`); preserve existing root JSON consumer fields. Fail on invalid selection, do not follow implicit symlink entries or referenced paths outside selection. Keep rich YAML assessment explicitly unverified rather than fabricate parser certainty.
3. Advisory size/UI flags are not packaging errors or usefulness scores. No universal token budget or usage inference.
4. Use source/caller evidence and confidence per recommendation; retirement needs canonical owner, caller migration, replacement (or explicit none), retention and owner decision. Missing evidence is a stop/unknown, not a retirement signal.
5. Preserve portable optional-binding discovery; none is configured or created here. No Firebed dependency, log collector, registry or new platform.
6. Reviewed design references at immutable pins: Peter Steinberger `steipete/agent-scripts@d210c0a77c8f9ae5e1d939b13238a75e87cdb69a`, `skills/skill-cleaner/SKILL.md`; Vincent Koc `vincentkoc/dotskills@c9ca51e3a4e93fe10266d78e430c6575a5b19d30`, `skills/technical-skill-finder/SKILL.md` and `references/scorecard.md`. Adapt conceptual guidance (trigger nouns, compare canonical copies, evidence/overlap/confidence); exclude personal paths/tools, log mining, loaded-inventory assumptions, Codex budget formulas and numeric score thresholds. Package-local credit/licenses will travel with the skill; shared notices are out of scope.

## Validation and lifecycle

- Full hermetic suite: **218 tests pass** (`full-tests.txt`, 105.208s). Deliberate negative-control sync diagnostics in the output are expected; unittest result is OK.
- Affected dedicated + portable/privacy + packaging suites: pass (`affected-tests.txt`). Dedicated fixtures exercise explicit selection, invalid selection, threshold categories, rich YAML uncertainty, duplicate identity, missing refs, multi-root named selection, read-only hashes, symlink/path-escape refusal and a guarded content-read allowlist.
- `synthetic-cases.json` + `QUALITATIVE.md`: eight realistic synthetic sources with explicit caller contracts; structural expectations are automated, usefulness assessments are author-applied and explicitly not independent/telemetry-backed.
- `self-structural.json`: explicit cleaner-only selection, no structural findings, qualitative assessment not performed. Counts remain advisory.
- `source-checks.json`: flat metadata, local Markdown links, exact upstream MIT notices, repository license and private-binding/machine-path scan pass. Upstream source hashes retained; no runtime/budget guidance copied.
- `git diff --check`: pass. Scope remains cleaner package + dedicated test/proof; no shared files, manifests or other skill folders changed.
- Minor implementation detail: explicit selected directory ancestors are resolved for identity (portable temporary-directory aliases); selections themselves and implicit entries cannot be symlinks, and linked files/references are not read.
- Source confirmation caught a natural-language `references/scripts` token as a helper candidate. It was clarified to “references and scripts”; this illustrates the documented bounded matcher, not exhaustive Markdown validation.
- Shared `docs/portable-skills.md` still describes the cleaner's older packaging-only scope. This is optional coordinator-owned catalog/documentation follow-up, not a packaging or runtime dependency; no shared edit was made.

No private logs read, installed skills refreshed, merge or deployment performed.

## Stop / next action

Implementation and local verification complete. Next: commit/push/PR, then exact-head CI + native ClawSweeper + comprehensive Spark-2 through canonical openclaw-autoreview. Pi lead owns this review generation until explicit handoff; record request IDs and gate state here. Pending receipts are not clean verdicts. No coordinator acceptance is claimed.
