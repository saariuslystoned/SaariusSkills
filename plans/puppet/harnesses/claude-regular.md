# Claude Code regular-session qualification harness (v0.1)

Scope: static command census, source/test inspection, and no-live-lane planning under
`plans/puppet/codex-goal-regular-qualification.md`. No live launch is performed in this lane.

## 1) Exact-version discovery: facts vs hypotheses

### Facts (from read-only census + source/tests)

- Executable command chain:
  - `command -v claude` -> `/opt/homebrew/bin/claude`
  - resolved binary: `/opt/homebrew/Caskroom/claude-code@latest/2.1.215/claude`
  - executable SHA-256: `90608b5c5ab504e96e77365cea6203d046e291d59b2bb42cf28dcb2ccdf9dd58`
- Version / help:
  - `claude --version` -> `2.1.215 (Claude Code)`
  - version payload SHA-256: `3c95eff850dac10d40c5692a73957f526b54a74767163913dc858c4f8d4c8c63`
  - `claude --help` SHA-256: `fcd5b45507c7c602d54d85a300eab288a8a3c6770c6def696ca19a3100725de4`
- `census_target('claude', adapter_implementation_fingerprint())`:
  - permission flag: `--dangerously-skip-permissions`
  - model flag: `--model`
  - effort flag: `--effort`
  - `project_isolation_flags`: `[]` (declared by help parse as `true`)
  - `sandbox_disable_declared`: `true` (help text has no positive `--sandbox`)
  - `prompt_transport`: `interactive_tmux_load_buffer_stdin_declared`
  - `session_profiles`: `{regular: "", loop: "/loop", goal: "/goal"}`
  - `launch_argv`: `["/opt/homebrew/Caskroom/claude-code@latest/2.1.215/claude", "--dangerously-skip-permissions"]`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - manifest caps are declared for launch/send/status/wait/checkpoint/resume/halt; manifest is initially `doctor_only`
  - adapter fingerprint: `dff76b92ab1ecea857a67118424fc9109b5ff2f7066e50f9595bc6c086076d6b`
  - protocol fingerprint: `a09805b247b6dcdaad8a7d45e8c29c2c4742c8dcce65283f853953c679590aab`
- `profiles.py` defaults:
  - `default_session_profile("claude") == "regular"`.
- `adapters.py` confirms first-launch profile-prefixing only:
  - initial message may be prefixed with `/loop` or `/goal`
  - follow-up messages are rejected if user provides slash commands and are sent unprefixed.
- `session.py` confirms the live contract only allows:
  - launch/send/status/wait/checkpoint/review/accept/halt
  - no public session-rejoin resume command exists in the public session command surface.

### Hypotheses / evidence gaps

- Default model/effort identity is unresolved unless explicitly passed with
  `--model` / `--effort`; static census can confirm flag names only.
- `/loop` runtime semantics are unproven in a real harness fixture.
- Workspace / project addendum behavior is not proven from `--help` (`--settings`,
  `--setting-sources`, and `--session-id` are declared, but bleed boundaries are not proved).
- Per-run additive system layer is available via CLI flags (`--append-system-prompt`,
  `--system-prompt`) yet not used in source to avoid prompt-in-argv transport and requires explicit
  conformance proof before selection.
- Live default-model observation command was not discovered from static help; a prior direct
  `claude models` probe did not produce output before being interrupted.

## 2) Instruction plane map for this version

### Plane 1: session-selected profile plane (candidate winner)
- Activation: `session_profile` in the contract; only prefixed on initial message.
- Known selectors: `regular`, `loop`, `goal`.
- Cleanup: session-local process/lease cleanup only; no global config touch expected from source.
- Risk: `/loop` runtime behavior is unproven; must be validated in a separate conformance
  row before promotion.

### Plane 2: workspace/repository addendum plane (unproven)
- Activation candidates: launcher/config source path (`--settings`, `--setting-sources`) plus local repo.
- Cleansheet requirement: keep generated settings under lane-owned fixture and verify ordinary
  sessions remain unchanged.
- Current status: hypothesis only; no direct proof in this static lane.

### Plane 3: additive per-run system-instruction plane (deferred)
- Candidates from docs: `--append-system-prompt` and `--system-prompt`.
- Hard constraint from source: all launch messaging must stay out of argv; this plane likely
  violates no-prompt-in-argv constraints unless implemented via non-argv transport.
- Current status: unsupported for this lane's regular baseline until source proof exists.

## 3) Default-model observation plan

1. Add a lane-owned isolated run fixture with deterministic fixture home and temporary
   settings source.
2. Run one regular session with no explicit `--model`/`--effort`.
3. Extend conformance/readiness handling to record the effective model/effort value in
   deterministic fixture output (or reject the lane as blocked if unavailable).
4. If the target does not expose explicit model/effort in the bounded handoff, classify
   default-model state as `model_unknown` and require explicit model pinning path for all live
   regular runs.

## 4) Regular launch / resume / steer / halt / no-bleed matrix

| Surface | Planned action | Exact expected evidence | Stop criteria |
| --- | --- | --- | --- |
| Launch | `session_profile=regular`, contract-bound fixture, no `--model`/`--effort` | `launch` transitions active, startup settle succeeds, manifest/process/socket/lease identities remain exact | blocked if manifest drift or post-launch process mismatch |
| Launch | `session_profile=loop` / `goal` | initial envelope prefix only on first input; same stability checks as regular | block and downgrade to hypothesis if `/loop` or `/goal` does not create exact, bounded initial handshake |
| Resume | reuse any resume API during same session profile | no supported capability in current contract; resume is treated as unsupported | hard stop; must be supported by explicit resume contract before lane promotion |
| Steer | ordinary follow-up via `send` with initial=False | no slash prefix injected, one delivery event, fixture handoff advances once | blocked if prefix appears in argv or message body |
| Halt | exact process shutdown via adapter halt action | exact pid `SIGINT` sequence, `HALTED`, no process bleed | blocked if process does not stop or registry/tmux evidence changes |
| No-bleed control | ordinary non-Puppet session + ordinary non-Puppet process population | unchanged target population except exactly registered session-owned process set | blocked if any ordinary session is attached or mutated |

## 5) Isolated config strategy

- Use only lane-owned fixture roots for proofs and state:
  - temporary fixture run tree under the lane workspace
  - temporary settings source file and explicit setting source constraints
  - no reads or writes against user global Claude config.
- Candidate isolation controls are to be applied through fixture arguments and `--settings`
  / `--setting-sources` in command entry, then validated by before/after checks on
  ordinary-config surfaces.
- Do not keep any live command artifacts inside the default user home between runs.

## 6) Required Puppet deltas for this lane

- Expand `skills/puppet/scripts/puppet_lib/probe.py` to record and verify effective default model/effort
  from a live regular Claude handoff or equivalent deterministic fixture claim.
- Extend `skills/puppet/scripts/puppet_lib/census.py` / `adapter_manifest.py` tests if
  future evidence is added for isolated settings sources so source-free mapping can prove real
  bleed boundaries for `/settings`-based addendum experiments.
- Add explicit probe fixtures/tests for Claude `loop` profile precedence and resume unsupported.
- Add no-bleed regression assertions for fixture-root-only settings handling.

## 7) Blockers and stop criteria

- Hard blockers:
  - No live default-model proof yet; cannot declare `model_default` exact.
  - `/loop` behavior unproven.
  - Resume is unsupported under current source for this lane.
  - Any static path or launch command that injects prompt text in argv.
- Stop criteria:
  - Do not move past static mapping until `session_profile=regular` is proven in fixture with
    launch/steer/halt sequence and explicit no-bleed gate.
  - Keep lane at `mapping` if default model, loop, or addendum control remains unresolved.
