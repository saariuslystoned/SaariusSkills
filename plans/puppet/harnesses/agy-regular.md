# AGY regular-session qualification lane (2026-07-22)

Parent: regular-lane packet `plans/puppet/codex-goal-regular-qualification.md`.
Scope: static census, authoritative documentation, source/tests inspection, and
fixture/test design only. No live target launch in this lane.

## Current controller verdict: unsupported planner-only

AGY regular sessions are not launchable or qualifiable in Puppet. The pure
controller verdict is body-free and always reports:

- `launch_authorized: false`
- `qualification_authorized: false`
- `agy_config_root_isolation_unproved`
- `agy_sandbox_off_unproved`
- `agy_native_instruction_plane_unqualified`
- `agy_default_model_unobserved`
- `agy_ordinary_session_no_bleed_unproved`

These blockers are immutable for this baseline. An exact parallel-process
override cannot clear them. The user-facing doctor reads only the contract
target and then rejects AGY through the same pure authority fence, before
manifest, authorization, proof/state-root, executable, profile, workspace,
tmux, process, parallel-override, or qualification-receipt access. Generic
session launch rejects AGY before doctor, process census, launch-environment
construction, proof/tmux setup, or target callbacks. Pass-B probe rejects AGY
before mapping validation, fresh census, process lookup, proof-root creation,
or tmux construction. Qualification and manifest promotion reject AGY even if
supplied a fallback-wrapper receipt.

Every authority fence is now profile-aware. `regular` receives the five
regular blockers; `goal`, `teamwork-preview`, invalid, and unbound profiles
receive the additional `agy_non_regular_profile_deferred` blocker and cannot
borrow any future regular-session authority. Promotion keeps an unbound profile
fenced until a receipt has been verified through a separately authorized path.
This does not qualify any command profile.

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
  - `--help` SHA-256: `61c94e66fc8e651d997c51989dfe411559ebff4630301daa20d41bf8b6d71d88`
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
  - `sandbox_disable_declared`: false. `--sandbox` enables terminal
    restrictions, while a persistent `enableTerminalSandbox` setting can also
    enable them; omission is not a controller proof of sandbox-off.
  - `project_isolation_declared`: true
  - `prompt_transport`: `interactive_tmux_load_buffer_stdin_declared`
  - `model_flag`: `--model`
  - `effort_flag`: `--effort`
  - `session_profiles`: `regular=""`, `goal="/goal"`, `teamwork-preview="/teamwork-preview"`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - `launch_argv`: exact resolved executable plus
    `--dangerously-skip-permissions --new-project`
  - declared capabilities map currently `declared` for launch/send/status/wait/checkpoint/resume/halt
    but manifest is `doctor_only: true` until qualification/receipt.
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
- During this lane’s static work, AGY config isolation remains a required TODO because no explicit
  `agy` config-root CLI control is proven from current `--help`.
- Source delta required before live execution: a proved native isolated config
  mechanism or a fail-closed unsupported verdict. Do not assume overriding
  `HOME` is safe because it may also change authentication and unrelated state.
- A native negative sandbox override is also required. `--new-project` proves
  project selection only; it does not neutralize the persistent sandbox setting.
- Any config-root override must remain per-lane and never cross-target.

## 6) Implemented source fence and future deltas

- Preserve and test integration commit `45f728f`, which makes `regular` the
  canonical default and prevents implicit `teamwork-preview` selection.
- Keep the pure AGY verdict and the unconditional doctor, launch, probe, and
  qualification fences in place until every blocker above is independently
  closed.
- Preserve the source-only compiler/workspace binding as provenance only. It
  must continue to rederive workspace inode identity and the regular verdict on
  every record read, and must not become an admitted launch plan while config
  isolation and a positive sandbox-off control remain absent.
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
  - No launch/modify path may touch live AGY configs/home.
  - No launch may claim YOLO completeness until sandbox-off is positively
    proved for the exact isolated run.
  - Default model/effect remains unresolved without live default-observation evidence.
- Stop criteria:
  - the current lane stops at the planner-only unsupported verdict; it makes no
    live or qualified claim.
  - a future lane may remove the fence only after one native instruction plane
    wins, config and sandbox isolation are exact, the default model is observed,
    and regular lifecycle shows clean `launch -> steer -> halt` plus an ordinary
    non-Puppet no-bleed control and explicit unsupported-resume handling.
