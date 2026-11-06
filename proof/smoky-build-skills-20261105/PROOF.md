# Smoky build skills proof

## Source and scope

The owner requested smoky-pr-simplify and smoky-performance in SaariusSkills with a PR. The source base is cbe0738b611b75cdf1dc458efdeb6863da102597. Existing smoky-deslop and smoky-ci-performance were inspected for overlap. The new skills target change-level simplification and application/service performance respectively.

## Upstream provenance

Read the following sources at OpenClaw commit 85c39026a90f58164595249f69c311ed71b44df8 through GitHub.

- .agents/skills/pr-simplify/SKILL.md, Git blob 728e8451571967488069df515409f7376407b2b6.
- .agents/skills/openclaw-performance/SKILL.md, Git blob 03008f8c4d7f85c2fa554b123cf2cd7361789c47.
- LICENSE, Git blob ed064819ab537575d0cad902f7e5af4a3488b1d0, MIT with Copyright (c) 2026 OpenClaw Foundation.

Adaptation omits upstream-specific runtime, host, command, numeric-threshold and merge-policy assumptions. Per-skill notices retain the pinned source and upstream license. The earlier activity sample establishes discovery, not measured effectiveness of the new skills.

## Validation

The implementation uses one smoky-performance entrypoint, with the existing CI/test references and capture helper migrated into it. New command documentation uses the consolidated path. The helper's only executable-file change is its usage path. Its serialized schema remains smoky-ci-performance.capture.v1 so existing receipt readers keep working. A regression assertion checks that schema in actual command receipts.

The source was checked on local Python 3.15.0. The complete suite passed with 227 tests in 145.590 seconds. Focused packaging tests passed with 31 tests, and capture-helper tests passed with 16 tests. Both skill directories passed the skill-creator quick validator. The system Python lacked PyYAML, so validation used an ephemeral uv environment with PyYAML. See local-validation.txt for exact commands and outputs.

Reviewed the full proposed change and compared the migrated helper, benchmark protocol and CI-efficiency guidance with the base. The helper differs only in its displayed usage path. The benchmark protocol and CI-efficiency guidance are preserved. The capture contract adds the renamed paths and explicitly documents the stable schema. Staged diff whitespace checks and proof event JSON parsing passed. Package tests confirm one discoverable performance skill, both new entrypoints, their metadata and license notices, and local documentation links.

These checks establish packaging and helper behavior. They do not measure application performance gains or prove improved agent decisions in real projects.

## Review and publication

Published [PR #223](https://github.com/saariuslystoned/SaariusSkills/pull/223). The implementation commit is 87146e2fd88abec030adf026eef40e374d6458ac. Later changes in this proof packet only record publication. The repository CI runs Python 3.14 on Linux and macOS, distinct from this local Python 3.15 result. The PR conversation and checks retain current external review and CI status for the current head.

The GitHub connector refused creation with HTTP 403, while the already authenticated GitHub CLI created the requested PR successfully. No credential or permission change was made.

The exact-diff media inventory found zero added or modified media files. The media-placement wrapper refused an unknown asset destination for this repository before inspecting candidates. This is a tooling limitation for this text-only change. There is no media placement to resolve or publish. The repository's only workflow at the base is tests.yml, and the initial PR readback exposed no native ClawSweeper review or intake. Missing native review remains missing evidence rather than a clean verdict. A separate comprehensive review can be tracked in the PR conversation.

No installation, release or merge is claimed.
