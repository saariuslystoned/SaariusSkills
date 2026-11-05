# CLI creator refinement proof

## Scope and source

Original authoring base (historical):
`19a31ea47001323ff39dea9d6dfd621f4d9c68f0` in SaariusSkills.
Current source and review evidence are identified in the PR description and
subsequent review records; initial checks below are not current-head clearance.
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

## Initial mechanical validation (historical)

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
| Unattended mutation: `records apply` receives piped input but lacks required confirmation | No prompt/selector/pager; fail promptly with nonzero exit and actionable stderr, without mutation. Test terminal-free defaults without a no-input flag and supported explicit no-input mode separately, each with closed/piped stdin and a bounded timeout to detect hangs; test defined machine error output if offered. `--force` may skip a local prompt only after actual authority is established, never authorize the action. |
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

The owner directed PR #221 to reach clean review and conditionally authorized
merge after the required clean reviews. The worker prepares evidence and
repairs; the assigned coordinator retains the merge step. This is a curated
summary of supplied authorization, not a verbatim quotation. Its private
origin identifiers remain in the existing private task record.
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

## Second Copilot findings and repair

[Review 5789584157](https://github.com/saariuslystoned/SaariusSkills/pull/221#pullrequestreview-5789584157)
on `8fe58b6bfdd32c7cb9685c9dc5bbd0570f8dcc5e` explicitly resolved the first two
findings, but recommended two distinct changes:

- [4484079921](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4484079921):
  `required_fix`. Removed raw private coordination identifiers from this public
  proof; retained the authorization decision in curated form and its origin
  identifiers only in the private task record. No history rewrite is claimed.
- [4484079999](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4484079999):
  `required_fix`. Non-TTY stdin alone is not proof of unattended operation.
  The contract now permits an explicitly requested, terminal-backed selector
  or pager consuming piped data when a separate terminal exists and no-input
  mode is off. Unattended/no-input calls still cannot prompt or hang; piped
  data never grants consent. Design check: piped selection with an explicit
  interactive request and available terminal may interact; absent terminal
  or no-input mode fails promptly if interaction is required. Piped mutation
  input without authority/confirmation still fails without mutation.

CI `42078970650` and comprehensive epoch 2
`req-20261105T175356Z-22804244315` were clean on that previous tuple, not the
second repair. The comprehensive actual output reported no actionable defects,
with exact-tuple/comprehensive/P3 attestation, but did not independently verify
reported tests or upstream licensing. Main meanwhile advanced to
`30128a680575dc3d17fd1417003e5fce90f85465` with the separate skill-cleaner slice;
this was integrated without conflict or edits to its source/shared files for
renewed current-base validation. No duplicate pending review was requested.

Second repair validation: **226 tests passed** in 99.649 s on the integrated
source (including the newly merged skill-cleaner coverage). Whitespace,
references, frontmatter and public-proof privacy checks passed. The explicit
terminal/no-input cases above are reasoned instruction walkthroughs, not
executed product behavior or independent harness proof. Fresh CI, Copilot and
comprehensive P3 evidence are still required for the published repaired tuple.

## Third Copilot findings and repair

[Review 5789729287](https://github.com/saariuslystoned/SaariusSkills/pull/221#pullrequestreview-5789729287)
on `7c8921caf0b91e49690981a4f46e2a3956fd8a62` resolved the second-round findings
but recommended two distinct low-severity fixes:

- [4484196119](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4484196119):
  `required_fix`. PR description retained initial source/test/route claims as
  current. Update it to the published repaired tuple and selected Copilot/P3/CI
  route, with explicit pending versus terminal evidence. Initial authoring base
  and mechanical validation here are now labeled historical.
- [4484196169](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4484196169):
  `required_fix`. Closed/piped stdin alone does not remove a controlling
  terminal. Verification now specifies no controlling terminal or a supported
  explicit no-input mode, still with bounded timeout and closed/piped stdin;
  explicitly requested terminal-backed interaction is tested separately.
  Walkthrough: a piped call with a terminal is not classified unattended solely
  by its stdin; no-input or terminal-free calls still must not prompt/hang.

CI `42080854144` and comprehensive epoch 3
`req-20261105T180540Z-229033117017` were clean on the third reviewed source,
not clearance for this follow-up. The comprehensive actual output had zero
findings and exact-tuple/comprehensive/P3 attestation; author tests and external
source claims were not independently verified by that reviewer. Main remains
`30128a680575dc3d17fd1417003e5fce90f85465`. These are distinct repairs with
reviewer-confirmed progress, not repeated unresolved findings.

Third repair validation: **226 tests passed** in 101.700 s; whitespace and
scoped reference/privacy checks pass. The unattended/terminal-backed cases
remain author design checks, not independent runtime proof. Renewed exact-head
CI/Copilot and exact-base/head comprehensive P3 evidence are required.

## Fourth Copilot findings and scoped repair

[Review 5789863953](https://github.com/saariuslystoned/SaariusSkills/pull/221#pullrequestreview-5789863953)
on `05eaf47bc8277ac6b29881d01ebedcf85f0b7949` resolved the previous
controlling-terminal finding but recommended a distinct verification fix:

- [4484303770](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4484303770):
  `required_fix`. Replaced either/or verification with separate cases for
  terminal-free default execution without a no-input flag and, where supported,
  explicit no-input mode. Each uses closed/piped stdin and a bounded timeout,
  forbids interaction and requires actionable nonzero failure for missing
  input/confirmation. The explicit mode must suppress interaction even when
  a terminal exists. Separately requested terminal-backed interactive cases
  remain permitted with a terminal available and no-input mode off.
- Repeated [4484196119](https://github.com/saariuslystoned/SaariusSkills/pull/221#discussion_r4484196119):
  `reject_false_positive` against verified current PR metadata. The description
  already identified the then-current tuple, 226-test result and Copilot/P3/CI
  route before that review request, with initial evidence labeled historical.
  No source change is manufactured for that repeated metadata concern.

The coordinator reassessed the repeated finding and authorized this one narrow
cycle: prior distinct repairs were resolved, not nonconverging. No renewed human
merge-authorization question or duplicate pending review is needed. CI
`42082419853` and comprehensive epoch 4 `req-20261105T181601Z-233211917374`
were clean for the previous tuple, not clearance for this repair.

Reasoned walkthrough: a CLI that suppresses prompts only when its no-input flag
is set must fail the independent terminal-free default case. A CLI that still
prompts through a terminal in explicit no-input mode must fail that separate
case. Explicitly requested piped selection with a terminal and no-input off
remains its own interactive case. These are author instruction checks, not
executed product tests or independent black-box proof. This change remains
skill guidance, not a product CLI or test-fixture project.

Fourth repair validation: **226 tests passed** in 99.800 s. Whitespace,
frontmatter (Ruby Psych), local references and scoped privacy checks passed.
No test framework, product fixtures or prose-matching tests added; x-api and
shared files remain unchanged. Fresh current-head CI/Copilot and current-base/head
comprehensive P3 evidence are required.
