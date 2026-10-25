# PStack single-source layout proof

Repository: `saariuslystoned/SaariusSkills`
Branch: `codex/pstack-vendor-only`
Base: `1411ac45bc0a1f28b492eb13eecf4fe0988646fa`
Date: 2026-10-25

## Result

The ten upstream skills exist only in `vendor/pstack/skills/`. Root `pstack/`
and the ten root discovery symlinks are removed. The authored Bobby Mode and
playbook sources are real directories in root `skills/`.

Codex and Claude manifests name both skill roots. Cursor names the vendor
skill paths directly. The optional Codex package points to `vendor/pstack/`
and contains only the ten upstream skills. AGY's separate vendor path install
is documented; no installed plugins or host configuration were changed.

## Preservation and verification

A byte comparison against the base confirmed the unchanged upstream pin,
all 35 files listed in `vendor/pstack/UPSTREAM.json`, and all three authored
source files formerly in `pstack/custom/skills/`. The initial sync check on the
base confirmed that the removed generated copies matched those sources.
The upstream MIT license remains in `vendor/pstack/LICENSE`; the authored
skills each retain the existing local MIT license.

- `python3 scripts/sync-pstack-skills --check`: passed.
- PStack sync suite: 10 tests passed.
- Packaging suite: 24 tests passed.
- Portable skill suite: 7 tests passed.
- `claude plugin validate .claude-plugin/plugin.json`: validation passed.
- `claude plugin validate .`: marketplace validation passed.
- Ledger and PhoneProof `--help` smokes: passed.
- Frontend picker fixture validation: `valid`.
- `git diff --check`: passed.
- `python3 -m unittest discover -s tests -q`: 180 tests passed in 139.548 seconds on Python 3.15.0. Raw output: [`full-suite.log`](full-suite.log).
  The first three diagnostics are expected negative-fixture output; the terminal result is `OK`.

The offline fixtures prove committed-source selection, rejection of vendor
hash drift and symlinks before mutation, preservation of local edits and
repository-owned vendor metadata, exclusion of unselected skills, absence of
legacy aliases/packages, and discovery of each skill once in each main manifest.

## Review and limits

Accepted: the optional `pstack-saarius` package loses its two locally authored
skills; both are still included in `saarius-skills`. Existing path consumers
must change `/pstack` to `/vendor/pstack`. Package versions advance to 0.7.1
and 0.2.0 to advertise the changed layout.

Rejected concern: removing generated copies changes upstream instructions.
The pin and all hashed upstream bytes are unchanged.

Rejected concern: an upstream refresh overwrites authored skill edits.
The updater writes only the vendor tree; an offline refresh test proves that
local edits survive unchanged.

Codex/Claude path support was checked against their official manifest docs,
linked in `vendor/pstack/README.md`. This is source and CLI validation, not a
claim of live UI discovery in every harness. Existing installed caches and
OpenClaw profiles were not changed or live-tested. Human merge remains pending.
