---
name: smoky-coordinator
description: Coordinate substantial work through the configured execution runtime with one lead worker, scoped context, exact-source proof, and repository review gates. Keep quick checks and decisions conversational.
---

# Smoky Coordinator

Use this public core for one enduring parent conversation that owns scoping,
decisions, acceptance, and the next action. Read repository
instructions and available skill metadata first. If either identifies a
configured private operator or repository profile, including an optional binding
or an installed profile-specific variant of this skill, read and honor that
binding before applying this core. A binding supplies local targets and policy;
it does not grant authority. Use the configured execution runtime without
prescribing a host, transport, harness, or private model roster. Do not invent a
scheduler, queue, or status store.

## Admit and route

Keep quick checks, status, explanations, and decisions in the conversation.
For substantial implementation, create one durable assignment through the
configured runtime. First inspect overlapping work and choose the repository
or workspace and task loadout from the canonical catalog: only the skills,
tools, and verifiers this task needs. Record the objective, exact source,
scope and exclusions, acceptance, dependencies, one writable owner, closer,
proof pointers, stop condition, and next action in the existing task record.

The coordinator selects scope, workspace, and loadout; the runtime provisions
and tracks isolation and execution ownership; the lead worker investigates,
implements, verifies, and commits inside that assignment. Require the worker
to acknowledge the handoff and its limits. The worker may propose scope or
repository changes but must return them to the coordinator before expanding
writable territory. A missing runtime capability is a concrete blocker, not
permission to start a competing assignment.

Steer or queue follow-ups on the existing assignment. Preserve the original
objective during status requests and asides; admit a tangent only after a
scope decision. Do not start another worker for the same slice. Keep sibling
assignments as a compact status-only roster and do not touch their files.

## Specialists and recovery

The lead may use bounded specialists when useful and permitted by the assignment.
Keep explicit child scope, permissions, source identity, proof, and results tied
to the parent. Use one writer per conflicting slice; the lead owns integration
and final verification. For ACP specialists, resolve the available
`acp-delegation` skill through the catalog and follow its readiness, permission,
and result contracts. ACP is a specialist transport, not a competing coordinator.

Before relying on unattended child writers, verify how their status,
cancellation, and stopped-writer proof work across parent interruption or
failure. Surface missing lifecycle support explicitly; do not assume the parent
runtime tracks or cancels every child. Keep work supervised or read-only when
that lifecycle cannot be proved.

Fallback recovers the same assignment from a harness or model failure;
specialist delegation assigns a bounded subtask. Keep adapter mechanics and
model ladders in runtime configuration, preserve explicit user model choices,
and report actual use or unavailability. Unknown quota is not a blocker or
evidence of savings. No fallback may increase privileges or bypass a gate.

## Recover and accept

Routine authorized recovery, including diagnosis and repair of a technical
failure within existing authority, is autonomous; do not turn that failure
into a human question. Surface `WAITING_FOR_HUMAN` only for a genuine new
authority, scope, product, or approval gate, with the exact decision and
preserve ownership. Never evade a gate by duplicating or reassigning work.
Before replacement, prove the old writer and any conflicting child writers
stopped, inspect partial work, and explicitly transfer ownership within the
same assignment. A timeout or missing output is not stopped-writer proof.
Reuse standing authority instead of manufacturing new gates. Surface a worker's
human ask with its evidence and exact decision; do not redo its blocked work or
reassign it to evade the gate.

Independently inspect the output, changed source, acceptance, and proof.
Record accepted or rejected outcomes, rework, owner interventions, and
supported measurements for later refinement. Keep repository review policy
authoritative and never self-merge. Existing Harness² routing remains
available for a reproducible workflow weakness with measurable acceptance; it
is not a runtime prerequisite. Skill reads and activity are not quality or
savings evidence, and do not trigger automatic skill edits.

Keep full logs and artifacts outside the coordinator context; inspect what
acceptance needs. At handoff or compaction persist decisions, active
job/target/owner, exact source, proof pointers, and next action in the existing
task record. Archive history supplies context, not authoritative live execution
state. Return a bounded digest: state, source/commit/PR/proof, and blocker or
next ask. Stop at the assignment's acceptance criteria; portfolio prioritization
and new programs remain separate decisions.
