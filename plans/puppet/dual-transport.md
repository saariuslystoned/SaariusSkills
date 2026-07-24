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

The view doorway remains backend-specific:

- tmux returns a short-lived, one-use, read-only attach doorway bound to the
  exact private socket, server, session, pane, and target identity;
- Herdr returns the exact operator session and owned tab/pane projection
  without transferring authority over the parent operator session.

Do not hide a tmux attach inside a Herdr pane and report it as the Herdr
backend. That may be a useful operator layout, but its target transport remains
tmux and its receipts must say so.

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

## Backend evidence

Never reinterpret an old receipt as another backend's proof. Every plan, lease,
handoff, checkpoint, halt receipt, and terminal-evidence record binds:

- backend name and schema version;
- exact backend executable/protocol identity;
- target executable and process identity when that capability is qualified, or
  an explicit `unavailable` capability result when it is not;
- run, source, worktree, and proof identity;
- allowed mode and human gates;
- the backend-specific session identity join.

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

Keep the current PR #5 proof ladder. The decisive vertical proof is one real
harness completing launch, non-argv input, structured checkpoint, read-only
attach, detach/reattach, controller verdict, exact halt, and preserved
evidence.

### Herdr experimental lane

Herdr may be offered as experimental after one fresh 1x1 run proves:

1. an explicit narrow capability for the parent operator session;
2. one newly created run-owned tab/pane and exact SSH target;
3. bounded non-argv input with monotonic sequence handling;
4. transcript-blind structural status and one structured checkpoint;
5. human client detach/reattach with the same leased identities;
6. non-destructive lease preservation at the stop condition.

Operations not yet qualified, including targeted halt or recovery, remain
explicitly unsupported. A preserved tab is not a successful halt.

### Herdr stable lane

Stable qualification still requires the stronger Herdr-Puppet acceptance
contract: remote process identity, targeted halt, fail-closed recovery,
wrong-target and out-of-band mutation probes, repeated concurrency proof,
redacted exact-head evidence, and independent review.

Crash recovery and repeated three-pane qualification therefore remain stable
promotion gates, not blockers for the clearly labeled experimental 1x1 lane.

## Integration order

Keep the current source owners separate until the two vertical paths are
honest:

1. PR #5 continues to harden Puppet's tmux controller and real-harness path.
2. Herdr-Puppet remains a separate experimental skill while its lease and
   input transport are qualified.
3. Run one minimum vertical proof through each backend.
4. Extract the shared transport-neutral controller interface from the proven
   behavior instead of predicting it inside a tmux-specific class.
5. Admit Herdr into Puppet as an optional backend without deleting the
   standalone experimental skill until compatibility and migration are proved.

PR #6's within-harness teamwork is a separate concurrency layer. A combined
route must cap top-level terminal lanes and per-harness helpers together and
retain one mutation owner per source slice.

## Non-goals

- Replacing tmux with Herdr.
- Requiring Herdr for Puppet installation or use.
- Treating labels, focus, or an Agents sidebar as runtime authority.
- Adopting arbitrary existing Herdr tabs or tmux sessions.
- Automatically changing backend after a launch or transport failure.
- Claiming that one backend's persistence, halt, recovery, or attach proof
  qualifies the other.

## Immediate close condition

This plan update is complete when it records the dual-backend boundary without
moving implementation between PR #5 and the Herdr-Puppet lane. The next work is
the two bounded vertical proofs, not a broad transport refactor.
