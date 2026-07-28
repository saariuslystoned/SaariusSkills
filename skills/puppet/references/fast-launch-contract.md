# Fast launch contract

Use the fanout coordinator for an operator-selected mix of one through five
qualified regular targets: `agy`, `codex`, `claude`, `cursor`, and `grok`.
Selection is explicit; Puppet does not route targets automatically.

## Warm path

1. Reuse each selected harness's qualified adapter manifest and, except for
   AGY, its stable enrolled private subscription profile. Do not run census,
   onboarding, login, probes, pairing, or qualification merely because the
   operator requested a new ordinary session.
2. Allocate one clean worktree, session, run root, proof root, state root, and
   task input artifact per selected target. Roots must not overlap.
3. Compile one exact `puppet.operator-run-plan/v1` packet per lane. Plan
   compilation is read-only and may proceed concurrently. Every plan in one
   set must share the same exact controller and campaign authority.
4. Submit the exact plan files together:

   ```bash
   python3 <skill-root>/scripts/puppet_fanout.py launch \
     --plan <agy-plan.json> \
     --plan <codex-plan.json> \
     --plan <claude-plan.json> \
     --plan <cursor-plan.json> \
     --plan <grok-plan.json> \
     --allow-live-launch \
     [--open-views]
   ```

   Omit every target the operator did not select. `--allow-live-launch`
   acknowledges only the existing exact YOLO launch commands in those plans;
   it grants no new account, external-effect, or qualification authority.
5. Read body-free progress events from stderr and the target-sorted aggregate
   result from stdout. The result binds every exact plan path, file hash,
   canonical plan hash, the plan-set hash, the fanout script's exact SHA-256,
   and the v0.1 controller identities. A full success exits 0, total failure
   exits 2, and partial launch or viewer completion exits 4.

The coordinator validates all plan identities and root separation before
submitting a child. Immediately before each launch, that lane recompiles its
exact plan through the immutable v0.1 controller. Every lane must pass that
read-only barrier before any controller starts. It then invokes each
single-target controller in its own isolated subprocess concurrently. Each
child has a 120-second controller deadline and a 15-second exact-controller
interrupt grace. It then terminates and, after five more seconds, kills only
that lane's isolated owned controller process group so a descendant cannot pin
the batch. Operator Ctrl-C instead sets one idempotent batch cancellation
event. No not-yet-started child may launch after it; each active exact child
gets five seconds for controller cleanup before the same bounded owned-group
fallback. The structured interruption receipt is emitted after that cleanup,
never after the full 120-second deadline. A timeout is never reported as a
clean failure. The coordinator never invokes qualification or account actions.

Child stdout and stderr are drained continuously so pipe backpressure cannot
stall a lane. Capture is memory-bounded to 1 MiB per stream and excess bytes
are discarded; oversized or malformed JSON fails closed. The aggregate never
copies raw child objects. It projects an action-specific allowlist, verifies
session/repository/branch/profile/process-state/viewer bindings, drops
unrecognized fields, and maps unknown child error text to
`controller_rejected`. Descendants retaining controller pipes cannot pin the
batch, even after leaving the owned process group; their lane output is
invalidated without closing a buffered pipe from another thread.

Startup gates, auth revalidation, prompt delivery, exact leases, and process
identity remain owned by the proven single-target controller. A runtime
failure is lane-local: active siblings remain active and are never
automatically halted. It runs one exact read-only `status` reconciliation for
each failed submitted launch and retains the exact status and conditional halt
commands. After every launch has settled, it creates fresh attach tickets
concurrently for active lanes, or opens structurally verified native read-only
views concurrently when `--open-views` was selected. The initial short-lived
attach command is omitted; the canonical fresh result is
`lanes.<target>.viewer.result`. Attach-command children use a separate
13.25-second worst-case supervision budget, below the controller ticket's
30-second TTL, so one stalled lane cannot expire a successful sibling's ticket
before aggregate output. The direct `attach` lifecycle uses the same bound.

## Lifecycle fanout

Use the same exact plan set for concurrent lifecycle reads or exact shutdown:

```bash
python3 <skill-root>/scripts/puppet_fanout.py status --plan <plan> [...]
python3 <skill-root>/scripts/puppet_fanout.py attach --plan <plan> [...]
python3 <skill-root>/scripts/puppet_fanout.py view --plan <plan> [...]
python3 <skill-root>/scripts/puppet_fanout.py halt --plan <plan> [...]
```

`attach` prints fresh one-use read-only attach commands. `view` opens native
read-only terminal windows. `halt` delegates only the exact `(state root,
session)` pair from each plan; it is not cleanup authority for any other
process or tmux session.

## Failure and recovery

- Invalid or tampered plans, duplicate targets or sessions, controller drift,
  shared worktrees, and overlapping run or profile roots fail before submission.
- A lane blocked after submission does not cancel, signal, halt, or delete a
  successful sibling.
- An uncertain controller invocation is reported as `recovery_required`, with
  exact status and conditional halt commands plus its reconciliation result.
- An uncertain `halt` gets the same read-only status reconciliation, but halt
  is never retried without adjudication.
- A blocked status exposes only validated launch-incomplete fields and a Grok
  dead-lease-candidate flag; arbitrary cleanup error text is not retained.
- A viewer failure does not change `action_ok` or imply launch failure and
  never halts the active target. It does make the complete requested workflow
  `ok: false`, names the lane under `viewer_failed_targets`, and exits 4.
- Do not rerun `launch` blindly after an operator interruption. Reconcile each
  exact session with concurrent `status`.

## Qualification boundary

This coordinator intentionally lives outside Puppet's adapter implementation
fingerprint. It composes already-qualified v0.1 commands without changing
their authority. Current qualification receipts remain campaign/goal-bound;
fanout does not reinterpret or automatically requalify them.

A future fast-path slice may add a controller-attested reusable qualification
certificate. It must preserve the original campaign/goal as provenance,
separately validate current task authorization, recheck live profile and source
identity immediately before launch, and fail closed on policy drift. Do not
obtain speed by removing the existing campaign/goal comparison or treating a
cached boolean as qualification authority.
