# Implementation Seed: `puppet` Skill + CLI

Status: overnight-ready design seed; reconciled with the GrillTrack authority,
evidence-admission, real-harness probe, YOLO-only, and autonomous-campaign locks

Canonical destination: `saariuslystoned/saariusskills/skills/puppet`

Initial dogfood lane: Codex controller → AGY harness → user-selected Gemini model

> **Mandatory operating warning:** Puppet live execution is YOLO-only. It
> launches target harnesses with their current-version unrestricted,
> always-approve permission mode and with the harness sandbox disabled where
> that control exists. Prompted or sandboxed live launches are unsupported.
> Installation and the zero-agent census do not launch a target, but the first
> live launch requires an explicit local acknowledgement. Do not use Puppet
> unless the target may receive the full machine access available to the
> operator account.

## Assignment

Build a portable `puppet` skill and companion CLI that lets an agent running in
one harness supervise an agent running in another harness through a durable
tmux session. Build it as an honest public consolidation of the operator's
already-evidenced local orchestration practice, subject to the admission matrix,
not as a greenfield wrapper that discards prior learning or copies
private-repository code without a license path.

Examples:

- Codex drives AGY running a selected Gemini model.
- Claude drives Codex.
- Codex drives Claude.
- AGY drives Cursor.
- Codex drives Grok through its current CLI adapter.

The target harness performs the assigned implementation or review. The controller owns the goal, safety envelope, monitoring, independent review, and final acceptance. A human can attach read-only to the target's tmux session from launch through closeout.

Do not merely rename the existing `teamwork-preview` skill. Extract its useful operational lessons, replace its one-harness assumptions with an adapter architecture, and forward-test the resulting technique.

Build `puppet` through one bounded, unattended, serial self-hosting campaign
after the minimum trusted kernel and first AGY adapter exist. One long-lived
Codex campaign controller may supervise AGY, Cursor, Claude, Codex, and Grok one
at a time. Each target edits a candidate worktree while Codex invokes the fixed,
controller-owned Puppet version recorded for that session. Codex learns from
exact commits, structured checkpoints, and evidence; it never learns by
scraping target terminals. Between sessions, it may promote an independently
accepted exact candidate without waking the user, within the one explicitly
authorized campaign envelope.

The repository root README must keep the promised tongue twister:

> Puppet uses agents like puppets to build Puppet—the skill that uses agents
> like puppets.

It may follow with the plainer explanation: “Puppet uses supervised agents to
build the system that supervises agents.”

Do not create a README inside `skills/puppet/`.

## Product thesis

`puppet` is not a generic process launcher, transcript scraper, or model router.
It is a small control plane for supervised agent sessions:

```text
controller skill
    ↓ task contract + explicit target/model selection
puppet CLI
    ↓ exact fingerprinted target adapter
tmux session containing target harness
    ↙                    ↓                         ↘
human read-only view   sanitized status       commit/checkpoint handoff
                           ↓                         ↓
                       controller verdict ← independent inspection
```

Adapter construction uses two passes:

```text
allowlisted zero-agent census
    → fingerprinted capability manifest
    → hard-disabled doctor-only adapter
    → standardized real-harness conformance contract
    → controller-verified capability graduation
```

Static CLI declarations, prior proof, and target self-reports may populate
claims. Only controller-observed behavior bound to the exact executable,
adapter, platform, and probe-protocol fingerprints may enable live behavior.
No fake target harness can qualify an adapter or satisfy product acceptance.

Long-running behavior comes from acceptance-driven session state, not instructions to “work longer.” A target checkpoint, local green test, commit, push, or CI start is not completion. The target remains active until the contract's terminal criteria are satisfied or an irreducible blocker is recorded.

## Key architectural decision

Make the CLI the cross-harness source of truth for session lifecycle,
checkpoint identity, controller verdicts, and self-hosting promotion history.
Make each controller's skill a thin operational wrapper around that CLI.

- The CLI owns tmux, process discovery, target adapters, message transport,
  exact session registration, lifecycle state, structured handoff validation,
  controller verdict recording, and sanitized evidence.
- The adapter lab owns the zero-agent census, evidence admission, generated
  doctor-only manifests, standardized real-harness probes, and capability
  graduation. Generated declarations never authorize a launch by themselves.
- `SKILL.md` teaches the current controller agent how to formulate a contract, launch a target, monitor it, steer it, review checkpoints, and close it safely.
- Controller-specific installation shims may expose the same skill to Codex, Claude, AGY, Cursor, or another environment without duplicating the orchestration logic.
- Target adapters describe how to launch and communicate with each target harness. They do not assume that all harnesses support the same slash commands, model flags, permission flags, or queuing behavior.
- Target beacons and handoffs are claims. They never advance the session to
  `ACCEPTED` and never promote a candidate without a controller verdict.
- During self-hosting, every controller command for a live session resolves to
  the fixed supervising executable path and hash recorded at launch. The target
  edits a distinct candidate worktree and cannot replace the supervisor during
  that run.
- One immutable Codex campaign controller owns unattended acceptance and
  between-session promotion. A target never reviews, certifies, or promotes its
  own candidate.
- Prior artifacts are admitted per invariant through a provenance-and-delta
  matrix. Extracted or reimplemented components rerun direct tests; stale,
  uncommitted, terminal-derived, branch-only, operator-specific, or
  license-uncleared material remains historical design input until revalidated.

## Recommended package layout

```text
skills/puppet/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── adapter_lab.py
│   ├── puppet.py
│   └── puppet_lib/
│       ├── __init__.py
│       ├── adapter_manifest.py
│       ├── adapters.py
│       ├── census.py
│       ├── conformance.py
│       ├── contracts.py
│       ├── handoffs.py
│       ├── journal.py
│       ├── promotions.py
│       ├── provenance.py
│       ├── registry.py
│       ├── session.py
│       ├── state.py
│       ├── tmux.py
│       ├── verdicts.py
│       └── safety.py
├── references/
│   ├── operating-contract.md
│   ├── adapter-contract.md
│   ├── prompt-patterns.md
│   ├── proof-provenance.md
│   └── yolo-contract.md
└── tests/
    ├── test_adapters.py
    ├── test_census.py
    ├── test_conformance_contract.py
    ├── test_contracts.py
    ├── test_handoffs.py
    ├── test_journal.py
    ├── test_provenance.py
    ├── test_self_hosting.py
    ├── test_state_machine.py
    ├── test_tmux_transport.py
    └── test_verdicts.py
```

Do not add a README, changelog, installation guide, or other duplicate
documentation inside the skill. Keep `SKILL.md` concise and route durable detail
to the references. Put the mandatory YOLO warning and self-hosting tongue
twister in the repository root README as well as the routed skill contract.

Use Python 3 standard library for v0.1 unless a concrete requirement proves it insufficient. Use subprocess argument arrays and explicit files/stdin; never construct shell commands from user messages.

## Adapter factory and evidence admission

The implementation campaign begins with one reusable developer surface:

```bash
python3 skills/puppet/scripts/adapter_lab.py census \
  --targets agy,cursor,claude,codex,grok \
  --out /abs/census.json
python3 skills/puppet/scripts/adapter_lab.py scaffold \
  --manifest /abs/census.json \
  --out skills/puppet/scripts/puppet_lib/generated
python3 skills/puppet/scripts/adapter_lab.py probe \
  --target agy \
  --profile interactive-v1 \
  --proof-root /abs/proof-root
python3 skills/puppet/scripts/adapter_lab.py verify --run /abs/proof-root
```

`census` is zero-agent and allowlisted. For each known entrypoint it records
requested path, resolved path, file identity and SHA-256, platform/architecture,
version output and hash, bounded help output hash, advertised capabilities, and
evidence references. It must not read authentication state, session stores,
transcripts, credentials, model conversations, or arbitrary configuration.

Each capability is one of `unknown`, `declared`, `historical`,
`controller_observed`, `controller_verified`, or `unsupported`. Only
`controller_verified` may graduate a behavior beyond `doctor-only`. Cache
identity includes the host, platform, executable identity/hash, version/help
hashes, adapter schema, adapter implementation, and probe protocol. Any change
invalidates the affected declarations and behavioral proof. Dynamic auth,
quota, model availability, repo identity, target locks, and YOLO authorization
are always rechecked live.

The manifest records separate proof state and evidence fingerprints for at
least `launch`, `send`, `status`, `wait`, `checkpoint`, `resume`, and `halt`.
Graduating one capability never implies another; `launch` proof, for example,
does not prove follow-up acknowledgement, resume, busy queuing, or halt.

The initial operator-terminal observations on 2026-07-21 are discovery inputs,
not permanent support claims:

| Harness | Observed CLI | Useful declared surfaces |
| --- | --- | --- |
| AGY | `agy 1.1.5` | interactive/print, conversation resume, model/effort, plan/accept-edits, permission bypass, sandbox flag |
| Cursor | `cursor-agent 2026.07.17-3e2a980`; `cursor 3.9.16` | JSON/stream JSON, chat resume, model, workspace/worktree, YOLO, sandbox disable |
| Claude | `Claude Code 2.1.215` | stream JSON/schema, session UUID/resume, model/effort, permission bypass, hooks |
| Codex | `codex-cli 0.145.0` | stdin exec, JSONL/schema, resume, model, cwd, approval/sandbox bypass |
| Grok | `grok 0.2.106 (bde89716f679)` | prompt file, JSON/streaming JSON, session ID/resume/fork, model/effort, permission bypass, sandbox, stdio/headless/server modes |

Codex changed versions during the design session; that observed invalidation is
why no adapter may rely on a frozen table without recensus.

Known diagnostic quirks are version-scoped manifest evidence, not universal
string heuristics. A dated, untrusted operator fixture records that AGY's
display `Gemini 3.6 Flash · high · AI: Out of credits` referred to exhausted
AI overage credits rather than subscription exhaustion or task failure in the
observed local setup. It must not stop or trigger diagnosis by itself. Freshly
validate the interpretation against the current executable/provider surface
before normalizing it as `agy_ai_overage_credits_exhausted`; never scrape a pane
to find it, and never promote it to a terminal verdict without separate
controller-observed failure evidence. Record whether a quirk came from operator knowledge, static census,
safe structured runtime output, or a real probe, and revalidate it when the
executable fingerprint changes. Other harness quirks enter through the same
evidence path rather than inference.

Use `plans/puppet/prior-proof-provenance.md` as the campaign's initial evidence
map. Private operator evidence is specification/provenance unless an explicit
rights-and-attribution path clears extraction into the MIT project. Every
admitted row binds the exact source identity and revision in machine-private
campaign state,
the narrow claim/invariant, proof artifact and strength, mechanism/version,
portability and operator-specific assumptions, license/attribution path,
admit/reimplement/design-only decision, deterministic tests to rerun, and the
smallest remaining live delta. Rerun deterministic tests for every extracted or
reimplemented component. Live-reprove only changed mechanisms and the complete
new Puppet composition; never transfer proof to a different revision or claim.

## CLI surface

The skill-local executable is invoked as:

```bash
python3 <skill-root>/scripts/puppet.py <command> ...
```

An optional, explicitly authorized installer may later link it as `~/.local/bin/puppet`. Do not require a global install.

### `doctor`

```bash
puppet doctor --controller codex --target agy --repo /abs/repo
```

Read-only checks:

- target binary discovery, resolved identity/hash, version/help hashes, and
  census cache validity;
- exact current-version unrestricted/always-approve flag mapping, including
  sandbox disablement when exposed;
- prominent YOLO-only warning and an explicit local standing-authorization
  record; missing authorization is a hard launch blocker;
- tmux availability;
- applicable repository instructions;
- exact repo/worktree/branch identity;
- target store/process lock conflicts;
- model and effort selection capability;
- unrestricted permission and sandbox-disable capability;
- message queuing capability;
- session-name and socket-path bounds;
- proof-root writability;
- whether controller and target would accidentally be the same live session;
- repo-instruction discovery (`AGENTS.md`, `GEMINI.md`, or adapter-specific
  equivalents), including conflicting or duplicate contracts.

Return structured JSON with `--json`. Always disclose that prompted and
sandboxed live operation are unsupported. Never inspect credentials,
environment-file contents, transcripts, cookies, authentication/session stores,
or authentication logs.

### `launch`

```bash
puppet launch \
  --controller codex \
  --target agy \
  --repo /abs/worktree \
  --session agy-cu-build \
  --contract /abs/contract.json \
  --model "Gemini 3.6 Flash" \
  --effort high \
  --proof-root /abs/proof-root
```

Behavior:

1. Run `doctor` and fail closed on ambiguity.
2. Read applicable repo-local instructions before compiling the initial prompt.
3. Validate the contract and explicit local unrestricted authorization.
4. Resolve the exact adapter's controller-verified YOLO mapping; fail closed if
   it cannot prove both automatic permission approval and sandbox disablement
   where the CLI exposes those controls.
5. Create one detached tmux session on a private, registry-bound socket in the
   exact worktree.
6. Launch the target with the adapter's supported unrestricted argument vector.
7. Deliver the initial prompt through stdin, a protected prompt file, or a
   session-qualified tmux buffer, never a process argument.
8. Record sanitized session metadata.
9. Print the human viewer command:

```bash
tmux -S /abs/registry-bound-private.sock attach-session -r -t agy-cu-build
```

Never automatically attach the controller to the interactive TUI. Never start
a second hidden target session when a reusable matching session already exists.
YOLO mechanics do not grant task authority outside the contract's allowed
actions and hard gates.

For a self-hosting launch, record both identities:

- the immutable supervising Puppet root, commit, tree hash, executable path,
  and executable hash used by the controller;
- the distinct candidate repo/worktree/branch that the target may mutate.

Fail closed if those roots overlap or if a subsequent controller command no
longer matches the recorded supervising executable.

### `send`

```bash
puppet send --session agy-cu-build --stdin < repair-packet.md
```

Behavior:

- Resolve the exact registered session and target adapter.
- Verify the pane's recorded shell plus descendant process identity, executable,
  and start time still resolve to the expected target; do not assume the pane
  PID itself is the harness process.
- Read the message from stdin or `--message-file`; do not accept secret-bearing content in argv.
- Apply the adapter's message envelope exactly once.
- Use a named tmux buffer, paste it literally, submit it, then delete the buffer.
- Serialize sends with a per-session lock.
- Reject target-specific side-channel commands unless explicitly supported by the adapter.
- If the target is busy, queue only when the adapter has proven queue semantics; otherwise return `busy` without injecting keystrokes.
- Append a sanitized event containing timestamp, message kind, content hash, and
  delivery state only. Never retain the message body. Distinguish `queued`,
  `submitted`, and target-acknowledged; transport success alone is not proof the
  parent consumed the steering turn.

For AGY, every substantive message must begin with exactly one literal `/teamwork-preview`. Reject `/btw`, `/side`, empty messages, and duplicated prefixes. The caller supplies the content; the adapter supplies the prefix.

### `status`

```bash
puppet status --session agy-cu-build --json
```

Return only sanitized state:

- session/controller/target identifiers;
- exact repo, worktree, branch, and mutation owner;
- tmux and target-process liveness;
- current lifecycle state and phase;
- active/completed/blocked helper counts when surfaced by the target;
- local/remote/PR heads when the contract uses git;
- CI and exact-head review state when supplied by a verified observer;
- last heartbeat/beacon time;
- blocker and next action.

Do not use `capture-pane`, `pipe-pane`, terminal transcripts, or arbitrary pane
content for controller monitoring. Consume beacons only through an explicit
adapter hook/event channel that carries the sanitized protocol. If an adapter
cannot prove such a channel, return reduced transport/process status and rely
on committed checkpoints instead of scraping the TUI.

Classify status evidence by source and authority: structural process/transport
liveness, controller-validated protocol progress, target checkpoint claims,
harness advisory state, provider execution errors, and terminal failures are
different facts. A banner, badge, or target-reported diagnostic is never by
itself a blocker or completion verdict. Stop only when controller-observed
protocol evidence proves a terminal condition or the bounded wait/repair policy
is exhausted.

### `wait`

```bash
puppet wait --session agy-cu-build --until checkpoint --timeout 60
```

Wait for one bounded interval. Valid conditions:

- `beacon`
- `checkpoint`
- `action-required`
- `target-stopped`
- `done`

This replaces fleets of duplicate scheduler cards. A controller that supports recurring wakeups may create at most one watcher per puppet session.

### `checkpoint`, `review`, and `accept`

```bash
puppet checkpoint --session agy-cu-build --handoff /abs/checkpoint.json
puppet review \
  --session agy-cu-build \
  --checkpoint <checkpoint-id> \
  --verdict repair \
  --evidence /abs/review.json
puppet accept \
  --session agy-cu-build \
  --checkpoint <checkpoint-id> \
  --evidence /abs/acceptance.json
```

- `checkpoint` is invoked by the controller after a target advertises a
  handoff. It validates and imports one of two explicitly tagged artifacts:
  `conformance` binds run ID, nonce, phase/sequence, executable, adapter, and
  protocol fingerprints and forbids a candidate commit; `source` binds the
  same run identity plus the exact candidate commit. The checkpoint ID is the
  hash of the canonical validated identity fields and artifact hash. Importing
  a target claim is not accepting it. After validation,
  `checkpoint` and `status` expose only the sanitized handoff reference, SHA-256,
  exact checkpoint identity, and validation state; they do not inline the
  handoff body. Codex opens the bounded referenced artifact separately when it
  needs substantive learning.
- `review` records a controller-only `repair`, `conformance_accept`,
  `source_accept`, `block`, or `fail` verdict against the exact checkpoint. A
  source head change invalidates a source verdict; executable, adapter,
  protocol, run-ID, nonce, sequence, or artifact drift invalidates a
  conformance verdict. Evidence bodies travel through explicit files/stdin,
  not argv.
- `accept` is controller-only and succeeds only when every terminal criterion
  has verified evidence at the exact checkpoint. The target cannot invoke a
  beacon, handoff, or lifecycle transition that substitutes for this command.
- v0.1 role separation is an orchestration authority boundary, not a claim of
  hostile same-UID containment. Strong isolation requires a separately proved
  sandbox or account boundary.

### Later command: `promote` (unsupported in bootstrap Puppet N)

```bash
puppet promote \
  --session agy-cu-build \
  --candidate-root /abs/candidate-worktree \
  --candidate <full-sha> \
  --campaign-authorization /abs/campaign.json
```

The minimum manually trusted bootstrap Puppet N must return `unsupported` for
`promote`. Candidate Puppet N+1 may add it only after the first real AGY
conformance run and independent-review bootstrap pass. The command may appear
in the accepted v0.1 only after its own deterministic and real-harness gates
pass. It is only for the Puppet self-hosting track and refuses unless:

- the session is `ACCEPTED` at the same full candidate commit;
- the candidate is distinct from the supervisor used for that session;
- the exact candidate commit/tree materializes to the recorded controller-owned
  qualification root, executable path, file identity, executable hash, and
  adapter/protocol fingerprints;
- deterministic exact-candidate and self-hosting tests passed from a
  controller-owned context and their result hashes are recorded;
- required real-harness conformance passed against exact fingerprints;
- an independent proved harness/model different from the implementation target
  reviewed the exact candidate and all required findings are resolved; the
  immutable Codex campaign controller remains the acceptance authority and may
  also be that reviewer only when it is genuinely a different harness/model
  from the implementation target and its bounded review-qualification proof
  and identity fingerprint are bound to the promotion;
- the controller recorded the checkpoint findings, residual risks, and an
  acceptance verdict; and
- the one explicit bounded campaign authorization covers the promotion and no
  external human gate or scope expansion is present.

Promotion occurs between target sessions. It atomically advances the stable
supervisor reference and records the old and new identities; it never rewrites
the executable controlling a live session. Promotion does not imply commit,
push, merge, deployment, installation, or deletion authority.
The append-only record includes old/new commits, trees, qualification roots,
executable fingerprints, deterministic test results, real probes, reviewer,
controller verdict, time, and rollback identity.

### `attach-command`

Revalidate the exact registered private socket and session, then print, but do
not execute, the read-only tmux viewer command. Callers cannot supply their own
socket or tmux target.

### `halt` and later `close`

```bash
puppet halt --session agy-cu-build
puppet close --session agy-cu-build
```

- `halt` gracefully asks the exact target process to exit and preserves
  tmux/state for audit.
- Puppet N returns `unsupported` for `close`. A later `close` removes the exact
  stopped tmux session only after separate explicit authorization.
- Never kill by broad process pattern.
- Never delete proof or state automatically.
- A session is preserved by default after target completion.

## Controller/target contract

Define a versioned JSON contract. Example:

```json
{
  "schema_version": 1,
  "objective": "Build the bounded computer-use observation milestone",
  "campaign_authorization_id": "campaign-20260721-puppet-v01",
  "controller": "codex",
  "target": "agy",
  "requested_model": "Gemini 3.6 Flash",
  "task_profile": "implementation_and_computer_use",
  "harness_trust": "unrestricted_required",
  "mutation_owner": "target",
  "repo": "/absolute/worktree",
  "branch": "codex/example",
  "max_helpers": 3,
  "allowed_modes": ["read", "test", "mutate", "local_commit"],
  "terminal_criteria": [
    {"id": "source_committed", "evidence": "full_local_git_sha"},
    {"id": "source_tests_green", "evidence": "exact_head_test_results"},
    {"id": "source_review_clean", "evidence": "exact_head_controller_verdict"},
    {"id": "real_probe_green", "evidence": "exact_fingerprint_probe_receipt"},
    {"id": "proof_reconciled", "evidence": "bounded_proof_index"}
  ],
  "hard_gates": [
    "merge",
    "push",
    "deploy",
    "force_push",
    "global_install",
    "external_send",
    "spend",
    "secrets",
    "account_change",
    "destructive_cleanup"
  ]
}
```

The CLI stores the contract because it is an explicit, inspectable artifact. It must not store prompts, transcripts, or secret-bearing logs.

`mutation_owner: target` means the controller may inspect and review but does not edit the target source slice. Supporting another ownership mode requires explicit contract support; never infer shared mutation.

## Lifecycle state machine

```text
NEW
  → PREFLIGHTED
  → STARTING
  → ACTIVE
  ↔ WAITING_EXTERNAL
  ├→ CONFORMANCE_READY
  │  → ACTIVE        (one sequenced follow-up)
  │  → CONFORMANCE_CHECKPOINT_READY
  │  → AWAITING_CONFORMANCE_REVIEW
  │  → ACCEPTED | BLOCKED | FAILED
  └→ SOURCE_CHECKPOINT_READY
     → AWAITING_SOURCE_REVIEW
     → ACTIVE        (repair requested)
     → SOURCE_ACCEPTED
     → PROOF_CHECKPOINT_READY
     → TARGET_DONE
     → AWAITING_CONTROLLER_REVIEW
     → ACTIVE        (repair requested)
     → ACCEPTED | BLOCKED | FAILED
  → HALTED
  → CLOSED          (explicit only)
```

The conformance branch is source-free: `ready` is a validated nonterminal
checkpoint, the controller sends exactly one follow-up, and the validated
follow-up handoff becomes the reviewable conformance checkpoint. It is keyed by
run ID, nonce, phase/sequence, exact executable/adapter/protocol fingerprints,
and artifact hashes; `candidate_commit` is forbidden. The source branch requires
a full candidate commit and retains exact-head invalidation. The target cannot
mark itself `ACCEPTED`. `PUPPET_DONE` is valid only for the source branch and
moves that session to `TARGET_DONE`; only the controller can bind a review or
acceptance verdict to either exact checkpoint kind through the CLI.

## Self-hosting ratchet

Self-hosting uses an additional promotion lifecycle outside the target session:

```text
STABLE_N (fixed path + commit + tree/executable hashes)
  → CANDIDATE_N_PLUS_1 (separate target-owned worktree)
  → TARGET_CHECKPOINT
  → EXACT_HEAD_TESTS_AND_REAL_PROBES
  → INDEPENDENT_CONTROLLER_REVIEW
  → CAMPAIGN_PROMOTION_GATE
  → STABLE_N_PLUS_1 (next session only)
```

- Keep one primary Codex orchestration session so it can accumulate project
  context, inspect checkpoint commits, steer later target runs, and act as the
  immutable campaign acceptance authority.
- Run only one target/mutation owner at a time during bootstrap.
- Start with the manually implemented and directly tested kernel plus generated
  doctor-only manifests. Prove AGY first with the standardized real-harness
  conformance contract.
- Before the first mutation, qualify an independent review rail that is
  materially different from the intended implementation target. The default
  bootstrap rail may be the fixed Codex campaign controller reviewing an AGY
  candidate, but only after a bounded read-only exact-head review fixture proves
  its reviewer identity, schema, finding classification, no-edit behavior, and
  stale-head invalidation. This qualifies the Codex controller as a review rail,
  not the Codex target adapter. If its exact controller/harness/model identity
  or review behavior cannot be proved, qualify another distinct serial review
  rail or stop before mutation.
- After both AGY control-loop and independent review-rail proof exist, use the
  stable version to supervise a bounded candidate improvement or next adapter.
- Qualify every new adapter through `censused` → `doctor-only` →
  `real-readonly` → `interactive-controlled` → `disposable-mutation` →
  controller acceptance before relying on it for the following rung. No fake
  target may qualify any rung.
- Never let a target certify its own adapter or candidate. Use a different
  target for later independent work and end the portability proof with a
  different harness acting as controller over Codex.
- Do not wake the user for routine repair, review, or exact-head internal
  promotion within the campaign. Stop on a human gate, ambiguous identity or
  proof, repeated repair failure, unproved behavior, or scope expansion.
- Preserve every prior stable identity and promotion record. Rollback means
  selecting a previously accepted immutable version, never reconstructing one
  from terminal history.

## Target adapter interface

Implement an internal adapter protocol resembling:

```python
class HarnessAdapter(Protocol):
    name: str

    def detect(self) -> DetectionResult: ...
    def fingerprint(self) -> ExecutableFingerprint: ...
    def doctor(self, context: LaunchContext) -> DoctorResult: ...
    def unrestricted_mapping(self, fingerprint: ExecutableFingerprint) -> YoloMapping: ...
    def build_launch_argv(self, context: LaunchContext) -> list[str]: ...
    def envelope_initial(self, contract: Contract, body: str) -> str: ...
    def envelope_followup(self, kind: str, body: str) -> str: ...
    def validate_pane(self, pane: PaneState) -> None: ...
    def can_queue_while_busy(self) -> bool: ...
    def graceful_halt_keys(self) -> list[str]: ...
```

Adapter capabilities must be discovered from the installed version. Do not
freeze volatile CLI flags into universal policy. If the requested model,
effort, unrestricted permission mapping, sandbox disablement, session identity,
or queuing behavior cannot be proved, fail closed with an actionable doctor
result.

### AGY adapter v0.1

This is the first adapter because Codex → AGY has the strongest admitted
historical real-run evidence. The adapter still remains unqualified until the
current exact executable passes the shared real-harness probe.

Requirements:

- Binary: `agy`.
- Interactive target inside tmux.
- Live launch is allowed only when the installed AGY fingerprint maps to its
  verified permission-bypass behavior with the sandbox disabled or absent.
- Model and effort selection use verified launch flags when available; otherwise use a deterministic, separately proven selector. Never silently accept model drift.
- Initial and follow-up substantive messages begin with exactly one `/teamwork-preview`.
- `/btw`, `/side`, duplicate prefixes, and direct transcript inspection are prohibited.
- Prefer one persistent AGY parent and no nested AGY process.
- Use AGY-native helpers, messaging, scheduling, and task management from the target parent.
- Default helper concurrency is three or fewer with disjoint scopes; close completed helpers before spawning replacements.

### Codex, Claude, Cursor, and Grok adapters

For each adapter:

1. Probe the installed binary and help/version output.
2. Record supported interactive, trust, model, effort, resume, queue, and graceful-stop capabilities.
3. Generate a hard-disabled doctor-only manifest.
4. Run the standardized bounded conformance prompt against the real installed
   CLI before graduating any live behavior.
5. Bind every result to the executable and probe fingerprints.
6. Do not invent flags from memory or from a target self-report.

An adapter may initially be `doctor-only` and return `unsupported` for launch. This is preferable to a misleading partial implementation.

## Standardized real-harness conformance contract

Run the same behavioral contract against AGY, Cursor, Claude, Codex, and Grok,
strictly one at a time. It is not a capability interview and it is not a model
quality benchmark. The semantic prompt body and strict handoff schema are
identical across all five. Only the adapter transport, exact unrestricted-mode
flags, requested harness/model fields, and a required native envelope such as
AGY's single `/teamwork-preview` prefix may differ; the envelope cannot change
the contract's authority or checkpoint schema.

The controller creates a disposable fixture with a random nonce, a bounded
contract, a strict handoff schema, an allowlisted proof root, and protected-root
before-state. It then launches the exact real CLI through the adapter's
doctor-verified unrestricted mapping. The target must:

1. read the contract and publish a nonce-bound `ready` checkpoint;
2. finish that turn while the same target session remains available;
3. receive exactly one follow-up carrying the next sequence and nonce;
4. publish a second checkpoint acknowledging that exact sequence; and
5. wait for the controller's exact graceful halt.

Both artifacts use `checkpoint_kind: "conformance"`. Their identity contains
the run ID, nonce, phase, sequence, message ID when applicable, prior-checkpoint
hash when applicable, executable fingerprint, adapter fingerprint, protocol
fingerprint, and artifact hash. They must omit `candidate_commit`. The ready
checkpoint is nonterminal; only the follow-up checkpoint may enter controller
conformance review and acceptance.

The controller verifies the executable/process/session identity, target birth
identity where the platform exposes it, prompt transport outside argv, bounded
sanitized artifacts, legal lifecycle transitions, no protected-source drift,
and a halt affecting only the registered target. It preserves the tmux evidence
session and never reads its pane or transcript. The disposable fixture bounds
and detects the cooperative task; YOLO mode means it does not provide hostile
same-UID containment.

The target may report its harness, model, effort, or capabilities inside an
allowlisted claims object. Those values remain `self_reported`. Controller
records requested and externally observed harness/model/version/effort, task
profile, latency, native turn/tool counts when safely exposed, checkpoint
quality, repair cycles, proof integrity, and verdict. These fields prepare a
future evidence-based auto router. v0.1 always preserves the user's right to
select and pin a target/model and never silently switches a live session. A
later auto mode may choose or change a worker only at a declared task or
checkpoint boundary, must explain the exact-version outcome evidence behind
the choice, and must not hard-code permanent brand roles such as “model X
always implements.”

The first live AGY run stops after exactly one conformance session reaches
`ACCEPTED`, `BLOCKED`, or `FAILED`; the ready checkpoint, one acknowledged
follow-up, controller verdict, and exact graceful halt are recorded; and tmux
evidence is preserved. Do not mutate Puppet source, promote a candidate, close
the session, or begin a second live target during that run.

## Prompt envelope

Every target receives a compact controller-neutral envelope:

```text
PUPPET_SESSION_V1
Read applicable repository instructions first.
The target parent owns: decomposition, implementation, integration, tests, and authorized checkpoint publication.
The controller owns: goal, gates, monitoring, independent review, and final acceptance.
Respect mutation_owner, allowed_modes, hard_gates, and terminal_criteria from the attached contract.
Helper reports and local checkpoints are not completion.
Remain active until all target-owned criteria are evidenced or a concrete blocker is recorded.
Publish only sanitized PUPPET_* beacons through the adapter's explicit
hook/event channel for the controller. Terminal display is for the human
observer and must not be the controller's monitoring transport.
At a source checkpoint, write one bounded structured handoff with the exact
candidate commit. At a conformance checkpoint, write the source-free run/nonce/
sequence and executable/adapter/protocol identity required by that schema.
Include only bounded claims, evidence references, decisions requested,
limitations, and a suggested next assignment. Do not write a transcript or
terminal summary.
```

The adapter may prepend a required native command such as AGY's `/teamwork-preview`, but it must not change the contract's authority.

## Beacon protocol

Use single-line JSON after a stable prefix on the explicit adapter hook/event
channel:

```text
PUPPET_STATUS {"phase":"implementation","active":3,"done":0,"blocked":0,"head":"abc123","next":"run native tests"}
PUPPET_ACTION_REQUIRED {"type":"human_gate","detail":"production deploy requested"}
PUPPET_CONFORMANCE_READY {"run_id":"<run-id>","phase":"ready","sequence":0,"ref":"handoffs/ready.json","sha256":"<64-char-hash>"}
PUPPET_CONFORMANCE_READY {"run_id":"<run-id>","phase":"followup","sequence":1,"ref":"handoffs/followup.json","sha256":"<64-char-hash>"}
PUPPET_CHECKPOINT {"source":"<40-char-sha>","proof":null,"ci":"pending"}
PUPPET_HANDOFF_READY {"checkpoint":"<40-char-sha>","ref":"handoffs/checkpoint.json","sha256":"<64-char-hash>"}
PUPPET_DONE {"outcome":"success","criteria":["source_pushed","source_ci_green"],"checkpoint":"<40-char-sha>"}
```

Reject malformed, multiline, oversized, or secret-shaped beacons. A beacon is
a status claim, not acceptance proof. `PUPPET_HANDOFF_READY` advertises an
artifact for controller import; it does not make target-authored state
authoritative.

## Structured checkpoint handoff

The target-to-controller learning channel is a bounded JSON handoff, not the
target's pane, transcript, chat store, or raw logs. It is a discriminated union.
A source handoff requires at least:

```json
{
  "schema_version": 1,
  "checkpoint_kind": "source",
  "session": "agy-cu-build",
  "run_id": "<run-id>",
  "nonce": "<controller-nonce>",
  "candidate_commit": "<40-char-sha>",
  "executable_fingerprint": "<sha256>",
  "adapter_fingerprint": "<sha256>",
  "protocol_fingerprint": "<sha256>",
  "timestamp": "<RFC3339>",
  "summary": "What changed and why",
  "claims": [],
  "evidence_refs": [],
  "decisions_requested": [],
  "limitations": [],
  "suggested_next_assignment": ""
}
```

A conformance handoff requires at least:

```json
{
  "schema_version": 1,
  "checkpoint_kind": "conformance",
  "session": "agy-conformance",
  "run_id": "<run-id>",
  "nonce": "<controller-nonce>",
  "phase": "followup",
  "sequence": 1,
  "message_id": "<controller-message-id>",
  "prior_checkpoint_sha256": "<ready-artifact-sha256>",
  "executable_fingerprint": "<sha256>",
  "adapter_fingerprint": "<sha256>",
  "protocol_fingerprint": "<sha256>",
  "timestamp": "<RFC3339>",
  "claims": [],
  "evidence_refs": [],
  "decisions_requested": [],
  "limitations": []
}
```

Bound field sizes and item counts. Reject absolute references outside the
declared repo/proof roots, mutable commit abbreviations, embedded logs,
transcripts, secrets, and credential-shaped content. Reject `candidate_commit`
on conformance handoffs and require it on source handoffs. The controller
validates and hashes the handoff; for source checkpoints it independently
inspects the candidate commit and evidence, while for conformance checkpoints
it independently verifies the run/nonce/sequence and executable/adapter/
protocol identities plus zero protected-source drift. It then records a verdict
or sends a bounded follow-up through `puppet send`. Interactive campaigns may
discuss material findings with the user; an unattended campaign records them
and continues within its envelope, waking the user only for a hard gate or
terminal blocker.

## Proof and review discipline

When a separately authorized contract uses source and proof pushes:

1. Target creates and pushes source `S`.
2. Target waits for exact-`S` push and pull-request CI.
3. Controller independently reviews exact `S`; a head change invalidates that
   verdict. Target repairs failures additively and repeats source CI/review.
4. Only after exact-`S` source acceptance, target creates proof-only child `P`
   naming full `S` and exact source run IDs.
5. Target verifies `P^ == S`, the claim equals the actual parent, and only the
   declared proof files changed.
6. Target pushes `P`, waits for exact-`P` CI, and emits `PUPPET_CHECKPOINT`.
7. Target emits a structured handoff bound to exact `P`.
8. Controller imports and validates the handoff, independently validates exact
   `P`, and records the final verdict through `puppet review`/`puppet accept`;
   it does not create an infinite proof-commit chain.

Review verdicts are invalidated by a head change. Never turn target self-reporting into a controller acceptance automatically.

The initial unattended Puppet campaign is local-only: it may create ordinary
commits in its isolated worktree but may not push, open a PR, merge, deploy, or
install globally. It still binds every test, review, handoff, and promotion to
the exact local head.

## Human tmux experience

The human observer is a first-class consumer.

- Launch prints the exact read-only attach command.
- Pane titles include target, repo, branch, and phase where practical.
- The session remains available after completion until explicitly closed.
- The target TUI is authentic; do not replace it with a summarized fake console.
- Codex/controller monitoring uses sanitized beacons, structured handoffs,
  exact commits, and state. It never reads the full TUI or transcript; the
  human may inspect the authentic TUI directly.

## Trust and safety model

Puppet live execution has exactly one supported harness trust profile: YOLO.
Prompted, sandboxed, and partial-auto launch modes are unsupported because they
break unattended orchestration.

- README, install guidance, `SKILL.md`, and `doctor` must disclose the
  unrestricted behavior before a user launches anything.
- Installation and zero-agent census remain non-launching. Before the first
  live launch, the operator must deliberately record standing unrestricted
  authorization in local, uncommitted policy. The public package never embeds
  an operator's authorization.
- Every adapter maps the exact current executable fingerprint to the harness's
  auto-approve/bypass control and sandbox-disable control where available.
  Unknown, partial, drifted, or unproved mappings fail closed; Puppet never
  silently falls back.
- YOLO grants harness mechanics, not task authority. It does not authorize
  merge, push, deploy, external send, spending, account/device/security change,
  secret access, destructive cleanup, or any other contract hard gate.
- Do not inspect `.env`, keychains, tokens, cookies, wallets, auth logs, private keys, or transcript files.
- Prompts travel through stdin or protected prompt files, never command-line arguments.
- Do not preserve arbitrary pane logs by default.
- Serialize session mutation and exact sends with local lock files.
- Reject recursive control of the current controller session unless explicitly designed and approved.

## Portable controller skills

`SKILL.md` should teach any compatible controller to:

1. Read the contract and applicable repo instructions.
2. Run `puppet doctor`.
3. Launch or reuse the exact target session.
4. Give the human the read-only tmux command.
5. Monitor sanitized status with bounded waits.
6. Send all steering through `puppet send`, never direct tmux keystrokes.
7. Import structured checkpoint handoffs without reading target terminals.
8. Review stable checkpoints independently and record an exact-head verdict.
9. Surface checkpoint discoveries, choices, and risks to the user in
   interactive operation; record them in campaign state/proof during unattended
   operation and continue unless a hard gate requires the user.
10. During an explicitly authorized unattended campaign, promote only an
    accepted exact candidate between sessions after the automated campaign gate;
    do not request per-rung user approval.
11. Preserve the session and evidence at handoff.
12. Halt/close only the exact registered target.

Controller-specific distribution:

- Codex: install/link the portable skill under its discovered personal skills root and generate `agents/openai.yaml`.
- Claude/AGY: use their discovered Agent Skills locations if compatible.
- Cursor or another harness without compatible skills: generate a thin native rule/command shim that tells the controller to call the same CLI.
- Grok or remote surfaces: use only their censused, real-conformance-proved
  local or remote transport.

Do not duplicate the core operating contract across controller shims.

## Sanitized state files

Each run root contains only:

```text
contract.json
campaign.json          # unattended self-hosting campaigns only
census.json
adapter-manifest.json
run-observation.json
state.json
events.jsonl
heartbeat
PROOF.md
handoffs/
  <checkpoint-id>.json
verdicts/
  <checkpoint-id>.json
review-qualifications/
  <reviewer-fingerprint>.json
promotions.jsonl       # self-hosting tracks only
conformance/
  <target>-<fingerprint>.json
```

Never include prompts, transcripts, raw pane logs, command arguments,
screenshots, source files, credentials, or raw CI logs unless the explicit
contract separately authorizes a known-safe artifact. Handoffs contain curated
claims and references, not copied conversations.

State writes are atomic. Event and promotion writes are append-only. Store full
target/controller version strings plus the supervising Puppet root, commit,
tree hash, executable path, and executable hash without storing secret-bearing
argv.

Every run, not only conformance runs, records requested and controller-observed
harness/model/version/effort, task profile/type, latency, safe native turn/tool
counts when exposed, checkpoint quality, repair cycles, proof integrity, and
controller verdict. Missing native metrics are `unavailable`, never inferred
from a transcript or target claim.

Long-running campaigns update `STATE.md`, `events.jsonl`, `heartbeat`, and
`PROOF.md`. The terminal proof identifies the locally committed candidate or
the exact blocker, every internal promotion, every real-harness probe, required
reviews, tests, gates honored, and the preserved rollback identities.

## Implementation phases

### Phase 0: campaign entry, provenance, and skeleton

- Start from a freshly fetched remote default in one isolated SaariusSkills
  worktree, with one branch, owner, and proof trail. Preserve any dirty primary
  checkout and all existing worktrees.
- Initialize the skill with the system skill-creator tooling and generate
  `agents/openai.yaml` from the completed skill.
- Import `plans/puppet/prior-proof-provenance.md` as curated design input.
  Reimplement private prior-art patterns unless a rights-and-attribution path
  explicitly permits code extraction into the MIT repository.
- Define campaign, contract, census, adapter manifest, lifecycle, journal,
  handoff, verdict, conformance, and promotion schemas.
- Create `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` before the job
  becomes long-running.

Stop condition: the package skeleton validates, provenance is classified, the
campaign boundary is recorded, and no live target has launched.

### Phase 1: minimum manually trusted Puppet N

- Implement only `doctor`, `launch`, `send`, `status`, `wait`, `checkpoint`,
  `review`, `accept`, `attach-command`, and `halt`. Return explicit
  `unsupported` for `promote`, `close`, controller-side source-editing or
  delivery commands, and undeveloped adapters. After the read-only AGY and
  independent-review bootstrap gates pass, `launch` may supervise a target
  contract whose allowed modes include `mutate` and `local_commit`, but only in
  that target's distinct candidate worktree.
- Implement the zero-agent census and generate doctor-only manifests for AGY,
  Cursor, Claude, Codex, and Grok.
- Implement controller-only exact-checkpoint verdicts, stable-supervisor and
  distinct-candidate identity, a tamper-evident/atomic journal, exact process
  and tmux identity, literal protected prompt transport, checkpoint
  containment, and preserved read-only human attach.
- Implement and deterministically test both checkpoint branches: source
  checkpoints require an exact candidate commit and stale-head invalidation;
  conformance checkpoints forbid a candidate commit and bind run ID, nonce,
  phase/sequence, executable/adapter/protocol fingerprints, artifact hashes,
  controller verdict, and fingerprint-drift invalidation.
- Make the YOLO-only warning, local standing authorization, exact
  current-version permission mapping, and fail-closed behavior unavoidable.
- Test pure kernel functions directly with deterministic unit, property, and
  Puppet-boundary fault-injection tests. Do not build a fake target harness or
  count simulated target behavior as qualification.

Stop condition: package validation and direct kernel tests pass; all five
manifests are fingerprinted and doctor-only; no real agent has launched.

### Phase 2: first real AGY conformance

- Run the standardized contract against the real installed AGY CLI in YOLO
  mode, inside a disposable fixture, from the fixed Puppet N supervisor.
- Prove exact-once `/teamwork-preview` envelope, ready checkpoint, persistent
  target availability, exactly one acknowledged follow-up, transcript-free
  status/wait, controller review/acceptance, protected-source no-drift, exact
  graceful halt, and preserved tmux evidence.
- Import the ready and follow-up artifacts through the source-free conformance
  checkpoint branch. Reject any candidate commit, identity drift, missing
  sequence/prior hash, or attempt to enter the source lifecycle.

Stop condition: exactly one AGY conformance session is accepted, blocked, or
failed with complete proof. Do not mutate Puppet, promote, close, or launch a
second live target in this phase.

### Phase 2.5: independent review-rail bootstrap

- Before any target mutates Puppet, qualify a reviewer that is materially
  different from that target. For the first AGY implementation rung, the fixed
  main Codex campaign controller may qualify through a controller-created,
  committed exact-head fixture with known required and rejected findings.
- Record the reviewer controller/harness/model/version/effort identity where
  exposed, review protocol and result hashes, exact base/head, read-only scope,
  classifications, and deterministic stale-head rejection. Validate the bounded
  review artifact independently and prove that the reviewer made no edits.
- This proof qualifies only the review rail. It does not graduate `codex`
  launch/send/status/wait/checkpoint/resume/halt capabilities and it cannot
  substitute for Codex Pass B later.
- If the main controller cannot prove an exact materially different identity or
  the fixture contract, use one already-proved real adapter to qualify a
  separate different model/harness serially. If neither route qualifies, stop
  before the first mutation with a precise blocker.

Stop condition: one independent review rail has a controller-validated,
fingerprinted qualification artifact ready to bind to the first exact candidate
review. No Puppet source mutation or promotion occurred during qualification.

### Phase 3: unattended self-hosting ratchet

- Use stable bootstrap Puppet N to supervise one real target implementing
  candidate N+1 in a separate worktree. The first slice is the bounded
  promotion command and its qualification machinery; later slices may add the
  next adapter.
- Refuse to start that mutation unless the Phase 2.5 reviewer qualification is
  current and materially different from the selected implementation target.
- Require committed checkpoints and structured handoffs. The immutable Codex
  campaign controller independently inspects exact commits and evidence.
- Make `promote` the first candidate N+1 slice after the AGY conformance and
  independent-review gates. Bootstrap N must continue returning `unsupported`
  while it supervises that mutation. Graduate the N+1 command only after its
  deterministic, exact-head, real-harness, independent-review, and controller-
  acceptance gates pass; then use the qualified N+1 release to promote later
  accepted candidates between sessions. Retain every prior stable version and
  rollback record.
- Continue one target at a time through real Cursor, Claude, Codex, and Grok
  conformance and disposable implementation rungs. Use current census results,
  not the design-session version table.
- After at most two review-triggered repair cycles for one slice, stop, split,
  defer, or record a blocker rather than reflexively extending the patch.

Stop condition: the v0.1 acceptance criteria pass or the campaign records one
precise evidence-backed blocker. Routine internal promotions require no user
interaction.

### Phase 4: distribution and controller portability

- Add controller-specific install/link instructions without performing a
  global install.
- Keep the portable skill canonical in SaariusSkills and validate trigger
  metadata in supported controllers.
- Use one proved non-Codex controller harness to supervise one bounded Codex
  target task, with the same CLI authority and proof contract.
- Record task/model outcome telemetry, but keep auto-routing deferred and
  explicit target/model selection authoritative.

### Phase 5: separately gated migration

- Keep `teamwork-preview` installed during development and while any active lane references it.
- Run one complete `agy-computer-use`-style milestone through `puppet`.
- Search known skill, automation, launcher, and repo references for `teamwork-preview`.
- Switch those references deliberately.
- Halt or preserve every old managed session.
- Remove the old skill recoverably only after the new path passes acceptance.

Do not delete or rewrite the active `teamwork-preview` skill as part of early implementation.

## Test matrix

Direct kernel and contract tests:

- exact-once AGY prefix;
- reject duplicate prefix, `/btw`, and `/side`;
- stdin/protected-file/buffer transport does not expose messages in argv;
- shell metacharacters remain literal;
- census allowlists executable discovery/version/help probes, caps time/output,
  avoids auth/session/config stores, and invalidates on any fingerprint change;
- `cursor-agent` and `cursor agent` remain separate entrypoints until observed
  process/fingerprint equivalence is proved;
- generated adapters cannot launch and every ungraduated capability returns
  `unsupported`;
- malformed contracts fail closed;
- lifecycle transitions reject illegal moves;
- target cannot self-accept;
- target handoff import cannot self-accept or create a controller verdict;
- handoffs reject mutable/abbreviated commits, transcripts, logs, secrets, and
  out-of-root references;
- controller review and acceptance bind to an exact checkpoint and are
  invalidated by a head change;
- session send lock serializes concurrent callers;
- wrong executable, process birth identity, pane, tmux socket/session identity,
  or supervising Puppet hash rejects send/status/halt;
- session collision does not start a second target;
- journal locking, canonical JSON, sequence/previous-hash chain, fsync, atomic
  replacement, replay, duplicate request IDs, truncation, symlink components,
  and interrupted writes fail safely;
- malformed/oversized/secret-shaped beacons are ignored and flagged;
- missing local YOLO acknowledgement, incomplete auto-approve/sandbox-disable
  mapping, or version drift prevents launch; no prompted/sandboxed fallback
  exists;
- AGY's normalized AI-overage-credit advisory cannot by itself mark a run
  blocked, failed, exhausted, or diagnostic-required; only separate
  controller-observed protocol/process evidence may do so;
- adapter capability failures are actionable;
- halt targets only the registered process/session;
- proof state never contains prompt/transcript bodies;
- a self-hosting session rejects overlapping supervisor and candidate roots;
- every controller command rejects a changed supervisor path/hash;
- promotion rejects an unaccepted candidate, a mismatched commit, a live
  session, missing campaign authorization, missing independent review, a human
  gate, or unresolved required findings;
- review qualification rejects edits, wrong or stale heads, malformed findings,
  unbound reviewer identity, and a reviewer that is not materially different
  from the implementation target;
- promotion preserves the prior stable identity and append-only history and
  affects only subsequent sessions.

Real-harness conformance, always serial and YOLO-only:

1. Codex/Puppet N → real AGY: ready checkpoint, one acknowledged follow-up,
   controller verdict, exact graceful halt, preserved tmux; no Puppet mutation
   or promotion.
2. Codex/stable Puppet → real AGY: bounded candidate implementation and first
   automated exact-head internal promotion under the campaign authorization.
3. Repeat the identical conformance contract and then one disposable
   implementation slice with real Cursor, Claude, Codex, and Grok, one at a
   time. Each adapter stays doctor-only until its own real proof passes.
4. Exercise busy-without-proved-queue, unacknowledged send, unexpected exact
   target exit, stale identity, malformed handoff, and graceful halt through
   controlled Puppet-boundary faults around real harness sessions; never target
   unrelated processes.
5. Use one proved non-Codex controller harness → real Codex for a bounded
   final portability task.

No fake target harness, pane scrape, transcript read, or target self-report may
substitute for these real behaviors.

## Acceptance criteria for v0.1

- The zero-agent census fingerprints AGY, Cursor, Claude, Codex, and Grok and
  generates hard-disabled doctor-only manifests without reading auth, session,
  transcript, or secret material.
- One command launches an exact target in a durable tmux session.
- The human receives a functioning read-only attach command.
- Every AGY substantive message begins with exactly one `/teamwork-preview` without relying on controller memory.
- Every live adapter is YOLO-only; the package warns users upfront, requires an
  explicit local acknowledgement, proves the exact current-version
  auto-approve/sandbox-disable mapping, and otherwise fails closed.
- Target/model/effort selections are verified or the launch fails closed.
- One persistent target parent survives helper work, local tests, and bounded
  controller waits.
- No more than the contract's helper cap is active without an explicit override.
- The target cannot mark itself accepted.
- Status works without transcript or arbitrary pane scraping.
- Codex learns from exact commits, validated checkpoint handoffs, and evidence,
  never target terminals or transcript stores.
- Controller-only review and acceptance commands bind verdicts to exact
  checkpoints. Source-head drift invalidates source verdicts; run, nonce,
  sequence, artifact, executable, adapter, or protocol drift invalidates
  conformance verdicts.
- Prompts and steering content do not appear in process arguments or state files.
- Source/proof checkpoint identity can be bound to exact heads.
- The first source-free AGY ready/follow-up pair is accepted through the
  conformance lifecycle without inventing a candidate commit, and a
  deterministic test proves conformance checkpoints reject candidate commits.
- The controller can reject a checkpoint and send one bounded repair packet through the same session.
- A rejected published checkpoint is repaired only with additive commits;
  committed history is never amended or rewritten.
- The human can audit the target TUI from launch through preserved closeout.
- A stable Puppet version can supervise a distinct Puppet candidate worktree
  without executing candidate code during the live session.
- A materially different review rail passes a bounded read-only exact-head
  fixture before the first AGY mutation; that proof is bound to later reviews
  and does not imply Codex target-adapter support.
- A candidate cannot become the next stable supervisor without independent
  exact-head verification, required real-harness proof, controller acceptance,
  and a matching bounded campaign authorization.
- Bootstrap Puppet N exposes only the minimum command surface and returns
  `unsupported` for `promote`; accepted v0.1 Puppet N+1 additionally exposes
  `promote` only after that command's full campaign qualification. `close`,
  controller-side source editing, delivery commands, and unproved adapters
  remain unsupported.
- At least one unattended N → N+1 internal promotion preserves the prior stable
  version and its append-only promotion/rollback record without per-rung user
  input.
- The identical behavioral conformance contract passes against the real AGY,
  Cursor, Claude, Codex, and Grok CLIs, one at a time; no fake target qualifies
  an adapter.
- Harness/model/task outcome fields are recorded for future evidence-based
  routing, while explicit target/model selection remains authoritative.
- Skill validation, direct kernel tests, real-harness conformance proof, and
  source-blind independent review pass at the exact locally committed candidate.
- The unattended campaign ends with either that fully proved local candidate or
  one precise blocker packet. It performs no merge, push, deploy, global
  install, external send, spending, destructive cleanup, secrets/accounts, or
  security change.

## Non-goals for v0.1

- Building a universal GUI automation framework.
- Scraping or indexing target transcripts.
- Automatically merging, deploying, spending, sending, or altering accounts.
- Supporting every harness before its real CLI is available and tested.
- Supporting prompted, sandboxed, or partial-auto live operation.
- Treating YOLO mode as isolation or as authority for gated external actions.
- Creating a cloud control plane.
- Automatically selecting or switching harnesses/models in v0.1. The evidence
  schema is included now; auto-routing remains deferred.
- Replacing native target teamwork/subagent systems.
- Letting multiple controllers mutate the same target session.
- Automatically deleting tmux sessions or proof roots.
- Reading target terminals or transcripts as the controller's learning channel.
- Letting a live target replace the Puppet executable supervising its session.
- Promoting a candidate outside one explicit campaign authorization or without
  exact-head tests, real-harness proof, independent review, acceptance, and
  rollback preservation.
- Guaranteeing unattended completion when a genuine external gate or ambiguous
  safety failure exists; the required fallback is a precise blocker packet.
- Claiming hostile same-UID containment without a separately proved isolation
  boundary.

## Guidance for the implementation agent

1. Treat `plans/puppet/codex-goal.md`, this seed,
   `plans/puppet/DECISIONS.md`, `plans/puppet/PROOF.md`, and
   `plans/puppet/prior-proof-provenance.md` as the campaign packet.
2. Read the system skill-creator instructions and active repository contracts
   completely. Use the repo's safe-worktree workflow before any source change.
3. Fetch the current remote default and build in a new isolated SaariusSkills
   worktree. Preserve the dirty main checkout, unrelated changes, and existing
   worktrees.
4. Inspect current local orchestration skills and separately authorized prior
   lanes only for admitted mechanics and test expectations. Do not copy stale
   model assumptions, transcript/pane monitoring, operator-specific host
   policy, or private source without a cleared license path.
5. Put the YOLO-only warning first in public documentation and make live launch
   impossible until exact mapping and explicit local authorization pass.
6. Implement and directly test the minimum trusted kernel, census, manifests,
   provenance, journal, contracts, and all five doctor-only adapters before any
   real launch. Do not create or use a fake target harness for qualification.
7. Keep the primary Codex campaign controller and every per-session Puppet
   supervisor fixed and controller-owned. Targets edit only separate candidate
   worktrees.
8. Run the approved shared prompt against real AGY first, then continue serially
   through real Cursor, Claude, Codex, and Grok. Launch every target YOLO-only.
9. Learn from exact commits, bounded structured checkpoints, native allowlisted
   events, and controller evidence, never target panes, transcripts, or session
   stores.
10. Within the explicit campaign envelope, independently review, repair, accept,
    and promote exact candidates between sessions without waking the user.
    Preserve prior stable versions and rollback records. Stop on hard gates,
    ambiguity, repeated repair failure, or scope expansion.
11. Do not merge, push, deploy, globally install, delete legacy skills, send
    externally, spend, change accounts/security, or inspect secrets/auth data.
12. Put “Puppet uses agents like puppets to build Puppet—the skill that uses
    agents like puppets” in the repository root README, not a skill-local
    README.
13. Finish locally committed with skill/package checks, direct tests, exact-head
    independent review, real-harness proof, updated `STATE.md`, `events.jsonl`,
    `heartbeat`, and `PROOF.md`, plus residual limitations. If completion is
    impossible, finish with one precise blocker packet instead of a false green.

Implementation stop condition: the v0.1 acceptance criteria pass at one exact
local candidate commit; real AGY, Cursor, Claude, Codex, and Grok conformance is
recorded sequentially; at least one unattended internal N → N+1 promotion has
preserved rollback; a human read-only attach path is proved; no active workflow
depends on a modified/deleted legacy skill; and no excluded delivery or external
human-gated action occurred. Otherwise stop with the exact evidence-backed
blocker and the next safe action.
