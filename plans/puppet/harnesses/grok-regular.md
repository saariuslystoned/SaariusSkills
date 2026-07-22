# Grok Build regular-session qualification harness (v0.1)

## Scope and lane contract

- File purpose: planning and static fixture design for the Grok regular-session qualifier under
  `codex-goal-regular-qualification.md`.
- Branch in scope: `codex/puppet-regular-grok-20260722`.
- Objective: map exact Grok regular session behavior for the three instruction planes for this
  installed version, then provide deterministic fixtures for a future live claim and no-bleed
  qualification.

## 1) Exact-version discovery: facts vs hypotheses

### Facts observed

- Executable resolution is an operator-local `grok` binary; the exact absolute
  path remains in the machine-private lane proof.
- Version:
  - `grok --version` -> `grok 0.2.106 (bde89716f679)`.
  - `grok version --json` -> `{"currentVersion":"0.2.106 (bde89716f679)","channel":"unknown"}`.
  - SHA-256 of executable:
    `7229f5e2a69b05832c86db82bebda541e92b5c24958fbfacf5c8f463394d3027`.
- `grok --help` and `grok help version` declare:
  - regular invocation supports `[PROMPT]` with `--resume`, `--continue`, `--single`, `--worktree`,
    `--agent`, `--rules`, `--system-prompt-override` (compat alias `--system-prompt`),
    `--model`, `--reasoning-effort`, `--always-approve`, and `--sandbox`.
  - command surface includes `agent`, `sessions`, `inspect`, `worktree`, `models`, and `trace`.
- `grok --help` does **not** display `--append-system-prompt`.
- `grok inspect` (default environment) reports a user config layer under the
  operator's Grok home and no project layer; contents were not read.
  - environment version `0.2.106`, project root and trust true;
  - external-compat surfaces enabled for cursor/claude/codex session integration.
- `grok models` output:
  - warning: unauthenticated session (`No auth credentials for cli-chat-proxy`);
  - default/available model reports `grok-4.5`.
- `GROK_HOME=<tmpdir> grok inspect --json` changes config disclosure (`configSources.layers: []`),
  while still reporting version `0.2.106` and project discovery.

### Hypotheses needing live proof

- Whether `--model`/`--reasoning-effort` can be used without argv injection in regular-session fixture
  and whether defaults can be observed deterministically at launch-time.
- Whether `--system-prompt-override`/`--system-prompt` and hypothetical `--append-system-prompt`
  plane are mutually composable with `--rules`.
- Whether `--rules` is applied once at fixture scope (config-like) or per-session transport.
- Whether regular/continue/resume ordering is stable when `--always-approve` is active.
- Whether `GROK_HOME` fully isolates writable config for this harness or whether a `HOME`-based fallback
  path is still required.

## 2) Instruction plane mapping: precedence, activation, cleanup

### Plane A: session-selected harness-global Puppet addendum

- Candidate: isolated harness-global plane via dedicated Grok profile/agent settings and global config
  under isolated `GROK_HOME`.
- Activation candidate:
  - run regular plan in `GROK_HOME` fixture with profile/agent settings present at global scope
    (exact file path and schema verified during implementation, not here).
  - launch argument should avoid prompt text in argv.
- Cleanup candidate:
  - preserve fixture-owned `GROK_HOME` as evidence until exact rollback and
    cleanup are separately authorized;
  - preserve non-owned live directories untouched.
- Unknowns:
  - exact precedence between `--agent` and additive per-run instruction input.
  - whether agent-profile activation differs from regular prompt transport.

### Plane B: workspace/repository plane

- Candidate: project/working-tree plane via per-repo instruction artifacts and/or worktree-scoped
  fixture files that Grok discovers for this repository root.
- Activation candidate:
  - run from fixture repo root (with deterministic temp checkout) and inject only lane-owned
    repository-plane artifact.
  - ensure project/root discovery remains visible in `grok inspect`.
- Cleanup candidate:
  - remove fixture-only repository artifacts and confirm no root or sibling repo files are modified.
- Grok documents named `AGENTS.md`/Claude-compatible files and `.grok/rules`
  from repo root toward cwd; exact conflict behavior still needs live proof.

### Plane C: additive per-run plane (`--rules`)

- Candidate: one-shot runtime transport in launch argv:
  - mandatory candidate from observed help is `--rules <RULES>` (append behavior in help text).
  - `--append-system-prompt` is not exposed by this exact help surface, though
    current official CLI documentation lists it as a Claude-compatible alias;
  - `--system-prompt-override` is replacement behavior and forbidden.
- Activation candidate:
  - pass non-empty additive rule payload and capture that launch remains non-interactive and argv-safe.
- Cleanup candidate:
  - no config writes expected if true runtime-only additive plane; if serialized, ensure lane-local and
    immediate cleanup.
- A literal `--rules` payload appears in argv and therefore fails Puppet's
  prompt-body transport gate. Keep this plane unsupported unless a native file
  or stdin form is proved.

Official surface references:
`https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/12-project-rules.md`
and `https://docs.x.ai/build/cli/reference`.

## 3) Current-default model observation

- Exact baseline command: `grok models`.
- Parse these signals:
  - default marker in output (e.g., `Default model: <name>`),
  - available model list,
  - auth warning and fallback semantics when unauthenticated.
- Treat this lane’s current default model as `grok-4.5` only in the exact evidence tuple above.
- Re-observe after each `--sandbox`/`--rules` change and whenever executable hash changes.

## 4) Regular lifecycle matrix (launch/steer/resume/halt/no-bleed)

1. **Launch (regular)**  
   - Inputs: isolated `GROK_HOME`, no prefix, standard regular session request.
   - Expected: one executable target under fixture, regular first-message path, ready checkpoint evidence.

2. **Steer follow-up**  
   - Inputs: second message on the same target via controller send.
   - Expected: monotonic follow-up sequence and checkpoint chain with no argv prompt injection.

3. **Resume behavior**  
   - Inputs: `--resume` (and `--continue` variants where available) on the target fixture session ID.
   - Expected: rebind to the exact registered process/session identity; if not exact, classify as unsupported
     for resume and route to workaround/defer.

4. **Halt behavior**  
   - Inputs: exact-target halt path for this adapter (`exact_pid_sigint` in current mapping).
   - Expected: only fixture target exits; fixture proof shows no collateral termination.

5. **No-bleed control**  
   - Inputs: baseline ordinary-run and isolated `GROK_HOME` run in parallel.
   - Expected: plain ordinary session and other fixtures remain unchanged; only fixture-specific
     artifacts persist under lane-owned paths.

6. **Sandbox/YOLO gating check**  
   - Inputs: exact mapping replay with and without `--sandbox` override where allowed by version.
   - Expected: explicit evidence whether sandbox-off is supported by this build’s declared flags.

## 5) Isolated `GROK_HOME` / config strategy

- Isolated base: per-lane temporary directory used as `GROK_HOME`.
- Fixtures run `grok` commands with `GROK_HOME=<lane_grok_home>`.
- Keep separate fixture repo trees and temporary proof roots for each control action.
- Required probe commands include:
  - `GROK_HOME=<tmp> grok inspect --json`
  - `GROK_HOME=<tmp> grok inspect` and `grok --help` under that env
  - `GROK_HOME=<tmp> shasum -a 256 $(command -v grok)` for consistency
- Cleanup: remove/recreate only lane-owned fixture root and `GROK_HOME` between states.
- Hard rule: never read or write global `~/.grok/*` or other user home instruction files in this lane.

## 6) Exact `--sandbox`-off / YOLO recensus requirements

- Current census declaration check is incomplete for sandbox-off as a first-class verified state:
  - must re-run `grok --help` after any executable/config drift,
  - must re-run `grok inspect` under isolated `GROK_HOME`,
  - must verify whether launch still accepts `--always-approve` without unintended sandbox fallback.
- Re-census command set for any recertification:
  - `grok --version`, `shasum -a 256 $(command -v grok)`, `grok --help`,
    `grok inspect --json`, `grok inspect`, `grok models`,
    plus manifest extraction through existing `python3` census path.

## 7) Required source deltas for this lane (planned)

- `skills/puppet/scripts/puppet_lib/census.py`
  - validate/record Grok `--rules`, `--always-approve`, and sandbox declaration behavior with exact
    current flags and any alias behavior.
- `skills/puppet/scripts/puppet_lib/profiles.py`
  - verify whether any additional Grok profile/agent surfaces are needed beyond `regular`.
- `skills/puppet/scripts/puppet_lib/adapters.py`
  - confirm any resume/steer envelope differences if `--append-system-prompt` or per-run plane is accepted.
- `skills/puppet/scripts/puppet_lib/probe.py`
  - expand resume and no-bleed assertions for Grok session identity and fixture boundaries.
- `tests/test_puppet_adapters.py` and `tests/test_puppet_probe.py`
  - add Grok-specific fixture proofs for regular launch, resume, and no-bleed; include `GROK_HOME` fixture case.

## 8) Blockers and stop criteria

- Blockers:
  - No authenticated `grok models` session; live model capability could change with auth state.
  - `--append-system-prompt` not surfaced in current help; needs external-source confirmation.
  - sandbox-off semantics are not currently proven for regular exact-YOLO; `--sandbox` behavior must be
    confirmed in harness context.
  - no-bleed proof cannot be accepted without an ordinary-session control in
    the same repository family.
- Stop condition:
  - If any one of: launch, follow-up, resume, halt, or no-bleed cannot be proven exact against the
    current executable/version tuple, mark Grok lane as `experimental`/`unsupported` by gate for this tuple and
    escalate as a hard blocker for this lane.
