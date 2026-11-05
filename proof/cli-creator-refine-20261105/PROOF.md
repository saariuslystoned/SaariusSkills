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

The initial route required CI, signed native ClawSweeper and comprehensive
Spark-2 review. Native enrollment was absent; no native verdict is claimed.
The current owner-selected route instead requires actual current-head Copilot,
comprehensive P3 exact-base/head review and CI. No shared enrollment/integration
changes are authorized. Request IDs, actual verdicts and dispositions belong in
the PR/task review record; successful delivery or submission is not clean review.
The assigned lead retains PR/review/repair ownership. Ryan's conditional merge
authorization is retained by the coordinator/closer, not exercised by this worker.
Live skill installation remains outside the assignment.

## First Copilot findings and repair

Owner steering supplied on this continuation cites Skill Refinery message
`1567958128006271179` in channel `1567890272011165777`: get PR #221 review-clean,
with merge preauthorized after the required clean reviews. This is a scoped
paraphrase of supplied provenance, not an independently retrieved quotation.
No duplicate first review was requested.

The owner-triggered [Copilot run 42077291157](https://github.com/saariuslystoned/SaariusSkills/actions/runs/42077291157)
completed successfully, but its actual [review 5789441856](https://github.com/saariuslystoned/SaariusSkills/pull/221#pullrequestreview-5789441856)
recommended changes on `7ce1efab955c3bb05029aea802c8e64f83e98189`:

- [4483964509](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4483964509):
  `required_fix`. The core unconditionally required building generated output
  and ambiguously grouped deterministic tests with golden snapshots. Core and
  reference now choose validation by artifact type (code/CLI, config, report),
  permit focused tests and restrict only golden snapshots to stable contracts.
  Design check: a generated report is checked by its consumer, not compiled;
  generated CLI code is still built and exercised; a focused parser test does
  not acquire a golden-fixture requirement.
- [4483964585](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4483964585):
  `required_fix`. The MIT paragraph's scope also encompassed the condensed
  clig.dev reference. The pinned clig.dev README confirms CC BY-SA 4.0. Notices
  now explicitly limit MIT to cli-printing-press and create-cli SKILL.md,
  distinguish the guide/condensed reference and link the separate license.
  No guide prose or condensed reference is vendored by this change.

The original comprehensive request `req-20261105T164826Z-2171980758` was fetched
and verified clean/P3/exact-tuple, but covers base `19a31ea47001323ff39dea9d6dfd621f4d9c68f0`
and the original head only. It cannot attest the repaired source/current main.
CI run `42068059872` passed both platforms on that old head, not this repair.

Main advanced through the other assigned refinery slices to
`6730419d5f4d622c1ed62b25c2eece28ed2266a5`. No paths overlap this four-file slice.
The supported materializer refused that non-ancestor base on the old branch;
main was therefore integrated without conflicts for current-base review and
integration testing, not to stimulate a duplicate pending review. Upstream
changes are preserved without independent edits to their source/shared files.
Renewed Copilot and comprehensive review are required after publishing repair.

Repair validation: `python3 -m unittest discover -s tests -q` passed **206 tests**
in 106.293 s on the integrated source (the retired session-viewer tests account
for the count change). `git diff --check` passed. Rechecked artifact-specific
verification examples, attribution scope against the pinned source/README,
local references, and the public diff for private/runtime content. These are
document/package checks and author judgments, not product runtime proof.

Jev baseline: `ineligible` because no canonical native ClawSweeper publication
exists; Copilot alone is not eligible input. Judge not-run, no labels or owner
interruption, timing not measured. Native absence is disclosed, not claimed
clean and not a blocker under the explicit owner-selected route.
