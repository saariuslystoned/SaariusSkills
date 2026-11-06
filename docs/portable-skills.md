# Portable maintenance and proof skills

The main plugin includes the reusable portable skills below. The coordinator
canonical name is `smoky-coordinator`.

| Skill | Responsibility |
| --- | --- |
| `smoky-skill-cleaner` | Read-only metadata, duplicate and reference checks |
| `smoky-behavior-validator` | Independent observable behavior contracts and proof |
| `smoky-cli-creator` | Command interface and output contracts |
| [`smoky-deslop`](../skills/smoky-deslop/SKILL.md) | Scoped changed-code cleanup that preserves behavior, security and reliability |
| [`smoky-technical-documentation`](../skills/smoky-technical-documentation/SKILL.md) | Source-truth human/agent docs, command fidelity and policy/status-preserving rewrites |
| [`smoky-pr-simplify`](../skills/smoky-pr-simplify/SKILL.md) | Smallest complete implementation across responsibilities, state and test value before review |
| [`smoky-performance`](../skills/smoky-performance/SKILL.md) | Comparable application, service, test and CI measurements with bounded improvements |
| `smoky-worktree` | Fresh source identity and isolated writable ownership |
| `smoky-coordinator` | One lead assignment through the configured runtime, bounded specialists, handoffs and exact-source closeout |
| `smoky-maintainer` | Bounded repository or selected-portfolio maintenance assessments and priorities; separate execution handoff |
| `smoky-portfolio-sweep` | Read-only qualification and serial authorized batch actions |

Each works without a private service, fleet or repository. Existing repository
instructions may name an optional local binding that supplies targets, tool
choices, capacity, model preferences and review policy. Read that binding only
when the task uses the repository; its existence grants no new permission.
Keep operational facts in the owning repository, not in another copy of the
public skill. Installation does not create or update any binding.
Treat separately listed installed variants as separate packages, not merged
policies. Read the configured profile-specific variant before the unbound core;
skip a repeated load when that profile is already active.
`dinkus-sweep` is one such installed variant: the DinkusKit profile of
`smoky-portfolio-sweep`, adding its repositories, batch card and review rails.

The skill audit helper uses the Python standard library and defaults to
read-only operation. Validation uses synthetic fixtures, not real session
archives.

The standalone `smoky-session-viewer` skill and its renderer are retired.
Historical proof remains available; retirement does not remove installed copies
or transcript data, and does not designate a replacement viewer.

The instructions are generalized owner-authored workflows. The coordinator
retains an acknowledgement of Vincent Koc's public
[factory model](https://github.com/vincentkoc/dotskills/blob/main/skills/tmux-agent-lane-orchestrator/references/factory-model.md)
and [worker contract](https://github.com/vincentkoc/dotskills/blob/main/skills/openclaw-pr-batch-sweep/references/worker-contract.md).
Its third-party notice preserves that project's MIT attribution. Those
projects' runtime, host, transport and review choices are not required here.

`smoky-deslop` and `smoky-technical-documentation` adapt the same project's
technical-deslop and technical-documentation at revision
`c9ca51e3a4e93fe10266d78e430c6575a5b19d30`. Each distributable directory
contains its license and full upstream MIT notice; the root
[notices](../THIRD_PARTY_NOTICES.md#dotskills-portable-adaptations) record the
source and adaptation boundaries. They add no runtime, STE lint requirement or
repository-wide audit default. Packaging audits remain with
`smoky-skill-cleaner`; writing-style cleanup remains distinct from code cleanup
and operational documentation verification.

`smoky-pr-simplify` and `smoky-performance` adapt pinned OpenClaw guidance.
Each skill directory preserves its source attribution and upstream MIT notice.
The performance skill includes the former CI performance helper and references.
Its existing receipt schema stays stable for consumers of prior measurements.
