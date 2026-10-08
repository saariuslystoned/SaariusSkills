# EmDash skills

The package includes seven discoverable skills:

| Skill | Responsibility |
| --- | --- |
| `emdash-sites` | Implementation decisions, draft safety, plugin surfaces and observable verification |
| `emdash-ci-deploy` | CI target isolation, deployment ordering and commit-aware release verification |
| `emdash-commerce` | Official-source platform comparisons before major Commerce/companion-plugin GrillTrack proposals or locks |
| `building-emdash-site` | Upstream schema, seed, queries and rendering mechanics |
| `creating-plugins` | Upstream native/sandboxed plugin mechanics |
| `emdash-cli` | Upstream command-line workflows |
| `upgrading-emdash` | Upstream upgrade workflow |

## Installation and ownership

Codex discovers `skills/` through `.codex-plugin/plugin.json`; Cursor lists the
seven directories in `.cursor-plugin/plugin.json`; Claude Code discovers the
standard `skills/` directory. AGY/path installations use the same directories
under the root plugin. Use the [repository install guide](../README.md#install).
For manual skill-only installations, copy all seven complete directories into
the harness's supported skill location. EmDash skills do not require the ACP
bridges. No installer or account configuration is changed by adding these files.

Upstream skill content is vendored verbatim at public commit
[`15dcb07160fb321aab93fa67c6d0cbfc1c33e90f`](https://github.com/emdash-cms/skills/tree/15dcb07160fb321aab93fa67c6d0cbfc1c33e90f),
the EmDash v1.2.0 skill release. [UPSTREAM.json](../vendor/emdash-skills/UPSTREAM.json)
records file hashes. The MIT license is preserved both beside the vendor mirror
and in every packaged upstream skill. The vendor mirror stays byte-for-byte unchanged. Packaged `creating-plugins`
references apply two deterministic corrections before distribution; the other
three skills retain verbatim upstream content. WordPress migration skills are outside this set.

Packaged `creating-plugins/references/block-kit.md` corrects the sandboxed form
handler to receive `(routeCtx, ctx)` and read `routeCtx.input`, preserving native
single-context examples. Its `references/hooks.md` requires a configured sender,
sets JSON content type and rejects unsuccessful email-provider responses with a
sanitized error. The projector validates exact source excerpts before patching;
a changed upstream excerpt stops packaging for review instead of silently
applying an outdated patch. These corrections are present in the primary skill,
so loading `creating-plugins` alone receives the safe examples.

`emdash-ci-deploy`, `emdash-sites` and `emdash-commerce` are maintained separately from the upstream
mirror. Sites adds implementation judgment and CLI draft/revision guidance;
Commerce prepares source-linked comparisons of 3–5 relevant platforms before
material product, API or data-model proposals. Commerce consumes current locks,
preserves unresolved choices and hands research back to GrillTrack without
replacing its lifecycle or authorizing implementation or delivery. It excludes
routine fixes and settled implementation unless material evidence calls for
reopening. Invoke it naturally or as `$emdash-commerce`; its official source map
is a starting point requiring fresh date/version/status checks.

Read Sites with the relevant mechanics skill. The
project's resolved implementation takes precedence over a historical release.

## Maintenance

Run `python3 scripts/sync-emdash-skills --check` to check vendor hashes and packaged
copies. To update the four-skill set, run
`python3 scripts/sync-emdash-skills --update --ref <public-upstream-commit>` and
review the new mirror, packaged copies and corrections together. `--source`
accepts a local upstream clone but still extracts the selected committed snapshot,
not its working files. Update this document's pin after reviewing a new release.
Run `python3 -m unittest discover -s tests -p 'test*emdash*.py'` and the packaging
suite before submitting changes. Updating the bundle does not update any site's
EmDash dependency, change production content or authorize a deployment.

CI Deploy provides portable pipeline and verification guidance. It does not bundle
a deploy script or a proven live pipeline, and preserves project approval gates.
