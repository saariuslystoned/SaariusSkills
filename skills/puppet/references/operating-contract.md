# Puppet operating contract

## Authority and ownership

The controller owns the contract, gates, lifecycle ledger, independent review,
verdicts, acceptance, and exact halt. The target owns only the task modes and
candidate worktree named by the contract. One target cannot accept itself.

Run one target and one mutation owner at a time. Bind every session to one
controller, target, repository, branch, proof root, private tmux socket, exact
process birth identity, and immutable supervising Puppet executable. Refuse
overlapping supervisor and candidate roots.

All real-harness probes and normal sessions serialize through the fixed
per-account controller lock at
`~/.local/state/saarius-puppet-controller-v1`. A normal session holds a durable lease from
launch admission through exact halt; changing a checkout, state root, or proof
root cannot bypass it. The controller attestation ledger is likewise fixed and
checkout-independent. Both mechanisms assume cooperative same-UID execution
and do not turn YOLO targets into hostile-code containment.

The durable lease binds activity kind, run, campaign, goal fingerprint, proof
root, state root, session, target, controller, process, and lifecycle state.
Normal launch, follow-up delivery, cleanup, and halt serialize through one
per-session operation lock. Graceful halt intent/submission entries bind the
target PID, v2 identity digest, action index, and action; an interrupted intent
is ambiguous and must never be resent. The explicit parallel-target override
accounts only for the named pre-existing process set; it does not bypass the
controller lease.

Halt action is target-aware: non-AGY uses exact positive-PID `SIGINT`; AGY uses
private-pane EOF. Never send tmux `C-c` or process-group signals.

A real-harness probe may observe a bounded same-executable child population
created by its registered pane process. Each child needs an exact live v2 birth
identity and executable identity plus an acyclic kernel-revalidated PPID chain to
the registered root from one bounded discovery pass plus birth-bound per-node
samples. On Darwin, birth identity is `proc_pidinfo` `(sec, usec)`; on Linux,
`(kernel.boot_id,
/proc/<pid>/stat_starttime_ticks)`. Siblings, children of a protected process,
missing parents, PID reuse, and identity drift fail closed. Keep full ancestry
history for transient descendants as receipt evidence. Puppet never signals those
descendants or a process group; non-AGY halt authority is the exact registered
positive PID and AGY EOF authority is the exact registered private pane. If a
provisional target cannot be fully controller-bound before input, keep it fenced
and non-qualifying without any halt action. After halt, the same-target population
must return to the exact protected baseline before a receipt can be accepted.

## Lifecycle

The source-free conformance branch is:

```text
NEW -> PREFLIGHTED -> STARTING -> ACTIVE -> CONFORMANCE_READY
    -> ACTIVE -> CONFORMANCE_CHECKPOINT_READY
    -> AWAITING_CONFORMANCE_REVIEW -> ACCEPTED | BLOCKED | FAILED -> HALTED
```

The source branch is:

```text
NEW -> PREFLIGHTED -> STARTING -> ACTIVE -> SOURCE_CHECKPOINT_READY
    -> AWAITING_SOURCE_REVIEW -> ACTIVE | SOURCE_ACCEPTED
    -> PROOF_CHECKPOINT_READY -> TARGET_DONE
    -> AWAITING_CONTROLLER_REVIEW -> ACTIVE | ACCEPTED | BLOCKED | FAILED
    -> HALTED
```

Reject every undeclared transition. A ready conformance checkpoint is
nonterminal. Only its exact follow-up may receive a conformance verdict. A head
change invalidates source review; any run, nonce, sequence, executable, adapter,
protocol, or artifact drift invalidates conformance review.

## Monitoring and evidence

Expose only structural process/tmux liveness, validated protocol progress,
bounded checkpoint references and hashes, controller verdicts, blockers, and
next actions. Never inspect a pane or transcript to learn status. Keep
advisories, provider errors, process state, protocol state, and terminal
verdicts separate.

State projections are atomic. Events and promotions are append-only and
hash-chained. Preserve stopped sessions by default. `halt` affects only the
registered target; `close` is unsupported by bootstrap Puppet.

An interrupted Pass B probe is recovered only through its persisted exact
identity with `adapter_lab.py recover`. Recovery never relaunches. It either
verifies the committed terminal receipt or gracefully halts the exact surviving
target and records a failed recovery result for controller review. On Linux,
use pidfd when available for signal delivery; on macOS, acknowledge residual
identity check-to-kill races and re-sample deterministically before blocker
finalization.

## Human gates

YOLO mechanics do not authorize merge, push, PRs, deploy, publish, global
install, external sends, spending, deletion/archive, account/security changes,
secret access, or interference with pre-existing processes and sessions.
