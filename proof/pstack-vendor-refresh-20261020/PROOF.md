# PStack vendor refresh proof — 2026-10-20

Status: READY_FOR_REVIEW. Source implementation complete; external reviews and merge belong to the coordinator.

## Source and ownership

- Repo: `saariuslystoned/SaariusSkills`.
- Worktree: `/Users/bobbybones/Developer/worktrees/SaariusSkills-codex-pstack-vendor-refresh-20261020`.
- Branch: `codex/pstack-vendor-refresh-20261020`.
- Base: `c6d9193b2c451943027d1ab73afd9fc59c2b5ae3`.
- Current upstream: `cursor/plugins@a66a8931c2dd71f1ed6abf6a52b1898a9f389ae4`, observed by fresh sparse clone of upstream main on 2026-10-20.
- Previous upstream: `fadd23794c0075468eb8964b0fd93e06e09486ad`.
- Before edits, all 34 files in the ten upstream-derived skill trees exactly matched the previous upstream pin. Three files in two local skills had no upstream counterparts. See `source-mapping.json` and `custom-preservation.json`.

## Result

`vendor/pstack` holds the verbatim selected snapshot: 34 skill files plus Lauren Tan's MIT license, with per-file SHA-256 and source commit in `UPSTREAM.json`. No additional upstream skills, agents, automations, assets or plugin manifests are imported. The 23 changed upstream-derived files are summarized in `upstream-diff-stat.txt`.

`pstack/custom/skills/bobby-mode` and `pstack/custom/skills/pstack-playbooks` are the hand-maintained local sources. Every original file is byte-for-byte identical to base, both there and in the generated package. The local license names Bobby Bones. The generated package adds source/license notices, not new behavior.

`pstack/skills` remains the generated compatibility/discovery root for all twelve skills. Root symlinks, plugin names, versions and discovery manifests are unchanged. `scripts/sync-pstack-skills` offers read-only `--check`, offline `--package`, and pinned `--update`. Updates use Git objects, ignore dirty upstream working files, exclude unselected skills, refuse unsupported selected symlinks, and refuse vendor/package drift before upstream refresh. They never write into custom sources or unrelated skills.

## Validation

| Check | Result | Artifact |
| --- | --- | --- |
| `python3 scripts/sync-pstack-skills --check` | PASS: 10 upstream + 2 custom; vendor hashes, projection, root symlinks and discovery | `sync-check.txt` |
| `python3 -m unittest discover -s tests -p test_sync_pstack_skills.py` | PASS: 7 tests covering refresh, dirty-source isolation, custom collision/preservation, drift, symlinks and offline projection | `sync-tests.txt` |
| Existing `test_packaging.py` suite | PASS: 22 tests | `packaging-tests.txt` |
| Original local source hashes | PASS: all three original files unchanged in custom source and package | `custom-preservation.json` |
| YAML parsing / name / description | PASS: twelve skills | `frontmatter-compatibility.json` |
| Generic skill-creator quick validator | Two local skills PASS; ten upstream skills rejected only for their existing `disable-model-invocation` key | `quick-validate.json` |
| Scope / unchanged discovery | No changed paths outside the assigned PStack/source/proof slice | `scope-check.json` |
| `git diff --check <base> HEAD` | One upstream EOF blank-line warning retained verbatim | `diff-check.txt` |
| Non-vendor `git diff --check` | PASS | `diff-check-owned.txt` |

The generic quick validator initially lacked PyYAML (`quick-validate-missing-pyyaml.json`). PyYAML 6.0.2 was installed in this task's disposable proof virtualenv, used to run validation and parse the metadata, then removed. The ten upstream `disable-model-invocation` fields are preserved rather than silently altering invocation policy. This is a validator-schema incompatibility inherited from the old upstream package, not claimed as a passing generic check.

The existing packaging test initially passed, then its global filesystem scan encountered the temporary virtualenv's binary (`packaging-tests-scratch-environment-failure.txt`). Removing only this task-created disposable environment restored the 22-test PASS. No change to the existing test or its scope was made.

The staged full diff reports `vendor/pstack/skills/automate-me/SKILL.md:104: new blank line at EOF`. This is a byte-for-byte upstream file, so it is preserved. The non-vendor diff passes. Source implementation commit: `66f52cd6169cc9fb44b21b37e21ec0ff5cd0a82d`.

## Boundaries and remaining review

This proves source/provenance, generated distribution and preservation; it does not prove every upstream workflow in a live host. Wider PStack skill references remain upstream text; excluded skills and Cursor agents were not activated. No installed plugin, global config, service, account or unrelated skill was changed. No private transcript, credential, auth log or environment contents were read. The public upstream clone and temporary scratch are ignored by Git; they are not PR contents.

External exact-head review and human merge remain pending. This worker does not merge or publish a plugin release.
