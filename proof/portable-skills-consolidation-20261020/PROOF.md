# Portable skill consolidation proof

Status: LOCAL_REVIEW_READY. Publication waits for coordinator privacy review.

## Changes

Eight stable skill IDs now have portable behavior, local references and optional repository bindings: skill audit, observable behavior validation, CLI design, isolated worktrees, private session viewing, Codex coordination, portfolio maintenance and selected-batch sweeps. No fleet, account, business-priority or fixed-model configuration is required by these public cores. Each core defers to a configured profile-specific installed variant or optional binding before execution, without inventing or searching for one. Separate installed variants are not treated as merged policy. Binding notes and source inspection evidence are stored outside this repository and are not part of this commit.

The main Codex and Claude plugin manifests are version 0.7.0; Cursor explicitly lists all eight skills. A separate opt-in marketplace entry resolves the existing PStack plugin at its unchanged source path and version. PStack/custom sources and EmDash/vendor files are unchanged.

Two owner-authored standard-library Python helpers are included. The audit is read-only and accepts explicit roots. The viewer accepts a named JSONL input, writes private HTML, escapes displayed content, uses best-effort token replacement, refuses source, hardlink and symlink output and requires explicit overwrite. It performs no transcript discovery or publishing. No real transcripts or runtime data were used for validation.

## Provenance

Helper authorship was checked in source-control metadata; the owner explicitly requested this public consolidation. The source shelf's lack of a license was not treated as a license grant. Newly generalized owner-authored content uses this repository's MIT license under that explicit request. Existing public conceptual attribution for the coordinator is retained in its third-party notice; the referenced project's MIT attribution is preserved. No private Git history or unfiltered proof tree is imported.

## Verification

- Seven fixture/packaging/privacy tests pass: `portable-tests.txt`.
- Twenty-two existing package tests pass: `packaging-tests.txt`.
- Eight skill audits have no reported issues: `skill-audit.json`.
- Scoped operator-marker check has no matches; its private marker list and raw findings remain outside the public tree: `privacy-summary.json`.
- Scope check reports no protected PStack or EmDash/vendor source changes: `scope.json`. Their dedicated source/package checks also pass: `pstack-check.txt`, `emdash-check.txt`.
- Diff whitespace check passes: `diff-check.txt`.

The marker scan is bounded evidence, not a complete privacy guarantee. Independent review of the exact public diff remains required before push. Helper tests prove only synthetic local behavior, not safe publication of generated HTML or live product behavior. No merge, installation, account change or deployment was performed.
