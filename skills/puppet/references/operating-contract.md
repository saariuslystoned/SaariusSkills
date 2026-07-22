# Puppet operating contract

## Authority and ownership

The controller owns the contract, gates, lifecycle ledger, independent review,
verdicts, acceptance, and exact halt. The target owns only the task modes and
candidate worktree named by the contract. One target cannot accept itself.

Run one target and one mutation owner at a time. Bind every session to one
controller, target, repository, branch, proof root, private tmux socket, exact
process birth identity, and immutable supervising Puppet executable. Refuse
overlapping supervisor and candidate roots.

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

## Human gates

YOLO mechanics do not authorize merge, push, PRs, deploy, publish, global
install, external sends, spending, deletion/archive, account/security changes,
secret access, or interference with pre-existing processes and sessions.
