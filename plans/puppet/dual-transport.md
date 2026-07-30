# Puppet dual-transport plan

Status: accepted product direction; implementation remains split between the
tmux-centered Puppet PR and the experimental Herdr-Puppet lane.

## Decision

Puppet should offer two explicit terminal backends behind one controller
contract:

```text
Puppet run contract
├── tmux backend
│   └── private tmux session -> read-only attach ticket
└── Herdr backend
    └── owned Herdr tab/pane -> SSH PTY -> remote harness
```

Puppet owns admission, authentication/profile policy, target identity,
instructions, sequencing, checkpoints, proof, review, acceptance, human gates,
and exact stop authority. A backend owns only its terminal/session identity,
prompt delivery, structural status, human-view doorway, and backend-specific
lifecycle evidence.

One installed Puppet skill may expose both backends. Herdr remains optional:
users who do not install or use Herdr retain the complete tmux path. Users may
set a preferred backend, but each run records one explicit backend before
launch. Puppet must not silently fall back to another backend after planning.

The current qualification target is the same five regular-session harnesses
for both backends:

```text
Codex CLI
Claude Code
Cursor Agent
Grok Build
AGY
```

That creates ten backend/harness qualification cells. A qualified tmux cell is
useful implementation evidence for the corresponding Herdr cell, but it is not
Herdr proof. Every cell must bind its own live backend, host, executable,
profile, absence of an explicit model selector for the default-model run,
controller-observed model/effort or explicit `unavailable`, instruction plane,
session identity, prompt delivery, checkpoint, view, and lifecycle evidence.

## User experience

The eventual public choice should be equivalent to:

```text
puppet ... --transport tmux
puppet ... --transport herdr
```

Exact CLI spelling may follow the existing command grammar. The invariant is
that the plan, lease, receipts, status, view result, and proof all name the
selected backend.

- `tmux` is the portable qualified default until another backend independently
  reaches the same stability class.
- `herdr` may enter as an explicit experimental opt-in after its minimum beta
  gate passes.
- A user-level preference may choose Herdr by default. It does not erase the
  per-run transport field or permit automatic fallback.
- One run uses one terminal backend. Initial v0.1 does not promise that a
  Herdr-native run can also be viewed through tmux, or that a tmux-native run
  can be adopted as a Herdr-native run.

One controller campaign may eventually run several lanes concurrently and mix
backends. Mixed-backend mutation remains `unsupported` until its dedicated
qualification gate passes. Every planned lane must record its own lane ID,
backend, harness, source slice, mutation owner, worktree, profile, session,
lease, and proof root before launch. No lane may have two input, halt, recovery,
or adoption authorities, and lanes that can write the same source slice remain
serialized under one mutation owner.

The view doorway remains backend-specific:

- tmux returns a short-lived, one-use, read-only attach doorway bound to the
  exact private socket, server, session, pane, and target identity;
- Herdr returns the exact operator session and owned tab/pane projection
  without transferring authority over the parent operator session.

Do not hide a tmux attach inside a Herdr pane and report it as the Herdr
backend. That may be a useful operator layout, but its target transport remains
tmux and its receipts must say so.

A Herdr-displayed read-only attachment to a tmux-owned target is deferred and
unsupported by this plan. If later research qualifies that projection, tmux
must remain the recorded execution backend and Herdr must receive no input,
halt, recovery, or adoption authority. Do not make that composition a
prerequisite or implied feature of the first dual-backend release.

## Shared controller boundary

The shared Puppet layer must remain transcript-blind during ordinary
operation. It may consume only structural state and bounded structured
checkpoints. Neither backend may copy pane contents, prompts, responses,
scrollback, account identifiers, auth material, or environment contents into
controller proof.

Authentication is independent of the terminal backend. A subscription already
authorized through a qualified host-local mechanism should be reused without
repeated prompts. Otherwise Puppet may present one explicit initial enrollment
handoff. No backend may copy authentication state between machines or make
ordinary terminal attachment an authentication authority.

Common operations should retain one semantic contract:

```text
doctor
plan
launch
send
status
wait
checkpoint
view
halt
```

Compatibility commands such as tmux `attach-command` may remain. Unsupported
backend operations must fail explicitly rather than borrow another backend's
authority.

Harness knowledge is reusable separately from backend proof. Puppet may reuse
or extract versioned facts and deterministic behavior for:

- executable discovery and fingerprinting;
- subscription/profile admission without copying authentication stores;
- regular-session launch envelopes and current default-model observation;
- startup trust, permission-bypass, and always-approve gates;
- harness-specific instruction wrappers and structured checkpoint prompts; and
- bounded prompt consumption, steering, and terminal-result classification.

The receiving backend must rerun those behaviors through its own transport on
the actual target host. It may not import a tmux receipt, manifest graduation,
target self-report, or operator recollection as Herdr qualification.

## Backend evidence

Never reinterpret an old receipt as another backend's proof. Every plan, lease,
handoff, checkpoint, halt receipt, and terminal-evidence record binds:

- backend name and schema version;
- exact backend executable/protocol identity;
- exact harness-adapter and transport-adapter fingerprints;
- target executable and process identity when that capability is qualified, or
  an explicit `unavailable` capability result when it is not;
- run, source, worktree, and proof identity;
- allowed mode and human gates;
- the backend-specific session identity join; and
- a per-operation qualification key over
  `(backend, harness, host, executable_fingerprint,
  harness_adapter_fingerprint, transport_adapter_fingerprint,
  protocol_fingerprint)`.

Every common operation records its own qualification result for that key:
`doctor`, `plan`, `launch`, `send`, `status`, `wait`, `checkpoint`, `view`,
`halt`, and `recover`. Reused code enters a new backend cell as no higher than
`declared`; it never carries `controller_verified` status across transports.

If a backend's current plan or lease cannot encode the harness-side fields in
that key, the row remains incomplete until a versioned controller-attested
harness binding is referenced by both records. A five-row summary matrix
cannot silently backfill missing lease authority.

An unavailable target-process identity must not be inferred or replaced with a
different process identity. In particular, an experimental Herdr record may
bind the foreground SSH process as transport evidence, but must not report it
as the remote harness process. Operations that require the unavailable
identity remain explicitly `unsupported`.

The tmux join includes its private socket, server, session, pane, and client
mode. The Herdr join includes the authorized parent session and workspace plus
the run-owned tab, pane, terminal, SSH target, and monotonic send sequence.

## Qualification levels

Do not make full stable qualification a prerequisite for honest experimental
use.

### tmux stable lane

Keep the current PR #5 proof ladder across Codex CLI, Claude Code, Cursor
Agent, Grok Build, and AGY. Each harness needs a real subscription-backed
regular session completing launch, non-argv input, structured checkpoint,
read-only attach, detach/reattach, controller verdict, exact halt, and
preserved evidence. A passing harness does not qualify another harness.

### Herdr experimental lane

Standalone Herdr-Puppet becomes eligible for experimental merge review and
admission only after one fresh 1x1 regular-session run for each of Codex CLI,
Claude Code, Cursor Agent, Grok Build, and AGY proves:

1. an explicit narrow capability for the parent operator session;
2. one newly created run-owned tab/pane and exact SSH target;
3. the exact remote executable, subscription-backed profile, absence of an
   explicit model selector, controller-observed model/effort or explicit
   `unavailable`, regular-session launch envelope, and harness-specific
   instruction wrapper;
4. any startup trust or unrestricted-mode gates required by that harness,
   cleared only inside the owned lane through a bounded, exact-workspace,
   single-use, sequence-bound backend operation;
5. independently observed harness readiness followed by bounded non-argv input
   with monotonic sequence handling;
6. prompt consumption, one sequenced steering turn, and one strict structured
   terminal checkpoint;
7. transcript-blind structural status and an operator-visible native TUI;
8. human client detach/reattach with the same leased Herdr identities; and
9. non-destructive lease preservation and maintenance inventory.

The controller records a five-row evidence matrix bound to the exact
Herdr-Puppet head. Doctor-only, launcher-only, mocked, unauthenticated,
parser-only, target-self-reported, or tmux-derived evidence does not satisfy a
row. No backend/harness cell inherits qualification from another cell.
All five rows bind one immutable runtime implementation head; a later
proof-only child commit may curate receipts without changing runtime bytes.
Any runtime-code change invalidates the five rows and requires affected live
qualification again.

An independently validated terminal artifact may explain or close out a run
whose strict checkpoint was not observed, but it cannot graduate that
backend/harness row. Exact-tab cleanup is optional maintenance proof behind its
own human gate; it is never a qualification prerequisite and is never
misreported as a remote-process halt.

Raw or manually injected startup-gate input is not qualifying evidence.
Harnesses whose gate must be cleared before ordinary readiness, including
Cursor Workspace Trust, require a dedicated pre-readiness reducer; otherwise
that harness row stops incomplete.

Operations not yet qualified, including targeted halt or recovery, remain
explicitly unsupported. A preserved tab is not a successful halt.

### Herdr stable lane

Stable qualification still requires the stronger Herdr-Puppet acceptance
contract: remote process identity, targeted halt, fail-closed recovery,
wrong-target and out-of-band mutation probes, repeated concurrency proof,
redacted exact-head evidence, and independent review.

Crash recovery and repeated concurrency qualification therefore remain stable
promotion gates, not blockers for the clearly labeled experimental
five-harness 1x1 matrix.

### Mixed-backend campaign lane

Mixed concurrency is qualified at the campaign layer, not by giving one target
two controllers. It remains explicitly `unsupported` until one exact-head
qualification runs exactly one tmux lane and one Herdr lane concurrently
against disjoint fixtures and proves:

1. separate worktree, profile, session, lease, and proof roots;
2. one aggregate top-level capacity cap and one mutation owner per source
   slice;
3. no input, checkpoint, proof, view, or closeout evidence bleed between
   lanes;
4. stopping the exact tmux lane leaves all Herdr identities unchanged; and
5. preserving the exact Herdr lane leaves all tmux identities unchanged and
   continues counting the preserved Herdr resources until separately
   authorized cleanup.

Only after that gate may a closeout run, for example, drive local Codex,
Claude, Cursor, or Grok lanes through tmux while a remote AGY lane runs through
Herdr. Every lane still keeps exactly one execution backend and exact
independent proof.

## Integration order

Keep the current source owners separate until the two vertical paths are
honest:

1. Freeze this ten-cell qualification boundary without moving implementation
   between the current source owners.
2. Finish PR #5 independently as the five-harness tmux/core Puppet vertical.
3. Finish Herdr-Puppet independently with the five-harness experimental matrix
   and explicit unsupported capabilities.
4. Reconcile this plan against both exact terminal heads and evidence sets.
5. Extract the shared transport-neutral controller and reusable harness
   adapter interface from proven behavior instead of predicting it inside a
   tmux- or Herdr-specific class.
6. Admit Herdr into Puppet as an optional backend without deleting the
   standalone experimental skill until compatibility and migration are proved.
7. Qualify mixed-backend campaigns only after single-backend lanes remain
   independently operable and diagnosable.

Harness-native helpers are a separate concurrency layer. A combined route must
cap top-level terminal lanes and helpers together, account for every helper,
and retain one mutation owner per source slice. No removed or experimental
slash-command profile is a dependency of this transport plan.

## Non-goals

- Replacing tmux with Herdr.
- Requiring Herdr for Puppet installation or use.
- Treating labels, focus, or an Agents sidebar as runtime authority.
- Adopting arbitrary existing Herdr tabs or tmux sessions.
- Automatically changing backend after a launch or transport failure.
- Claiming that one backend's persistence, halt, recovery, or attach proof
  qualifies the other.
- Claiming that one harness's success qualifies a different harness.
- Giving tmux and Herdr concurrent mutation or lifecycle authority over the
  same target.

## Immediate close condition

This refresh is complete when it records the ten backend/harness cells, the
reusable-harness-versus-fresh-proof boundary, and safe mixed-backend lane
semantics without moving implementation between PR #5 and the Herdr-Puppet
lane. The next work is to finish both standalone verticals against this
contract, not begin the broad transport refactor early.
