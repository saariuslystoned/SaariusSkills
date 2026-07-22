# Cursor Agent regular-session qualification harness (v0.1)

## Scope and lane contract

- File purpose: planning and static fixture design for Cursor Agent regular-session qualification under
  `codex-goal-regular-qualification.md`.
- Branch in scope: `codex/puppet-regular-cursor-20260722`.
- Objective: map exact Cursor Agent regular-session behavior for the three instruction planes for this
  installed tuple, and define deterministic isolated evidence and source deltas so the lane can later be
  qualified with no transcript bleed.

## 1) Exact-version discovery: facts vs hypotheses

### Facts observed

- Executable discovery by command census:
  - `command -v cursor-agent` -> `/Users/bobbybones/.local/bin/cursor-agent`
  - resolved executable path: `/Users/bobbybones/.local/share/cursor-agent/versions/2026.07.17-3e2a980/cursor-agent`
- Version / help hashes:
  - `cursor-agent --version` -> `2026.07.17-3e2a980`
  - executable SHA-256: `eed61c5224668c9236334c4c68936a16aecc37374b592f59e31eb50433817831`
  - version text SHA-256: `ff67fa8c4d173904e13f0da944d7f763f5399ec48052b81c1ae3c7d87f118f4a`
  - `cursor-agent --help` SHA-256: `bb2aed29e46b3c80635858d2181c140985dbf9f6a96d788f1b6a8adbb0d725af`
- `census_target('cursor', adapter_implementation_fingerprint())` (`protocol_fingerprint: a09805b247b6dcdaad8a7d45e8c29c2c4742c8dcce65283f853953c679590aab`):
  - `permission_flags`: `["--yolo"]`
  - `project_isolation_flags`: `[]` (declared true by zero-agent schema)
  - `sandbox_disable_declared`: `true` (`--sandbox disabled`)
  - `model_flag`: `--model`
  - `session_profiles`: `{"regular": ""}`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - `launch_argv`: `["/Users/bobbybones/.local/share/cursor-agent/versions/2026.07.17-3e2a980/cursor-agent","--yolo","--sandbox","disabled"]`
  - capabilities declared: `launch/send/status/wait/checkpoint/resume/halt` = `declared`
  - manifest state: `doctor_only = true` until qualified
  - `adapter_fingerprint` matches other lanes:
    `dff76b92ab1ecea857a67118424fc9109b5ff2f7066e50f9595bc6c086076d6b`
- `cursor-agent --help` confirms:
  - command format is `agent [options] [command] [prompt...]`
  - notable supported features for this lane: `--yolo`, `--model`, `--resume`, `--continue`,
    `--workspace`, `--add-dir`, `-w/--worktree`, `--worktree-base`, `--list-models`, `generate-rule|rule`
- `cursor-agent models` output first lines:
  - default/current model token is `auto`
  - output includes `gpt-5.6-sol-*`, `claude-*`, `gemini-*`, plus many Cursor/Opus/Sonnet model variants.

### Hypotheses requiring proof

- Default effective model and effort when `--model` is omitted are not proven by static census.
- Exact `--workspace`/`--add-dir` and worktree arguments’ precedence over prompt transport are unproven.
- Whether live resume semantics are usable in regular lane practice is not proven (the protocol allows resume,
  but this lane requires explicit evidence under an isolated fixture).
- Any additive per-run instruction-plane (`--append-system-prompt` equivalent) remains unsupported from current
  help surface and requires live proof.

## 2) Instruction planes for this version

The lane maps three candidate planes to minimize prompt-in-argv risk:

- **Plane 1: session profile plane (declared highest priority candidate)**
  - Activation: `session_profile=regular` in contract; applied via `adapter.envelope(..., initial=True)` as first
    message prefix.
  - Scope: first message only; follow-up send uses unprefixed body.
  - Cleanup: only session/process lease controls; no global file mutation expected when launched with fixture root.

- **Plane 2: workspace/repository addendum plane (hypothesized)**
  - Activation candidates: `--workspace`, `--add-dir`, `-w/--worktree`, `--worktree-base` and/or run-path.
  - Unknowns: precedence and inheritance between worktree setup and workspace roots.
  - Cleanup: lane-owned fixture directories and worktree path only.

- **Plane 3: additive per-run system-instruction plane**
  - Candidate: non-argv alternatives only (no proven equivalent found in current help other than `generate-rule`
    command flow).
  - Current status: unresolved; do not claim until fixture proof exists.

## 3) Default-model observation plan

1. Run isolated fixture with `cursor-agent --list-models` and `cursor-agent models` in bounded env.
2. Launch regular profile with no explicit `--model` and record whether ready-state reveals an explicit resolved
   default.
3. If default remains opaque, pin explicit model for this lane and classify model identity as fixture-bound.

## 4) Regular launch / resume / steer / halt / no-bleed matrix

| Surface | Planned action | Expected evidence | Stop criteria |
| --- | --- | --- | --- |
| Launch | `session_profile=regular` only, YOLO-on + sandbox-off mapping | single launch artifact with deterministic startup settle and active process identity | blocked if process identity drifts vs manifest launch_argv |
| Steer | second `send` on same session, initial=False | exact unprefixed follow-up transport, checkpoint progression | blocked if slash-prefix enforcement breaks or no checkpoint delta |
| Resume | `resume` / `continue` against registered target | exact resume rebind to same session/fixture process identity | hard-stop if resume path is non-reproducible or cross-target |
| Halt | exact halt action | one targeted stop and clean process exit; no collateral mutation | blocked if lingering process remains or collateral stop observed |
| No-bleed control | ordinary and fixture targets parallel | ordinary sessions unchanged outside lane-owned fixture artifacts | blocked if any ordinary process or config outside fixture mutates |

## 5) Isolated fixture strategy

- Use a lane-owned fixture run root under
  `runs/puppet-v01-regular-qualification-20260722/lanes/cursor/` with dedicated
  temporary directories for workspace/worktree experiments.
- Keep all evidence under lane-owned fixture and run roots.
- Avoid touching `~/.cursor`, `~/.local/share/cursor-agent` user-default config outside fixture scope unless
  explicitly approved.
- Re-run all cursors probes when executable, manifest hash, or help hash changes.

## 6) Required Puppet source deltas for this lane

- `skills/puppet/scripts/puppet_lib/census.py`
  - keep cursor-specific `--yolo`, `--sandbox`, and `--model` mapping as explicit provenance for this tuple.
- `skills/puppet/scripts/puppet_lib/probe.py`
  - record and verify explicit default-model observation (or mark as `model_unknown`) for Cursor with regular profile.
- `skills/puppet/scripts/puppet_lib/adapter_manifest.py` / `tests/test_puppet_probe.py`
  - require resume evidence before marking resume as `controller_verified` for cursor live claims.
- Tests:
  - add explicit cursor fixture assertions for resume/no-bleed behavior under worktree/workspace planes.

## 7) Blockers and stop criteria

- Hard blockers:
  - Any default-model ambiguity that affects deterministic regular-session guarantees.
  - No proven isolated resume behavior under this exact executable/version tuple.
  - No proven non-bleed enforcement across fixture vs ordinary sessions.
  - Any source command or fixture operation that writes prompt-bearing values into argv.
- Stop criteria:
  - Keep this lane `mapping` until regular-profile launch/steer/halt and no-bleed are proven by fixture proof.
  - Defer or downgrade resume if it cannot be proven exact for this tuple.
