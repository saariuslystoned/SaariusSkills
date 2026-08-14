# Claude Code regular-session qualification harness (v0.1)

Scope: static command census, source/test inspection, and no-live-lane planning under
`plans/puppet/codex-goal-regular-qualification.md`. The bounded startup-gate
reducer and durable-profile ready path are implemented and component/session
tested. The public controller path for a linked ordinary control, structural
native-view observations, paired no-bleed verification, and a promotable paired
receipt is implemented.

An exact-head authenticated live matched pair is now qualified and controller
accepted at head `8ecf3a2e1dfcb92687c7e3ebbae1b4ddf4bddb45` (see the
2026-07-27 checkpoint in section 7). What remains missing are the two later
public lifecycles that do not follow from the accepted pair: the public mutating
session lifecycle and the distinct read-only cross-review. The current
documentation session is the first exact-head public mutating lifecycle and is
itself still pending controller review and halt.

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
- Historical `census_target('claude', adapter_implementation_fingerprint())`
  snapshot, recorded before the current controller source changes:
  - permission flag: `--dangerously-skip-permissions`
  - model flag: `--model`
  - effort flag: `--effort`
  - `project_isolation_flags`: `[]`; the current parser's vacuous `true` is not
    proof of workspace/config isolation.
  - `sandbox_disable_declared`: currently inferred as `true` from the absence
    of a help row. That is not proof of the effective setting and must be
    replaced before live qualification.
  - `prompt_transport`: `interactive_tmux_load_buffer_stdin_declared`
  - `session_profiles`: `{regular: "", loop: "/loop", goal: "/goal"}`
  - `launch_argv`: `["/opt/homebrew/Caskroom/claude-code@latest/2.1.215/claude", "--dangerously-skip-permissions"]`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - manifest caps are declared for launch/send/status/wait/checkpoint/resume/halt; manifest is initially `doctor_only`
  - historical adapter fingerprint: `dff76b92ab1ecea857a67118424fc9109b5ff2f7066e50f9595bc6c086076d6b`
  - historical protocol fingerprint: `a09805b247b6dcdaad8a7d45e8c29c2c4742c8dcce65283f853953c679590aab`
  - this snapshot is not a current doctor manifest and grants no launch or
    qualification authority.
- Pure source identity at controller head
  `b2f443bc941567830f6a5b7d2c141b2b1a651a81`, computed without invoking
  Claude or reading operator state:
  - adapter fingerprint: `db3b4391007e46105f53a802d9bec80e732237f8878b44c6a165c5aca7cf78a9`
  - protocol fingerprint: `a4e220c27ecfd4b3a28245e4849bad4b9296f192155a2d8b865ca1109d3e1ce9`
  - a fresh exact-version census remains required before any live lane.
- `profiles.py` defaults:
  - `default_session_profile("claude") == "regular"`.
- `adapters.py` confirms first-launch profile-prefixing only:
  - initial message may be prefixed with `/loop` or `/goal`
  - follow-up messages are rejected if user provides slash commands and are sent unprefixed.
- `session.py` confirms the live contract only allows:
  - launch/send/status/wait/checkpoint/review/accept/halt
  - no public session-rejoin resume command exists in the public session command surface.
- `profiles.input_readiness_strategy_for("claude")` returns
  `bounded_claude_startup_gate_reducer`; every other target returns
  `bounded_structural_settle`. Claude launch therefore drives the bounded
  startup-gate reducer (`puppet_lib.claude_startup_gates`) before prompt
  delivery instead of a plain structural settle.

### Hypotheses / evidence gaps

- Static census cannot resolve the default model or effort. The paired
  qualification path proves only that both launch plans selected
  `model=default` and `effort=default`, supplied neither selector flag, and
  retained `resolved_identity=unavailable` and `effort=unavailable`. It does
  not invent or persist a model name.
- `/loop` runtime semantics are unproven and deferred from this regular lane.
- Workspace / project addendum behavior is not proven from `--help` (`--settings`,
  `--setting-sources`, and `--session-id` are declared, but bleed boundaries are not proved).
- Exact parser probes recognize `--append-system-prompt-file <file>` even
  though it is not rendered as a standalone help row. Replacement
  `--system-prompt` and `--system-prompt-file` remain forbidden.

## 2) Instruction plane map for this version

`session_profile=regular` is the active unprefixed lifecycle selection. `/loop`
and `/goal` remain deferred commands, not instruction planes.

### Plane 1: session-selected harness-global Puppet addendum
- Use a Puppet-namespaced custom output style under a lane-owned
  `CLAUDE_CONFIG_DIR`, selected by a lane-owned `--settings` file containing
  `outputStyle`. Set `keep-coding-instructions: true` so Claude Code's coding
  instructions remain active. A matched control receives the same isolated
  catalog but omits the selector.
- Do not use `--agent`: it replaces broader main-session behavior.

### Plane 2: workspace/repository addendum plane (supported, unqualified)
- Claude discovers project/local `CLAUDE.md` and `.claude/rules` surfaces.
- Use a create-only Puppet-namespaced `.claude/rules/*.md` artifact in an
  isolated worktree, preserving existing repository authority, then prove
  discovery order and exact cleanup. Do not use `.claude/settings.local.json`:
  this version resolves it through the main checkout across worktrees.

### Plane 3: additive per-run system-instruction plane (candidate)
- `--append-system-prompt-file <path>` is parsed by the exact binary and is
  documented as additive to the default prompt. The instruction body therefore
  need not enter argv. Exact additive behavior, built-in retention, and
  no-bleed still require isolated live proof.
- Literal prompt flags expose instruction text in argv and fail closed; the
  lane-owned file form is the viable candidate.

Official surface references: `https://code.claude.com/docs/en/memory`,
`https://code.claude.com/docs/en/cli-usage`, and the installed exact-version
`claude --help` output.

## 3) Default-model-unavailable evidence

Both members use the same authenticated private subscription profile and the
ordinary census launch vector. The verifier requires the instruction manifests'
runtime binding to be exactly `{model: default, effort: default}`, their model
observation to remain `current_default/unavailable/unavailable`, and both launch
vectors to omit `--model` and `--effort`. This proves use of the current
unresolved default without reading UI text, config bodies, or a transcript.

## 4) Regular launch / resume / steer / halt / no-bleed matrix

| Surface | Planned action | Exact expected evidence | Stop criteria |
| --- | --- | --- | --- |
| Launch | `session_profile=regular`, contract-bound fixture, no `--model`/`--effort` | `launch` transitions active, startup settle succeeds, manifest/process/socket/lease identities remain exact | blocked if manifest drift or post-launch process mismatch |
| Plane control | selected instruction plane plus ordinary control | exact one-use sidecar is consumed and unlinked before a hash-only controller observation; checkpoint JSON stays marker-free; built-ins and repo rules remain active | blocked on bleed, replacement, precedence ambiguity, or marker retention |
| Resume | reuse any resume API during same session profile | no supported capability in current contract; resume is treated as unsupported | hard stop; must be supported by explicit resume contract before lane promotion |
| Steer | ordinary follow-up via `send` with initial=False | no slash prefix injected, one delivery event, fixture handoff advances once | blocked if prefix appears in argv or message body |
| Halt | exact process shutdown via adapter halt action | exact pid `SIGINT` sequence, `HALTED`, no process bleed | blocked if process does not stop or registry/tmux evidence changes |
| No-bleed control | ordinary non-Puppet session + ordinary non-Puppet process population | unchanged target population except exactly registered session-owned process set | blocked if any ordinary session is attached or mutated |

## 5) Isolated config strategy

- Use only lane-owned fixture roots for proofs and state:
  - temporary fixture run tree under the lane workspace
  - temporary settings source file and explicit setting source constraints
  - no reads or writes against user global Claude config.
- Set `CLAUDE_CONFIG_DIR` to the exact Puppet-owned private subscription
  profile's config directory and pass lane-owned `--settings` plus
  exact `--setting-sources user,project,local`. `--settings` merges; it is not
  itself an isolation boundary. Managed policy remains higher authority and an
  unexpected conflict blocks qualification.
- Authentication is established only by the human inside that private profile;
  Puppet rechecks its body-free status immediately before target start and
  never copies or inspects credentials. Do not use `--bare`, which prevents
  normal authentication behavior and disables hooks/customizations.
- Do not keep any live command artifacts inside the default user home between runs.

## 6) Required Puppet deltas for this lane

- Implemented source substrate: the additive plane now composes with the exact
  private profile environment and config identity, with create-only artifact
  materialization, immediate auth/identity revalidation, exact rollback, and a
  joined body-free receipt. Activation-lifecycle proof remains non-promotable.
- Implemented startup-gate reducer (live component/session evidence):
  `puppet_lib.claude_startup_gates` is the Claude-only bounded input-readiness
  strategy. Before the initial prompt it captures only the bounded owned pane
  (<= 64 KiB) of the exact registered Claude process, decodes strict UTF-8, and
  classifies it against a fixed allowlist — `security_notice`, an exact-workspace
  `workspace_trust` prompt, `bypass_warning`, or `ready`. It retains only gate,
  selection, byte-size, SHA-256, and timing metadata and never keeps raw bytes
  (`raw_retained` stays false). For the trust prompt it requires the displayed
  workspace path to equal the contract worktree exactly (space-preserving,
  duplicate-label and substring-decoy safe). Where a confirmation is required it
  moves selection to and recaptures the exact authorized `yes` choice (trust
  choice 1, bypass choice 2) before sending Enter. A login/account/terms/
  subscription/OAuth/permission, unknown, ambiguous, oversize, or non-UTF-8
  screen fails closed with no retry, and the reducer is bounded by the Claude
  startup-settle and transition deadlines with hard poll-iteration caps.
  Immediately before delivery, `revalidate_claude_ready_process` re-verifies
  process/pane/executable identity and that the pane is still `ready`. This is
  unit- and integration-tested (`tests/test_puppet_claude_startup_gates.py`,
  including the launch ordering gate -> paste -> submit); it is live
  component/session evidence, not a promoted Pass-B qualification receipt.
- Implemented durable-profile behavior: an enrolled, stable Puppet-owned Claude
  profile may present the `ready` screen immediately on later runs, so the
  reducer reaches `ready` and delivers with no intermediate gate navigation and
  no keys sent. A fresh, un-enrolled profile instead shows the logged-out
  screen, which the reducer classifies as a fail-closed forbidden gate; Puppet
  must not copy auth into it or run an unattended login and may only present the
  one-time human enrollment handoff. This durable/ready-immediate path is live
  component evidence and does not by itself promote the lane.
- Still add and prove immutable `--settings` and `--setting-sources` launch
  deltas when the selected plane requires them.
- Replace help-absence sandbox inference with observed isolated settings/hook
  evidence. Record sanitized `SessionStart` and `InstructionsLoaded` events and
  bind the observed default model to the receipt.
- Materialize per-run files beneath a 0700 lane root as 0600 regular
  non-symlink files; revalidate inode/hash before launch and exact rollback.
- Keep Claude `/loop` and `/goal` evidence in the deferred command map; do not
  make either a regular-baseline gate.
- Add no-bleed regression assertions for fixture-root-only settings handling.

## 7) Blockers and stop criteria

### Experimental matched-control protocol boundary

`scripts/matched_control_experimental.py` defines only a body-free candidate index. It is
not imported by `adapter_manifest.py` or `adapter_lab.py`, every referenced
observation is labeled non-authoritative, and its fixed status is
`forbidden_missing_controller_producer_and_verifier`. A structurally valid
candidate produces no pass/no-bleed verdict. Existing activation-lifecycle
receipts remain non-promotable.

The production Pass-B activation path now consumes a controller-owned
producer/recovery route without widening this candidate validator:

`puppet_lib/matched_control.py` now supplies a narrower compile-only substrate.
It validates the exact Claude additive descriptor, derives an opaque marker from
the controller run identity, injects that marker exactly once into the activated
compiled bytes, and returns only a hash-bound `compiled_binding_only` record.
The record fixes `delivered`, `checkpoint_observed`, `lease_bound`,
`no_bleed_evaluated`, `no_bleed_verified`, `runtime_scan_authorized`,
`promotion_authorized`, and `qualification_authorized` to false, with
`result: not_evaluated`. Its public compiler writes no journal and touches no
runtime. A private probe-owned compiler binds the exact ready request to the
same source-owned marker; qualification still has no consumer.

The same module now revalidates the compiled object from its exact in-memory
bytes and can derive an `activation_plan_join_only` record from the exact
`ActivationPlan`, descriptor, and current doctor-only, unqualified adapter
manifest/implementation/execution-file/exact-mapping tuple. The schema-v2 saved
record is verified only by rebuilding it from those inputs; schema v1 is
rejected, and callers cannot supply a marker or marker digest. It remains
body-free and fixes delivery, runtime scan, checkpoint observation, no-bleed, qualification, and
promotion to false. It intentionally carries no controller, campaign, goal, or
authority claim. The activated live probe consumes this join only through the
fixed controller attestation and one-use reservation path.

`puppet_lib/matched_control_authority.py` provides the source-only pre-delivery
authority stage: it rebuilds the join internally and appends an
idempotent body-free event to a fixed controller-authority journal. The event
contains no marker digest, instruction body, or transcript data, and its public
surface accepts no caller marker, digest, event, or journal. The live probe
requires it before reservation and materialization, while the event still
leaves delivery, runtime scan, qualification, and promotion unauthorized.

1. **Implemented source ordering:** the controller-owned attestation and
   one-use reservation precede materialization, launch, and delivery. No caller
   can supply a marker, digest, binding row, event, or journal.
2. Run two sequential, controller-created Claude fixture sessions under exact
   leases: an activated lane and a distinct ordinary control with the same
   default-model selection and no native plane. Bind full session, target,
   process-birth, lease, workspace, config, and tmux-server identities.
3. **Implemented activated-lane signal lifecycle:** reserve the fixed leaf
   through retained workspace/handoff directory descriptors before delivery;
   after exact ready, validate the internally rederived bytes, unlink before
   journaling, and retain hashes only. After exact halt, rejoin the observation
   and reject any recreated leaf before rollback or receipt. Recovery never
   reuses a reservation and consumes an exact stranded signal only after target
   death. Marker bytes never enter handoff JSON, proof references, transcripts,
   or durable events.
4. Produce exact pre-launch and post-halt target census rows for both sessions.
   Derive protected-population equality and exact control target absence in the
   verifier; do not serialize caller-authored before/after verdicts.
5. Join each terminal halt to the controller halt-control journal, exact target
   process, exact tmux server/pane, terminal target absence, and terminal lease.
   Do not infer halt from `stopped` or `signal_sent` booleans alone.
6. Join activation rollback to its transaction journal and require its terminal
   row to follow the activated halt terminal row. Ordering comes from chained
   controller journal transitions, never a caller-authored event list.
7. Revalidate the current manifest, execution files, adapter/protocol hashes,
   descriptor, config/workspace identities, and interrupted recovery state at
   verification time. Any missing, ambiguous, or mixed run fails closed.
8. The public pair covers the exact controller probe entry path. Direct
   out-of-controller Claude launches remain outside this receipt scope.
9. Keep model/provider facts unavailable. Never select a model to make the
   proof easier.

The source path now exists, but promotion still requires real accepted inputs.
`adapter_lab qualify` continues to reject every activation-only receipt and
every unpaired ordinary-control receipt.

- Hard blockers:
  - No live hook proof yet; the default model remains unqualified.
  - Managed settings or instructions can invalidate assumed isolation or
    sandbox behavior.
  - Resume is unsupported under current source for this lane.
  - Any static path or launch command that injects prompt text in argv.
- Stop criteria:
  - Do not move past static mapping until `session_profile=regular` is proven in fixture with
    launch/steer/halt sequence and explicit no-bleed gate.
  - Keep lane at `mapping` if the default model or every safe instruction-plane
    candidate remains unresolved.

The source-owned marker compiler now uses a fixed one-use sidecar at
`handoffs/.puppet-claude-marker-signal-v1`; marker bytes are forbidden from the
durable ready/follow-up JSON. The binding commits the exact signal protocol and
the activated probe guard opens it relative to retained workspace and
handoff-directory descriptors, validates exact bytes and file identity, unlinks
before journaling, and retains hashes only. The matched-ready contract permits
exactly ready JSON plus this transient leaf, then consumes the leaf before the
follow-up set check. A terminal post-halt recheck and interrupted recovery both
fail closed on missing, drifted, non-source, or recreated signal evidence. This
still authorizes neither delivery, target authorship, scanning, checkpoint
claims, lease ownership, no-bleed, qualification, nor promotion.

The terminal activation receipt now includes the body-free activation
attestation and hash-only signal observation as mandatory proof references.
Standalone receipt verification rebuilds the exact ready request from the
validated ready handoff, rejoins both artifacts to the fixed controller
journals and source-owned activation plan, and requires the terminal state to
retain their exact hashes. Missing, tampered, wrong-authority, or source-drifted
artifacts and a post-observation recreated signal leaf therefore fail before
the existing matched no-bleed qualification fence; this binding does not
itself prove no-bleed or authorize promotion.

`run_observations.py` now emits a create-only
`zero_agent_claude_matched_control_blocker` record from the exact current
matched-control binding, pre-delivery authority, signal observation, probe
integration, and terminal-verifier source hashes. It records every runtime,
model, and checkpoint observation as `unavailable`, fixes the controller
verdict to `blocked`, and keeps launch, delivery, checkpoint, no-bleed,
model-selection, qualification, and promotion authority false. The record
contains no instruction body, marker name or bytes, sidecar path, handoff
content, transcript, configuration, or authentication data and is not consumed
by probe, adapter, session, or qualification paths.

This source-only packet is durable blocker evidence, not a Claude run. The next
irreducible gate remains an authenticated private-profile runtime pair: one
activated fixture followed by a distinct ordinary control under the same
default-model-unavailable tuple.

The public operator plan now projects that source truth without consuming or
constructing an observation. An exact doctor-only, unqualified Claude manifest
emits `waiting_for_human` at `claude_regular_pass_b`, carries the same six
source-only blockers, expects the existing
`zero_agent_claude_matched_control_blocker` kind, and reports no preserved
evidence because no packet was supplied. It proposes only `doctor`; all six
session lifecycle surfaces are unsupported, while private-profile setup remains
a human-gated proposal under
`human_approve_authenticated_claude_matched_control_pair`. The plan reads no
Claude auth/config state and exercises no observation, matched-control,
profile, runtime, process, tmux, or viewer path.

### Public paired qualification sequence

The controller-owned command path is:

1. Run the existing Claude activation probe with `--plane-descriptor`.
2. While that exact run is live, attach one read-only native tmux viewer using
   the run state's controller-produced `attach_command`, then run
   `adapter_lab.py observe-claude-view --proof-root ROOT --run-id ACTIVATION`.
   The create-only observation stores client/process/tmux hashes, joins them to
   the fixed controller journal, and explicitly records that no body capture
   occurred.
3. Run the ordinary Claude probe with no plane descriptor and
   `--paired-activation-receipt ROOT/probes/ACTIVATION/receipt.json`. The
   activation receipt, campaign, goal, controller, profile, and process hash
   become an immutable control-state binding before launch.
4. Capture the same structural read-only view observation for the control run.
5. Run:

   ```text
   adapter_lab.py pair-claude \
     --manifest MANIFEST --mapping MAPPING \
     --activation-receipt ROOT/probes/ACTIVATION/receipt.json \
     --control-receipt ROOT/probes/CONTROL/receipt.json
   ```

   The fixed output is
   `ROOT/probes/CONTROL/claude-paired-receipt.json`. It is emitted only after
   both source receipts reverify; their identities, profile, default selection,
   empty pre/post populations, distinct process/tmux/workspace identities,
   read-only native views, source binding, and controller-ledger order match.
6. Supply only that paired receipt to `adapter_lab.py qualify`.

Recovery of the linked control must repeat
`--paired-activation-receipt` with the same activation receipt. Pair and view
artifacts are create-only. No command captures pane text, prompt/reply bodies,
instruction bodies, config bodies, or auth material.

The bounded startup-gate reducer and durable-profile ready path remain live
component and session evidence for input readiness and enrollment reuse. They do
not stand in for the promoted Pass-B qualification receipt. The remaining work
is the live, human-approved authenticated pair above; source-only code does not
substitute for those inputs.

### 2026-07-26 current-head behavioral checkpoint

At source head `b2ee409b767a4d8fd169238f3ff4cb4e8a7b309e`, the root
controller ran a fresh subscription-backed activation/control pair with Claude
Code `2.1.215`, the durable Puppet-owned profile, the regular session profile,
the current provider default model, and explicit
`--dangerously-skip-permissions`.

Both distinct sessions reached input readiness through
`bounded_claude_startup_gate_reducer` without operator input, produced ready
and follow-up checkpoints, received a real read-only native tmux/iTerm view,
and halted only their exact registered target PIDs. The activation artifact
rolled back, both post-halt target populations were empty, the terminal pair
reported `no_bleed_verified: true`, and `adapter_lab.py verify` independently
accepted the paired receipt. No pane body, prompt body, reply body,
authentication material, or configuration body was retained.

The curated body-free record is
`../live-proof/claude-b2ee409-20260726.json`. It deliberately separates the
live claim—ready was reached through the reducer with no human keystrokes—from
the deterministic gate-specific claim. Unit/integration tests cover security
Enter, exact-workspace trust choice 1, bypass choice 1 to choice 2 followed by
Enter, unknown/account-gate refusal, and same-process/worktree revalidation
before delivery. The specific optional screen sequence for this live run is
not persisted.

This is a behavioral checkpoint, not the final campaign receipt. Any later
change to the qualifying implementation fingerprint requires a fresh
source-stable pair before five-harness closeout.

### 2026-07-27 exact-head paired qualification (controller accepted)

At exact source head `8ecf3a2e1dfcb92687c7e3ebbae1b4ddf4bddb45`, the root
controller personally launched two real subscription-backed Claude Code
`2.1.215` regular sessions through Puppet using the durable isolated Claude
profile, the current provider default model, no `--model`/`--effort` selectors,
and `--dangerously-skip-permissions`. The bounded startup-gate reducer reached
`ready` without operator keystrokes; both members produced ready and sequenced
follow-up checkpoints, each had one structurally observed native read-only
iTerm/tmux viewer with `body_capture_performed=false`, both exact-halted their
owned PIDs, the activation artifact rolled back, protected process baselines
matched, and the paired receipt reports `no_bleed_verified=true`.

The exact structural identities of the accepted pair (derived only from the
private structured artifacts, not from any terminal, prompt, reply, auth, or
config body) are:

- campaign: `puppet-v01-claude-paired-8ecf3a2-20260727`, `result=accepted`,
  controller `codex-root-controller`, attestation ledger sequence 49.
- activation run `claude-activation-8ecf3a2-20260727`: receipt
  `8ee5f5d264262eab21ef67fdc9af3ad3d85a453986d02d2d6c506844bcda2492`, native
  view `e8c2bd721e806ae977dd83122559ca7c20cf1f539e2fe56c220cd85e81a7c879`, plane
  activation `rolled_back` at `activation_lifecycle_only` scope, empty post-halt
  population.
- ordinary control run `claude-control-8ecf3a2-20260727`: receipt
  `4dcfe15082b57f16b99cbd8ecf9ece6fca3805be4962b78488016e433720cc9c`, native
  view `4c75927acb0d2ff62acdcbe2743e33dda6b50664c8444e86159ffd4489525315`, empty
  post-halt population.
- paired receipt
  `d1eabfe460ac656fc70bc462e10128dd8b3079d1d4caa33abe3f18a402bab44f`:
  `no_bleed_verified=true`, distinct processes/sessions/workspaces, two native
  read-only views, `default_model_observation` fixed to
  `{selection: current_default, resolved_identity: unavailable, effort:
  unavailable}`.
- qualified manifest file
  `91a33b5a23211361e8e3d60c68c53bde7b8cf46c315a474bef9a65bf7f2d60d3`,
  independently derived manifest fingerprint
  `636022ff9710b86060740801bdc38ea65366b6b2367b6e5ab499fa9d602d3909`; bound
  fingerprints executable `90608b5c…`, adapter `8c57bc93…`, execution
  `15990cbf…`, protocol `a4e220c27ecfd4b3a28245e4849bad4b9296f192155a2d8b865ca1109d3e1ce9`.

The curated transcript-free record is
`../live-proof/claude-8ecf3a2-20260727.json`. It keeps the layers honest: the
paired qualification above is accepted, but the two later public lifecycles are
still missing. No resolved model identity is claimed, and `/goal`, `/loop`,
resume, and operator-global routes remain deferred, not promoted.

Two distinct lifecycles remain open after this accepted pair:

1. **Public mutating session lifecycle (still missing).** The current
   documentation session (`puppet-claude-public-8ecf3a2-20260727`, run
   `claude-public-mutating-8ecf3a2-20260727`) is the first exact-head public
   mutating lifecycle. It is itself pending controller review and exact halt
   until after its local commit; its checkpoint, tests, acceptance, and halt are
   not pre-claimed here.
2. **Read-only cross-review (still missing).** A distinct cockpit read-only
   cross-review of the accepted pair has not been controller accepted.

Neither missing lifecycle is implied by the accepted pair. Any later change to
the qualifying implementation fingerprint still requires a fresh source-stable
pair before five-harness closeout.
