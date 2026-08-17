# Transport schema

Herdr-Puppet uses six primary versioned JSON records:

- `herdr-puppet.destination-catalog.v1`: exact named machine profiles.
- `herdr-puppet.remote-harness-census.v3`: body-free remote executable,
  profile, launch, source, and lifecycle attestation.
- `herdr-puppet.harness-binding.v3`: controller-attested remote harness,
  profile, launch, adapter, source, and instruction-plane identity.
- `herdr-puppet.plan.v2`: source-only intent, explicit parent capability,
  destination authority, and its canonical fingerprint.
- `herdr-puppet.lease.v3`: exact owned tab/pane/terminal/SSH identity, selected
  authority fingerprint, and the next legal submission sequence.
- `herdr-puppet.event.v1`: append-only controller journal event.

The JSON Schemas in this directory are normative for their public fields:

- [plan.schema.json](plan.schema.json)
- [lease.schema.json](lease.schema.json)
- [lease-v1.schema.json](lease-v1.schema.json),
  [lease-v2.schema.json](lease-v2.schema.json), and
  [plan-v1.schema.json](plan-v1.schema.json), frozen from `f73caf2` as
  historical structural contracts,
- [event.schema.json](event.schema.json)
- [destination-catalog.schema.json](destination-catalog.schema.json)
- [remote-harness-census.schema.json](remote-harness-census.schema.json)
- [harness-binding.schema.json](harness-binding.schema.json)
- [remote-harness-census-v2.schema.json](remote-harness-census-v2.schema.json),
  [harness-binding-v2.schema.json](harness-binding-v2.schema.json), and
  [harness-binding-v1.schema.json](harness-binding-v1.schema.json), frozen
  only for historical status, preservation, maintenance, and exact cleanup.

Earlier census v1/v2 and binding v1/v2 records are historical evidence only
and cannot be upgraded into current model/lifecycle evidence; rows use v3
end-to-end for fresh lineage. A canonical lease carrying a valid historical
binding remains inspectable and cleanable through the bounded maintenance
surfaces, but every fresh qualification transition rejects it and requires a
new census plus an active plan-v2 carrying a binding-v3 record.

The active census-v3 JSON Schema expresses static profile state/status pairs
and harness-specific lifecycle shapes. Runtime `validate_remote_census` remains
the semantic authority for derived fingerprints, source/path joins, and other
dynamic cross-field facts JSON Schema cannot honestly express. Census-v2 is a
frozen historical structural artifact, not current qualification authority.

AGY v3 census requires `--model gemini-3.7-flash-high`, an exact `--model`
help token, and exactly one model-list row whose first TSV cell equals that
name. Missing, default, ambiguous, or unavailable selection fails without
emitting the help or model inventory. Other harnesses reject `--model`.

For live Claude rows, harness census binds both source and run identity:
the census must use `--run-id`, the marker root must be absent before
launch via `--claude-hook-root`, and `claude --help` must include
`--settings`. The helper is source-owned; the exact interpreter identity and
derived settings are hash-bound. Transport operations validate sequence,
binding, and receipt consistency. Copying a receipt file over the exact leased
SSH target supplies operational provenance, not cryptographic remote-origin
proof.

`herdr-puppet.lease.v3` is the strict active shape. Historical lease-v1 and
lease-v2 remain for status, preservation, maintenance, and exact cleanup, while
all fresh qualification transitions require v3. Upgrade legacy v1/v2 with
`lease-migrate`; `lease-migrate-v1` remains a v1-only compatibility alias.
The generic command emits `herdr-puppet.lease-migrate.v1`; the compatibility
alias preserves its historical `herdr-puppet.lease-migrate-v1.v1` receipt.
Ordinary operations do not migrate implicitly. Runtime validation enforces
canonical nested authority, deterministic labels, integer fields, unique arrays,
and RFC 3339 evidence before migration writes. Migration never promotes
readiness or invents checkpoint evidence; it may conservatively normalize or
demote legacy readiness. It otherwise derives only `legacy_explicit`, `machine:
null`, the recorded workspace label, and the label-derived fresh-tab ordinal,
then computes v3 authority. An unbound historical lease remains
non-qualifying evidence. Binding-v1/v2 remains valid for historical status
and maintenance after migration.

## Plan lifecycle

`plan` is non-mutating. Its preferred route resolves `--machine` from one
bounded catalog whose profiles contain exactly `name`, `workspace_label`, and
`ssh_target`; the catalog must be one caller-owned, regular, bounded,
non-symlink file and the label must resolve to one live workspace. Schema
`uniqueItems` rejects byte-identical rows; runtime catalog validation is the
property-wise uniqueness authority for profile names and workspace labels. The complete old
workspace-ID/label/SSH triple remains a mutually exclusive compatibility
route, and `--ordinal` is only a deprecated alias for `--tab-ordinal`.
Every plan requests a fresh tab. Creating it changes `state` from
`planned` to an independently stored lease with `state: active`.

Plan-v1 is frozen read-only/status evidence. It cannot initialize new mutation
authority or create a tab; a fresh active plan-v2 is required.

The CLI writes the private plan only to create-only `--output` and emits a
sanitized selection receipt containing machine, workspace label, fresh-tab
request, and ordinal. It retains neither SSH target nor catalog path.

When `qualification-create-tab` is invoked through the public controller, the
matching controller journal is a mutation precondition. Its `plan.json`,
`events.jsonl`, initialization event, and run ID are checked before
`tab create`. A missing, malformed, empty, or cross-run journal fails before
any tab, pane, SSH process, or lease is created. The plan's canonical
`proof_root` is also the exact journal `run_root`. Journal initialization and
later consumers resolve and compare those paths, so copying an otherwise
matching journal to another root cannot split lease-global event or beacon
attempt history.

Initialization validates the full active plan, hashes its canonical JSON, and
records both that digest and its selected-authority fingerprint in the first
event. Create exact-matches the loaded journal plan to the incoming plan before
any Herdr call. Every later active lease/journal preflight independently
projects and compares run/harness, session, destination machine/workspace/fresh
ordinal, deterministic label, SSH target, source, proof root, complete harness
binding, and model identity from the stored plan and lease.

The create mutation focuses the exact new tab in the plan's target workspace.
Herdr 0.7.3 owns focus at the server, so this also makes that workspace and tab
visible in the operator's isolated session. This is required for reliable
operator observation and output waits; it does not authorize focus, adoption,
or cleanup of any pre-existing tab.

## Lease lifecycle

A lease binds:

```text
session
destination_selection.machine
destination_selection.workspace_label
destination_selection.tab.request=fresh
destination_selection.tab.ordinal
selected_authority_sha256
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
harness_readiness_evidence
harness_readiness_operator
harness_readiness_verified_at
harness_readiness_submission_seq
harness_readiness_nonce_sha256
harness_binding
harness_launch
startup_gate_operations
caller_text_files
caller_text_files_removed
remote_task_files
interactive_sends
pending_interactive_send
pending_sequence_operation
```

Every lease mutation uses one exact sibling lock file, reloads the lease from
disk inside that cross-process lock, and joins immutable lease identity before
checking mutable state. A caller supplies the expected sequence; equality with
the reloaded `next_seq` is mandatory. The selected Herdr operation and atomic
sequence advance occur while the lock is held, so concurrent processes cannot
both pass the same sequence. Interactive sends additionally reserve their
delivery durably before Herdr mutation so a controller or host interruption
cannot make replay look safe. Beacon waits durably reserve
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

`qualification-send` sends `text` plus its bounded submit-key vector as one
newline-delimited JSON request to the exact, current-user-owned Unix socket
bound in the lease. Multiline Claude sends use `keys: ["enter", "enter"]`;
single-line Claude and every other harness use `keys: ["enter"]`. Its receipt
is scoped to `herdr_pane_input_only`. It proves Herdr accepted that pane
request; it does not prove the remote harness was ready, submitted the prompt,
started work, loaded an extension, or called a tool. Before mutation, it rejects
any fully assembled strict checkpoint token with a real nonce; callers must
describe the prefix, checkpoint class, and nonce as separate prompt fragments.
This keeps rendered user input from matching the output watcher. The adapter
rechecks the socket file identity after connecting and before dispatch. That
inode check narrows path-replacement races; it does not prove a native Herdr
server incarnation.

`qualification-send` emits `herdr-puppet.qualification-send.v2`; bounded waits emit
`herdr-puppet.qualification-beacon-wait.v2`. Their v1 receipts remain
historical artifacts and are not emitted by the active controller.

A send is first reserved in the canonical lease as
`pending_interactive_send` with exact sequence, phase, prompt hash, wrapper
state, and `pending_or_unknown` delivery state. The controller fsyncs the
replacement lease and parent directory before asking Herdr to mutate. After a
valid acknowledgement it atomically clears the reservation, appends the send
to the two-entry `interactive_sends` ledger, and advances `next_seq`. The
controller journal must match that completed ledger. A crash, timeout, lost or
mismatched acknowledgement, or failed final lease write leaves a durable
reservation and blocks replay.

`qualification-reconcile-send` is not a generic recovery path. It accepts only
the exact pending second steering send on a non-Claude row, after one completed
wrapped initial send and controller-observed STATUS consumption. It requires
the same sequence and prompt hash plus independent evidence that the text was
applied, clears the reservation without another Herdr mutation, and records
transport `reconciled`. An unknown initial send or any unknown Claude send must
be preserved and restarted as a fresh row. If the lease finalizes reconciliation
but its completion event does not, an exact retry repairs only that missing
journal event; it never sends pane input again.

`qualification-run` is the shell-command surface. It accepts non-empty UTF-8
command content only through standard input or a caller-owned `--text-file`,
with the same 256 KiB limit, then calls Herdr 0.7.3
`pane run <pane_id> <command>` exactly once. The public controller never
accepts the command in its own argv. The downstream Herdr CLI necessarily
receives the command argument defined by that interface, so the adapter passes
a fully redacted safe command to every error path, discards stdout, and records
only the command hash. Before the Herdr call, the lease records an exact
`pending_sequence_operation`. A nonzero, timeout, interruption, or failed final
lease write leaves `next_seq` unchanged and that reservation blocks replay;
preserve the row. A finalized zero exit clears the reservation, advances the
sequence, and records
`submission_mode: atomic_shell_command` and
`execution_acceptance: unverified`; it does not establish shell, harness, MCP,
or task readiness.

After the first STATUS checkpoint, use `qualification-run` for the exact
in-row census helper in create-only `--output` mode with a unique completion
checkpoint. The helper fsyncs the completed JSON before emitting STATUS; wait
for that beacon before copying the file. A successful `pane run` acknowledgement
or an empty output path is not completion. The controller compares that
sanitized census with the
plan/lease binding through `harness-census-verify`. Its journal fingerprint
covers stable census facts and deliberately excludes only `recorded_at`, so a
newer observation of identical facts is idempotent. Recorded time may advance;
executable/version/help fingerprints, enrolled dedicated-user profile,
model selection, launch vector, host, and source worktree may not. AGY binds
the exact argv `[<absolute-agy>, --model, gemini-3.7-flash-high,
--dangerously-skip-permissions, --sandbox=false, --new-project, --log-file,
/dev/null]`; other harnesses retain their current-default observation.
The generic shell-command surface rejects every harness launch after shell
readiness. Only `qualification-harness-launch` may submit the bound regular
launch vector, once, at the exact next sequence. It deliberately records
`remote_harness_pid: unavailable`; Herdr's foreground SSH PID is a different
identity. Harness launch and startup-gate input use the same durable
pre-mutation reservation. An unfinalized reservation is unknown delivery, not
permission to launch or press the gate again.

Non-cursor harnesses must remain on an enrolled dedicated-user profile with
`status_exit: 0` for this comparison. Cursor may report the provisional
`interactive_pending` + `null` status pair before the first in-row launch as
an explicit temporary state. Its census process exits zero when that body-free
provisional record is written; this is census success, not an enrollment or
readiness claim.
An unsuccessful non-Cursor enrollment probe emits neither an active v3 census
record nor a completion checkpoint: `unavailable` is not an active v3 profile
state.

The controller never writes or copies prompt or command content, so callers
own the lifecycle of any input file. If an orchestration bridge cannot
reliably half-close stdin, create one private task-owned input file, use
`--text-file`, require the exact sequence acknowledgement, and then remove
only that file. Acceptance of either operation is not execution proof.

New leases begin with `shell_readiness: unverified` and
`harness_readiness: unverified`. A strict shell `STATUS` checkpoint advances
only `shell_readiness` to `status_verified`; later `qualification-run`
submissions fail closed until that transition, except for one strict sequence-2
`STATUS` retry after the journal records a failed wait for the sole sequence-1
run and classifies that first command as the same strict probe.
That exception accepts only the canonical standalone `printf` probe with a new
safe nonce, records `shell_status_retry: true`, and cannot start a harness or
recur at sequence 3.
AGY rows then stay `harness_acceptance=unverified` and
`harness_readiness=checkpoint_pending` after the initial wrapped send with
`--checkpoint-nonce`; exact `HERDR_PUPPET_STATUS <nonce>` at that sequence
advances to `checkpoint_verified` and allows steering. `qualification-harness-ready`
is not used for AGY.
Interactive pane input is separate:
`qualification-harness-ready` requires the exact leased repo and worktree, an
explicit operator identity, bounded
`operator_observed_ready_input` evidence, confirmation, and a fresh structural
join before advancing `harness_readiness` to `operator_verified`.
`qualification-send` and send reconciliation require that state even at sequence 1
for Codex/Claude/Cursor/Grok. AGY has no operator-ready gate and keeps the same
`qualification-run` noninteractive restriction.

Before readiness, `qualification-startup-gate` accepts only a
harness-specific allowlisted gate/action, exact worktree and unrestricted
posture confirmation, one safe operator ID, and the exact next sequence.
Allowlisted key vectors are bounded to `a`, `enter`, `up`, and `down`.
`not_present` advances the sequence without pane input. Cursor readiness
requires a recorded Workspace Trust result. Each gate is single-use and every
gate operation becomes invalid after readiness.

Cursor permits only Workspace Trust with `accept` or `not_present`. Codex and
Claude permit Workspace Trust, security acknowledgement, and permission-bypass
confirmation with their exact action allowlists. AGY and Grok require an empty
startup-gate ledger.

The first ordinary prompt must carry a
`herdr-puppet.instruction-wrapper.v1` manifest. The controller recomputes the
rendered body hash and verifies the binding, run ID, universal/harness/model/
lifecycle layers, and `initial_message_wrapper` plane before dispatch.
Wrapper manifests and events retain hashes and sizes, never the task body.
AGY uses the explicit Gemini 3.7 model layer; other rows retain the
default-unresolved layer.

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

For Claude lifecycle rows, the registered remote task paths must be the eight
expected marker names under the exact run-bound hook root:

- `session_start-0001.json`
- `user_prompt_submit-0001.json`
- `user_prompt_submit-0002.json`
- `stop-0001.json`
- `stop-0002.json`
- `stop_failure-0001.json`
- `stop_failure-0002.json`
- `overflow.json`

Claude settings execute isolated Python `-I -c` with a settings-embedded
bootstrap. That bootstrap checks the resolved running interpreter path, hashes
the bound interpreter, then opens the bound helper without following symlinks
and checks its owner, size, and SHA-256 before compiling it. The helper performs
the same source-bound check on the implementation before compiling it. The
overflow sentinel makes extra or conflicting hook events receipt-invalid.
`qualification-claude-receipt-command` derives this same pre-execution-verified
route for observation; directly invoking the mutable worktree helper is not
qualifying evidence. The verified helper reads the markers and emits one
sanitized receipt.
That receipt is copied to a caller-owned bounded regular file on the controller;
`qualification-claude-lifecycle-observe` reads only that local file and never
reads the remote marker root or pane transcript. UserPromptSubmit hook JSON is
read only in bounded memory so its `prompt` field can be hashed; the raw input
and prompt are never retained, and other hook events leave stdin unread. The
receipt exposes only the prompt fingerprints needed to bind native submission
to the controller's exact sequenced sends. When cleanup is authorized, move
the exact marker root recoverably, verify every registered path is absent, and
record the removal evidence through maintenance.

`lease-preserve` atomically changes an active lease to `preserved`, records one
bounded reason, and performs no Herdr mutation. A preserved tab remains visible
but cannot receive controller input.

A strict `DONE` or `ACTION_REQUIRED` beacon performs that same local
preservation transition inside the beacon's final lease lock. `STATUS` and
`not_matched` leave the lease active. The standard long-running qualification
watcher uses a 480000 ms native timeout and a 510 s controller cap. One
additional bounded wait is allowed after the first `not_matched`, using the
same nonce and submission sequence. Each attempt is consumed by its durable
pre-wait
reservation, including when the controller exits before finalization. A
matched nonce, cross-sequence reuse, or third reservation is rejected.
After the second `not_matched`, the controller must explicitly
`lease-preserve --reason checkpoint_failed` before leaving the run; no timeout
automatically preserves or authorizes replay.

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
