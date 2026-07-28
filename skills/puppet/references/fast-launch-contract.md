# Fast launch contract

Use the campaign launcher and fanout coordinator for an operator-selected mix
of one through five qualified regular targets: `agy`, `codex`, `claude`,
`cursor`, and `grok`. Selection is explicit; Puppet does not route targets
automatically.

## Build the warm catalog once

Use `catalog-init` after real qualification, or when the exact controller,
authorization, manifest, adapter, protocol, or private-profile binding changes:

```bash
python3 <skill-root>/scripts/puppet_launch.py catalog-init \
  --out <private-0700-parent/warm-catalog.json> \
  --authorization <authorization.json> \
  --manifest agy=<qualified-agy.json> \
  --manifest codex=<qualified-codex.json> \
  --manifest claude=<qualified-claude.json> \
  --manifest cursor=<qualified-cursor.json> \
  --manifest grok=<qualified-grok.json> \
  --profile codex=<stable-codex-profile> \
  --profile claude=<stable-claude-profile> \
  --profile cursor=<stable-cursor-profile> \
  --profile grok=<stable-grok-profile>
```

The output path must not exist. The command concurrently verifies, but never
creates, each existing qualification. It writes a mode-0600 create-only,
body-free catalog binding the shared campaign/goal/controller authority and
each exact manifest, qualification, adapter, protocol, execution, and stable
profile identity. AGY has no private-profile argument.

The catalog is a fingerprinted index, not new authority and not proof that a
current task may launch. It remains bound to the qualification's exact
campaign and goal. Rebuild it at a new path after any bound input changes;
never edit it or use a cached Boolean as launch authority.

## One-request ordinary path

Use `prepare` when the operator wants the exact campaign artifacts without
starting a harness:

```bash
python3 <skill-root>/scripts/puppet_launch.py prepare \
  --catalog <warm-catalog.json> \
  --target codex,claude,grok \
  --repo <clean-source-git-root> \
  --commit <exact-source-head> \
  --prompt-file <task-input.txt> \
  --launch-id <new-id> \
  --campaign-root <new-private-campaign-root> \
  --worktree-parent <existing-worktree-parent>
```

Use `run` for preparation plus one concurrent launch. Select any comma-separated
mix, repeat `--target`, or pass `--target all`:

```bash
python3 <skill-root>/scripts/puppet_launch.py run \
  --catalog <warm-catalog.json> \
  --target all \
  --repo <clean-source-git-root> \
  --commit <exact-source-head> \
  --prompt-file <task-input.txt> \
  --launch-id <new-id> \
  --campaign-root <new-private-campaign-root> \
  --worktree-parent <existing-worktree-parent> \
  --allow-live-launch \
  [--open-views]
```

`--allow-live-launch` must be present before `run` creates anything. It
acknowledges only the exact existing YOLO launch commands; it grants no account,
external-effect, qualification, or broader mutation authority. The default
modes are `read` and `test`. Add repeatable `--mode mutate` or
`--mode local_commit` only when the task actually authorizes those effects.
For a mutating mix, name exactly one selected owner and at least one explicit
support-lane mode:

```bash
python3 <skill-root>/scripts/puppet_launch.py run \
  ... \
  --target codex,claude,cursor \
  --mode read --mode test --mode mutate --mode local_commit \
  --mutation-owner claude \
  --allow-live-launch
```

Only `claude` receives `mutate` and `local_commit` in that example. Codex and
Cursor receive only the operator-named `read`/`test` intersection. A
multi-target mutating request without `--mutation-owner`, or without an
explicit `read` or `test` support mode, fails before creating anything. A
single-target mutating request derives its sole selected target as owner.

Preparation first validates the clean exact source, prompt artifact, catalog,
fresh IDs, non-overlapping roots, and every selected target. Git worktree
allocation is serialized because lanes share mutable repository metadata.
After allocation, it compiles all selected exact
`puppet.operator-run-plan/v1` packets concurrently, validates the complete plan
set, and publishes the campaign. Fanout then crosses one global read-only
barrier and starts the selected harness controllers concurrently.

Catalogs, contracts, plans, and the completed campaign are create-only. A
body-free `prepare-state.json` advances atomically and always records attempted,
created, and ambiguous exact worktree identities plus
`automatic_cleanup: false`. If preparation fails or is interrupted after a Git
operation may have begun, preserve those exact worktrees and partial artifacts
for adjudication; never guess at cleanup or silently retry with the same IDs.

An ordinary `prepare` or `run` never invokes census, onboarding, login, probe,
pairing, qualification, or an auth-store read. The qualified single-target
controller still performs its narrow body-free login and identity
revalidation immediately before launch. Runtime failures remain lane-local:
never halt an active sibling automatically.

Read body-free progress events from stderr and the target-sorted aggregate
result from stdout. The result binds every exact plan path, file hash,
canonical plan hash, the plan-set hash, the fanout script's exact SHA-256, and
the v0.1 controller identities. A full success exits 0, total failure exits 2,
and partial launch or viewer completion exits 4.

## Lower-level fanout

When exact plan files already exist, submit them directly:

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

Omit every target the operator did not select. Prefer `puppet_launch.py run`
for new ordinary campaigns so worktree and plan preparation use the same
validated path.

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

## Campaign lifecycle

Use the create-only campaign manifest for subsequent concurrent actions:

```bash
python3 <skill-root>/scripts/puppet_launch.py status --campaign <campaign.json>
python3 <skill-root>/scripts/puppet_launch.py attach --campaign <campaign.json>
python3 <skill-root>/scripts/puppet_launch.py view --campaign <campaign.json>
python3 <skill-root>/scripts/puppet_launch.py halt --campaign <campaign.json>
```

`status` is structural and transcript-blind. `attach` prints fresh one-use
read-only attach commands. `view` opens native read-only terminal windows.
`halt` delegates only the exact lane state-root/session pairs preserved by that
campaign; it is not cleanup authority for any other process or tmux session.

The lower-level equivalent accepts the same exact plan set:

```bash
python3 <skill-root>/scripts/puppet_fanout.py status --plan <plan> [...]
python3 <skill-root>/scripts/puppet_fanout.py attach --plan <plan> [...]
python3 <skill-root>/scripts/puppet_fanout.py view --plan <plan> [...]
python3 <skill-root>/scripts/puppet_fanout.py halt --plan <plan> [...]
```

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
