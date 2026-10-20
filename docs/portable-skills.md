# Portable maintenance and proof skills

The main plugin includes eight reusable skills. Their names remain stable:

| Skill | Responsibility |
| --- | --- |
| `smoky-skill-cleaner` | Read-only metadata, duplicate and reference checks |
| `smoky-behavior-validator` | Independent observable behavior contracts and proof |
| `smoky-cli-creator` | Command interface and output contracts |
| `smoky-worktree` | Fresh source identity and isolated writable ownership |
| `smoky-session-viewer` | Explicit local JSONL input to private searchable HTML |
| `smoky-codex-coordinator` | Bounded worker assignments, handoffs and exact-source closeout |
| `smoky-maintainer` | Portfolio selection and decision-ready maintenance briefs |
| `smoky-portfolio-sweep` | Read-only qualification and serial authorized batch actions |

Each works without a private service, fleet or repository. Existing repository
instructions may name an optional local binding that supplies targets, tool
choices, capacity, model preferences and review policy. Read that binding only
when the task uses the repository; its existence grants no new permission.
Keep operational facts in the owning repository, not in another copy of the
public skill. Installation does not create or update any binding.

The two Python helpers use the standard library. Audit defaults are read-only;
the session viewer reads a named input and writes only its requested local
output. Renderer redaction is best-effort: an HTML file can still contain
private messages, paths and instructions. It is never automatically public-safe.
Validation uses synthetic fixtures, not real session archives.

The instructions are generalized owner-authored workflows. The coordinator
retains an acknowledgement of Vincent Koc's public
[factory model](https://github.com/vincentkoc/dotskills/blob/main/skills/tmux-agent-lane-orchestrator/references/factory-model.md)
and [worker contract](https://github.com/vincentkoc/dotskills/blob/main/skills/openclaw-pr-batch-sweep/references/worker-contract.md).
Its third-party notice preserves that project's MIT attribution. Those
projects' runtime, host, transport and review choices are not required here.
