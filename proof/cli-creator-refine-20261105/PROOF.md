# CLI creator refinement proof

## Scope and source

Base: `19a31ea47001323ff39dea9d6dfd621f4d9c68f0` in SaariusSkills.
This packet accompanies only `skills/smoky-cli-creator/` authoring changes.
The accepted scope is selective discovery, compact specification, authorized
implementation and real-use verification—not a CLI product or generator.
Design-only requests remain design-only; routine authorized choices do not
acquire a new approval gate. Existing compatibility and action gates remain.

The three adapted guidance sources and immutable revisions are recorded in
[the skill notices](../../skills/smoky-cli-creator/THIRD_PARTY_NOTICES.md).
Source comparison retained discovery-before-creation, useful CLI ergonomics,
mechanical-versus-reasoned assessment, conditional cache provenance, real
workflow/generated-output checks and selective golden coverage. It excluded
mandatory frameworks, SQLite, MCP, scorecards, pipeline/ledger machinery,
private credential conventions and ship/install permissions. This is adapted
guidance, not wholesale upstream text or code. MIT notices are distributable
with the skill. No shared packaging or other skill changed.

## Mechanical validation

- `python3 -m unittest discover -s tests -q`: **208 tests passed** in 99.305 s,
  including existing packaging, metadata, reference and public-boundary tests.
- `git diff --check`: passed before publication.
- Frontmatter parsed with Ruby standard-library Psych; exactly the existing
  `name` and a string `description`, with the canonical skill name retained.
  The author's optional Python quick validator was unavailable because PyYAML
  was absent; no dependencies were installed. Existing metadata tests passed.
- Local links/reference paths passed. Pinned upstream files and clig.dev
  returned HTTP 200 via raw-source GETs; GitHub web HEAD was refused (403),
  so source paths were checked against those retrieved revisions instead.
  Public diff inspected for private paths, runtime/profile facts and
  credential material.
- Existing UI metadata and invocation policy remain appropriate and unchanged.

These checks prove document/package properties, not future model compliance.
No executable product, cache or generator changed. No prose-matching tests,
incidental snapshots, new CLI fixtures or invented runtime claims were added.

## Reasoned scenario walkthroughs

These are synthetic design exercises by the author, **not independent harness
forward-tests or black-box runtime proof**. They check whether applying the
instructions yields a proportionate interface decision.

| Request / constraints | Resulting interface decision and verification plan |
| --- | --- |
| Small existing CLI: add `report list --limit N`; existing parser, exit 64 for usage, text output, no machine consumer | Delta spec: positive integer N, repository default when omitted, reject invalid values with exit 64. Keep all old invocations/output and facade. Add focused parser/entry-point tests for default, N=1 and invalid N; no new tree/framework/JSON/cache/ledger. |
| Spec only: design `notes find QUERY` for humans and a script | Supply synopsis, query/empty-result semantics, human display and consumer-required structured shape, stderr and exits plus examples. Walk through success, no matches and missing query. Stop with runtime behavior unproved; do not edit source or implement a tool. |
| New CLI request for a service with a mature official CLI | First compare the requested workflow with the official command and existing repo facade. If it already serves the workflow, recommend its invocation, not generation. If only a local transformation is missing, specify that narrow gap; do not silently replace the requested product or create a duplicate API client. |
| Authorized implementation: extend existing `bundle inspect FILE` with `--summary` | Write a short delta spec, then implement in the existing parser/helper and update help/tests within source authority. Exercise the delivered entry point on a synthetic bundle and bad input; compare old invocation behavior. Do not pause for a second design approval or install/publish the result. |
| Unattended mutation: `records apply` receives piped input but lacks required confirmation | No prompt/selector/pager; fail promptly with nonzero exit and actionable stderr, without mutation. Closed/piped stdin and a bounded timeout test detect hangs; test defined machine error output if offered. `--force` may skip a local prompt only after actual authority is established, never authorize the action. |
| Cache-backed `inventory list` with an existing source selector | Distinguish a local read from a live check/refresh using the existing interface. Report known observation time and scope, or unknown/stale/partial; a failed refresh must not look fresh. Test selection and fallback reporting. A file-only filter with no cache gets none of these features. |
| Authorized template change producing a CLI | Generate the affected representative variant, build the result and invoke its normal task and invalid-input path against safe fixtures. Template compilation or a matching snapshot alone is insufficient. No generator/runtime dependency is introduced by this skill authoring task. |
| Proposed golden for a stable offline structured command; unrelated timestamp-heavy/private diagnostics | Consider the small stable public schema/artifact subset; use focused assertions for field logic. Exclude incidental/private diagnostics. Inspect any intentional contract change rather than blindly accepting fixture updates. A documentation edit alone needs no golden test. |
| A redesign would rename an established flag or change JSON/exit semantics beyond the assignment | Preserve the old contract and name the unresolved breaking choice with affected callers and a migration option. Ask only if the material compatibility/scope decision cannot be resolved from authority; force cannot expand scope. Record the decision in the existing task/PR, not a new ledger. |

Judgment: the revised core supports both bounded standalone design and
source-authorized delivery without mandatory helper skills or private runtime
assumptions. The reference adds conditional depth without making every option
a checklist requirement. Documentation tests and these walkthroughs are not
claims that a new command was built, deployed, independently reviewed or used
against a real service.

## Review and gates

Required publication gates are exact-head CI, signed native ClawSweeper and
comprehensive Spark-2 review. Their request IDs/results and any dispositions
belong in the PR/task review record; submission is not a clean verdict.
The assigned lead retains PR/review/repair ownership until clean/green or a
concrete blocker. Merge and live skill installation remain outside this work.
