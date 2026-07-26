# SaariusSkills issue #15 Phase 1 proof

schema: smoky.swarm.route_terminal_proof.v1
result: failed
route_id: route_20260726_004123_40146_saariusskills-custom-agent-qualification
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: 12bd40ccac16d113e1efdfbfd3cc1c28151eff75
run_id: saariusskills-issue15-phase1-20260726

## Scope

This packet qualifies ordinary workspace-local Antigravity custom-agent
discovery and exact identity selection. PR #6 is historical research only.
`/teamwork-preview`, fan-out, Puppet transport, product mutation, merge,
deployment, publishing, auth changes, global agent installation, and foreign
session inspection are outside this phase.

## Result

- C1 fixture integrity passed before and after execution.
- C2 discovery passed when the workspace was bound explicitly with
  `--add-dir`; the cwd-only control found none of the four fixtures.
- The selected recon profile produced an exact identity artifact and the
  controller verifier passed it.
- C3 nevertheless failed: the workspace hook produced no event file, so tool
  gating, invocation count, fully-idle state, and independent active-profile
  metadata were not proven.
- C4–C8 were not run after that fail-closed result.
- The exact owned tmux session and raw CLI log were cleaned. The disposable
  workspace is preserved for bounded observer diagnosis. No foreign session
  was inspected, resumed, signaled, or cleaned.

## Evidence

- `capability-fingerprint.json`
- `materialization.json`
- `discovery-cwd.json`
- `discovery-explicit-workspace.json`
- `positive-recon-verification.json`
- `positive-recon-log-sanitized.json`
- `attempt-01-runtime.json`
- `fixture-postflight.json`
- `behavior-report.json`

## Commands

- `agy agents` through the allowlist inventory filter: exit `2`
- `agy --add-dir <workspace> agents` through the same filter: exit `0`
- fresh tmux TUI with exact `--agent`, `--model`, `--effort`, `--sandbox`,
  `--add-dir`, and `--log-file`: started and exact identity result appeared
- result verifier: exit `0`
- sanitized log probe: exit `0`, with no allowlisted metadata match
- exact-owned tmux teardown and raw-log removal: exit `0`

## Next route

Revise the observer packaging against the CLI-specific workspace plugin
surface or an absolute hook command, freeze a new exact head and fingerprint,
and rerun C1–C3. Do not admit C4–C8 or Phase 2 until event and active-profile
evidence is present.
