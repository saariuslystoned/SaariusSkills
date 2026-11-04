# Bobby mode portable revision

## Assignment and scope

The supplied 2026-11-04 request authorizes a revision of
`skills/bobby-mode/SKILL.md`, a reviewable commit, and a non-force push and draft
PR if permitted. This packet records the reasoning and local checks. It is not
runtime, installation, deployment, or merge proof.

- Repository: `saariuslystoned/SaariusSkills`.
- Assigned branch: `ridge/bobby-mode-portable-20261104`.
- Assigned base: `3c176f392220c3e34a67b3fe250342600596d9b0`.
- One writer in the assigned isolated Ridge mount; initial worktree clean.
- Scope: the canonical skill and this proof packet only. Existing sibling files,
  vendored skills, manifests, installed skills, and other checkouts stay outside
  this revision.
- Stop conditions: conflicting ownership, source ambiguity, unavailable write
  access, or a preference decision unsupported by the supplied evidence.

Read the Ridge `AGENTS.md`, repository `CONTRIBUTING.md`, relevant README
development and ownership guidance, and the local worktree policy. The mounted
repository has no separate `AGENTS.md`. The assigned base was retained rather
than replacing it with another revision.

Authoring guidance came from current `vendor/pstack/skills/automate-me/SKILL.md`,
`vendor/pstack/skills/unslop/SKILL.md`, and the available skill-creator guidance.
The explicit task replaces automate-me's transcript mining, extra agents,
Cursor-only authoring and installation instructions. No Cursor tool or another
person's mode was assumed. Existing implicit discovery was preserved; the
description now restricts applicability to Bobby. No new invocation-policy file
or manifest change was needed.

## Provenance finding

The inspected local Git repository is not shallow. `git log --all --follow`
traces the canonical file through these paths:

| Commit | Date | Evidence |
| --- | --- | --- |
| `efd83726c1d8e2797efaa6c2d310846571b28472` | 2026-08-28 | Adds `pstack/skills/bobby-mode/SKILL.md`, the local `pstack/skills/automate-me/SKILL.md`, and its `scripts/automate_me.py` together. Commit title explicitly mentions the bobby-mode profiler. |
| `7417b042cd89953922d8ac3d0210c64870033c02` | 2026-09-25 | Removes the local automate-me script during the upstream skill refresh. |
| `fd44ea424e2d98915ca7a89c55beed382c0b4701` | 2026-10-20 | Preserves the same skill at `pstack/custom/skills/bobby-mode/SKILL.md` during vendoring. |
| `b31c1c78dce266dd44f548af0efc34bc137a50dc` | 2026-10-25 | Moves the same skill into canonical `skills/bobby-mode/SKILL.md`. |

The initial file, preserved custom file, canonical move, and assigned base all
resolve to blob `a4dcd4e8833ce21025b6225d73001d9dd663cfd9`.
An AST-only inspection of the historical generator confirms that its
`generate_profile_content()` returns a constant. That constant, normalized as
the script's writer does, is byte-identical to the initial skill. No historical
script was executed.

**Conclusion:** a pre-vendor automate-me relationship is documented in source.
The script was removed before the October vendoring. This does not establish
that automate-me was actually executed to create the committed file. Its fixed
output also does not establish that the profile was derived from a comprehensive
review of conversation history. The inspected file history supplies no such run
receipt. The rewrite removes that unsupported claim rather than substituting a
new origin story.

Existing `skills/bobby-mode/SOURCE.md` identifies the file as a Saarius
customization; it does not identify a generation run. The sibling custom
instructions reinforce VTT tolerance, direct brevity, evidence and minimal code.
They were inspected as existing skill context, not edited. No private
transcripts, credential stores, or unrelated historical preferences were used.

## Rationale and preservation review

| Existing behavior or problem | Revised treatment and evidence |
| --- | --- |
| AGY title and universal operator wording | Plain Bobby title and assistant-neutral instructions, as explicitly requested. No hosts, models, tool catalogs or private operating mechanics. |
| Comprehensive multi-harness history claim | Removed for the provenance limitation above. |
| VTT, no filler, direct high-signal responses | Retained. Context may resolve obvious transcription errors; consequential ambiguity warrants a question. |
| Mandatory bullets, code blocks and tables | Formats serve the answer. Plain paragraphs are allowed; brevity keeps necessary decision, risk and result detail. This implements the supplied request's explicit format tradeoff. |
| Avoid speculative commentary | Evidence and inference stay distinct. A proposed new preference requires confirmation instead of becoming settled history. |
| Bounded action, proof, review, human gate | Retained without private execution machinery. Evidence supports non-trivial work claims; ordinary conversation does not require a proof packet. Mandatory repository checks remain mandatory. |
| Worktrees and minimal diffs | Retained with explicit preservation of dirty checkouts and unrelated work. |
| Human gates | Every old category remains: merges, production deployment, credentials, rotations, non-test communications, customer impact, destructive cleanup and migrations. Repository and organization contracts add their own requirements. Preferences grant no authority. |
| Personal applicability | Applies to Bobby, not other participants in shared conversations. No new preferences are inferred for other people. |

These are draft editorial choices grounded in the supplied request and existing
skill. They are not claims of newly discovered historical preferences. No
unresolved preference requires a human answer before presenting this revision.
Personal fit remains for Bobby to assess in draft review.

## Validation

No new tests were added for this prose-only change. The existing package checks
and explicit metadata checks cover the changed artifact.

- `git diff --check`: passed after the skill edit.
- `python3 scripts/sync-pstack-skills --check`: passed, ten upstream and two
  local skills, upstream pin unchanged.
- `python3 -m unittest tests.test_packaging tests.test_sync_pstack_skills -q`:
  passed, 36 tests. The sync tests use temporary fixture repositories; their
  update messages are not updates to the actual vendor tree.
- `skill-creator/scripts/quick_validate.py skills/bobby-mode`: unavailable
  because this Python environment lacks PyYAML. No package was installed.
- Ruby `YAML.safe_load` and explicit metadata checks: passed. Name, scalar
  description, permitted keys, description length, and unfinished scaffold
  checks passed. No link dependency or private execution binding appears in
  the revised skill. `validation.json` records the content hash and results.
- `python3 -m unittest discover -s tests -q`: passed, 186 tests in 95.086
  seconds. `unittest.txt` contains the captured result. Refusal and drift
  messages in that log come from negative test fixtures.
- Documented ledger `--help`, frontend picker fixture validation, and phone
  proof `--help` smoke checks: all passed. Adjacent text logs record commands,
  output and exit codes.

The writer inspected the complete diff and rationale before packaging. Manual
scenario review covered a short factual answer, a detailed decision explanation,
obvious VTT errors versus action-changing ambiguity, another participant's
request, an unsupported new preference, a source edit needing evidence, and every
existing human-gate category. The text preserves the relevant distinctions; this
is a source review, not a claim of live behavior across assistant products.

## Publication

Remote preflight `git ls-remote --heads origin
refs/heads/ridge/bobby-mode-portable-20261104` initially failed because
`github.com` could not resolve. The later authorized publication attempts
succeeded without an authentication or configuration change. No credentials
were inspected.

- Source and validation commit: `7c6e55cf78d597ef0a06716360516ad03cc0152d`.
- `git push origin HEAD:refs/heads/ridge/bobby-mode-portable-20261104` succeeded
  without force and created the assigned remote branch.
- `gh pr create --draft --base main --head
  ridge/bobby-mode-portable-20261104` with an explicit repository and prepared
  body succeeded.
- [Draft PR #210](https://github.com/saariuslystoned/SaariusSkills/pull/210)
  was read back as `OPEN`, `isDraft: true`, base `main`, and the assigned branch
  at the source commit above.

This follow-up records publication only. The skill content and validation hash
are unchanged. Neither local checks nor draft publication claim external review,
merge, installation or deployment.
