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

## Initial validation (implementation commit `6e69102`)

Historical results before the review repair and main reconciliation below; these files are not current-head review clearance.

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

## Review repair / main reconciliation (2026-11-05)

- PR: https://github.com/saariuslystoned/SaariusSkills/pull/219. Same assigned Pi writer and worktree; Blaze remains coordinator/closer.
- Current owner instruction continues Copilot + comprehensive P3 + CI as the selected route. Native ClawSweeper is absent and **not** claimed clean; no sender/enrollment/account changes. Jev baseline remains ineligible without native publication (judge not-run, no labels).
- Fetched and merged real main `e93e6e6588a2df1fe21af61ca2b7926e3406505b` without conflicts or rewriting history. Other workers' behavior-validator/session-viewer changes are inherited unchanged, not authored by this slice. Original starting base remains recorded above as history.
- Comprehensive generation 1 `req-20261105T163527Z-215549618815` reviewed `19a31ea47001323ff39dea9d6dfd621f4d9c68f0` / `6e69102ba4bf18a8d2478595474ef2385ab5b201`, qualified comprehensive/P3, one P3 finding: existing directory references were falsely reported missing. **required_fix**, reproduced with a selected synthetic `references/examples/` directory. Accept file or directory existence after the unchanged scope/symlink guard; do not enumerate or read reference contents.
- First repair `bae6f17`: added two behavioral regression cases (existing vs absent directories with guarded content reads/read-only hashes; internal/external symlink directories remain unverified). Dedicated **12 pass**, full **218 pass**, 104.913s. These intermediate results are historical, not final repair evidence.
- Copilot review `5788709031` at original head `6e69102` raised three issues: directory references (same defect as comprehensive, already repaired), fully unsupported rich frontmatter falsely marked missing, and optional UI read failure skipping reference checks. All **required_fix**; no summary-only concern left unclassified. Reproduced both distinct remaining defects with synthetic block-scalar/alias metadata and invalid UTF-8 UI plus a required missing reference. Reproduction fails before the fix, passes afterward. Track opening-delimiter presence independently of parsed values; catch optional UI reads locally and continue structural checks.
- Second repair `cbbdfbd`: dedicated **14 pass**, full **220 pass**, 96.786s; exact-head CI and comprehensive generation 3 passed. Historical after the next repair.
- Copilot review `5788832057` at `cbbdfbd` confirmed the first three issues resolved and raised quoted YAML keys treated as literal names and trailing periods stripped from literal reference targets. Both **required_fix**, reproduced before repair (`turn2-gen2-reproduction.txt`). Conservatively defer non-simple YAML keys rather than implementing a YAML parser; preserve paths following simple code/link delimiters and dot components before the scope guard, trimming sentence periods only on plain prose candidates. New tests cover quoted keys, literal dotted files, dot-dot escape and prose punctuation.
- Main advanced to `6730419d5f4d622c1ed62b25c2eece28ed2266a5` (#218); merged conflict-free, retaining the other owner's source/proof unchanged. This supersedes e93e6e6 as the current review base.
- Third repair validation: dedicated **16 pass**, full hermetic **222 pass**, 106.089s. Tests assert report behavior, not prose. Deliberate sync negative-control diagnostics are expected. Runtime output is retained separately from the initial tracked test files.
- Runtime proof: `~/Developer/_machine-runs/skill-cleaner-refine-20261105/turn2-{dedicated,full}-tests.txt`, `turn2-copilot-reproduction.txt`, `turn2-second-repair-{dedicated,full}.txt`, `turn2-gen2-reproduction.txt`, `turn2-third-repair-{dedicated,full}.txt`; exact-head review generations, summary/inline finding dispositions, CI and final main reconciliation are retained in that same existing task record and PR checkpoint to avoid proof-only head churn.

## Stop / next action

Push the scoped repair non-force and obtain current-head Copilot, exact-base/head comprehensive P3 and successful CI. Inspect actual review summaries as well as inline findings. Record exact IDs and current main at terminal handoff; no duplicate pending generations. Return clean evidence or a concrete blocker to Blaze for head-pinned merge; **never self-merge**, install/roll out or claim task acceptance. Retain scoped review/repair ownership while waiting.
