---
name: smoky-cli-creator
description: Design, implement or review CLI interfaces and verify command behavior. Use for specification-only requests or authorized creation and changes to commands, arguments, help, output and safe mutation boundaries.
---

# CLI Design and Delivery

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

This core works directly in a supported standalone coding harness or as worker guidance; it requires no particular runtime, framework or generator.

## Discover and bound the task

Before creating a command, check the repository's existing facade and relevant official or mature CLIs. Identify the actual user-workflow gap; recommend reuse or a narrow extension when it already meets the need. For a small existing-command change, inspect only the relevant parser, help, tests and callers—not the whole ecosystem. Preserve established syntax, defaults, schemas and exit behavior unless the requested change authorizes a compatibility break.

Establish whether the request is specification-only, implementation, or review. Do not turn a design-only request into source changes. When source changes are authorized, carry the design through implementation and testing; routine interface choices within that authority do not need a separate approval ceremony. Ask only about material unresolved scope, compatibility or authority decisions.

## Specify, then implement within authority

Read `references/cli-contract.md` for interface and verification details. Write a compact interface specification proportional to the change: audience and gap, usage/inputs, state changes, output/errors, applicable configuration and authorization, examples and compatibility. A small flag change may need only a few lines in the existing task or PR record. Omit irrelevant surfaces rather than adding flags or features to fill a template.

For mutation, define preview/dry-run side effects and unattended authorization. A force flag may bypass a local prompt only within the caller's existing authority; it never grants authority. Keep credentials out of argument values and diagnostics; use the repository's approved consumer when needed.

For authorized implementation, use the established parser, facade, language and test harness. Keep changes focused, update affected help/docs and preserve existing callers. Do not add a new framework, cache, MCP server, generator or installation step without an actual requirement. Source authorization is not permission to ship, install, deploy or perform a gated external action.

## Verify and hand off

Exercise representative user workflows and failure paths against the delivered command—not just compilation or `--help`. When output is generated, build and exercise representative resulting output, not templates alone. Use deterministic/golden tests only for real stable observable contracts; prefer focused assertions for individual semantics and never snapshot private or incidental content.

Separate mechanical results (parsing, tests, stream separation, exits) from reasoned judgments (discoverability, usefulness, compatibility). For spec-only work, report design checks and unproved runtime behavior rather than claiming execution. Use `smoky-behavior-validator` only when genuinely independent observable-interface proof is appropriate and available; authoring-source inspection is not black-box proof. Use `smoky-worktree` when available and needed for source isolation, or follow the repository's existing isolation mechanism. Neither skill is a prerequisite for standalone use.

Return the compact spec or its location, changes, evidence, compatibility decisions, remaining limits and next action/stop reason. Reuse the existing task/proof record; do not create a new ledger for every small command. Upstream influences and adaptation boundaries are credited in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
