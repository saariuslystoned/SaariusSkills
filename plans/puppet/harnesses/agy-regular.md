# AGY regular-session qualification lane (updated 2026-07-26)

Parent: regular-lane packet `plans/puppet/codex-goal-regular-qualification.md`.
Scope: static census, authoritative documentation, source/tests inspection, and
fixture/test design. The source now describes a promotable regular route on an
explicit shared-vendor-auth/config basis. Source state is never launch
authority: a fresh Pass B, promotion of its accepted receipt, and a clean
execution-time doctor remain required.

## Current controller verdict: shared-vendor-auth/config regular route

AGY regular sessions launch on an explicit shared-vendor-auth/config route but
are not yet fully qualified. The body-free `regular` verdict reports:

- `status: shared_vendor_auth_config_route`
- `route: shared_vendor_auth_config_route`
- `launch_authorized: true`
- `qualification_authorized: false`
- `agy_fresh_pass_b_required`
- `agy_regular_receipt_promotion_required`
- `agy_clean_doctor_required`

The route runs under the operator's real `HOME` because AGY exposes no
admitted config-root selector; private-profile isolation is explicitly not
claimed. Shared vendor auth/config, tmux-buffer instruction transport with
native `--agent` deferred, an unclaimed provider-default model identity, and
deferred explicit model/effort/resume are accepted limitations rather than
launch gates.

Every authority fence is profile-aware. `regular` is admitted on the shared
route and carries the three source-only blockers. `goal`, `teamwork-preview`,
invalid, and unbound profiles fail closed with the additional
`agy_non_regular_profile_deferred` blocker and cannot borrow regular-session
authority. The user-facing doctor reads only the contract target and rejects a
non-regular profile before manifest, authorization, proof/state-root,
executable, profile, workspace, tmux, process, parallel-override, or
qualification-receipt access. Generic launch rejects a non-regular profile
before doctor, process census, launch-environment construction, or proof/tmux
setup; the Pass-B probe rejects it before mapping validation, fresh census,
process lookup, proof-root creation, or tmux construction. Public qualification
first verifies the receipt, then requires its explicit `session_profile` to be
`regular`, and verifies the qualified manifest again with that explicit
profile. Promotion keeps an unbound profile fenced.

This verdict does not alter status, halt, or recovery for an already registered
Puppet-owned AGY session. Puppet must not inspect, steer, halt, or otherwise
intervene in an ordinary non-Puppet AGY session.

## 1) Exact-version discovery facts vs hypotheses

### Current AGY 1.1.7 controller facts

- Exact executable:
  `/Users/bobbybones/.local/bin/agy`
- SHA-256:
  `48e37ce7ef2db0e8972b6fed36ce866d4b094c587d377029ba7223565f49aed8`
- Exact regular launch argv:
  `/Users/bobbybones/.local/bin/agy --dangerously-skip-permissions
  --sandbox=false --new-project --log-file /dev/null`
- A bounded semantic write, exact executable/birth/cwd lease, read-only native
  attach, sequenced steering, clean head, and exact process-tree halt were
  independently controller-checked through a Puppet-owned private tmux lane.
- Same-user `agy models` succeeded with its body discarded. No auth store was
  copied or inspected.

These facts repair the source route; they are not a reusable qualification
receipt.

### Preserved historical AGY 1.1.5 census facts

- The earlier read-only census recorded:
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

### Current source mapping

- Manifest-derived control mapping (`census_target`):
  - `permission_flags`: [`--dangerously-skip-permissions`]
  - `project_isolation_flags`: [`--new-project`]
  - `sandbox_flags`: [`--sandbox=false`]. Parser acceptance alone cannot
    complete the mapping while omitting this semantic bucket or the exact argv
    token.
  - `sandbox_disable_declared`: true only when exact
    `--sandbox=false help` acceptance, invalid-value rejection, the help
    surface, semantic bucket, and launch argv agree.
  - `project_isolation_declared`: true
  - `prompt_transport`: `interactive_tmux_load_buffer_stdin_declared`
  - `model_flag`: `--model`
  - `effort_flag`: `--effort`
  - `session_profiles`: `regular=""`, `goal="/goal"`, `teamwork-preview="/teamwork-preview"`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - `launch_argv`: exact resolved executable plus the live-proved regular tail
    `--dangerously-skip-permissions --sandbox=false --new-project --log-file
    /dev/null` (no `--model`/`--effort`, and `--log-file` pinned to
    `/dev/null`).
  - declared capabilities map currently `declared` for launch/send/status/wait/checkpoint/resume/halt
    but manifest is `doctor_only: true` until qualification/receipt.
- Live-proved regular launch route (`puppet_lib.agy_launch`):
  - Runs on the shared vendor auth/config route under the operator's real
    `HOME`; `validate_agy_regular_launch_params` fails closed on any private
    `profile_root` claim, on non-regular profiles, on explicit `--model`/
    `--effort`, on omission or drift of `--sandbox=false`, on `--agent`, on a
    non-`/dev/null` log destination, and on reordered, duplicated, extra, or
    slash-prefixed argv.
  - `run_agy_status_preflight` runs a body-free `agy models` preflight before
    start under the exact closed target environment and cwd, discarding raw
    stdout/stderr. Its binding joins executable identity, same-user account
    `HOME` identity, cwd, argv hash, environment names/fingerprint, and status.
    All are rebuilt immediately before target exec; drift fails closed.
  - Pre-start shared-auth revalidation re-derives the executable
    device/inode/SHA-256 before the second status probe and fails closed on any
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
- The historical 1.1.5 `agy models` observation emitted:
  `gemini-3.6-flash-high`, `gemini-3.6-flash-medium`, `gemini-3.6-flash-low`,
  `gemini-3.5-flash-high`, `gemini-3.5-flash-medium`, `gemini-3.5-flash-low`,
  `gemini-3.1-pro-high`, `gemini-3.1-pro-low`, `claude-sonnet-4-6`,
  `claude-opus-4-6-thinking`, `gpt-oss-120b-medium`.

### Hypotheses / evidence gaps

- The provider default is used when `--model/--effort` are omitted, but its
  identity remains intentionally unclaimed.
- Parser acceptance alone remains insufficient: exact `--sandbox=false` must
  stay joined to the semantic bucket, launch argv, admitted environment, and
  fresh Pass-B receipt.
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

## 3) Optional future default-model observation

The current regular route does not claim the provider-default model identity.
The following remains a separate future proof design:

1. Build isolated conformance fixture root and prompt fixture only.
2. Use `session_profile=regular` in contract and omit `--model`/`--effort` in launch command.
3. Require first checkpoint/handoff artifact to include an explicit resolved model record if AGY exposes it via the
   proven conformance envelope; this is part of live evidence and may require a source delta if it is currently absent.
4. If absent, retain the accepted
   `agy_provider_default_model_identity_unclaimed` limitation. Any explicit
   model-selection variant requires separate qualification.

## 4) Future regular qualification matrix (not executable)

| Surface | Planned action | Expected evidence | Stop criteria |
|---|---|---|---|
| Launch | `regular` profile, one isolated fixture root, pre-verified manifest | launch intent, activation, startup settle (8.0s), target identity stable after settle, registered pane | Pass to `ACTIVE` with exact manifest/process/tmux identity |
| Launch | omitted or explicit `session_profile` | canonical contract resolves both to `regular` | Pass only when both forms bind the same effective contract identity |
| Resume | `resume` API invocation under regular profile | explicit refusal unless capability is requalified | Block and record as `unsupported` unless runtime contract changes |
| Steer | follow-up via `send` with ordinary text (`initial=False`) | one `send` delivery, no extra prefix injection | Pass if plain message accepted; no profile-prefix in follow-up |
| Halt | graceful stop with EOF behavior | one EOF when target transitions to stopped, exactly once on already-complete target | Pass if no false repeated halt attempts and no target overrun |
| No-bleed control | ordinary AGY session not owned by this lease | exact private socket/process evidence before and after the Puppet lane | Pass only if the protected ordinary socket/process identity remains running and unchanged |

## 5) Isolated config-root strategy

- Regular AGY lane must run in an isolated fixture candidate root (`worktree`, `proof_root`, `state_root`).
- No fixture may read or mutate live `agy` global config/home artifacts.
- Google documents a useful native split: AGY stores subscription tokens in the
  operating system's secure keyring and silently reuses a valid keyring profile,
  while persistent preferences live at
  `~/.gemini/antigravity-cli/settings.json`. This means Puppet should reuse the
  operator's keyring rather than copy credentials or force a second login.
- The preserved 1.1.5 help snapshot exposed no AGY config-root control, and the
  current 1.1.7 route admits no such selector. The compatible Gemini CLI's
  `GEMINI_CLI_HOME` is design input only and cannot be borrowed by name.
- The accepted resolution is the explicit shared-vendor-auth/config route: the
  regular launch runs under the operator's real `HOME` and uses same-user
  shared vendor auth/config without inspecting its store; Puppet claims no
  private-profile isolation. Puppet still does not copy credentials, force a
  second login, or write global config. It pins the closed launch environment's
  `HOME` to the same-user account HOME and binds that directory identity to the
  status probe and target launch.
- `--sandbox=false` is required in the semantic bucket and exact launch argv;
  parser acceptance alone is not authority. `--new-project` proves project
  selection only. Neither creates private config isolation.
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
- Retain provider-default model identity as unclaimed unless a separate
  observation route is qualified.
- Make resume outcome explicit in capability proof (currently not promoted by resume contract).
- Extend instruction-plane testing for AGY to prove workspace/per-run-plane precedence before allowing any mixed-plane defaulting.
- Extend no-bleed proof so ordinary AGY session/process is never modified by non-owned lanes.

## 7) Blockers and stop criteria for this lane

- Hard blockers:
  - `/goal` and `/teamwork-preview` must remain deferred and not promoted by this lane.
  - No launch/modify path may write or mutate live AGY global configs; the
    shared route uses same-user vendor auth/config and real `HOME` without
    inspecting the store or claiming private isolation.
  - No launch may claim YOLO completeness merely from parser acceptance or
    while omitting `--sandbox=false` from either semantic bucket or exact argv.
  - Provider-default model identity, explicit model/effort, resume, and native
    `--agent` remain accepted/deferred limitations, not regular-route claims.
- Stop criteria:
  - the current lane admits the regular shared-vendor-auth/config route as
    launch-authorized but withholds a promoted qualification receipt; it makes
    no fully-qualified claim.
  - the qualification fence may be removed only by a fresh accepted Pass B,
    explicit regular-profile promotion, and clean doctor. Pass B must show
    `launch -> steer -> halt` plus controller-observed exact private
    socket/process no-bleed evidence for an ordinary non-Puppet session.
