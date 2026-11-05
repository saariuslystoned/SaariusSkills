# Two-part audit policy

## Evidence boundary

Use only user-selected roots/skills and explicitly scoped supporting source/callers. Record exact source revision or content identity, selected paths and what was actually read. Caller evidence can be a manifest entry, invocation test, named workflow contract or a supplied task example; it need not be usage telemetry. A static caller proves a declared dependency, not recent execution. Mark unread references, absent caller evidence, unknown usage and inferred runtime state separately. Never search personal logs or auth stores as a side effect.

## Part 1: structural facts vs advisories

| Area | Check | Interpretation |
| --- | --- | --- |
| Metadata | Required name/description and native format; directory/name agreement under applicable authoring rules | Broken under those rules, or unverified if parser cannot establish it |
| References | Actual target of each documented local path, relevant scripts/assets and links | Missing required target is a packaging defect; a deliberate placeholder needs source confirmation |
| Duplicate names | Compare full bodies, references, policy differences, canonical ownership and scoped callers | Comparison candidate, never automatic removal |
| Discoverability | Task/action/object nouns, scoped manifest entry/alias and UI prompt where that surface is used | Missing required enrollment can be broken; optional UI absence is advisory |
| Context cost | Description characters, body words, repeated guidance and which references are actually loaded | Advisory pressure, not measured tokens or a harness budget |

### Helper contract and limits

`audit-skills` requires `--root PATH` (immediate child directories only) **or** repeatable `--skill PATH` (only named directories). It does not search parents/siblings or recurse into shelves. Roots and explicit selections must be existing directories, not symlink entries; ancestor aliases are resolved once for selection identity. Implicit symlink entries are reported/skipped. A shelf's non-skill directory can therefore appear as `missing-skill-md`; select individual skills to avoid unrelated shelf children.

Reads are limited to `SKILL.md` and optional `agents/openai.yaml`. It checks existence of simple `references/…` tokens in the body without reading their content or following symlinks. Escaping references and linked input files are unverified; no target is read through them. Full Markdown links, anchors, transitive references, script behavior, manifest enrollment and full YAML validation remain manual/native checks. It cannot establish loaded inventory, callers, usefulness, usage or retirement readiness.

JSON preserves `skill_count`, `skills`, `duplicate_names` and `issue_counts` for existing consumers. Each skill separates `packaging_errors`, `advisories` and `unverified`; `issues` is their compatibility union. `qualitative_assessment: not-performed` is explicit. Unsupported frontmatter (including block scalars/nested YAML, quoted keys, comments and implicit null/bool/numeric/date-like scalars), unreadable inputs and symlinks require confirmation, not a fabricated validity verdict. The flat parser conservatively defers ambiguous unquoted values; quote an intended string or use the repository's native validator. No claim of exhaustive reference coverage follows from a clean helper report.

Defaults of 300 description characters, 80 minimum body words and 900 maximum body words are adjustable **advisory heuristics**. Optional OpenAI UI metadata and its prompt are also advisory unless the selected surface requires them. No automatic token conversion or universal context percentage applies. Exit 0 means a report was produced, even with findings; invalid selection/arguments or shelf enumeration failure returns 2. Do not use exit 0 as a packaging gate without examining the report and applicable native validation.

## Part 2: qualitative evidence rubric

| Question | Evidence to compare | Useful recommendation |
| --- | --- | --- |
| Is the trigger clear and bounded? | Description vs body purpose and a concrete requested task/caller | Update vague action/object nouns or overbroad claims; preserve real trigger vocabulary |
| Does this own a distinct role? | Same-scope skill contracts, policy differences and caller routes | Keep complementary roles; consolidate only demonstrably redundant responsibility into a named canonical owner |
| Does the workflow still work? | Named command/flag/API vs current source/help, test or owner contract | Update stale assumptions; distinguish unverified runtime availability from proven obsolescence |
| Does each instruction help? | Requirement vs successful task path and essential safety/approval rules | Remove redundancy in a proposed update, move specialized detail to references, or retain justified safeguards |
| Does it solve the caller's actual problem? | Supplied example/contract/test vs outputs and prerequisites | Keep demonstrated fit; identify a specific gap rather than infer usefulness from length/popularity |

Use high confidence for direct source plus representative caller corroboration; medium for clear source facts with incomplete caller coverage; low for an inference or missing observations. Do not compute confidence from arbitrary numerical scores. A recommendation's confidence is not a usage estimate. If no caller evidence is supplied, report source-level concerns provisionally and state what would qualify the judgment.

## Recommendation and retirement contract

Return a compact report:

- **Coverage:** selected paths, source identity, files/callers read, commands/checks, skipped/unverified areas and privacy boundary.
- **Part 1:** packaging defects, advisories and duplicate/discoverability candidates separately, with source anchors and validator limits.
- **Part 2:** role/trigger/workflow/instruction findings, each with source and caller evidence; distinguish fact, inference and unknown.
- **Recommendations:** `skill | keep/update/consolidate/retire | reason | source + caller evidence | confidence | next action / owner gate`.

`Keep` can coexist with packaging fixes. `Update` must identify the concrete change. `Consolidate` must name the retained canonical source/owner, semantic differences to preserve and caller migration, not just a duplicate count.

A qualified **retire recommendation** must identify:

1. Canonical source and accountable owner (including any retained copy).
2. Known callers, discovery aliases/dependencies, what was searched within scope and gaps; a plan to migrate or deliberately end each dependency.
3. Replacement and capability/policy parity, or explicit **no replacement** and the owner's decision to end that capability.
4. Retention needs: references, provenance/license, historical proof, rollback and repository archival/deletion policy.
5. The outstanding owner decision and a separately authorized implementation path.

If these are missing, state **retirement not qualified**, list missing evidence and prefer a provisional keep/update. No usage record found is not evidence of disuse. A recommendation is not deletion, caller migration, installation or distribution authority.
