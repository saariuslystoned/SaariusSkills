# pstack (Saarius Edition)

Selected engineering skills by [Lauren Tan](https://github.com/poteto) from
[`cursor/plugins`](https://github.com/cursor/plugins/tree/main/pstack), plus
the local Bobby Mode and engineering playbooks. The plugin keeps its existing
`pstack-saarius` name and `pstack/skills/` discovery path.

## Source ownership

| Source | Contents | How to change it |
| --- | --- | --- |
| [`../vendor/pstack/`](../vendor/pstack/) | Verbatim upstream snapshot, MIT license and hash manifest | Run the upstream update command; never hand-edit |
| [`custom/skills/`](custom/skills/) | Local `bobby-mode` and `pstack-playbooks` sources | Edit here, then regenerate the package |
| [`skills/`](skills/) | Generated distribution of the ten upstream and two custom skills | Do not hand-edit; run the package command |

The upstream pin is
`a66a8931c2dd71f1ed6abf6a52b1898a9f389ae4` (2026-10-20), recorded with
per-file hashes in [`UPSTREAM.json`](../vendor/pstack/UPSTREAM.json).
The previous ten upstream skill trees matched the old
`fadd23794c0075468eb8964b0fd93e06e09486ad` pin exactly. Bobby Mode's two files
and `pstack-playbooks` are preserved from the local source without rewriting
their contents. Future upstream refreshes cannot select either custom skill.

The ten upstream skills are `architect`, `automate-me`, `blast-radius`,
`create-verification-skill`, `how`, `maintain-verification-skill`, `reflect`,
`tdd`, `unslop` and `why`. Other upstream skills, agents, automations, assets,
and plugin manifests are not imported or activated. Upstream references to
the wider PStack suite remain upstream content; this selected package does
not claim to supply that entire suite. Repository contracts still determine
available tools, model routes, approval and privacy boundaries.

## Refresh and verify

From the repository root:

```sh
# Read-only: upstream hashes, generated outputs, local sources and discovery.
python3 scripts/sync-pstack-skills --check

# Local customization only: regenerate from the existing verified vendor pin.
python3 scripts/sync-pstack-skills --package

# Refresh the same ten skills from current upstream main.
python3 scripts/sync-pstack-skills --update

# Pin a reviewed commit from a local clone; uncommitted files are ignored.
python3 scripts/sync-pstack-skills --update --source /path/to/cursor-plugins --ref <commit>

python3 -m unittest discover -s tests -p 'test_sync_pstack_skills.py'
python3 -m unittest discover -s tests -p 'test_packaging.py'
```

Review the upstream diff and generated outputs before committing. The script
checks only its owned trees; it does not install plugins, rewrite the root
skill symlinks, alter host configuration or change any unrelated skill.
An upstream update refuses existing vendor/package drift. Move intended local
edits to their custom source and run `--package` before refreshing upstream;
unexpected handwritten package changes are never silently discarded.

## Existing discovery

Root `skills/<name>` symlinks continue to target `pstack/skills/<name>` for
SaariusSkills discovery. The separate plugin at `pstack/.codex-plugin/plugin.json`
continues to discover `./skills/`. Keep both paths intact. Installed copies
are separate deployment instances; this source update does not refresh them.

For an existing OpenClaw profile that explicitly loads this package, preserve
its configured root and allowed symlink target. Do not copy these skills into
Skill Workshop or change gateway configuration as part of an upstream refresh.
