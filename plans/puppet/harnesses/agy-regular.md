# AGY regular-session qualification lane (2026-07-22)

Parent: regular-lane packet `plans/puppet/codex-goal-regular-qualification.md`.
Scope: static census, authoritative documentation, source/tests inspection, and
fixture/test design only. No live target launch in this lane.

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
  - AGY regular profile launch is supported by adapter shape. Omitted and
    explicit `session_profile: regular` contracts canonicalize to the same
    identity; `/teamwork-preview` is retained only as a deferred explicit
    mapping.
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
- A fixture must use a Puppet-namespaced custom agent, add only scoped
  orchestration guidance without replacing repository authority, and prove
  selector behavior, discovery order, built-in retention, and cleanup.

### Plane 3: additive per-run system instruction / native equivalent (unknown)
- No supported additive system-instruction flag or file transport was found in
  exact-version help.
- The ordinary task prompt is not sufficient to claim a native instruction
  plane. Keep this candidate unsupported unless a native additive path is
  proved without putting instruction bodies in argv.

## 3) Default-model observation plan

1. Build isolated conformance fixture root and prompt fixture only.
2. Use `session_profile=regular` in contract and omit `--model`/`--effort` in launch command.
3. Require first checkpoint/handoff artifact to include an explicit resolved model record if AGY exposes it via the
   proven conformance envelope; this is part of live evidence and may require a source delta if it is currently absent.
4. If absent, classify as `model_unknown` blocker and promote a separate model-observation variant with explicit
   model selection (`--model` from `agy models`) before this lane can be promoted as regular-default complete.

## 4) Regular matrix (launch / resume / steer / halt / no-bleed)

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

## 6) Required Puppet source deltas for this lane

- Preserve and test integration commit `45f728f`, which makes `regular` the
  canonical default and prevents implicit `teamwork-preview` selection.
- Add explicit regular-plane fixture proving steps for `session_profile=regular` in source.
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
  - one native instruction plane must win or the harness must fail closed;
    regular lifecycle must show clean `launch -> steer -> halt` and a no-bleed
    control, plus explicit handling for unsupported resume.
