---
name: smoky-behavior-validator
description: Verify a web app, CLI, API, device or artifact against an observable behavior contract without reading its implementation. Use for independent user-visible proof.
---

# Behavior Validator

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Use `references/contracts.md` to define the observable goal, target, allowed inputs, expected results and exclusions before testing. Use `references/report-schema.md` when structured output is needed.

Remain outside the implementation: do not read source, diffs, implementation tests, build internals or developer explanations to decide whether behavior passes. Exercise the public interface using the authorized fixture and target. If implementation access is necessary to continue, report `blocked_source_required` and hand the task back rather than silently changing roles.

Vary relevant inputs, repeat an action, reopen or refresh, and test obvious invalid cases in proportion to the contract. Verify resulting state and persistence; a static screenshot or successful command alone does not establish the claimed interaction.

Mark every clause pass, fail, blocked or out of scope. Attach concise evidence and reproducible steps. After a repair, rerun failed clauses and adjacent regressions. Source review belongs to a separate review role; transcript rendering is supporting context, not application behavior. Keep private data, credentials and unrelated logs out of reports.
