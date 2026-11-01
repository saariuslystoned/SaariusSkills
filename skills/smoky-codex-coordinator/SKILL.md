---
name: smoky-codex-coordinator
description: Legacy alias for smoky-coordinator during the v1 migration cycle.
---

# Legacy alias

Use [`smoky-coordinator`](../smoky-coordinator/SKILL.md) as the canonical
public core. This alias exists for one migration cycle only. Load the
canonical skill once, then follow its optional binding and repository policy;
do not load this alias recursively or treat it as a separate coordinator.
