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
- A bounded safe-field-only `codex doctor --json` observation reports model
  `gpt-5.6-sol`, provider `openai`, and authenticated status for the ordinary
  environment. This does not prove the same model/auth tuple in an isolated
  root.
- `CODEX_HOME=<temp> codex doctor --json` loads default config and reports
  `model: <default>`, but authentication is coupled to `CODEX_HOME` and is not
  present in a new lane root.
- Current official Codex documentation defines `CODEX_HOME` as the shared root
  for configuration, authentication, logs, sessions, skills, and standalone
  package metadata. `CODEX_SQLITE_HOME` redirects only SQLite-backed state; it
  is not a credential/config split. See
  <https://learn.chatgpt.com/docs/config-file/environment-variables#core-locations>.
- Official authentication documentation permits `CODEX_ACCESS_TOKEN` as a
  process-local credential for trusted CLI/app-server automation without a
  persisted login. This is the only documented clean route found for combining
  a fresh Puppet-owned `CODEX_HOME` with ChatGPT/Codex entitlement; Puppet does
  not currently have such a token authority. See
  <https://learn.chatgpt.com/docs/config-file/environment-variables#authentication-and-network>
  and <https://learn.chatgpt.com/docs/enterprise/access-tokens#use-an-access-token-with-codex-cli>.
- A 2026-07-22 status-only probe ran Codex 0.145.0 with an empty private
  `CODEX_HOME`, a closed non-secret environment, and
  `cli_auth_credentials_store="keyring"`. `codex login status` returned
  `Not logged in`; the private root remained empty. Therefore this machine's
  ordinary login cannot be assumed reusable from an isolated home through the
  keyring selector. No session was launched and no credential value or auth
  file was read.

### Hypotheses requiring proof

- `codex --help` output alone is insufficient for instruction-plane precedence
  among global profiles, project guidance, and per-run instructions.
- `codex resume` may rebind the registered session in ways that differ from non-AGY
  harnesses; resume behavior is not equivalent across harnesses.
- Default model reporting from `doctor` may differ by authenticated vs unauthenticated
  environment and must be treated as live-state fact per run.
- The regular TUI's authenticated state cannot be copied or linked from the
  live home. A brokered process-local access-token route or a human login into
  the lane root requires a separate gate; neither is currently available.
- `--ephemeral` or `CODEX_SQLITE_HOME` may reduce specific persistence, but
  neither is evidence of an isolated configuration/instruction stack because
  the ordinary `CODEX_HOME` still owns auth, configuration, logs, sessions,
  skills, and other state. Do not use either as a substitute for the lane root.

## 2) Instruction planes: precedence, activation, cleanup unknowns

`session_profile=regular` is the active unprefixed lifecycle selection, not an
instruction plane.

- **Plane 1: session-selected harness-global Puppet profile**
  - Official Codex configuration supports `--profile <name>`, which layers
    `$CODEX_HOME/<name>.config.toml` over the base user config.
  - Candidate Puppet profiles may use additive `developer_instructions`; never
    use `model_instructions_file`, which replaces built-in base instructions.
  - Qualification must use a lane-owned `$CODEX_HOME/<namespace>.config.toml`,
    select it with `--profile <namespace>`, and show that a matched control
    without the profile receives no Puppet instruction. Authentication
    isolation is the current blocker; never copy, link, read, or hash live
    credentials.

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
   - Inputs: a future exact Puppet-created session ID only.
   - Expected: a new process generation bound to the exact registered prior
     session. Bare resume and `--last` are forbidden because they can select a
     non-Puppet operator session. The current Puppet command surface keeps
     resume unsupported.

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
- Launch commands with explicit `-C <absolute-fixture-repo>` and no
  ChatGPT-app-specific project assumptions.
- Do not copy/symlink the ordinary auth file, inspect Keychain/token stores, or
  put credentials in argv. A future approved broker may inject only a
  process-local credential into the exact Puppet child; otherwise a
  human-present login must initialize the isolated root.
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
- `skills/puppet/scripts/puppet_lib/tmux.py` / launch planning
  - add allowlisted environment and exact absolute `-C`/profile bindings
    without a shell wrapper or instruction/credential body in argv, state, or
    proof.

## 7) Blockers and stop criteria

- Blocker: any executable/help/help-sha/`CODEX_HOME` drift after this census.
- Blocker: inability to prove prompt transport without argv prompt injection.
- Blocker: resume cannot be proven exact and isolated from ordinary session state.
- Blocker: plain regular steer is not accepted without the target admitting exactly one
  follow-up checkpoint under bounded fixture control.
- Blocker: any source/credential/global-session state read/write outside the lane fixture
  root.
- Blocker: no approved authentication-preserving isolated `CODEX_HOME` route is
  currently available. The supported candidate is controller-brokered,
  process-local `CODEX_ACCESS_TOKEN` injection into the exact child with no
  value in argv, proof, logs, or agent context; no such authority exists in the
  current campaign.
- Stop condition: no unsupported claims beyond this lane scope; if model/plane/resume
  evidence is inconclusive, defer plane choice and keep harness status as `experimental`
  with blockers recorded.
