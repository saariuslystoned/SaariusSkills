# EmDash skill packaging proof

Status: prepared locally; exact-head independent review and merge pending.
Scope: five portable EmDash skills, upstream provenance, packaging and checks.
Owner/lane: emdash_migration. Closer: coordinating reviewer.
Mode: source mutation only. Gate: human-approved merge; no deployment or install.
Branch: `codex/emdash-public-migration`.
Public base: `4397e4481a1ee4cce28a516dd32c1d7202fcf124`.
Upstream skill pin: `15dcb07160fb321aab93fa67c6d0cbfc1c33e90f`.
The PR head identifies the candidate; `files.sha256` binds the new skill content.

## Implemented

- Packaged `emdash-sites` plus four upstream skills for existing Codex, Cursor,
  Claude Code and path-based discovery. Cursor's explicit list is extended;
  existing directory-based manifests need no change.
- Preserved MIT license and upstream provenance. The vendor mirror remains
  byte-for-byte unchanged. Packaged plugin examples apply deterministic reviewed
  corrections; notices distinguish these from verbatim upstream content.
- Sync checks both the vendor mirror and packaged copies. Updates affect only
  the four declared EmDash skill directories, and reject destination symlinks.
- Applied route-context and email-result corrections to primary packaged plugin
  examples; retained the rationale and CLI draft/revision guidance in the companion. Repository-wide third-party notices also follow the
  existing GrillTrack notice-copy packaging contract.

## Verification

- `python3 scripts/sync-emdash-skills --check`: PASS, 23 vendor files and four
  packaged skills match.
- `python3 -m unittest discover -s tests -p 'test_sync_emdash_skills.py' -q`:
  PASS, 25 tests, including immutable snapshot extraction, invalid input,
  symlink refusal, drift detection/repair and unrelated-skill preservation.
- `python3 -m unittest discover -s tests -p 'test_packaging.py' -q`:
  PASS, 15 tests, including skill discovery and standalone licenses.
- `python3 -m unittest discover -s tests -p 'test_plugin_corrections.py' -q`:
  PASS, wrapper runs 10 Node cases: 8 models and 2 executing actual packaged
  examples for sandboxed dispatch and email sender/status handling.
- Skill Creator `quick_validate.py skills/emdash-sites`: PASS using ephemeral
  PyYAML dependency. System Python lacked that optional dependency initially.
- All relative Markdown links in `skills/emdash-sites`: resolve locally.
- `git diff --check`: PASS.

- `python3 -m unittest discover -s tests -q`: repair PASS, 171 tests in
  148.655 seconds (including the transferred correction wrapper).

## Review repair, cycle 1

Accepted two P2 findings as `required_fix`: the primary sandboxed Block Kit
example exposed an invalid single-context handler, and the primary email example
omitted sender/status validation. Corrected the packaged references at source
projection time while retaining the exact upstream vendor snapshot. Regression
checks cover changed-anchor refusal, untouched native examples, vendor hashes,
idempotent projection, and actual extracted-example behavior.

The owner authorized a one-time review exception for PR #117: passing CI and
clean comprehensive OpenClaw review suffice; native ClawSweeper is not required
for this PR. This does not change review policy for other PRs.

## Limits and privacy

This is documentation and packaging proof, not proof of a deployed EmDash site,
installed harness refresh, real email delivery or production commerce behavior.
The mock correction tests explicitly use synthetic data. No live installation,
account, credential, publication or deployment operation was performed.

Reviewed export content excludes internal identities, private repository links,
incident narratives, topology and organization-specific channel policy. Only
public upstream provenance is retained. Source Git history is not imported.
Root privacy review passed for the complete staged export. Independent final
review is pending; no repository merge is authorized here.
