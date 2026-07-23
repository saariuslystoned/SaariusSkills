# Puppet plan: hierarchical Antigravity teamwork

Status: proposed experimental capability; static investigation complete, live
fanout qualification blocked

Date: 2026-07-22

## Decision

Puppet should own hierarchical Google Antigravity teamwork as a separately
qualified experimental command profile. It must not enter Puppet's regular
baseline merely because the installed harness exposes `/teamwork-preview` or
custom-agent commands.

Antigravity documents persistent custom CLI agents, conversation-scoped dynamic
subagent definitions, nested subagents, task management, inter-agent messaging,
and result relay. That makes four specialized leaders with four leaves each
architecturally plausible. It does not prove that one installed CLI or app can
reliably sustain the resulting 20 helpers. Puppet must earn that claim through
version-bound live proof.

The durable authority boundary is:

```text
controller_parent (Puppet/Codex; supervises, reviews, and accepts)
└── agy_root (target parent and sole candidate integration writer)
    ├── reconnaissance leader ── up to four leaves
    ├── implementation leader ── up to four leaves
    ├── verification leader ──── up to four leaves
    └── proof leader ─────────── up to four leaves
```

Four leaders plus sixteen leaves equals 20 helpers, or 21 actors including the
AGY root. The controller parent remains outside that helper count and is the
only acceptance and promotion authority. Under Puppet v0.1's
`mutation_owner: target` contract, the AGY root is the sole target-side
integration writer whenever mutation is authorized; the controller does not
edit the target source slice.

## Evidence and non-claims

### Locally observed static evidence

The investigation observed this capability tuple without reading prompts,
transcripts, process arguments or environments, authentication material, or
conversation stores:

| Item | Observation |
|---|---|
| AGY CLI | `1.1.5` |
| Antigravity desktop app | `2.3.1` |
| Antigravity IDE companion | `2.1.1` |
| Persistent custom-agent inventory | no entries returned |
| Python Antigravity SDK runtime | not installed |
| Guarded teamwork runner | refused launch while another AGY process was active |
| Workspace-profile inventory visibility (2026-07-23) | four well-formed workspace profiles not listed by the pre-session inventory command; see [discovery proof](antigravity-discovery-proof.md) |

An empty persistent-agent inventory does not prevent dynamic custom subagents.
It does mean that workspace-profile discovery and `/teamwork-preview` leader
selection remain unproved.

### Documented behavior

Vendor documentation describes:

- custom CLI agents and agent selection;
- dynamic subagent definition with separate write, MCP, and subagent-tool
  capabilities;
- direct and nested invocation, lifecycle management, and messages;
- nested subagents up to a maximum depth of ten;
- child results returning to their parent and nested updates relayed toward the
  root;
- tasks and scheduling;
- Stop hooks with a `fullyIdle` field; and
- `/teamwork-preview` as an Ultra preview.

Sources: [CLI custom agents](https://antigravity.google/docs/cli/commands/agents),
[subagent hierarchy and lifecycle](https://antigravity.google/docs/subagents),
[hooks](https://antigravity.google/docs/hooks),
[plans and credits](https://antigravity.google/docs/plans), and the distinct
[SDK overview](https://antigravity.google/docs/sdk-overview).

### Experiment disposition

The planned disposable experiment began with a guarded 2x2 preflight. The
runner found a pre-existing AGY process and failed closed before submitting a
prompt or spending experiment quota. It did not bypass, inspect, interrupt,
reuse, or clean up that process.

Because the 2x2 calibration did not start, the 4x4 stage was not attempted.
This was a safety pass under the original exclusivity guard, not evidence that
nested fanout is unsupported.

### Concurrency posture: isolation, not exclusivity (operator decision, 2026-07-23)

The operator runs multiple concurrent AGY sessions on this machine as a normal
operating state. A pre-existing AGY session is therefore no longer a launch
blocker. The exclusivity guard is replaced by an isolation contract that every
live probe and calibration must satisfy:

- launch only fresh sessions from a disposable workspace; never pass
  `--continue` or resume a conversation ID the experiment did not create;
- never enumerate, inspect, signal, or clean up AGY processes by name,
  pattern, or process group; track and manage only the process and
  conversation IDs the experiment itself spawned;
- keep prompts, agents, and any writes scoped to the disposable workspace;
  never write global configuration or the global custom-agent directory; and
- treat resource contention with concurrent sessions (slow spawns, queued
  helpers, quota pressure) as recordable telemetry, not as license to touch
  the other sessions.

The current accepted claims are therefore:

- custom and nested agents are documented capabilities;
- the proposed topology fits the documented depth limit;
- no concurrent-helper maximum is published;
- CLI direct fanout, nested 2x2 fanout with a contained forced-failure retry,
  and nested 4x4 fanout (20 helpers, 21 actors) are live-demonstrated on CLI
  `1.1.5` via token-relay smoke probes run concurrently with unrelated
  operator AGY sessions (2026-07-23; see the
  [discovery and live-probe proof](antigravity-discovery-proof.md));
- those smoke probes rely on root-reported relay output and are not yet
  contract-grade: no external ledger, capability fingerprint, sanitized
  telemetry, or independent actor-count observation bound them;
- the same 4x4 also passed on `claude-sonnet-4-6`, so the capability is
  harness-level rather than specific to one model family;
- dynamic capability booleans do not strip shell tools from leaves: a
  no-write leaf's write attempt was stopped by the permission layer and the
  conversation-private artifact store, not the capability declaration, so
  read-only guarantees require workspace isolation (see the proof packet's
  second campaign);
- headless print mode soft-denies all tool confirmations under the default
  `request-review` permission mode, and subagent conversations are
  log-observable only on tool-confirmation events;
- the stage-1 static contract is implemented and passing
  (`puppet_lib/teamwork.py`, `tests/test_teamwork.py`);
- one authorized real-work 4x4 proved genuine distributed file reads (six
  leaf results matched controller-held ground truth, with 12 log-observed
  tool-using conversations) while also observing live fabrication by one
  leader, two false `NOT_FOUND` results, and one leader hang ending in an
  incomplete join — so real-workload 4x4 reliability remains unearned even
  though token-relay 4x4 passed three times;
- workspace-profile discovery and `--agent` selection remain unproved, and the
  CLI silently falls back to the default agent on an unknown `--agent` name;
- app direct and nested fanout remain independently live-unverified; and
- reliable, contract-grade 4x4 operation is demonstrated but not yet an
  accepted qualification claim.

## Capability matrix

| Surface | Direct helpers | Nested helpers | Custom leaders | Root relay | 2x2 proven | 4x4 proven |
|---|---|---|---|---|---|---|
| CLI 1.1.5 | live-demonstrated (2 dynamic leaves, token relay) | live-demonstrated at depth 2 (2x2 and 4x4 smoke probes) | dynamic definitions live-demonstrated; workspace profiles undiscovered pre-session and `--agent` falls back silently | live-demonstrated (aggregates and 16-token relay) | smoke: yes (clean + forced-failure retry); contract-grade: no | smoke: yes, two identical clean passes; contract-grade: no |
| App 2.3.1 | shared-harness documentation only | shared documentation only | dynamic behavior documented; app selection not run | shared documentation only | no | no |
| Python SDK | documented as a separate programmatic surface | not locally tested | declarative configuration documented | telemetry/lifecycle documented | runtime absent | runtime absent |

CLI and app proof must remain separate even where they share harness
documentation. SDK documentation is design input only; the initial Puppet
implementation should not depend on a locally absent runtime.

## Custom-agent strategy

Qualify dynamic custom definitions first. They expose explicit capability
booleans and avoid mutating live global configuration. During calibration:

- leaders receive subagent tools but no write or MCP capability;
- leaves receive no write, MCP, or subagent capability;
- every definition is scoped to the disposable conversation; and
- the AGY root may schedule and aggregate but may not accept or integrate.

Workspace profiles under `.agents/agents/<name>/agent.md` are a second,
independent qualification path. If proven, Puppet may materialize hash-bound
profiles create-only into a disposable workspace. It must not write the global
custom-agent directory by default. Persistent-profile discovery does not prove
that `/teamwork-preview` will choose those profiles as its four leaders.

## Leader contracts

### 1. Reconnaissance and decomposition

Responsibility: read the applicable repository authority, map source, test,
proof, and dependency boundaries, and propose a disjoint task graph.

Leaf schema: one bounded source or contract question, read-only, with exact
source identity, allowlisted scope, expected artifact schema, and timeout.

Completion: every proposed task names dependencies, risk, evidence references,
allowed mode, and an overlap decision.

Escalation: ambiguous authority, shared-source overlap, secrets or auth
boundaries, or required material outside the admitted project returns to the
controller parent.

### 2. Implementation design

Responsibility: turn admitted tasks into one coherent patch and test plan for
the single integration mutation owner.

Leaf schema: focused patch design, test design, migration analysis, or
read-only implementation review over a disjoint slice.

Completion: ordered patch plan, path manifest, affected-test plan, conflict
analysis, and unresolved risks. When mutation is authorized, the AGY root
applies and integrates the candidate change under the target's single writer
lease.

Escalation: a second writer request, shared-core collision, scope expansion,
hard gate, or repeated repair returns to the controller parent.

### 3. Verification and adversarial review

Responsibility: independently search for hidden failures and validate behavior
against the accepted clauses.

Leaf schema: deterministic checks, boundary or invalid inputs, concurrency and
failure-containment probes, or exact-head review. Leaves remain read-only.

Completion: findings are classified as `required_fix`,
`reject_false_positive`, `defer`, or `human_gate`, with bounded evidence and
residual risk.

Escalation: head drift, an untestable claim, transcript dependence, or two
repair cycles stops the hierarchy for controller adjudication.

### 4. Proof and integration preparation

Responsibility: reconcile the task ledger, artifact hashes, source identity,
cleanup evidence, acceptance clauses, and promotion readiness.

Leaf schema: proof-index validation, sanitized telemetry audit, cleanup and
no-bleed audit, or acceptance-matrix audit.

Completion: one aggregate packet names the exact candidate identity when
applicable, terminal and accounted counts, missing evidence, gates, and a
recommendation. It is not an acceptance verdict.

Escalation: missing or duplicate tasks, ambiguous cleanup, nonterminal helpers,
stale source identity, or unsupported capability blocks controller acceptance.

## Leaf task ledger

Every admitted leader and leaf is represented by a bounded record:

```text
experiment_id
capability_fingerprint
task_id
parent_task_id
leader_role
leaf_role
exact_source_head
scope_digest
allowed_mode
allowed_paths
mutation_lease_id | null
input_digest
expected_artifact_schema
timeout_budget
credit_budget_class
attempt
physical_attempt_id
dedupe_key
retry_of | null
state
result_ref | null
result_digest | null
relay_received_at | null
error_class | null
terminal_at | null
cleanup_state
```

Identifiers are opaque and bounded. Paths and result references are
allowlisted and repository-relative. Error classes are enums, never raw error
payloads. Low-entropy values use a run-scoped, domain-separated keyed digest.

Execution, accounting, and decision are separate state dimensions so a failure
does not imply that a result existed:

```text
execution:  proposed -> admitted -> dispatched -> running
                                           -> result_ready
                                           -> blocked | timed_out | killed
accounting: unaccounted -> leader_accounted -> parent_accounted
decision:   pending -> accepted | rejected | deferred
```

Only `result_ready` work can be validated and accepted. Failed execution is
still leader- and parent-accounted without inventing a result reference.

The stable logical dedupe key binds the experiment, capability fingerprint,
leader, leaf scope, exact source head, and contract hash; it does not include a
physical attempt. Every retry receives a new physical attempt ID and ordinal
while retaining that logical result key. Only one physical attempt may supply
the accepted logical result.

## Mutation authority

Calibration uses `mutation_lease=none`. The AGY root, all leaders, and all
leaves operate in `observe` or `suggest` mode.

A later, separately qualified implementation profile preserves Puppet v0.1's
`mutation_owner: target` contract and may grant the AGY root one candidate-
writer lease in the target's isolated worktree. Leaders and leaves remain
read-only; the AGY root integrates and returns one exact candidate commit; and
the controller parent alone reviews and accepts it. Controller-side source
editing remains unsupported. Any future `mutation_owner: controller` mode is a
post-v0.1 extension requiring its own explicit contract and qualification.

High fanout must never create sixteen writers against one source slice.

## Relay and parent completion barrier

Leaves send bounded results to their assigned leader. Each leader validates and
deduplicates its leaf results, then sends one aggregate packet to the AGY root.
Cross-leader messages are advisory and cannot satisfy the root barrier.

The AGY root may publish `hierarchy_complete` only when:

1. every admitted ledger row is terminal and parent-accounted;
2. every required result reference and digest validates;
3. active leader, leaf, and owned-task counts are zero;
4. an independently qualified, controller-owned, immutable and hash-bound Stop
   hook outside the target-writable slice reports `fullyIdle=true`, or the
   controller proves the equivalent from its authoritative ledger and exact
   owned-task inventory;
5. the calibration has no mutation lease, or a candidate-writer lease is
   closed;
6. fixture and source identity remain stable; and
7. exact cleanup and no-bleed checks pass.

The controller parent may accept only after independently validating that
packet, reviewing the exact candidate when applicable, and confirming the same
barrier and cleanup evidence. A helper result, leader aggregate, root beacon,
hook event, or `hierarchy_complete` claim is never controller acceptance.

An optional controller-owned Stop hook may return `continue` while
`fullyIdle=false`, but only when its immutable content and installation path
are fingerprinted outside any target-writable slice, with an absolute deadline
and at most three continuations. At the bound it records
`completion_barrier_timeout` and fails closed. A mutable workspace hook or any
unqualified hook is advisory only and cannot satisfy completion. The
controller ledger and exact owned-task inventory remain authoritative.

## Concurrency, credit, timeout, and failure controls

- Begin with two leaders and two leaves per leader at depth two below the AGY
  root, despite the documented depth-ten maximum.
- Preserve Puppet's contract `max_helpers` as the aggregate hard cap. The
  existing default of three admits neither experiment: 2x2 requires an explicit
  campaign/profile override to `max_helpers=6`, and 4x4 requires a later
  explicit override to `max_helpers=20`.
- Track `max_leaders`, `max_leaves_per_leader`, `max_total_helpers`,
  `max_simultaneous_leaves`, and observed `peak_active_helpers` as subordinate
  constraints and telemetry; none may exceed `max_helpers`.
- Treat 4x4 as 20 helpers and 21 AGY actors including the root. Never report 16
  leaves as the total actor count.
- Use an external wall-clock timeout plus per-leaf and per-leader budgets. A
  target's own timeout or top-level process exit does not prove a complete
  hierarchy join.
- Use a baseline-only credit class initially. Do not change account overage
  settings. Stop on an authoritative failed model request or quota response;
  an advisory “out of credits” footer alone is not terminal truth.
- Permit at most one retry per leaf. Reconcile all of a leader's leaves before
  retrying that leader. Never retry the whole hierarchy automatically.
- Contain a leaf failure to its leader aggregate. A leader failure blocks
  parent acceptance but does not cancel independent leaders unless shared
  source identity or a writer lease is affected.
- Cancel and clean up exact owned subagent and task IDs only. Never use broad
  process names, patterns, or process groups that could include pre-existing
  work.
- If cleanup identity is ambiguous, emit a reaper handoff and stop rather than
  guessing.

Every live preflight must also prove Puppet's existing unrestricted-execution
contract: deliberate standing authorization in local uncommitted policy, an
exact executable fingerprint mapped to verified auto-approval behavior, and a
verified disabled-or-absent harness sandbox. Unknown, partial, or drifted
mappings fail closed. The capability fingerprint binds those observations,
the teamwork profile and helper override, adapter and probe protocol, agent
catalog, and prompt-transport method.

## Sanitized telemetry

The controller may retain:

- capability fingerprint and experiment ID;
- opaque conversation, leader, leaf, and task IDs;
- created, admitted, running, peak-active, terminal, accounted, and cleaned
  counts;
- lifecycle event kind and allowlisted tool name;
- step number, bounded timestamps, boolean error state, termination reason
  enum, and `fullyIdle`;
- result references and digests; and
- retry, timeout, credit, cleanup, and final disposition enums.

It must not retain prompts, messages, transcripts, pane output, screenshots,
tool arguments, raw errors, process arguments or environments, auth logs,
cookies, credentials, or source and artifact contents. Telemetry loss is a
proof limitation, not permission to inspect a transcript.

## Proposed Puppet changes after qualification review

### Skill and references

- Add `skills/puppet/references/antigravity-teamwork.md` with the qualified
  command lifecycle, topology, leader contracts, ledger, barrier, limits, and
  capability matrix.
- Add `templates/instructions/lifecycle/teamwork-preview.md`; keep the regular
  instruction lifecycle unchanged.
- If workspace profiles qualify, add hash-bound templates under
  `templates/agents/agy/<leader>/agent.md` and materialize them create-only into
  disposable workspaces.
- Keep `SKILL.md` limited to routing, required qualification, and hard stops.

### Runtime and scripts

- Add a `teamwork` contract object that preserves the aggregate `max_helpers`
  cap and adds topology, depth, simultaneous-helper, observed-peak, writer-
  lease, retry, timeout, credit, and capability-proof fields.
- Add `puppet_lib/teamwork.py` for ledger transitions, dedupe, relay accounting,
  completion barriers, and sanitized summaries.
- Extend beacon and handoff schemas with topology counts, terminal/accounted
  counts, bounded result references and digests, and explicit unavailable
  markers.
- Extend the adapter lab with separate CLI and app `teamwork-preview` profiles.
  Bind qualification to executable or app identity, command lifecycle, agent
  catalog, protocol, topology, relay, barrier, timeout, credit policy, and
  cleanup fingerprints. Doctor must also verify the local unrestricted
  authorization, exact-version auto-approval mapping, sandbox-disabled-or-
  absent state, non-argv prompt transport, and explicit aggregate helper cap.
- Add a privacy-safe experiment runner that does not create prompt or pane
  logs, owns an external timeout, inventories exact owned IDs, and emits a
  cleanup handoff rather than killing ambiguous work.

## Minimal repository contract

Do not add or expand a repository `AGENTS.md` for this proposal. Numeric limits,
leader taxonomy, vendor behavior, telemetry schemas, and cleanup mechanics
belong in Puppet references and scripts.

Only after live qualification proves that the invariant is durable and
repo-wide should a contract add this one sentence:

> Hierarchical helpers remain subordinate to one target parent; only that
> target parent integrates, while Puppet alone reviews and accepts, and helper
> completion is never acceptance.

## Staged adoption and keep/reject gates

1. **Static contract.** Implement deterministic ledger, dedupe, barrier,
   timeout, and hostile-input tests. Keep only if no path requires transcript or
   payload storage and every mutation lease is exclusive.
2. **Discovery.** In a disposable workspace, prove dynamic definitions and,
   separately, workspace `agent.md` discovery, selection, no-bleed, and
   rollback. Keep only the mechanisms the harness actually selects.
3. **CLI 2x2.** Run once clean and once with a forced leaf failure and retry.
   Launch only with deliberate local unrestricted authorization, a proved
   exact-version auto-approval and sandbox-disabled-or-absent mapping, and an
   explicit campaign/profile `max_helpers=6` override. Keep only if exact
   topology, relay, joins, timeouts, accounting, and cleanup pass twice on the
   same complete capability fingerprint.
4. **CLI 4x4.** Attempt only after stage 3. Record four leaders, sixteen leaves,
   20 total helpers, observed peak-active helpers, and maximum simultaneous
   leaves. Require a distinct explicit `max_helpers=20` campaign/profile
   override and revalidate the unrestricted/sandbox mapping. Keep only what is
   observed, terminal, relayed, deduplicated, and cleaned without credit or
   timeout ambiguity.
5. **App 2x2 then 4x4.** Repeat independently in a disposable app project. Do
   not inherit CLI proof, unrestricted-execution authorization, sandbox state,
   or helper-cap overrides.
6. **Experimental Puppet profile.** Enable only for an exact qualified tuple;
   leave the regular baseline unchanged.
7. **Promotion review.** Require exact-head independent review, a two-cycle
   repair cap, and controller acceptance. Reject default enablement after any
   executable, app, protocol, profile, or source-identity drift until reproof.

## Acceptance decision

Keep this design as an experimental Puppet plan. Reject default enablement and
global custom-agent installation until the staged proof completes at contract
grade. Live capability is no longer the open question: on 2026-07-23, under
the isolation posture, CLI `1.1.5` demonstrated direct fanout, nested 2x2 with
a contained forced-failure retry, and two identical clean nested 4x4 passes
(20 helpers, 21 actors) concurrently with unrelated operator AGY sessions.

What remains before an experimental Puppet profile is the contract-grade
harness around that demonstrated capability: the stage-1 static ledger,
dedupe, barrier, and timeout tests; a guarded runner that binds a full
capability fingerprint; sanitized telemetry with independent actor-count
observation rather than root self-report; and the app-surface qualification,
which inherits nothing from these CLI results.
