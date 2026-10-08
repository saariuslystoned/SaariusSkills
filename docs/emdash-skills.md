# EmDash skills

The package includes five discoverable skills:

| Skill | Responsibility |
| --- | --- |
| `emdash-sites` | Implementation decisions, draft safety, plugin surfaces and observable verification |
| `building-emdash-site` | Upstream schema, seed, queries and rendering mechanics |
| `creating-plugins` | Upstream native/sandboxed plugin mechanics |
| `emdash-cli` | Upstream command-line workflows |
| `upgrading-emdash` | Upstream upgrade workflow |

## Installation and ownership

Codex discovers `skills/` through `.codex-plugin/plugin.json`; Cursor lists the
five directories in `.cursor-plugin/plugin.json`; Claude Code discovers the
standard `skills/` directory. AGY/path installations use the same directories
under the root plugin. Use the [repository install guide](../README.md#install).
For manual skill-only installations, copy all five complete directories into
the harness's supported skill location. EmDash skills do not require the ACP
bridges. No installer or account configuration is changed by adding these files.

Upstream skill content is vendored verbatim at public commit
[`15dcb07160fb321aab93fa67c6d0cbfc1c33e90f`](https://github.com/emdash-cms/skills/tree/15dcb07160fb321aab93fa67c6d0cbfc1c33e90f),
the EmDash v1.2.0 skill release. [UPSTREAM.json](../vendor/emdash-skills/UPSTREAM.json)
records file hashes. The MIT license is preserved both beside the vendor mirror
and in every packaged upstream skill. These license/notice additions do not
modify upstream skill content. WordPress migration skills are outside this set.

`emdash-sites` is maintained separately. It records corrections to examples at
the bundled pin: sandboxed versus native handler contexts, email sender/status
handling, and revision isolation for CLI draft updates. Read it with the relevant
mechanics skill. The project's resolved implementation takes precedence over a
historical skill release. Standalone upstream-only installation omits these local
corrections; install the full set for the maintained guidance.

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
