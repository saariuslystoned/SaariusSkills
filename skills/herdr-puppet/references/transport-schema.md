# Transport schema

Herdr-Puppet uses four versioned JSON records:

- `herdr-puppet.harness-binding.v1`: controller-attested remote harness,
  profile, launch, adapter, source, and instruction-plane identity.
- `herdr-puppet.plan.v1`: source-only intent plus the explicit parent
  capability.
- `herdr-puppet.lease.v1`: exact owned tab/pane/terminal/SSH identity and the
  next legal submission sequence.
- `herdr-puppet.event.v1`: append-only controller journal event.

The JSON Schemas in this directory are normative for their public fields:

- [plan.schema.json](plan.schema.json)
- [lease.schema.json](lease.schema.json)
- [event.schema.json](event.schema.json)
- [harness-binding.schema.json](harness-binding.schema.json)

`herdr-puppet.lease.v1` has one strict canonical shape. Current controller
operations reject historical lease-v1 files that omit the readiness/file
fields or use the former `harness_readiness: status_verified` value. Upgrade
such a file explicitly with `lease-migrate-v1`; ordinary status, probe,
preservation, cleanup, and journal-refresh paths never perform an implicit
compatibility migration. Runtime validation enforces the canonical nested
authority objects, integer fields, safe label, unique arrays, and RFC 3339
evidence times before migration may write. Migration never invents a harness
binding; an unbound historical lease remains non-qualifying evidence.

## Plan lifecycle

`plan` is non-mutating. A plan is usable only when its doctor and workspace
observations match live Herdr state. Creating a tab changes `state` from
`planned` to an independently stored lease with `state: active`.

When `qualification-create-tab` is invoked through the public controller, the
matching controller journal is a mutation precondition. Its `plan.json`,
`events.jsonl`, initialization event, and run ID are checked before
`tab create`. A missing, malformed, empty, or cross-run journal fails before
any tab, pane, SSH process, or lease is created. The plan's canonical
`proof_root` is also the exact journal `run_root`. Journal initialization and
later consumers resolve and compare those paths, so copying an otherwise
matching journal to another root cannot split lease-global event or beacon
attempt history.

The create mutation focuses the exact new tab in the plan's target workspace.
Herdr 0.7.3 owns focus at the server, so this also makes that workspace and tab
visible in the operator's isolated session. This is required for reliable
operator observation and output waits; it does not authorize focus, adoption,
or cleanup of any pre-existing tab.

## Lease lifecycle

A lease binds:

```text
session
workspace_id
tab_id
pane_id
terminal_id
ssh.pid
ssh.argv
ssh.target
next_seq
shell_readiness
harness_readiness
harness_binding
harness_launch
startup_gate_operations
caller_text_files
caller_text_files_removed
remote_task_files
```

Every lease mutation uses one exact sibling lock file, reloads the lease from
disk inside that cross-process lock, and joins immutable lease identity before
checking mutable state. A caller supplies the expected sequence; equality with
the reloaded `next_seq` is mandatory. The selected Herdr operation and atomic
sequence advance occur while the lock is held, so two processes submitting the
same sequence produce at most one Herdr mutation. Beacon waits durably reserve
one of the nonce's two allowed attempts in the journal while holding that same
lease lock, then snapshot and release the lock during the long blocking wait.
They reacquire it and reject any full-lease revision change or missing/ambiguous
reservation before finalizing. A run, readiness transition, preservation, or
cleanup therefore cannot be overwritten by stale wait state, and a third
concurrent waiter cannot reach Herdr.

The lower-level token probe follows the same no-long-lock wait shape without
consuming a beacon attempt. Before reading the pane it takes the exact sibling
lease lock, reloads the canonical lease from disk, and requires the caller
payload to equal the complete current lease revision. It then snapshots,
releases the lock for `wait output`, and reacquires it to reject any complete
revision change before journaling or returning a result. A stale active or
preserved caller payload therefore cannot authorize a pane read.

`qualification-send` sends `text` plus `keys: ["enter"]` as one
newline-delimited JSON request to the exact, current-user-owned Unix socket
bound in the lease. Its receipt is scoped to `herdr_pane_input_only`. It proves
Herdr accepted that pane request; it does not prove the remote harness was
ready, submitted the prompt, started work, loaded an extension, or called a
tool. The adapter rechecks the socket file identity after connecting and
before dispatch. That inode check narrows path-replacement races; it does not
prove a native Herdr server incarnation. A lost, malformed, or mismatched
acknowledgement is an unknown delivery outcome. Never retry that sequence:
stop and use `qualification-reconcile-send` only after independent evidence
establishes that the original input was applied.

`qualification-run` is the shell-command surface. It accepts non-empty UTF-8
command content only through standard input or a caller-owned `--text-file`,
with the same 256 KiB limit, then calls Herdr 0.7.3
`pane run <pane_id> <command>` exactly once. The public controller never
accepts the command in its own argv. The downstream Herdr CLI necessarily
receives the command argument defined by that interface, so the adapter passes
a fully redacted safe command to every error path, discards stdout, and records
only the command hash. A nonzero or timed-out Herdr call leaves `next_seq`
unchanged. A zero exit advances the sequence but records
`submission_mode: atomic_shell_command` and
`execution_acceptance: unverified`; it does not establish shell, harness, MCP,
or task readiness.

After the first STATUS checkpoint, use `qualification-run` for the exact
in-row census helper in create-only `--output` mode with a unique completion
checkpoint. The helper fsyncs the completed JSON before emitting STATUS; wait
for that beacon before copying the file. A successful `pane run` acknowledgement
or an empty output path is not completion. The controller compares that
sanitized census with the
plan/lease binding through `harness-census-verify`. Recorded time may advance;
executable/version/help fingerprints, enrolled dedicated-user profile,
default-model observation, launch vector, host, and source worktree may not.
The generic shell-command surface rejects every harness launch after shell
readiness. Only `qualification-harness-launch` may submit the bound regular
launch vector, once, at the exact next sequence. It deliberately records
`remote_harness_pid: unavailable`; Herdr's foreground SSH PID is a different
identity.

The controller never writes or copies prompt or command content, so callers
own the lifecycle of any input file. If an orchestration bridge cannot
reliably half-close stdin, create one private task-owned input file, use
`--text-file`, require the exact sequence acknowledgement, and then remove
only that file. Acceptance of either operation is not execution proof.

New leases begin with both `shell_readiness: unverified` and
`harness_readiness: unverified`. A strict shell `STATUS` checkpoint advances
only `shell_readiness` to `status_verified`; later `qualification-run`
submissions fail closed until that transition, except for one strict
sequence-2 STATUS retry after the journal records a failed wait for the sole
sequence-1 run and classifies that first command as the same strict probe.
That exception accepts only the canonical standalone `printf` probe with a
new safe nonce, records `shell_status_retry: true`, and cannot start a harness
or recur at sequence 3. Interactive pane input is separate:
`qualification-harness-ready` requires the exact leased repo and worktree, an
explicit operator identity, bounded
`operator_observed_ready_input` evidence, confirmation, and a fresh structural
join before advancing `harness_readiness` to `operator_verified`.
`qualification-send` and send reconciliation require that state even at
sequence 1. Noninteractive AGY remains on `qualification-run`.

Before readiness, `qualification-startup-gate` accepts only a
harness-specific allowlisted gate/action, exact worktree and unrestricted
posture confirmation, one safe operator ID, and the exact next sequence.
Allowlisted key vectors are bounded to `a`, `enter`, `up`, and `down`.
`not_present` advances the sequence without pane input. Cursor readiness
requires a recorded Workspace Trust result. Each gate is single-use and every
gate operation becomes invalid after readiness.

The first ordinary prompt may carry a
`herdr-puppet.instruction-wrapper.v1` manifest. The controller recomputes the
rendered body hash and verifies the binding, run ID, universal/harness/model/
lifecycle layers, and `initial_message_wrapper` plane before dispatch.
Wrapper manifests and events retain hashes and sizes, never the task body.

The explicit legacy adapter preserves that split. A historical
`harness_readiness: status_verified` value migrates to
`shell_readiness: status_verified` plus `harness_readiness: unverified`; it
never becomes operator-verified harness readiness. Omitted readiness fields
default to `unverified`, and omitted caller/remote file arrays default to empty
arrays. The migration validates the historical baseline, locks and reloads the
exact lease file, writes the canonical shape atomically, performs no Herdr
mutation, and reads no transcript. Canonical `operator_verified` readiness is
valid only with all three bounded evidence fields: the fixed
`operator_observed_ready_input` class, a safe operator identifier, and an
RFC 3339 timestamp. Any other readiness state must omit those fields.

The private lease may retain normalized controller-local paths for caller-owned
command or prompt files, so maintenance can check those files on the
controller filesystem. Receipts label them `controller_local` and expose only
lifecycle booleans and the `caller_owned` classification, not paths or content.

A task file referenced by a launcher running over the leased SSH target is
different. Register its normalized absolute POSIX path through
`remote-task-file-register` before launch. That operation binds the path to the
exact SSH target and leased source without calling local filesystem APIs.
Exact remote paths appear only in the private lease and maintenance output;
registration receipts and ordinary journal events expose neither the path nor
a path hash. Final maintenance accepts one exact registered path, explicit
confirmation, and either `operator_verified_remote_absence` or
`source_bound_terminal_artifact` before marking `removal_verified`.
`cleanup-preserved-tab` rejects an unverified registered remote file.

`lease-preserve` atomically changes an active lease to `preserved`, records one
bounded reason, and performs no Herdr mutation. A preserved tab remains visible
but cannot receive controller input.

A strict `DONE` or `ACTION_REQUIRED` beacon performs that same local
preservation transition inside the beacon's final lease lock. `STATUS` and
`not_matched` leave the lease active. The standard 420-second AGY recipe uses a
480000 ms native timeout and a 510 s controller cap. One additional bounded
wait is allowed after the first `not_matched`, using the same nonce and
submission sequence. Each attempt is consumed by its durable pre-wait
reservation, including when the controller exits before finalization. A
matched nonce, cross-sequence reuse, or third reservation is rejected.

Preservation is not tab cleanup. A later tab close requires separately
authorized `cleanup-preserved-tab`, an initialized journal, a preserved lease,
and exact repeated tab-ID confirmation. The command verifies the exact tab and
pane disappeared and the leased foreground SSH PID is absent. PID reuse blocks
verification rather than being accepted as success. It sends no direct
process termination signal and does not infer cleanup authority from a
milestone, label, ordinal, age, focus, or failed beacon.

Do not infer a missing ID or repair a mismatch by searching labels. Recovery
remains disabled until remote-process adoption and crash behavior are
qualified.

Herdr 0.7.3 does not expose native server-incarnation identity. The records
therefore state `incarnation_proven: false`; reconnect or handoff invalidates
the live lease until full structural requalification.

## Journal lifecycle

The controller journal is append-only JSONL. Store:

- timestamps, command names, result classifications, and sequence numbers;
- exact structural IDs needed to diagnose authority joins;
- prompt or nonce hashes rather than prompt/response content;
- strict checkpoint classes rather than contract-beacon text;
- concise operator observations and improvement candidates.

`maintenance-checkpoint` joins live structure through the exact lease,
classifies the run as `active`, `preserved`, `stale`, or `ambiguous`, and
records per-resource state plus the next maintenance route. It never reads pane
text, closes a tab, or reaps a process.

`cleanup-preserved-tab` journals request and verified-close events, then adds
`cleanup_state: closed` and the verification timestamp to the lease. Repeated
cleanup is idempotent only when exact tab/pane and foreground SSH PID absence
remain verified.

Do not store pane text, scrollback, environment values, credentials, account
identifiers, or auth logs. Curate and redact a separate public proof before
committing any dogfood result.
