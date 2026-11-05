---
name: smoky-behavior-validator
description: Verify a web app, CLI, API, device or artifact against an observable behavior contract without reading its implementation. Use for independent user-visible proof.
---

# Behavior Validator

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Use this workflow directly in a supported harness or within an assigned worker task; no coordinator service is required. Start from the task's acceptance criteria. Use `references/contracts.md` to record a short inline or linked contract: observable goal, exact target/version/environment, authorized fixtures/actions, expected results and exclusions. Target-owned published interface specs, acceptance criteria, fixtures and externally observable state are valid inputs. Flag missing or conflicting expectations; do not invent product rules. Apply the verdict rules in `references/report-schema.md` to every report, including inline reports; only its JSON format is optional.

## Stay source-blind

Do not read the tested target's implementation source, diffs, internal tests, build internals or developer explanations as validation evidence. Prefer a separate context containing only the contract, authorized fixtures and observations. If implementation details are already in context or arrive during testing, disclose the contamination and hand independent validation to a clean source-blind context; do not claim independence. If implementation access is necessary to continue, report `blocked_source_required` and hand the task back rather than silently changing roles. Inspecting this skill's source to author or review its instructions is not validation of a product.

## Exercise and report

Exercise the user/operator interface on the exact authorized web, CLI, API, registered test-device or artifact target using available approved tools. Honor action and privacy gates; availability is not permission to switch identities/devices or send, spend, deploy or mutate beyond scope. Missing tools, access or authorization are blockers, not permission to install tools, provision access or bypass controls.

Add relevant input variations, retry/reopen and invalid or boundary cases in proportion to the acceptance criteria and risk. Verify resulting state and persistence where claimed; a static screenshot or successful command alone does not establish additional behavior promised by the contract. Do not manufacture requirements from exploratory probes.

Mark every clause pass, fail, blocked or out of scope, with concise evidence, reproducible steps, target identity and limits. A trivial check can be a short inline report; require no elaborate packet. Never present source edits, builds or synthetic/mock checks as live product behavior proof. Keep credentials, private data and unrelated logs out of reports.

Code-aware review and repairs belong to separate roles. Report behavioral findings against contract clauses, not code locations or implementation style. After a separate repair, rerun affected clauses and adjacent regressions on the identified new target. Transcript rendering is supporting context, not application behavior.
