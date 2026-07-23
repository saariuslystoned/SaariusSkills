# Antigravity teamwork: discovery and live smoke-probe proof packet

Status: stage-2 discovery findings recorded; live CLI fanout demonstrated at
smoke grade through nested 4x4; contract-grade calibration and app surface
still open

Date: 2026-07-23

## Scope and verdict

This packet records two proof campaigns for the
[hierarchical Antigravity teamwork plan](antigravity-teamwork.md), both run on
AGY CLI `1.1.5` from a disposable workspace outside the repository, under the
operator's isolation posture: unrelated operator AGY sessions were active
throughout and were never inspected, resumed, signaled, or cleaned up; every
probe launched a fresh session; no global configuration or global custom-agent
directory was written.

Verdicts:

1. **Discovery (read-only):** workspace `.agents/agents/<name>/agent.md`
   profiles are not listed by the pre-session inventory command, and
   `--agent` with an unknown name silently falls back to the default agent.
2. **Live fanout (smoke):** dynamic subagent definition, direct 2-leaf
   fanout, nested 2x2 with a contained forced-failure retry, and nested 4x4
   (4 leaders, 16 leaves, 20 helpers, 21 actors) all completed cleanly, the
   4x4 twice with identical results.

## Isolation posture

Adopted by operator decision on 2026-07-23 and recorded in the plan's
concurrency-posture section: concurrent operator AGY sessions are a normal
operating state and are not a launch blocker. Every probe here satisfied the
isolation contract — fresh sessions only, no `--continue` or foreign
conversation IDs, no process enumeration or cleanup by name or pattern, all
activity scoped to the disposable workspace.

## Capability tuple observed

| Item | Observation |
|---|---|
| AGY CLI | `1.1.5` |
| Model used for all live probes | `gemini-3.6-flash-low` |
| Prompt transport | non-interactive print mode with explicit print timeout |
| Permission posture | default (no skip-permissions flag, no sandbox flag) |
| Persistent custom-agent inventory (repo root and workspace) | no entries returned |
| Concurrent unrelated AGY session present | yes, boolean presence only |

## Discovery findings (read-only)

The four leader profiles were authored in the vendor-documented workspace
layout with `name` and `description` frontmatter and instruction bodies
transcribed from the plan's leader contracts. Exact copies are preserved as
repository fixtures:

| Fixture | SHA-256 |
|---|---|
| `fixtures/antigravity-teamwork/agents/recon-leader/agent.md` | `30fb822e332500e09dbbd96f96be2116d7873714e45be0b54b32930e7776a285` |
| `fixtures/antigravity-teamwork/agents/implementation-leader/agent.md` | `66bb39c39470a2112375faf2ff7b565f1aa7547f3b76059a65ccffa56a55ab79` |
| `fixtures/antigravity-teamwork/agents/verification-leader/agent.md` | `856e3d504a1131bb6c44eb85d22a818c9c9dfb0ce5a5f950a7f9d7438ba9a918` |
| `fixtures/antigravity-teamwork/agents/proof-leader/agent.md` | `4f66a5a1b25707bf0daefa070d19fa871ef36c65ae747d9e8286cd383827c439` |

Findings:

1. The `agents` inventory command returned an empty list from the repository
   root (negative control), from the workspace containing all four profiles,
   and after the workspace became a git repository. Workspace profiles are
   invisible to the pre-session inventory surface.
2. A print-mode session launched with `--agent recon-leader` answered as the
   default `Antigravity` agent, and a control launch with a deliberately
   nonexistent agent name did the same with no error. Unknown `--agent`
   values fall back silently. Any future leader-selection qualification must
   therefore include an in-session identity echo; launch success proves
   nothing about selection.
3. The workspace `agent.md` schema carries only `name` and `description` — no
   capability booleans. Leader/leaf capability restrictions cannot be
   declared in workspace profiles, which strengthens the plan's decision to
   qualify dynamic definitions first.

## Live smoke probes

All probes ran the same day on the same tuple, sequentially, each in a fresh
print-mode session from the disposable workspace. Challenge tokens were
authored by the controller; expected and received values matched exactly in
every clean run.

| Probe | Topology | Result |
|---|---|---|
| Direct fanout | root + 2 dynamic leaves | both tokens relayed exactly in one final line |
| Nested 2x2, clean | root + 2 leaders + 4 leaves (6 helpers) | all 4 tokens relayed in order; leaders completed out of order and the root joined correctly |
| Nested 2x2, forced failure | as above, one leaf deliberately returning a schema-invalid token | the owning leader detected the invalid token, retried exactly once, and reported `retries=1`; the failure never left that leader's aggregate; final relay and retry audit both correct |
| Nested 4x4, pass 1 | root + 4 leaders + 16 leaves (20 helpers, 21 actors) | all 16 tokens relayed in specified order; actor audit `leaders=4 leaves=16 helpers=20 actors-including-root=21`; anomaly audit `none` |
| Nested 4x4, pass 2 | identical rerun | identical clean result |

The 4x4 leaders used the plan's four leader names (recon, implementation,
verification, proof) as dynamic definitions with subagent capability and no
write or MCP access; all leaves were defined with no write, MCP, or subagent
capability, per the calibration profile.

## Limitations and non-claims

- **Smoke grade, not contract grade.** Relay lines, actor audits, and anomaly
  audits are root-reported. No external ledger, independent actor-count
  observation, sanitized lifecycle telemetry, or capability fingerprint bound
  these runs. Because the root's prompt contained the expected tokens, token
  relay alone cannot exclude a degenerate root fabricating results without
  spawning; interim progress messages are consistent with real spawning but
  are not proof. Contract-grade calibration must add external observation.
- Capability-restriction requests (no write/MCP for leaders, none of the
  three for leaves) were instructions to the root; their enforcement was not
  independently verified.
- No claim about `/teamwork-preview` leader selection, workspace-profile
  selection, the desktop app surface, or sustained load beyond these
  single-shot probes. App qualification inherits nothing from these results.
- Credit accounting, timeout behavior under contention, and cleanup
  verification were not exercised beyond normal session completion.

## Second probe campaign (2026-07-23, session 2)

A follow-up campaign targeted the smoke-grade limitations, using the same
disposable workspace and isolation posture, with per-session `--log-file`
harness logs retained in the disposable workspace (event kinds, boolean
outcomes, and opaque conversation IDs only are quoted here).

### Harness-log and permission findings

- Default CLI permission mode is `request-review`, and headless print mode
  **soft-denies every tool confirmation** (`Print mode: soft-denying tool
  confirmation`). Leaf tasks that need tools therefore silently no-op in
  print mode unless permissions are pre-authorized for the session. A
  real-work 4x4 (leaves reading seeded nonce files) failed closed on exactly
  this before any model output.
- Subagent conversations surface in the harness log as **distinct
  conversation IDs on tool-confirmation events**; tool-less token-relay runs
  log only the root conversation. Independent actor-count observation is
  therefore possible, but only for tool-using hierarchies.

### Capability-enforcement probe (leaf write and spawn attempts)

One leader, two leaves, on `claude-opus-4-6-thinking`, default permissions.
Filesystem ground truth: the attempted `seed/violation.txt` was never
created. The harness log shows why, and the why matters:

- a leaf defined "without write capability" **still held a run-command
  (shell) tool**; the write attempt was stopped by the permission layer
  (`approved=false`), not by the capability declaration; and
- the leaf's dedicated file-write surface is an artifact store confined to
  the conversation's own private directory; a workspace-relative write was
  rejected as an invalid artifact path.

Consequence adopted into the plan: dynamic capability booleans do not remove
shell access, so under skip-permissions (YOLO) a nominally read-only leaf
could write via shell. Calibration read-only guarantees must come from
disposable-workspace/worktree isolation and post-run no-bleed checks, never
from capability declarations alone.

### Model-diversity 4x4

The identical 4x4 token-relay probe on `claude-sonnet-4-6` passed cleanly —
all 16 tokens in order, correct actor audit, `anomaly-audit: none` — with
per-leader message IDs and idle lifecycle notifications visible. Combined
with the two Gemini flash passes, hierarchical fanout is demonstrated on two
distinct model families through the same harness, so the capability is
attributable to the harness rather than one model.

### Stage-1 static contract harness

`puppet_lib/teamwork.py` and `tests/test_teamwork.py` implement the plan's
stage-1 deterministic contract: the exact leaf-ledger field set; the three
independent state dimensions with enforced transitions; the logical dedupe
key excluding physical attempts; single-retry and single-accepted-attempt
rules; aggregate `max_helpers` with only the canonical 3/6/20 values and
subordinate cap/telemetry checks; the seven-condition completion barrier
returning machine-readable unmet-condition enums; and an
allowlist-sanitized summary that provably rejects free-text payloads. The
full repository suite passes (80 tests: 30 pre-existing, 50 new), and
hostile paths were independently re-verified outside the test suite.

### Real-work 4x4 (ground-truth nonce harvest)

With the operator's explicit standing authorization for per-session
auto-approval, the real-work 4x4 ran once: sixteen seeded files, each
holding a controller-generated nonce recorded before any AGY session
existed; each leaf assigned exactly one file to read; the root instructed
never to read seed files itself. Outcome — the single most informative run
of the campaign:

| Leader | Result against controller ground truth |
|---|---|
| proof | 3 of 4 nonces exact matches; one leaf reported `NOT_FOUND` for a file that exists |
| implementation | 3 of 4 exact matches; one `NOT_FOUND` |
| verification | **all four returned values fabricated** — well-formed, wrong length, matching nothing |
| recon | never reported; the root hit the external print timeout and the session exited nonzero with an incomplete hierarchy join |

Harness-log corroboration for the same run: **12 distinct conversation IDs**
performed approved tool calls (9 file views, 3 searches, 1 directory
listing). Six leaf results matching pre-recorded nonces plus
harness-approved read events across 12 conversations establishes that real
distributed file work occurred — the fabrication caveat no longer applies to
the demonstration of genuine hierarchical delegation.

Findings this run adds:

1. **Fabrication is a live failure mode, not a theoretical one.** One leader
   returned four plausible, correctly-formatted, entirely invented values.
   Aggregate output that "looks right" is worthless without controller-held
   ground truth or result-digest validation; the plan's ledger validation
   and acceptance rules are confirmed necessary by direct observation.
2. **Leaf file resolution is unreliable.** Two leaves reported `NOT_FOUND`
   for existing workspace files, consistent with the enforcement probe's
   observation that subagent relative paths can resolve against a
   CLI-private directory rather than the workspace. Leaf task contracts
   must carry absolute-within-workspace path anchoring.
3. **Incomplete joins happen.** A leader can hang past the deadline; the
   external wall-clock timeout fired exactly as the plan requires, and the
   session's own exit did not represent a completed hierarchy — validating
   the plan's rule that a target-side exit never proves a complete join.
4. **Reliable 4x4 under real tool load is NOT yet demonstrated.** Token
   relay passed 4x4 three times across two model families, but the first
   tool-using 4x4 delivered 6 verified results out of 16. Real-workload
   capacity claims remain unearned pending repeat runs under the
   contract-grade harness.

## Next proof

Remaining open work: repeat real-work 4x4 runs under the stage-1 ledger with
result-digest validation and per-leaf path anchoring, to separate transient
failures from structural limits; a guarded runner binding a full capability
fingerprint with sanitized telemetry and log-derived actor observation; an
in-session identity-echo check for any leader-selection claim; and
independent app-surface qualification.
