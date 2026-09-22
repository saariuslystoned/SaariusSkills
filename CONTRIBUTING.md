# Contributing

SaariusSkills is experimental. Keep `main` honest about what is available,
tested, planned, and proven.

Contributions should:

- preserve intent-aware activation without canned user prompt gates;
- keep the core domain-neutral and move specialized depth into references;
- preserve non-destructive ledger history;
- keep product decisions separate from delivery authorization;
- include tests for state, safety, packaging, or renderer behavior they change;
- preserve pinned provenance and applicable notices;
- avoid committing generated picker work, credentials, private project data, or
  misleading proof.

Pre-implementation design bundles must say plainly that runtime behavior is
unproved, publish curated decisions instead of raw operator event history, and
remove private-repository paths, revisions, topology, and checkout state.

Develop changes on a branch and open a pull request. Do not add a case-study
claim until the linked run and inspectable evidence exist.

## Plugin surfaces

Packaging changes must keep the harness-specific manifests honest together:

- **Codex:** `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`
- **Cursor:** `.cursor-plugin/plugin.json` and `.cursor-plugin/mcp.json`
- **AGY / path installs:** root `plugin.json`

When you add or rename packaged skills, update every manifest that lists skill
paths and extend `tests/test_packaging.py`. Document install steps in
[README.md](README.md) for Codex, Cursor, and AGY when behavior differs.
