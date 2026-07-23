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

### Hypotheses / evidence gaps

- Static census cannot resolve the default model. A sanitized `SessionStart`
  hook exposes the selected model, source, permission mode, and cwd without
  reading a transcript. Effective effort is not exposed and remains
  `unavailable`.
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

## 3) Default-model observation plan

1. Use a unique lane-owned `CLAUDE_CONFIG_DIR`, a deterministic technical
   settings file, and `--setting-sources user,project,local`.
2. Run the interactive regular TUI with no explicit `--model` or `--effort`.
3. A controller-owned `SessionStart` hook records only session ID, source,
   model, permission mode, cwd, and optional agent type. It discards transcript
   paths and emits no output.
4. Record the observed model exactly and effort as `unavailable`; never pin a
   different model merely because the default is opaque.

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

The next implementation must add one controller-owned producer/verifier route,
not widen this candidate validator:

`puppet_lib/matched_control.py` now supplies a narrower compile-only substrate.
It validates the exact Claude additive descriptor, derives an opaque marker from
the controller run identity, injects that marker exactly once into the activated
compiled bytes, and returns only a hash-bound `compiled_binding_only` record.
The record fixes `delivered`, `checkpoint_observed`, `lease_bound`,
`no_bleed_evaluated`, `no_bleed_verified`, `runtime_scan_authorized`,
`promotion_authorized`, and `qualification_authorized` to false, with
`result: not_evaluated`. It writes no journal, touches no runtime, and is not
wired into probe or qualification. This closes only the source-owned marker
compilation/body-retention gap; every runtime join below remains required.

The same module now revalidates the compiled object from its exact in-memory
bytes and can derive an `activation_plan_join_only` record from the exact
`ActivationPlan`, descriptor, and current doctor-only, unqualified adapter
manifest/implementation/execution-file/exact-mapping tuple. The schema-v2 saved
record is verified only by rebuilding it from those inputs; schema v1 is
rejected, and callers cannot supply a marker or marker digest. It remains
body-free and fixes delivery, runtime scan, checkpoint observation, no-bleed, qualification, and
promotion to false. It intentionally carries no controller, campaign, goal, or
authority claim. This is a source substrate only and the live probe does not
consume it.

`puppet_lib/matched_control_authority.py` provides the source-only pre-delivery
authority stage: it rebuilds the join internally and appends an
idempotent body-free event to a fixed controller-authority journal. The event
contains no marker digest, instruction body, or transcript data, and its public
surface accepts no caller marker, digest, event, or journal. It explicitly
leaves delivery, runtime scan, qualification, and promotion unauthorized. The
live probe still does not consume the attestation.

1. Wire the controller-owned pre-delivery attestation into the probe's ordering
   before materialization/delivery. Do not accept an arbitrary marker, digest,
   binding row, or journal from a caller.
2. Run two sequential, controller-created Claude fixture sessions under exact
   leases: an activated lane and a distinct ordinary control with the same
   default-model selection and no native plane. Bind full session, target,
   process-birth, lease, workspace, config, and tmux-server identities.
3. Prepare the fixed one-use signal leaf through a retained workspace directory
   descriptor before delivery. After the ready handoff, open the exact sidecar
   with no-follow semantics, validate the internally rederived marker bytes,
   unlink it before journaling, and persist hashes only. Never put marker bytes
   in a handoff, proof reference, transcript, or durable event.
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
8. Qualify direct and cockpit entry modes as separate matched pairs. The current
   candidate may name either mode only to plan evidence; it proves neither.
9. Keep observed model/provider facts symbolic and unqualified until the live
   sanitized controller hook is journal-joined. Never select a model to make the
   proof easier.

Only after that producer and verifier exist may a new receipt scope be proposed
for `adapter_lab qualify`; the current command must continue rejecting every
activation receipt.

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
the controller must later open it relative to a retained workspace directory
descriptor, validate exact bytes and file identity, unlink it before journaling,
and retain hashes only. This compile protocol is not wired into the probe and
does not yet authorize delivery, scanning, checkpoint claims, no-bleed,
qualification, or promotion. A later conformance-contract version must allow
the one-use signal explicitly and consume it before the exact handoff-set check.
