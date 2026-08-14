# Campaign recovery

Recovery reconciles the persisted exact identities for an interrupted
probe or run. It may halt the exact target but never relaunches it. Any
identity or state ambiguity leaves the lane fenced for controller
adjudication instead of being guessed at or cleaned up automatically.

## Recovering an interrupted probe

If a probe is interrupted, use `adapter_lab.py recover` with the same
target, run ID, controller, campaign, goal, manifest, mapping,
authorization, and proof root. Recovery reconciles the persisted exact
identities and may halt that exact target; it never relaunches.

## One-use reservations and stop-and-preserve

Claude matched-control probe reservations are one-use. Never retry or
relaunch the same run after reservation; use exact `adapter_lab.py
recover`. Stop and preserve the run when its attestation, reservation,
ready checkpoint, or hash-only signal observation is missing or
drifted. Also stop on a non-source, ambiguous, or post-observation
recreated signal leaf; do not manually delete or recreate it.

The matched-control pairing and promotion rules live in
[qualification-contract.md](qualification-contract.md).

## Grok dead-lease reconciliation

Ordinary `halt` targets only the exact registered target; this is the
sole exception path.

`reconcile-grok-dead-lease` is the sole exceptional controller-only path
for an explicitly named Grok registry record that remains `BLOCKED` with
a proven-dead `launch_incomplete` target and preserved dead pane. It
strictly revalidates the recorded process, private tmux topology, and
canonical fixed Grok lease generation and its exact backed legacy
compatibility fence. Under the target lock and then the existing legacy
lock, it changes only the exact `halting` target generation and
matching fence to `halted`. It never signals, attaches, updates the
registry or proof journal, creates or repairs authority evidence, or
relaxes ordinary `status` and `halt`. Replay may validate closed
schema-v1 process history; the current fence still must match the
target's full v2 birth identity.

## Activation rollback fencing

A failed or timed-out activation rolls back only after the controller
proves the exact target stopped and the protected same-target
population returned to baseline. Halt, population, artifact, or
rollback ambiguity leaves the activation fenced for controller
adjudication; recovery never relaunches or guesses at cleanup. The
exact per-harness activation transactions live in
[qualification-contract.md](qualification-contract.md).
