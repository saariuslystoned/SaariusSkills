# Upstream comparisons

Reviewed 2026-11-05. These are design references, not imported runtime policies or required dependencies. No upstream prose, scripts or templates are copied into this skill.

## steipete/agent-scripts

Pinned revision: [`d210c0a77c8f9ae5e1d939b13238a75e87cdb69a`](https://github.com/steipete/agent-scripts/tree/d210c0a77c8f9ae5e1d939b13238a75e87cdb69a).

Read [maintainer-orchestrator](https://github.com/steipete/agent-scripts/blob/d210c0a77c8f9ae5e1d939b13238a75e87cdb69a/skills/maintainer-orchestrator/SKILL.md) and its [policy check](https://github.com/steipete/agent-scripts/blob/d210c0a77c8f9ae5e1d939b13238a75e87cdb69a/scripts/test-maintainer-orchestrator-policy).

Useful comparisons: explicit discovery boundaries; no workers or ongoing monitoring merely because a task exists; concrete owner choices; no automatic dependency/release follow-up. Here these reinforce a recommendation-only stopping point.

Not adopted: its multi-item-only activation, personal portfolio selection, Codex project-thread model, implementation/landing workflow or release policy. This skill explicitly supports one repository and leaves all execution to a separate handoff. Its literal-text policy check is not behavioral proof and is not copied.

## vincentkoc/dotskills

Pinned revision: [`c9ca51e3a4e93fe10266d78e430c6575a5b19d30`](https://github.com/vincentkoc/dotskills/tree/c9ca51e3a4e93fe10266d78e430c6575a5b19d30).

Read the [factory model](https://github.com/vincentkoc/dotskills/blob/c9ca51e3a4e93fe10266d78e430c6575a5b19d30/skills/tmux-agent-lane-orchestrator/references/factory-model.md) and [worker contract](https://github.com/vincentkoc/dotskills/blob/c9ca51e3a4e93fe10266d78e430c6575a5b19d30/skills/openclaw-pr-batch-sweep/references/worker-contract.md).

Useful comparisons: evidence before success claims, risk-proportionate detail, idle capacity as valid, read-only qualification distinct from implementation, and contributor content as untrusted evidence. Here these support bounded research and an explicit handoff rather than a worker factory.

Not adopted: lane classes, fixed worker counts, tmux, OpenClaw-specific tooling, host/testing policy, public-mutation serialization or cleanup lifecycle. Those belong to the active repository/workflow, not a portable assessment skill.

The pinned [vendored Anthropic skill-creator](https://github.com/vincentkoc/dotskills/blob/c9ca51e3a4e93fe10266d78e430c6575a5b19d30/vendor/anthropics/skill-creator/SKILL.md) informed lean progressive disclosure and qualitative decision scenarios. Its evaluation workers, viewer and description-optimization machinery are not required here.
