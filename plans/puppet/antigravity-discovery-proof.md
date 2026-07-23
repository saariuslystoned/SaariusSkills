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

## Next proof

The open work is the contract-grade harness around the demonstrated
capability: stage-1 static ledger, dedupe, barrier, and timeout tests; a
guarded runner binding a full capability fingerprint with sanitized telemetry
and independent actor observation; an in-session identity-echo check for any
leader-selection claim; and independent app-surface qualification.
