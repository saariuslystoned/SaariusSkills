# Cursor Agent regular-session qualification harness (v0.1)

## Scope and lane contract

- File purpose: planning and static fixture design for Cursor Agent regular-session qualification under
  `codex-goal-regular-qualification.md`.
- Branch in scope: `codex/puppet-regular-cursor-20260722`.
- Objective: map exact Cursor Agent regular-session behavior for the three instruction planes for this
  installed tuple, and define deterministic isolated evidence and source deltas so the lane can later be
  qualified with no transcript bleed.

## 1) Exact-version discovery: facts vs hypotheses

### Facts observed

- Executable discovery by command census:
  - `cursor-agent` resolves through an operator-local symlink to a 1,074-byte
    versioned shell launcher. That launcher `exec`s a bundled Node binary plus
    `index.js`; launcher and runtime process identity are distinct.
- Version / help hashes:
  - `cursor-agent --version` -> `2026.07.17-3e2a980`
  - executable SHA-256: `eed61c5224668c9236334c4c68936a16aecc37374b592f59e31eb50433817831`
  - bundled Node SHA-256:
    `336b5b3ebc5deb86df842102b20b6e4761605b7a667823e68dda7761b91a161b`
  - bundled `index.js` SHA-256:
    `f45ce0860ce8c282110c2f8cfc04e0e8d8b3bc6a83ad01fcded0b5916e1e3a6e`
  - version text SHA-256: `ff67fa8c4d173904e13f0da944d7f763f5399ec48052b81c1ae3c7d87f118f4a`
  - `cursor-agent --help` SHA-256: `bb2aed29e46b3c80635858d2181c140985dbf9f6a96d788f1b6a8adbb0d725af`
- `census_target('cursor', adapter_implementation_fingerprint())` (`protocol_fingerprint: a09805b247b6dcdaad8a7d45e8c29c2c4742c8dcce65283f853953c679590aab`):
  - `permission_flags`: `["--yolo"]`
  - `project_isolation_flags`: `[]`; the current `all([])` result is a vacuous
    truth and not isolation proof. A typed absolute `--workspace` selector is
    required before live launch.
  - `sandbox_disable_declared`: `true` (`--sandbox disabled`)
  - `model_flag`: `--model`
  - `session_profiles`: `{"regular": ""}`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - `launch_argv`: shell launcher plus `--yolo --sandbox disabled`; this is not
    launch-ready because it omits the absolute workspace selector and the live
    process becomes bundled Node after `exec`.
  - capabilities declared: `launch/send/status/wait/checkpoint/resume/halt` = `declared`
  - manifest state: `doctor_only = true` until qualified
  - `adapter_fingerprint` matches other lanes:
    `dff76b92ab1ecea857a67118424fc9109b5ff2f7066e50f9595bc6c086076d6b`
- `cursor-agent --help` confirms:
  - command format is `agent [options] [command] [prompt...]`
  - notable supported features for this lane: `--yolo`, `--model`, `--resume`, `--continue`,
    `--workspace`, `--add-dir`, `-w/--worktree`, `--worktree-base`, `--list-models`, `generate-rule|rule`
- `cursor-agent models` output first lines:
  - default/current selector is `auto - Auto (current, default)`; resolved
    provider/model and effort remain `unavailable`.
  - model-list SHA-256:
    `7160694a310c168cee2cc97747d08d19683a9529515a9252c8bae7e611541d3f`
  - output includes `gpt-5.6-sol-*`, `claude-*`, `gemini-*`, plus many Cursor/Opus/Sonnet model variants.

### Hypotheses requiring proof

- Default effective model and effort when `--model` is omitted are not proven by static census.
- Exact absolute `--workspace` behavior and workspace trust remain unproved.
  Saved workspace names, `--add-dir`, and Cursor-managed `--worktree` are not
  baseline candidates.
- Puppet currently lacks a process-generation resume contract. Bare resume,
  `--continue`, and latest-session selection could adopt an operator session and
  are forbidden; only a future exact Puppet-created chat ID can be considered.
- Any additive per-run instruction-plane (`--append-system-prompt` equivalent) remains unsupported from current
  help surface and requires live proof.

## 2) Instruction planes for this version

The lane maps three candidate planes to minimize prompt-in-argv risk:

`session_profile=regular` is the active unprefixed lifecycle selection, not an
instruction plane.

- **Plane 1: session-selected harness-global Puppet addendum**
  - Cursor User Rules are the supported all-project surface, but the current CLI
    exposes no public per-run User Rules profile or config-root selector.
  - Keep this candidate unsupported until an isolated, reversible activation
    path is proved. Never mutate live User Rules during launch.

- **Plane 2: workspace/repository addendum plane (supported, unqualified)**
  - Candidate surfaces are `.cursor/rules/*.mdc`, `AGENTS.md`, and documented
    compatibility rules. Workspace/worktree flags choose scope but are not
    themselves instruction injection.
  - Select scope only through `--workspace <absolute-lane-path>`. Prove
    precedence and preserve existing repo rules in the isolated worktree.

- **Plane 3: additive per-run system-instruction plane**
  - No supported public primary-agent system-prompt append/file flag was found.
    The installed internal-only flag is not a product contract.
  - Keep this plane unsupported; `generate-rule` is an authoring command, not a
    run-scoped instruction transport.

Official surface references: `https://docs.cursor.com/context/rules-for-ai`
and `https://docs.cursor.com/en/cli/using`.

## 3) Default-model observation plan

1. Run isolated fixture with `cursor-agent --list-models` and `cursor-agent models` in bounded env.
2. Launch regular profile with no explicit `--model` and record whether ready-state reveals an explicit resolved
   default.
3. If resolution remains opaque, record selector `auto`, catalog hash, and
   resolved identity/effort as `unavailable`. Do not pin an explicit model as a
   substitute for the default tuple.

## 4) Regular launch / resume / steer / halt / no-bleed matrix

| Surface | Planned action | Expected evidence | Stop criteria |
| --- | --- | --- | --- |
| Launch | `session_profile=regular` only, YOLO-on + sandbox-off mapping | single launch artifact with deterministic startup settle and active process identity | blocked if process identity drifts vs manifest launch_argv |
| Steer | second `send` on same session, initial=False | exact unprefixed follow-up transport, checkpoint progression | blocked if slash-prefix enforcement breaks or no checkpoint delta |
| Resume | future exact Puppet-created chat ID only | a new process generation bound to exact prior session identity | unsupported until that contract exists; bare/latest/continue are forbidden |
| Halt | exact halt action | one targeted stop and clean process exit; no collateral mutation | blocked if lingering process remains or collateral stop observed |
| No-bleed control | ordinary and fixture targets parallel | ordinary sessions unchanged outside lane-owned fixture artifacts | blocked if any ordinary process or config outside fixture mutates |

## 5) Isolated fixture strategy

- Use a lane-owned fixture run root under
  `runs/puppet-v01-regular-qualification-20260722/lanes/cursor/` with dedicated
  temporary directories for workspace/worktree experiments.
- Keep all evidence under lane-owned fixture and run roots.
- Do not read or modify live Cursor User Rules or config contents. The installed
  executable may be fingerprinted read-only; configuration proof stays inside
  lane-owned fixture/worktree surfaces.
- Official config paths are fixed at user `~/.cursor/cli-config.json` and
  workspace `.cursor/cli.json`; no public config-root selector was found. An
  isolated home lacks a proved authorized auth path, and `--api-key` in argv is
  forbidden. Trust/auth isolation remains a gate.
- Re-run all cursors probes when executable, manifest hash, or help hash changes.

## 6) Required Puppet source deltas for this lane

- `skills/puppet/scripts/puppet_lib/census.py`
  - bind both launcher and bundled runtime/package identities; replace vacuous
    project isolation with a dynamic absolute `--workspace` selector.
- `skills/puppet/scripts/puppet_lib/adapters.py`
  - construct and validate `launcher --yolo --sandbox disabled --workspace
    <absolute-lane-path>`; reject saved names, expanded directories,
    Cursor-managed worktrees, auth flags, and undocumented prompt/config flags.
- `skills/puppet/scripts/puppet_lib/probe.py`
  - record selector `auto`, model-list hash, and literal `unavailable` resolved
    model/effort for the current default tuple.
- `skills/puppet/scripts/puppet_lib/adapter_manifest.py` / `tests/test_puppet_probe.py`
  - require resume evidence before marking resume as `controller_verified` for cursor live claims.
- Tests:
  - add explicit cursor fixture assertions for resume/no-bleed behavior under worktree/workspace planes.

## 7) Blockers and stop criteria

- Hard blockers:
  - Any default-model ambiguity that affects deterministic regular-session guarantees.
  - Launcher/runtime identity mismatch until the shell launcher, bundled Node,
    and entrypoint are all bound and verified.
  - No safe isolated authentication/trust path for a disposable config home.
  - `--yolo` remains subject to explicit permission denials; unknown user or
    project policy and MCP approval prompts can invalidate unrestricted mode.
  - No proven isolated resume behavior under this exact executable/version tuple.
  - No proven non-bleed enforcement across fixture vs ordinary sessions.
  - Any source command or fixture operation that writes prompt-bearing values into argv.
- Stop criteria:
  - Keep this lane `mapping` until regular-profile launch/steer/halt and no-bleed are proven by fixture proof.
  - Defer or downgrade resume if it cannot be proven exact for this tuple.
