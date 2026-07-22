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
- `codex --help` help output includes `--goal` equivalent via profile routing:
  `session_profile` options for Codex are `regular` and `goal`.
- `codex doctor --json` reports loaded config model as `gpt-5.6-sol` (model provider
  `openai`) in the current environment.
- `codex doctor --json` in isolation (`CODEX_HOME=<temp>`) loads defaulted config,
  reports `model: <default>`, and does not require the default home config to parse.

### Hypotheses requiring proof

- `codex --help` output alone is insufficient for instruction-plane precedence:
  session-prefix `/goal` vs config-level profile vs fixture/runtime instructions.
- `codex resume` may rebind the registered session in ways that differ from non-AGY
  harnesses; resume behavior is not equivalent across harnesses.
- Default model reporting from `doctor` may differ by authenticated vs unauthenticated
  environment and must be treated as live-state fact per run.

## 2) Instruction planes: precedence, activation, cleanup unknowns

The lane uses the exact `session_profile` contract values for `regular` and `goal`.

- **Plane 1: session-selected harness-native profile (highest priority candidate)**
  - Activation: `session_profile` from contract, transformed via
    `adapter.envelope(..., initial=True)` and injected as initial message prefix.
  - Precedence candidate: highest for this exact version because it uses first-prompt
    command routing and keeps prompt body out of argv.
  - Cleanup: no config writes outside fixture; only contract-scoped process
    ownership and session lease cleanup.
  - Unknowns: whether `/goal` requires one specific trust gate in the fixture
    before `ready.json` is written, and whether `/goal` remains required after the first
    fixture message.

- **Plane 2: repository/workspace addendum / local config-plane**
  - Activation candidate: `-p <CONFIG_PROFILE_V2>` and/or `-c` overrides to
    `$CODEX_HOME/<name>.config.toml`.
  - Unknowns: exact effective precedence between `-p` profile, `-c` overrides,
    session prefix (`/goal`), and workspace working-dir (`-C`) in this exact build.
  - Cleanup unknowns: whether profile artifacts remain under `CODEX_HOME` and whether
    stale profile files can bleed into ordinary sessions.

- **Plane 3: additive per-run system instruction-equivalent input**
  - Activation candidate: prompt body as stdin plus profile/`--config` overrides.
  - Unknowns: whether this can be modeled as a persistent contract without global
    writes and without any `/goal` profile at all.
  - Cleanup unknowns: whether per-run input gets memoized in any durable Codex rollout
    artifacts even under isolate roots.

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

2. **Launch regular with `/goal` prefix**
   - Input: `session_profile=goal`, initial envelope prefixed.
   - Expected: same process identity contract as regular launch plus deterministic
     ready/follow-up sequence and zero ordinary-session pollution.

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
- Cleanup boundary: delete/replace only lane-owned `CODEX_HOME` and fixture roots after
  proving completion, never global user paths.
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
