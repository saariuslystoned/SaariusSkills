# EM-Commerce REA guidance

Scope: extend the existing skill with selective reverse-engineering analysis
(REA), retaining official platform comparisons and ordinary-fix exclusions.
This is instruction and packaging evidence, not deployed runtime proof.

## Source and boundary checks

- Fresh base: `b31c1c78dce266dd44f548af0efc34bc137a50dc`.
- One focused reference is linked from `SKILL.md`; existing platform source map
  is unchanged. Implicit invocation remains enabled.
- Compared the guidance with the approved requirements: current decisions
  govern research use, evidence strength stays visible, existing records own
  unresolved questions, and no workflow/roadmap is a research prerequisite.
- DinkusKit's public organization vision and scope/planning documents are
  explicit baseline inputs; conflicts with local charters and owner decisions
  must be surfaced. This instruction applies only to DinkusKit work.
- Relative Markdown links resolve. The new text contains no private corpus
  names, paths, revisions, captures, merchant records or vendor code.
- No manifests, installation, accounts, CI configuration or product runtime
  changed. Research grants no new action authority.

## Independent behavioral check

A fresh-context agent used the draft against three synthetic scenarios:

- A cross-site knowledge question with no chosen workflow: distinguished
  schema/UI evidence from enforced and proved support.
- A new static-bundle finding against a locked cutover: continued the lock and
  deferred extra scope to the existing record.
- An unresolved marketing split: reused the proposal, preserved the open
  question and incomplete research, and continued unrelated checkout work.

All three passed without contradictory instructions. Missing capture dates were
reported as freshness gaps. The check evaluated instruction use; it does not
prove future agent behavior on every task.

## Validation

- Skill-creator `quick_validate.py skills/emdash-commerce`: passed.
- `python -m unittest discover -s tests -q`: 180 tests passed in 144.087s
  on Python 3.12.9 at `4cd3e3b`; intentional refusal-path diagnostics were
  followed by `OK`.
- `python skills/grilltrack/scripts/grilltrack_ledger.py --help`: passed.
- `python skills/grilltrack/scripts/validate_picker.py fixtures/frontend-picker/manifest.json`: passed.
- Relative-link check and `git diff --check`: passed.

After the organization-baseline link addition, repeated skill validation,
24 packaging tests, relative-link and whitespace checks passed. Both organization
document URLs resolved through GitHub's contents API. The full suite was not
repeated for this Markdown-only instruction.

CI and external review results belong to the PR and its exact head. Opening
the PR does not merge it or update installed skill copies.
