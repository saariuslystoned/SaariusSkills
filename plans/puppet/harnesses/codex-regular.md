# Codex regular-session qualification harness (v0.1)

Status: launch-disabled workspace-plane planning only; no live Codex session is
qualified.

## Scope and lane contract

- File purpose: planning and proof-prep for Codex regular-session qualification under
  `codex-goal-regular-qualification.md`.
- Current source lane: `codex/puppet-codex-workspace-plan` from exact integrated
  base `8f64210dccad81377ec33e482c79703c6c7a8806`.
- Objective: map exact Codex regular-session behavior for the three instruction planes,
  select a winner for the exact installed version, and define deterministic evidence and
  fixture deltas so the lane can qualify with no transcript bleed.

## 1) Exact-version discovery: facts vs hypotheses

### Facts observed

- Requested command path: `command -v codex` -> `/opt/homebrew/bin/codex`, which is
  a symlink and is not the execution-file identity.
- Resolved regular execution file:
  `/opt/homebrew/Caskroom/codex/0.145.0/codex-aarch64-apple-darwin`.
- `codex --version` -> `codex-cli 0.145.0`.
- Resolved regular-file hash (SHA-256):
  `1da3f4e0e96028b8a771814293c3033dafd1971f943f6c7e79b0897fe705f590`.
- The regular unrestricted mapping is exactly the resolved execution file followed by
  `--dangerously-bypass-approvals-and-sandbox`. That one switch is declared in both
  the permission and sandbox-disable buckets. Project isolation remains incomplete.
- `model_flag=--model` records capability discovery only. The active baseline exposes
  fixed symbolic `model_selection=current_default` and
  `effort_selection=current_default`; it accepts no model, effort, profile, or config
  selector.
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
  - `codex_workspace_plane.py` now plans one exact create-only root
    `AGENTS.md` candidate for an absent preimage and binds its compiled-contract
    hash, instruction-manifest hash, current source-only launch context, private
    lane/workspace/`CODEX_HOME` identities, and exact `-C <workspace>` delta.
    The record is body-free and keeps materialization, verification, rollback,
    recovery, launch, and qualification disabled. It is not activation proof.

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
  - If model resolves to `<default>` under isolated `CODEX_HOME`, record it as
    `available-for-test-plan-only`. The source-only baseline remains
    `model_selection=current_default`; model pinning is outside this gate.

## 4) Regular-session launch/steer/resume/halt/no-bleed matrix

1. **Launch regular without prefix**
   - Input: `session_profile=regular`, fixed symbolic
     `model_selection=current_default` and `effort_selection=current_default`.
     There are no model/effort caller parameters or selector flags.
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

## 6) Implemented substrate and remaining Puppet source deltas

- `skills/puppet/scripts/puppet_lib/codex_workspace_plane.py`
  - implements the launch-disabled body-free workspace plan described above;
    revalidation rebuilds the exact plan from current source-owned launch,
    root, manifest, and contract inputs, and rejects an existing or symlinked
    `AGENTS.md` before any mutation;
  - composes the exact resolved executable, unrestricted flag, absolute `-C`
    workspace, session/run identity, and closed `CODEX_HOME`-only environment
    into a standard admitted-launch plan while preserving every source-only
    blocker and `launch_authorized=false`;
  - all lifecycle entry points unconditionally raise `UnsupportedError`.

- `skills/puppet/scripts/puppet_lib/codex_launch.py`
  - now exposes a source-only doctor observation that rebuilds the existing
    private-root launch context, requires zero pre-existing Codex processes,
    runs only the exact resolved executable plus `doctor --json` under the
    closed `CODEX_HOME`-only environment, and revalidates the complete context
    after the command;
  - retains only the bounded raw-output hash/byte count and the allowlisted
    `config.load` model/provider pair. Duplicate, alias-ambiguous, malformed,
    non-UTF-8, oversized, nonzero, timed-out, or drifted observations fail
    closed. `<default>` remains `available_for_test_plan_only`; an explicit pair
    remains `observed_only` until same-runtime live proof exists;
  - fixes launch, model-selection, same-runtime, and qualification authority to
    false and has no probe, adapter, session, or tmux consumer.

- `skills/puppet/scripts/puppet_lib/census.py`
  - record Codex-specific model/probe identity facts from `codex doctor --json` to
    distinguish default-model and provider identity from command-line assumptions.
- `skills/puppet/scripts/puppet_lib/adapter_manifest.py`
  - include explicit default-model/evidence fields for the observed Codex run tuple
    and validate them in qualification receipts.
- `skills/puppet/scripts/puppet_lib/probe.py`
  - add model/effort capture for default model observation and tie it to probe evidence.
  - expand resume/handoff assertions for Codex-specific resume path and no-bleed gates.
- `skills/puppet/scripts/puppet_lib/codex_launch.py`
  - add a source-only Codex launch-context gate:
    - bind the requested symlink `/opt/homebrew/bin/codex` separately from the exact
      resolved regular execution file
      `/opt/homebrew/Caskroom/codex/0.145.0/codex-aarch64-apple-darwin`, and revalidate
      that resolved file's current identity and bytes,
    - admit only the resolved-file plus
      `--dangerously-bypass-approvals-and-sandbox` argv mapping, with no model,
      effort, profile, or config override,
    - doctor-only manifest enforcement for source-only regular sessions,
    - 0700 private lane/workspace/CODEX_HOME checks and non-overlap,
    - closed launch environment built from empty ambient state, and
    - candidate-process evidence collection with malformed evidence fail-closed.
- `tests/test_puppet_adapters.py` and `tests/test_puppet_probe.py`
  - codex-specific test cases for all three planes, no-bleed and resume ambiguity,
    plus one test for isolated `CODEX_HOME` noninterference.
- `skills/puppet/scripts/puppet_lib/tmux.py` / launch planning
  - add allowlisted environment and exact absolute `-C`/profile bindings
    without a shell wrapper or instruction/credential body in argv, state, or
    proof.

- `tests/test_puppet_codex_launch.py`
  - source-only Codex launch gate tests covering manifest binding, path/version checks,
    candidate-process call shape, no-ambient env, and an ambient
    `CODEX_ACCESS_TOKEN` non-leak canary.
- `skills/puppet/scripts/puppet_lib/run_observations.py`
  - persists the exact body-free `CodexDoctorObservation` as an atomic,
    create-only zero-agent outcome record;
  - records requested/current-default versus observed model/provider facts,
    exact version, task/profile, bounded latency, explicit `unavailable`
    native/checkpoint metrics, zero repairs, source-only proof integrity, and
    a blocked controller verdict; and
  - validates the source digest and every false authority bit while remaining
    disconnected from launch, session, probe, adapter, and qualification
    consumers.

## 7) Blockers and stop criteria

- Unconditional source-only blocker: approved process-local auth broker unavailable.
- Unconditional source-only blocker: native instruction plane
  activation/precedence/no-bleed unproved.
- Unconditional source-only blocker: live doctor/current-default and Pass-B lifecycle
  unproved.
- Unconditional source-only blocker: launch remains fenced/source-only.
- Mapping blocker while applicable: native-plane mapping remains incomplete because
  project isolation has not been proved.
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
