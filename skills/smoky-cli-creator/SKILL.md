---
name: smoky-cli-creator
description: Design or review command trees, arguments, output formats, exit codes, help, previews and safe mutation boundaries. Use when creating or changing a CLI interface.
---

# CLI Design

Read the current request and trusted repository instructions first. If they name an optional binding for this skill, read it for local targets, tools and policy. Without a binding, use the portable workflow below. A binding does not grant authority to act.

Read `references/cli-contract.md`, then inspect the existing command parser and caller conventions. Preserve the repository's established interface where it already works.

Identify the command's audience, inputs, state changes, outputs and authorization boundary. Write a compact spec covering the command tree, usage, options, standard output versus diagnostics, exit codes, configuration precedence and examples. Include machine-readable output when a program consumes it.

For mutation, define what preview or dry-run actually does and how non-interactive calls obtain authorization. A force flag may bypass a local prompt only within the caller's existing authority; it does not authorize an external action. Never place credentials in argument values or diagnostic output. Use the repository's approved credential consumer if needed.

Validate representative success and failure invocations against the observable contract. Prefer the existing parser and test harness over introducing a new command framework. Use `smoky-behavior-validator` for independent interface proof and `smoky-worktree` when source changes need isolation. Return the spec and evidence, with unresolved compatibility choices clearly named.
