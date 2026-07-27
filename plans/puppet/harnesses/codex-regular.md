# Codex regular-session qualification harness (v0.1)

Status: the current Codex pair was independently reverified and qualified at
source head `cdaf38877ed61d607de03129fc6036b728958fbf` with the exact logged-in
private-profile binding. The pair remains body-free `paired_evidence_only`; the
separately verified qualified manifest is the runtime-authority boundary. This
still-running public source lifecycle is not yet controller-accepted, and a
final integrated-head rerun remains pending.

## Scope and lane contract

- File purpose: planning and proof-prep for Codex regular-session qualification under
  `codex-goal-regular-qualification.md`.
- Historical and current bounded evidence are curated in
  `plans/puppet/live-proof/codex-57175e3-20260726.json` and
  `plans/puppet/live-proof/codex-cdaf388-20260727.json`.
- Objective: map exact Codex regular-session behavior for the three instruction planes,
  select a winner for the exact installed version, and define deterministic evidence and
  fixture deltas so the lane can qualify with no transcript bleed.

### Exact-head qualification checkpoint (2026-07-27)

- At source head `cdaf38877ed61d607de03129fc6036b728958fbf`, the
  exact current executable was
  `/opt/homebrew/Caskroom/codex/0.145.0/codex-aarch64-apple-darwin`, SHA-256
  `1da3f4e0e96028b8a771814293c3033dafd1971f943f6c7e79b0897fe705f590`.
  The controller accepted distinct positive and ordinary-control receipts, the
  terminal pair, and an actual read-only native-view receipt, then qualified
  manifest fingerprint
  `442042bed81a3739dc5d8cc2f27c6b6ca1bec87c8033bf2cb0efed85c5e76a85`.
- Both members used the same exact logged-in Puppet-owned private profile and
  current-default model/effort with no selector. Their resolved model and
  effort identities remain honestly unavailable. Worktrees, target processes,
  tmux identities, and controller leases were distinct; checkpoints were
  sequenced; and both owned trees reached exact terminal halts.
- Repairs at `3d184b4`, `c259450`, and `cdaf388` respectively removed generated
  census time from receipt identity, consumed the current nested pair schema,
  and closed the qualified mapping against the exact current executable.
- This checkpoint does not claim controller acceptance of the still-running
  public lifecycle or completion of the final integrated-head rerun. Native
  instruction-plane behavior and the deferred command/model surfaces remain
  outside its scope.

## 1) Exact-version discovery: facts vs hypotheses

### Facts observed

- On 2026-07-26 the root controller ran two real subscription-backed Codex
  regular sessions at exact source head `57175e3`: a positive direct-worktree
  member and a later ordinary member in a distinct clean linked worktree from
  the same Git common repository and exact head.
- Both members used the same Puppet-owned private `CODEX_HOME`, the same
  no-selector current-default launch vector, two sequenced structured
  checkpoints, distinct process/tmux/controller-lease identities, empty
  pre/post Codex populations, and exact owned-tree halts.
- A real Terminal tmux client attached read-only to the live positive TUI and
  detached while the target remained alive. The observer retained structural
  identity only and captured no pane body, prompt, transcript, or scrollback.
- `pair-codex` created body-free paired receipt SHA-256
  `e67adce0a728fc8fe42f3cd55f8782d89398f8880e1f0737bfbc2889eaa4e718`;
  `verify-codex-pair` independently rebuilt it. Its result remains
  `paired_evidence_only`, with its own public-launch and promotion flags false
  by contract. A separately verified qualified manifest is the launch
  authority boundary.

- Requested command path: `command -v codex` -> `/opt/homebrew/bin/codex`, which is
  a symlink and is not the execution-file identity.
- The 2026-07-23 CP-1 recensus resolves the requested symlink first to the
  official npm JavaScript launcher
  `/opt/homebrew/lib/node_modules/@openai/codex/bin/codex.js`, then statically
  binds its bundled native execution file at
  `/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex`.
- The exact npm launcher hash (SHA-256) is
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`.
  Census invokes the native file directly for version/help and records the
  launcher as support provenance; it does not execute Node or follow a child.
- `codex --version` -> `codex-cli 0.145.0`.
- Resolved regular-file hash (SHA-256):
  `1da3f4e0e96028b8a771814293c3033dafd1971f943f6c7e79b0897fe705f590`.
- The regular unrestricted doctor mapping is exactly the resolved execution
  file followed by `--dangerously-bypass-approvals-and-sandbox`. That one switch
  is declared in both the permission and sandbox-disable buckets. The doctor
  mapping remains incomplete until terminal qualification; the exact-head
  qualified manifest closes project isolation against the current executable.
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
- The exact-head qualification proves one authenticated isolated route through
  the already enrolled Puppet-owned private profile. It does not authorize
  copying or linking authentication state, unattended login, or reuse of an
  operator-global home; a new enrollment or broker route remains separately
  human-gated.
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
  - A future qualification of this native plane must use a lane-owned
    `$CODEX_HOME/<namespace>.config.toml`, select it with
    `--profile <namespace>`, and show that a matched control without the profile
    receives no Puppet instruction. The exact-head pair proves its enrolled
    private-profile authentication boundary, not native profile-plane
    activation or precedence; never copy, link, read, or hash live credentials.

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
   - Input: one controller-linked positive direct-worktree run plus a distinct
     ordinary-control run using the same exact Puppet-owned subscription
     profile and the same provider-default/no-selector launch vector.
   - Expected: distinct accepted checkpoints, workspaces, target processes,
     tmux servers/sockets/sessions, and controller leases; exact terminal halts;
     and no population bleed. A single positive receipt never promotes.

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
   - Start both runs from the same stable Puppet-owned private `CODEX_HOME`
     profile, but in distinct non-overlapping workspaces and with distinct
     tmux/process/controller-lease identities.
   - Require empty same-target populations before each launch and after each
     exact halt. The control is linked to the earlier positive receipt before
     launch and cannot run from an operator-global or second profile.

## 5) Isolated `CODEX_HOME` / config-root strategy

- Use one stable, current-UID mode-0700 Puppet-owned private profile and pass
  its exact root as `CODEX_HOME` for both members of the pair. Do not create a
  second control profile or place the profile inside a disposable run/proof
  root.
- Keep fixture config minimal and lane-local; never read or write
  `~/.codex/config.toml` during this lane.
- Launch commands with explicit `-C <absolute-fixture-repo>` and no
  ChatGPT-app-specific project assumptions.
- Do not copy/symlink the ordinary auth file, inspect Keychain/token stores, or
  put credentials in argv. The exact-head pair reused its already enrolled
  Puppet-owned private profile. A future approved broker may inject only a
  process-local credential into the exact Puppet child; otherwise a
  human-present login must initialize any new isolated root.
- Cleanup boundary: preserve lane-owned roots as evidence until exact rollback
  and cleanup are separately authorized; never target global user paths.
- Verification precondition: any evidence that references config/profile paths must
  resolve under the lane-owned fixture root only.

## 6) Implemented substrate and remaining Puppet source deltas

- `skills/puppet/scripts/puppet_lib/codex_qualification.py`
  - links the ordinary control to one earlier controller-attested positive
    worktree receipt before launch and requires the same subscription-profile
    hash/root, regular session profile, provider-default model/effort, and
    identical no-selector argv/closed profile fingerprint;
  - requires distinct non-overlapping workspaces, target processes, tmux
    sockets/sessions/servers, accepted checkpoints, and exact halted controller
    leases, plus empty before-launch and after-halt target populations;
  - observes a real native tmux viewer only through a distinct read-only client
    and executable/process identity while the positive target is alive, then
    requires its detach without ever reading or retaining pane body, prompt,
    transcript, scrollback, or auth/config content;
  - accepts only a self-hashed operator plan proving exact `direct_git_root` or
    `cockpit_explicit` entry for the positive worktree repository, branch, and
    head; and
  - creates the paired proof with exclusive create semantics and controller
    attestation, then independently rebuilds it from terminal artifacts. The
    result is always `paired_evidence_only` with launch/promotion false.
- `skills/puppet/scripts/adapter_lab.py`,
  `skills/puppet/scripts/puppet_lib/probe.py`, and
  `skills/puppet/scripts/puppet_lib/adapter_manifest.py`
  - expose the linked ordinary-control, structural viewer, create-only pair,
    and pair-verification source surfaces;
  - accept Codex `qualify` only after independently rebuilding the terminal
    pair against the current doctor manifest, current nested pair schema, exact
    executable mapping, and exact private-profile binding;
  - keep the pair non-launchable by itself. Public doctor/launch must consume
    the separately qualified manifest and reverify its pair/profile binding.
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
  - resolves only the exact known Codex 0.145.0 npm launcher layout to its
    bundled native file, records a `direct_with_support` execution tuple, and
    invokes only that native file for bounded version/help census;
  - reject unknown script launchers, launcher hash drift, package-layout drift,
    native-file drift, and requested-link drift before emitting a manifest.
- `skills/puppet/scripts/puppet_lib/adapter_manifest.py`
  - include explicit default-model/evidence fields for the observed Codex run tuple
    and validate them in qualification receipts.
- `skills/puppet/scripts/puppet_lib/probe.py`
  - add model/effort capture for default model observation and tie it to probe evidence.
  - expand resume/handoff assertions for Codex-specific resume path and no-bleed gates.
- `skills/puppet/scripts/puppet_lib/codex_launch.py`
  - add a source-only Codex launch-context gate:
    - bind the requested symlink `/opt/homebrew/bin/codex` separately from the
      exact npm launcher and bundled native execution file, then revalidate the
      requested link, launcher bytes, and native-file identity,
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

- `skills/puppet/scripts/puppet_lib/operator_plan.py`
  - emits a body-free `target_gate` for a doctor-only, unqualified Codex
    manifest with state `waiting_for_human`, failed invariant
    `approved_authentication_preserving_private_codex_home_route_unavailable`,
    rung `codex_regular_pass_b`, the exact manifest/executable/version/adapter/
    protocol identity, every source-only blocker, and the expected launch,
    workspace-plan, doctor, and zero-agent observation kinds. Because planning
    supplies and validates none of those artifacts, preserved evidence kinds
    remain empty;
  - keeps only `doctor` as a proposed Codex diagnostic and marks launch,
    status, waits, attach, open-view, and halt unsupported with reason
    `codex_regular_session_source_only_unqualified`;
  - records `profile-init` as a human-gated proposal. The only named choices
    are `process_local_broker` and
    `human_present_lane_owned_home_login`; neither name carries a value or
    selector, and choosing or executing either route remains outside planning.

## 7) Blockers and stop criteria

- Exact-head qualification checkpoint satisfied: the subscription-backed pair
  was independently reverified, the exact executable mapping was closed, and
  the qualified manifest was created with the same logged-in private-profile
  binding.
- The paired receipt remains evidence-only and non-launchable by itself. The
  separately verified qualified manifest is the runtime-authority boundary.
- Remaining controller gate: this still-running public source lifecycle is not
  yet accepted, and the final integrated-head rerun is incomplete.
- Remaining evidence boundary: resolved model and effort identities are
  unavailable because the pair used the current defaults with no selector.
- Remaining native-plane blocker: instruction activation, precedence,
  cleanup, and no-bleed claims are unproved and deferred.
- Blocker: any executable/help/help-sha/`CODEX_HOME` drift after this census.
- Blocker: inability to prove prompt transport without argv prompt injection.
- Blocker: resume cannot be proven exact and isolated from ordinary session state.
- Revalidation requirement: any new lifecycle must preserve bounded ordinary
  steering and sequenced checkpoints under the exact qualified contract.
- Blocker: any source/credential/global-session state read/write outside the lane fixture
  root.
- Human gate for new authentication: the qualified enrolled private profile is
  the only accepted current route. A new profile still requires an approved
  process-local broker or human-present enrollment; neither permits automatic
  login or inspection of an existing home.
- Stop condition: no unsupported claims beyond this lane scope; if model/plane/resume
  evidence is inconclusive, defer plane choice and keep harness status as `experimental`
  with blockers recorded.
- `/goal`, `/loop`, explicit model selection, model pinning, and resume remain
  deferred and are not implied by this regular provider-default pair.
