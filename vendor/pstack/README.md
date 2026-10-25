# PStack upstream skills

Ten selected engineering skills by [Lauren Tan](https://github.com/poteto)
from [`cursor/plugins`](https://github.com/cursor/plugins/tree/main/pstack).
They live only in this directory. There is no generated root `pstack/` package
and no upstream PStack aliases under root `skills/`.

## Source ownership

- `skills/` and `LICENSE` are the verbatim upstream snapshot.
- `UPSTREAM.json` records the pin and each upstream file's SHA-256 hash.
- `README.md`, `.codex-plugin/plugin.json` and `plugin.json` are repository-owned
  documentation and discovery metadata, preserved by the updater and excluded
  from upstream hashes. No upstream plugin manifests are imported.
- [`../../skills/bobby-mode/`](../../skills/bobby-mode/) and
  [`../../skills/pstack-playbooks/`](../../skills/pstack-playbooks/) are authored
  Saarius skills. Edit them directly; upstream refreshes never write there.

The upstream pin remains `a66a8931c2dd71f1ed6abf6a52b1898a9f389ae4`
(2026-10-20). The ten selected skills are `architect`, `automate-me`,
`blast-radius`, `create-verification-skill`, `how`,
`maintain-verification-skill`, `reflect`, `tdd`, `unslop` and `why`.
Other upstream skills, agents, automations and assets are not imported.
References to the wider PStack suite remain upstream content; this selected
package does not supply that entire suite.

## Refresh and verify

From the repository root:

```sh
# Read-only: upstream hashes, local sources and direct plugin discovery.
python3 scripts/sync-pstack-skills --check

# Refresh the same ten skills from current upstream main.
python3 scripts/sync-pstack-skills --update

# Pin a reviewed commit from a local clone; uncommitted files are ignored.
python3 scripts/sync-pstack-skills --update --source /path/to/cursor-plugins --ref <commit>

python3 -m unittest discover -s tests -p 'test_sync_pstack_skills.py'
python3 -m unittest discover -s tests -p 'test_packaging.py'
```

An update refuses existing vendor drift. Review the upstream diff before
committing. `--package` remains a read-only compatibility alias for `--check`;
there is no projection or regeneration step.

## Discovery and migration

The main Codex and Claude Code plugins name both root `skills/` and
`vendor/pstack/skills/`. Cursor names the ten vendor skill directories directly.
The optional Codex `pstack-saarius` marketplace entry points here and discovers
`./skills/`. It contains only upstream skills; Bobby Mode and the playbooks
belong to the main Saarius Skills plugin. Avoid installing both Codex entries
unless you intentionally want the upstream skills in both namespaces.

For AGY, the root path install covers authored skills. Install this directory
as an additional path-based plugin for the upstream skills:

```sh
agy plugin install /path/to/SaariusSkills/vendor/pstack
```

Existing path-based integrations using `/path/to/SaariusSkills/pstack` must
switch to `/path/to/SaariusSkills/vendor/pstack`. Refresh existing marketplace
installs to pick up the changed package path. No installed cache, OpenClaw
profile or host configuration is changed by the sync script or this migration.

Manifest path formats:
[Codex](https://developers.openai.com/plugins/deploy/submission#package-identity-and-components),
[Claude Code](https://code.claude.com/docs/en/plugins-reference#path-rules).
