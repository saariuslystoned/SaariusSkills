# AGY regular-session qualification lane (updated 2026-07-26)

Parent: regular-lane packet `plans/puppet/codex-goal-regular-qualification.md`.
Scope: static census, authoritative documentation, source/tests inspection, and
fixture/test design. The regular route is now launch-authorized at the source
level on an explicit shared-vendor-auth/config basis; full qualification (a
promoted Pass-B receipt) is still pending and no promoted qualification receipt
is claimed here.

## Current controller verdict: shared-vendor-auth/config regular route

AGY regular sessions launch on an explicit shared-vendor-auth/config route but
are not yet fully qualified. The body-free `regular` verdict reports:

- `status: shared_vendor_auth_config_route`
- `route: shared_vendor_auth_config_route`
- `launch_authorized: true`
- `qualification_authorized: false`
- `agy_config_root_isolation_unproved`
- `agy_sandbox_off_unproved`
- `agy_native_instruction_plane_unqualified`
- `agy_default_model_unobserved`
- `agy_ordinary_session_no_bleed_unproved`

The route runs under the operator's real `HOME` because AGY exposes no
config-root selector; private-profile isolation is explicitly not claimed. The
five blockers are now qualification limitations, not launch fences: launch is
authorized, but a promoted qualification receipt is withheld until config-root
isolation, sandbox-off behavior, a native instruction plane, the default model,
and ordinary-session no-bleed are independently proved.

Every authority fence is profile-aware. `regular` is admitted on the shared
route and carries the five qualification blockers. `goal`, `teamwork-preview`,
invalid, and unbound profiles fail closed with the additional
`agy_non_regular_profile_deferred` blocker and cannot borrow regular-session
authority. The user-facing doctor reads only the contract target and rejects a
non-regular profile before manifest, authorization, proof/state-root,
executable, profile, workspace, tmux, process, parallel-override, or
qualification-receipt access. Generic launch rejects a non-regular profile
before doctor, process census, launch-environment construction, or proof/tmux
setup; the Pass-B probe rejects it before mapping validation, fresh census,
process lookup, proof-root creation, or tmux construction; and qualification and
manifest promotion reject a non-regular or fallback-wrapper receipt. Promotion
keeps an unbound profile fenced until a receipt is verified through a separately
authorized path.

This verdict does not alter status, halt, or recovery for an already registered
Puppet-owned AGY session. Puppet must not inspect, steer, halt, or otherwise
intervene in an ordinary non-Puppet AGY session.

## 1) Exact-version discovery facts vs hypotheses

### Facts (from read-only census + source/tests)

- Executable discovered by `census_target`/command checks:
  - Requested path: `agy` (the exact operator-local absolute path is retained
    in the machine-private lane proof)
  - SHA-256: `6509d6ca54a66e3eaf61dfe35308ba1dfa1e6b552ef5c4f5f861562c6811ecaf`
  - `--version` output: `1.1.5`
  - `version_sha256`: `1c60df040a80b6d2e3f56442b17d127d8620cd773873e6e1353362f989b1deca`
  - `--help` SHA-256: `b208f7290114292858a1944ac90349bcd1f75168eb85c76ac40c8208cea342f5`
  - `--help` reports:
    - `--dangerously-skip-permissions`
    - `--model`
    - `--effort`
    - `--new-project`
    - `--sandbox`
    - `--agent`
    - `--add-dir`
    - `--continue`
    - `--conversation`
- Manifest-derived control mapping (`census_target`):
  - `permission_flags`: [`--dangerously-skip-permissions`]
  - `project_isolation_flags`: [`--new-project`]
  - `sandbox_flags`: `[]`. The live-proved regular launch route binds an empty
    sandbox semantic bucket.
  - `sandbox_disable_declared`: true only at the parser/declaration layer. The
    zero-agent census requires exact `--sandbox=false help` acceptance and
    rejects `--sandbox=puppet-invalid help`; Google documents that command-line
    overrides supersede persistent preferences and that
    `enableTerminalSandbox` is a boolean setting. That acceptance is parser-only
    and carries no launch authority: the regular launch validator rejects
    `--sandbox=false` in argv, and runtime sandbox-off semantics remain part of
    the later conformance probe and do not clear the `agy_sandbox_off_unproved`
    qualification blocker by themselves.
  - `project_isolation_declared`: true
  - `prompt_transport`: `interactive_tmux_load_buffer_stdin_declared`
  - `model_flag`: `--model`
  - `effort_flag`: `--effort`
  - `session_profiles`: `regular=""`, `goal="/goal"`, `teamwork-preview="/teamwork-preview"`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - `launch_argv`: exact resolved executable plus the live-proved regular tail
    `--dangerously-skip-permissions --new-project --log-file /dev/null` (no
    `--sandbox=false`, no `--model`/`--effort`, and `--log-file` pinned to
    `/dev/null`).
  - declared capabilities map currently `declared` for launch/send/status/wait/checkpoint/resume/halt
    but manifest is `doctor_only: true` until qualification/receipt.
- Live-proved regular launch route (`puppet_lib.agy_launch`):
  - Runs on the shared vendor auth/config route under the operator's real
    `HOME`; `validate_agy_regular_launch_params` fails closed on any private
    `profile_root` claim, on non-regular profiles, on explicit `--model`/
    `--effort`, on `--sandbox=false`, on `--agent`, on a non-`/dev/null` log
    destination, and on reordered, duplicated, extra, or slash-prefixed argv.
  - `run_agy_status_preflight` runs a body-free `agy models` preflight before
    start, discarding raw stdout/stderr and retaining only a route/status
    marker; a non-zero or failed invocation fails closed.
  - `verify_agy_executable_not_updated` re-derives the executable
    device/inode/SHA-256 immediately before start and fails closed on any
    auto-updater replacement race between preflight and launch.
- Source evidence at the admitted lane base:
  - `profiles.default_session_profile("agy")` returned `"teamwork-preview"`.
    Integration commit `45f728f` changed the default to `regular` and made the
    resolved profile part of canonical contract identity.
  - `Adapter.envelope()` allows exactly one native profile prefix on initial send,
    rejects caller-supplied slash-prefixes (`/goal`, `/teamwork-preview`, `/btw`, `/side`) on follow-ups.
  - AGY graceful halt action is `tmux_pane_eof` (twice if still alive).
  - The adapter statically constructs the regular profile shape, but that shape
    grants no launch authority. Omitted and explicit
    `session_profile: regular` contracts canonicalize to the same identity;
    `/teamwork-preview` is retained only as a deferred explicit mapping.
- Model list command discovered: `agy models` currently emits:
  `gemini-3.6-flash-high`, `gemini-3.6-flash-medium`, `gemini-3.6-flash-low`,
  `gemini-3.5-flash-high`, `gemini-3.5-flash-medium`, `gemini-3.5-flash-low`,
  `gemini-3.1-pro-high`, `gemini-3.1-pro-low`, `claude-sonnet-4-6`,
  `claude-opus-4-6-thinking`, `gpt-oss-120b-medium`.

### Hypotheses / evidence gaps

- Default model and default effort when `--model/--effort` are omitted are not proved by static census.
- The regular route binds no sandbox flag. Exact parser acceptance and
  documented preference precedence keep `--sandbox=false` a parser-only
  negative-override candidate with no launch authority, and no Puppet
  conformance run has yet independently observed any runtime sandbox-off effect.
- Real-world runtime effects of `goal` and `teamwork-preview` profile commands for this lane are deferred
  (must not be enabled/qualified here).
- Runtime resume behavior remains unsupported for regular lane planning unless a dedicated resume contract is
  added and proven.
- `AGY` workspace/repository addendum and additive per-run native instruction plane behavior are not proven.

## 2) Instruction planes for AGY regular lane

`session_profile=regular` is Puppet's lifecycle selection and produces an
unprefixed message. It is not one of the three instruction planes.

### Plane 1: session-selected harness-global Puppet addendum (documented candidate, blocked)
- Exact help exposes `--agent`; official AGY custom-agent documentation places
  global agents at `~/.gemini/config/agents/<name>/agent.md`.
- Exact help exposes no config-root selector. Puppet must not write the live
  global location or copy/read authentication material to manufacture an
  isolated home.
- This plane remains hard-disabled until native activation, precedence,
  authentication-preserving isolation, and rollback are controller-proved.

### Plane 2: workspace/repository addendum plane (documented candidate, unqualified)
- Official AGY documentation places workspace custom agents at
  `.agents/agents/<name>/agent.md`, selectable through `--agent`. Operator field
  work separately indicates worktree `AGENTS.md` wording materially affects
  AGY/Gemini behavior.
- `puppet_lib.instruction_planes` now owns one exact AGY 1.1.5 descriptor:
  `.agents/agents/puppet-<rendered-sha>/agent.md`, create-only under the
  workspace root, with planned `--agent puppet-<rendered-sha>`. Its status is
  factual but `activation: disabled`; exact validation rejects global/config
  roots, unnamespaced paths, selector drift, activation changes, and blocker
  removal.
- `puppet_lib.agy_workspace_plane` now supplies a source-only, body-free join
  from that descriptor to the shipped compiler bytes/manifest, exact Pass-B
  contract/run identities, a current-UID `0700` workspace root recaptured by
  no-follow directory descriptors, the exact current doctor manifest and
  adapter/protocol/execution tuple, and the immutable regular-session verdict.
  Its public record fixes materialization, activation, launch, and
  qualification authority to false. No launcher, materializer, probe, session,
  or qualification consumer accepts it.
- A fixture must use a Puppet-namespaced custom agent, add only scoped
  orchestration guidance without replacing repository authority, and prove
  selector behavior, discovery order, built-in retention, and cleanup.

### Plane 3: additive per-run system instruction / native equivalent (unknown)
- No supported additive system-instruction flag or file transport was found in
  exact-version help.
- The ordinary task prompt is not sufficient to claim a native instruction
  plane. Keep this candidate unsupported unless a native additive path is
  proved without putting instruction bodies in argv.

## 3) Future default-model observation gate

The following is a future proof design, not an executable Puppet path:

1. Build isolated conformance fixture root and prompt fixture only.
2. Use `session_profile=regular` in contract and omit `--model`/`--effort` in launch command.
3. Require first checkpoint/handoff artifact to include an explicit resolved model record if AGY exposes it via the
   proven conformance envelope; this is part of live evidence and may require a source delta if it is currently absent.
4. If absent, classify as `model_unknown` blocker and promote a separate model-observation variant with explicit
   model selection (`--model` from `agy models`) before this lane can be promoted as regular-default complete.

## 4) Future regular qualification matrix (not executable)

| Surface | Planned action | Expected evidence | Stop criteria |
|---|---|---|---|
| Launch | `regular` profile, one isolated fixture root, pre-verified manifest | launch intent, activation, startup settle (8.0s), target identity stable after settle, registered pane | Pass to `ACTIVE` with exact manifest/process/tmux identity |
| Launch | omitted or explicit `session_profile` | canonical contract resolves both to `regular` | Pass only when both forms bind the same effective contract identity |
| Resume | `resume` API invocation under regular profile | explicit refusal unless capability is requalified | Block and record as `unsupported` unless runtime contract changes |
| Steer | follow-up via `send` with ordinary text (`initial=False`) | one `send` delivery, no extra prefix injection | Pass if plain message accepted; no profile-prefix in follow-up |
| Halt | graceful stop with EOF behavior | one EOF when target transitions to stopped, exactly once on already-complete target | Pass if no false repeated halt attempts and no target overrun |
| No-bleed control | ordinary AGY session not owned by this lease | state isolation + no mutation by Puppet sends/halts on non-registered process | Pass only if ordinary session remains running and unmodified |

## 5) Isolated config-root strategy

- Regular AGY lane must run in an isolated fixture candidate root (`worktree`, `proof_root`, `state_root`).
- No fixture may read or mutate live `agy` global config/home artifacts.
- Google documents a useful native split: AGY stores subscription tokens in the
  operating system's secure keyring and silently reuses a valid keyring profile,
  while persistent preferences live at
  `~/.gemini/antigravity-cli/settings.json`. This means Puppet should reuse the
  operator's keyring rather than copy credentials or force a second login.
- AGY exposes no explicit `agy` config-root CLI control in the exact 1.1.5
  `--help`, so private config isolation is not achievable. The compatible Gemini
  CLI's `GEMINI_CLI_HOME` is design input only: that selector is absent from the
  exact AGY 1.1.5 binary surface and cannot be borrowed by name.
- The accepted resolution is the explicit shared-vendor-auth/config route: the
  regular launch runs under the operator's real `HOME` and reuses the native
  vendor keyring, and Puppet claims no private-profile isolation. Puppet still
  does not copy credentials, force a second login, or write global config, and
  does not override `HOME`, because that could change authentication and
  unrelated state.
- `--sandbox=false` is parser-only and carries no launch authority; the regular
  route binds an empty sandbox bucket. `--new-project` proves project selection
  only. Neither closes config isolation or live sandbox-off semantics.
- No fixture may read or mutate global config beyond this shared-auth keyring
  reuse, and no config-root override may cross targets.

### Adjacent PR #6 evidence

[SaariusSkills PR #6](https://github.com/saariuslystoned/SaariusSkills/pull/6)
records fresh AGY 1.1.5 print sessions from a disposable workspace, including
direct fanout, nested 2x2, and two nested 4x4 smoke passes, while unrelated
operator AGY sessions remained untouched. Those successful model calls are
operator-specific evidence that the already-authorized native subscription can
serve fresh sessions without copying an auth profile. The packet does not bind
auth status, global-config reads, sandbox-off semantics, or Puppet's private
runtime tuple, so it is admitted here as route evidence rather than a launch or
qualification receipt.

## 6) Implemented source fence and future deltas

- Preserve and test integration commit `45f728f`, which makes `regular` the
  canonical default and prevents implicit `teamwork-preview` selection.
- Keep the profile-aware fences in place: admit `regular` on the shared route,
  fail non-regular and fallback-wrapper profiles closed, and withhold a promoted
  qualification receipt until every blocker above is independently closed.
- Preserve the source-only compiler/workspace binding as provenance only. It
  must continue to rederive workspace inode identity and the regular verdict on
  every record read, and must not become an admitted launch plan while config
  isolation and live sandbox-off semantics remain absent.
- A detection-only population classifier now retains every current-UID process
  with the fixed `agy` basename before splitting candidates by the exact
  current-manifest runtime path/device/inode. A same-name different-version or
  different-vnode process remains a mismatched hard blocker and cannot be
  hidden by a parallel override. The classifier is wired only behind the
  unconditional contract-first AGY doctor/launch fence; it reads no argv,
  config, transcript, credential, or session-store content and grants no
  runtime authority. This source primitive does not by itself prove no-bleed.
- Add explicit regular-plane fixture proving steps for
  `session_profile=regular` only after a separately reviewed source change
  makes the live proof lane eligible.
- Add explicit model-observation handling (or explicit-block strategy) for omitted `--model`.
- Make resume outcome explicit in capability proof (currently not promoted by resume contract).
- Extend instruction-plane testing for AGY to prove workspace/per-run-plane precedence before allowing any mixed-plane defaulting.
- Extend no-bleed proof so ordinary AGY session/process is never modified by non-owned lanes.

## 7) Blockers and stop criteria for this lane

- Hard blockers:
  - `/goal` and `/teamwork-preview` must remain deferred and not promoted by this lane.
  - No launch/modify path may write or mutate live AGY global configs; the
    shared route reuses the native keyring and real `HOME` without claiming
    private isolation.
  - No launch may claim YOLO completeness merely from parser acceptance;
    sandbox-off still must be observed for the exact run.
  - Default model/effect remains unresolved without live default-observation evidence.
- Stop criteria:
  - the current lane admits the regular shared-vendor-auth/config route as
    launch-authorized but withholds a promoted qualification receipt; it makes
    no fully-qualified claim.
  - a future lane may remove the qualification fence only after one native
    instruction plane wins, config and sandbox isolation are exact, the default
    model is observed, and regular lifecycle shows clean `launch -> steer ->
    halt` plus an ordinary non-Puppet no-bleed control and explicit
    unsupported-resume handling.
