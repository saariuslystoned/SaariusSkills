---
name: smoky-cli-creator
description: Design or review command trees, arguments, output formats, exit codes, help, previews and safe mutation boundaries. Use when creating or changing a CLI interface.
---

# CLI Design

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Read `references/cli-contract.md`, then inspect the existing command parser and caller conventions. Preserve the repository's established interface where it already works.

Identify the command's audience, inputs, state changes, outputs and authorization boundary. Write a compact spec covering the command tree, usage, options, standard output versus diagnostics, exit codes, configuration precedence and examples. Include machine-readable output when a program consumes it.

For mutation, define what preview or dry-run actually does and how non-interactive calls obtain authorization. A force flag may bypass a local prompt only within the caller's existing authority; it does not authorize an external action. Never place credentials in argument values or diagnostic output. Use the repository's approved credential consumer if needed.

Validate representative success and failure invocations against the observable contract. Prefer the existing parser and test harness over introducing a new command framework. Use `smoky-behavior-validator` for independent interface proof and `smoky-worktree` when source changes need isolation. Return the spec and evidence, with unresolved compatibility choices clearly named.
