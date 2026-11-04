---
name: smoky-ci-performance
description: Diagnose and improve test runtime or CI efficiency with comparable evidence, preserved test semantics, and conservative delivery gates. Use for bounded performance work; do not use as a universal test runner or CI service.
---

# CI and test performance

Use this skill for one bounded performance question in an existing repository.
Read the nearest repository instructions and use its existing commands, checks,
workflow definitions, and reporting formats. Do not invent a scheduler, CI
service, universal test runner, or guessed command.

Choose one mode:

- **Test runtime:** reduce test, import, setup, build, or coverage-path cost while
  retaining the same assertions, coverage meaning, and relevant integration
  proof.
- **CI efficiency:** reduce queue, setup, build, restore, test, or workflow
  waste without weakening required checks, status semantics, or failure
  visibility.

## Evidence contract

Bind every comparison to the exact source revision, relevant config, runtime
and tool versions, environment, dependency/build inputs, cache identity and
state, selector, and command. Record queue, setup, build, import, test, and
post-test/coverage phases separately when available. Distinguish CPU-bound,
RSS/memory-bound, I/O/wait-bound, and queue/setup time; wall time alone is not
diagnosis.

Establish a comparable baseline. Repeat the same measurement when noise could
change the decision, and disclose discarded, failed, stale, or incomparable
runs. For caches, account for producer cost, restore cost, cache-hit
verification, invalidation, partial/stale data, and miss behavior. A faster
step is not automatically a cheaper run: report timing and bill/resource
impact separately, including whether execution is free, public, or
self-hosted.

Make one targeted improvement at a time. Preserve test and coverage semantics;
do not hide failures, remove assertions, narrow required selectors, or turn a
required check optional. Selectors need a conservative fallback, and required
status must remain required. Classify results strictly as success, failure,
cancelled, stale, partial, or inconclusive—never promote a partial or stale
result to green.

Keep rejected experiments and their evidence. Stop when the meaningful target
is demonstrated or no worthwhile candidate remains; there is no forced
speedup goal. A skill scaffold or structural check is unqualified until a
real campaign supplies comparable before/after evidence.

## Repository profile

When a repository needs repeatable guidance, propose a small profile rather
than guessing commands. Keep it repository-owned and reviewable:

```yaml
source: exact revision or reference
runtime: versions and runner identity
commands:
  baseline: existing command
  candidate: existing command or narrowly documented change
  verify: required checks
identity:
  config: relevant files or digest
  environment: non-secret relevant variables
  cache: key, scope, producer, restore, verification, miss policy
metrics: [queue, setup, build, import, test, coverage, wall, cpu, rss, bill]
selector: changed-scope rule with conservative fallback
stop: measurable target or no-worthwhile-candidate rule
```

Do not put secrets, tokens, host-layout details, or account data in profiles or
reports. Private paths are prohibited in PUBLIC profiles and reports. An
authorized private-repository profile may use necessary non-secret
repo-relative source and proof references. Route actual execution and
verification through the repository’s owned commands. Keep the source change,
measurement artifacts, rejected candidates, semantic/coverage notes, and final
classification inspectable.

For the measurement and CI-specific checklists, read:

- [benchmark-protocol.md](references/benchmark-protocol.md) for baseline,
  attribution, and result classification.
- [ci-efficiency.md](references/ci-efficiency.md) for workflow, cache, selector,
  and required-status review.
