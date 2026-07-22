# Codex regular-session qualification harness (v0.1)

## Scope and lane contract

- File purpose: planning and proof-prep for Codex regular-session qualification under
  `codex-goal-regular-qualification.md`.
- Branch in scope: `codex/puppet-regular-codex-20260722`.
- Objective: map exact Codex regular-session behavior for the three instruction planes,
  select a winner for the exact installed version, and define deterministic evidence and
  fixture deltas so the lane can qualify with no transcript bleed.

## 1) Exact-version discovery: facts vs hypotheses

### Facts observed

- Executable resolution: `command -v codex` -> `/opt/homebrew/bin/codex`.
- `codex --version` -> `codex-cli 0.145.0`.
- Binary hash (SHA-256): `1da3f4e0e96028b8a771814293c3033dafd1971f943f6c7e79b0897fe705f590`.
- `codex --help` declares `--model`, `--sandbox`, `--profile`, `--c` overrides,
  `resume`, and an `--json`/`--summary` style diagnosis path via `doctor`.
- Puppet source declares `session_profile` values `regular` and `goal`; this is
  not a claim from `codex --help`, and `goal` is deferred from the active baseline.
- `codex doctor --json` reports loaded config model as `gpt-5.6-sol` (model provider
  `openai`) in the current environment.
- `codex doctor --json` in isolation (`CODEX_HOME=<temp>`) loads defaulted config,
  reports `model: <default>`, and does not require the default home config to parse.

### Hypotheses requiring proof

- `codex --help` output alone is insufficient for instruction-plane precedence
  among global profiles, project guidance, and per-run instructions.
- `codex resume` may rebind the registered session in ways that differ from non-AGY
  harnesses; resume behavior is not equivalent across harnesses.
- Default model reporting from `doctor` may differ by authenticated vs unauthenticated
  environment and must be treated as live-state fact per run.

## 2) Instruction planes: precedence, activation, cleanup unknowns

`session_profile=regular` is the active unprefixed lifecycle selection, not an
instruction plane.

- **Plane 1: session-selected harness-global Puppet profile**
  - Official Codex configuration supports `--profile <name>`, which layers
    `$CODEX_HOME/<name>.config.toml` over the base user config.
  - Candidate Puppet profiles may use additive `developer_instructions`; never
    use `model_instructions_file`, which replaces built-in base instructions.
  - Qualification must use an isolated `CODEX_HOME`, prove auth still works
    without copying credentials, and show that a control session without the
    selected profile receives no Puppet instruction.

- **Plane 2: repository/workspace addendum**
  - Codex discovers root-to-cwd `AGENTS.md` guidance and trusted project
    `.codex/config.toml` layers; closer guidance/config wins conflicts.
  - The fixture must preserve existing repository instructions. Prefer a scoped
    additive project layer or nested fixture over overwriting an existing file.
  - Exact discovery, trust behavior, and cleanup remain live proof requirements.

- **Plane 3: additive per-run system instruction**
  - `-c developer_instructions=...` is additive, but a literal instruction body
    would be exposed in argv and therefore fails Puppet's transport gate.
  - Keep this plane unsupported unless a current native file/stdin/app-server
    path is proved additive and transcript-blind.

Official surface references: Codex manual sections “Custom instructions with
AGENTS.md,” “Profiles,” “Project config files,” and “Instruction Overrides.”

## 3) Current-default model observation plan

- Baseline model observation command: `codex doctor --json`.
- Parse at least:
  - `checks.config.load.details.model`
  - `checks.config.load.details.model provider`
- Compare with fixture-actual model by invoking at least one non-effectful launch step
  under that model binding.
- Model observation policy:
  - Treat model/provider as `exact` only if both values are parseable and contract
    matches manifest evidence.
  - If model resolves to `<default>` under isolated `CODEX_HOME`, record as
    `available-for-test-plan-only` and require explicit test model pinning before any
    live assertions.

## 4) Regular-session launch/steer/resume/halt/no-bleed matrix

1. **Launch regular without prefix**
   - Input: `session_profile=regular`, no requested model.
   - Expected: accepted launch with no prompt in argv, one PID-bound process snapshot,
     and fixture `ready.json` ready-phase acknowledgment.

2. **Instruction-plane control**
   - Input: selected candidate plane plus a matched ordinary control without it.
   - Expected: exact contract marker only in the Puppet-owned checkpoint and no
     activation in the control session.

3. **Follow-up steering**
   - Input: second message via controller send (non-prefix) on same session.
   - Expected: sequence increments and `followup.json` references exact prior
     checkpoint hash.

4. **Resume behavior**
   - Inputs: `codex resume` (targeted and `--last`) in an isolated run.
   - Expected: exact target identity rebind; no session migration; classified separately
     as its own command profile with explicit blocker if replay path is not exact.

5. **Halt behavior**
   - Input: exact PID signal path.
   - Expected: single targeted halt, registered process terminates, same-session
     evidence retained.

6. **No-bleed ordinary control**
   - Start control session in ordinary `CODEX_HOME` and one in isolated `CODEX_HOME`;
     verify launch/ready/follow-up only occurs in the isolated session and ordinary
     session state remains unchanged.

## 5) Isolated `CODEX_HOME` / config-root strategy

- Use a dedicated temporary root (for example
  `runs/puppet-v01-regular-qualification-20260722/lanes/codex/tmp/codex-home`)
  and pass it as environment variable `CODEX_HOME` for all Codex commands in this lane.
- Keep fixture config minimal and lane-local; never read or write
  `~/.codex/config.toml` during this lane.
- Launch commands with explicit `-C <fixture-repo>` and no `ChatGPT.app`-specific
  project assumptions.
- Cleanup boundary: preserve lane-owned roots as evidence until exact rollback
  and cleanup are separately authorized; never target global user paths.
- Verification precondition: any evidence that references config/profile paths must
  resolve under the lane-owned fixture root only.

## 6) Required Puppet source deltas (blocked to future lane implementation)

- `skills/puppet/scripts/puppet_lib/census.py`
  - record Codex-specific model/probe identity facts from `codex doctor --json` to
    distinguish default-model and provider identity from command-line assumptions.
- `skills/puppet/scripts/puppet_lib/adapter_manifest.py`
  - include explicit default-model/evidence fields for the observed Codex run tuple
    and validate them in qualification receipts.
- `skills/puppet/scripts/puppet_lib/probe.py`
  - add model/effort capture for default model observation and tie it to probe evidence.
  - expand resume/handoff assertions for Codex-specific resume path and no-bleed gates.
- `tests/test_puppet_adapters.py` and `tests/test_puppet_probe.py`
  - codex-specific test cases for all three planes, no-bleed and resume ambiguity,
    plus one test for isolated `CODEX_HOME` noninterference.

## 7) Blockers and stop criteria

- Blocker: any executable/help/help-sha/`CODEX_HOME` drift after this census.
- Blocker: inability to prove prompt transport without argv prompt injection.
- Blocker: resume cannot be proven exact and isolated from ordinary session state.
- Blocker: plain regular steer is not accepted without the target admitting exactly one
  follow-up checkpoint under bounded fixture control.
- Blocker: any source/credential/global-session state read/write outside the lane fixture
  root.
- Stop condition: no unsupported claims beyond this lane scope; if model/plane/resume
  evidence is inconclusive, defer plane choice and keep harness status as `experimental`
  with blockers recorded.
