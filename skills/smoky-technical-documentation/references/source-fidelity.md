# Source fidelity before style

Use this checklist for claims in the requested scope. Keep a small claim-to-evidence map inline unless durable proof has a declared consumer. Cite the source revision/version; date observations that can change independently of code.

| Claim | Check | What the check does not prove |
| --- | --- | --- |
| Command/subcommand/flag | Owning parser, wrapper and safe `--help`; tests for accepted combinations | That a live mutation is authorized or succeeds |
| Alias/default/config precedence | Resolver and entrypoint code plus applicable policy; test conflicting inputs if safe | That a similarly named alias has the same policy |
| Local path | Existence and case, relative to the declaring file or command's working directory | A deployed URL or generated output exists |
| Link/anchor/navigation | Read the target, check its actual section and description; use the native link/build checker | That filesystem slugs equal framework routes |
| Generated documentation | Locate the generator and its input; check regeneration/check mode in scope | That hand-editing generated output is durable |
| Version/feature/API | Manifest, implementation, tests and applicable release record | That main has shipped or a deployment uses that version |
| Operational status | Dated, version-bound deployment/observation evidence with its limits | That a past healthy observation is current health |

## Commands and examples

- Check exact spelling, case, arguments, quoting, aliases, required flags and order-sensitive behavior. Inspect wrappers as well as underlying tools; they may change defaults and authorization.
- Confirm prerequisites and working directory. Avoid examples that rely on an undeclared environment, leak sensitive data or hide failure behind a pipeline.
- Prefer hermetic parser tests, safe help and repository-native docs/snippet checks. First verify that a help or dry-run path has no unwanted side effects. A “dry-run” may contact a service or write state; the name is not a safety guarantee.
- Preserve literal commands during a prose rewrite. Correct a literal only with source evidence, clearly identified as a factual correction. Never run deploy/send/delete/install/auth-changing actions merely to verify a sentence.
- Report static-only or not-run checks and why. A link checker passing does not prove that a command works or that a page's description is true.

## Framework and information architecture

Read the existing docs configuration and nearest examples. Resolve source paths relative to their declarer, and published routes through the framework's mapping. Preserve existing anchors, redirects and version selectors; when an authorized move needs compatibility, verify old and new destinations with native tooling. Do not split a coherent lookup table or migrate the framework just to meet a size heuristic.

For multilingual changes, follow the repository's source-language/parity policy. Report missing translated warnings, steps or version notes rather than claiming parity from matching headings.

## Status-preserving example

Source says: “Export is implemented and tested locally, but not deployed. After owner approval, run `tool export --preview` to inspect the plan.” A rewrite must retain the not-deployed state, approval condition and exact command. “Export is available; run `tool export`” is wrong even if it reads better. Verify the preview flag in the parser without running the gated export.
