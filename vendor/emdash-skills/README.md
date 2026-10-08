# Vendored EmDash agent skills

Verbatim skill content and MIT license from [emdash-cms/skills](https://github.com/emdash-cms/skills).
`UPSTREAM.json` records the public upstream revision and SHA-256 file manifest.
The WordPress migration skills are outside this package's scope.

Do not edit vendored skill content. `scripts/sync-emdash-skills --update --ref <sha>`
refreshes the upstream mirror and its packaged copies in `skills/`. The matching
`--check` verifies both. The surrounding README and packaged license/notice files
are maintained locally; upstream skill bytes remain unchanged.

Read [EmDash packaging and corrections](../../docs/emdash-skills.md) for ownership,
installation and version-specific guidance.
