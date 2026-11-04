# CI efficiency checklist

Inspect the existing workflow and repository profile before proposing a change.
Keep required checks and failure visibility intact.

- Attribute queue, setup, checkout, dependency, build, cache restore/save,
  import, test, coverage, artifact, and teardown time separately.
- For caches, bind key and scope to the relevant source/config/runtime inputs.
  Include producer cost, restore cost, hit verification, invalidation,
  partial/stale data behavior, and the cold-miss path.
- For changed-scope selectors, define the matching rule and a conservative
  fallback. Uncertain, malformed, or unavailable change data must select the
  safe broader check, not skip it.
- Keep required status required. A cancelled, stale, partial, or missing
  result is not success; surface it explicitly and preserve retry/recovery
  semantics already owned by the repository.
- Compare execution timing with billed/resource impact. A free or public
  runner can still consume scarce capacity; a self-hosted runner can trade
  queue time for machine utilization.
- Make one bounded change and verify both the workflow configuration and the
  repository’s existing required checks. Do not add a scheduler, CI service,
  universal test runner, or publication step.

Record the exact files, command/config identity, before/after evidence, semantic
and coverage impact, rejected alternatives, result classification, and stop
decision.
