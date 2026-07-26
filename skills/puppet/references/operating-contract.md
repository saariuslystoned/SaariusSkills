# Puppet operating contract

## Authority and ownership

The controller owns the contract, gates, lifecycle ledger, independent review,
verdicts, acceptance, and exact halt. The target owns only the task modes and
candidate worktree named by the contract. One target cannot accept itself.

Run at most one live lane per harness target and one mutation owner per source
slice. Different harness targets may run independently after each owns a
separate lease. Bind every session to one controller, target, repository,
branch, proof root, private tmux socket, exact process birth identity, and
immutable supervising Puppet executable. Refuse overlapping supervisor and
candidate roots.

Real-harness probes and normal sessions serialize per target through the fixed
per-account authority root at
`~/.local/state/saarius-puppet-controller-v1`. Each target has its own lock,
atomic current projection, and append-only history. A normal session holds its
target lease from launch admission through exact halt; changing a checkout,
state root, or proof root cannot bypass it. Every per-target mutation takes the
target lock before the short-lived legacy global lock. The legacy projection
anchors one active target at a time so older controllers still observe an
active claim and fail closed; per-target histories remain authoritative. The
controller attestation ledger is likewise fixed and checkout-independent.
These mechanisms assume cooperative same-UID execution and do not turn YOLO
targets into hostile-code containment.

Each durable target lease binds activity kind, run, campaign, goal fingerprint, proof
root, state root, session, target, controller, process, and lifecycle state.
Normal launch, follow-up delivery, cleanup, and halt serialize through one
per-session operation lock. Graceful halt intent/submission entries bind the
target PID, v2 identity digest, action index, and action; an interrupted intent
is ambiguous and must never be resent. The explicit parallel-target override
accounts only for the named pre-existing process set; it does not bypass the
same-target controller lease.

Halt action is target-aware: non-AGY uses exact positive-PID `SIGINT`; AGY uses
private-pane EOF. Never send tmux `C-c` or process-group signals.

A real-harness probe may observe a bounded same-executable child population
created by its registered pane process. Each child needs an exact live v2 birth
identity and executable identity plus an acyclic kernel-revalidated PPID chain to
the registered root from one bounded discovery pass plus birth-bound per-node
samples. On Darwin, birth identity is `proc_pidinfo` `(sec, usec)`; on Linux,
`(kernel.boot_id,
/proc/<pid>/stat_starttime_ticks)`. Siblings, children of a protected process,
missing parents in an extra's chain, PID reuse, and identity drift fail closed.
A protected or registered root needs only its own exact node; an unreadable
foreign parent grants no authority and is not traversed. A same-target row proven
gone before identity sampling may be omitted, but every protected and registered
identity must still be present and every surviving extra must still prove its
complete chain. Keep full ancestry history for observed transient descendants as
receipt evidence. Puppet never signals those descendants or a process group;
non-AGY halt authority is the exact registered positive PID and AGY EOF authority
is the exact registered private pane. If a provisional target cannot be fully
controller-bound before input, keep it fenced and non-qualifying without any halt
action. After halt, the same-target population must return to the exact protected
baseline before a receipt can be accepted.

## Lifecycle

Startup is `compile and hash-bind regular wrapper -> reserve exact lease -> bare
YOLO CLI -> bounded structural settle -> exact identity recheck -> deliver
wrapper`. The rendered body exists only in memory and the target transport; the
registry and journal retain hashes and a sanitized manifest. Every later
operation revalidates that artifact. The settle never establishes semantic
readiness; a validated checkpoint is the first consumption proof.

The regular wrapper is not a harness-native instruction-plane result. Native
commands are versioned lifecycle state machines, not universally initial-only
selectors: later command work must prove activation, continuation, steering,
resume, and termination behavior separately.

### Repository entry and instruction planes

Support both entry shapes without assuming an operator-specific cockpit. When
the controller starts outside the target repository, require its explicit path.
When it starts inside the target, infer the current Git root unless the user
supplies another target. A mutating target always receives an isolated
worktree, branch, owner, and proof trail. Keep controller code, state, native
instruction artifacts, and proof outside the candidate worktree.

Compose the regular effective contract from the shipped universal, harness,
current-default-model, and lifecycle templates plus the runtime contract, task,
and optional user addendum. Treat every different composition as a different
fingerprint. Normal customization uses the addendum; a changed baseline or
template root must requalify.

Test harness-global/profile, workspace/repository, and additive per-run planes
as separate exact-version candidates. A fallback initial-message wrapper cannot
stand in for one. Activate a factual candidate only inside lane-owned roots and
only for a Puppet-owned qualification session. Never edit the operator's live
global harness files during launch.

For a native activation, persist and verify create-only intent before the
artifact, combine its closed environment and argv delta with the exact adapter
launch mapping, and build the value-private admitted launch plan before lease
admission. The native delta must compose with the exact authenticated private
subscription profile; it may not substitute an activation-only config root.
Revalidate the profile auth status, activation receipt, artifact, roots,
executable, and final launch identity immediately before starting the pane.
After exact halt, roll back only the receipt-bound artifact and
transaction-created directories; preserve ambiguity instead of deleting by
path.

Claude matched-control activation adds a source-bound pre-delivery gate:
compile the exact ready request, plan, attest through fixed controller
authority, and spend a one-use signal reservation before materialization or
launch. The ready checkpoint is valid only with the exact transient sidecar;
the controller consumes and unlinks it before follow-up, then rechecks absence
after exact target halt before rollback or receipt. Interrupted recovery never
relaunches or reuses the reservation. It reconciles an exact stranded signal
only after target death and rejects any missing, drifted, non-source, or
post-observation recreated leaf.

Cursor qualification activates only from a body-free request bound to the
fresh doctor manifest. Pass B derives an exact root `AGENTS.md` descriptor
after compilation. Require that path to be absent, then create the deterministic
Puppet qualification wrapper mode 0600 with no-follow `O_EXCL`. Bind its
wrapper bytes and the enclosed effective-contract SHA-256 separately in the
descriptor assertion, plan, and materialization receipt. Never overwrite,
append to, or follow a repository-owned `AGENTS.md`. Compose exactly one
absolute `--workspace` selector followed by the one fixed non-secret opaque
activation trigger, with the enrolled private profile. The trigger is a single
literal final argv element; its hash and the full launch vector are bound in
proof. No compiled contract, task body, or operator-supplied prompt may appear
in argv. Revalidate the profile, artifact, and launch vector immediately before
launch. Ordinary control and regular launches remain positional-prompt-free and
use post-launch transport. While active,
structurally observe one human read-only native tmux client attach and detach
without reading pane content. After exact registered-PID halt, verify the
receipted vnode and unlink only that file. Failed or timed-out runs may do the
same only after exact halt and protected-population baseline restoration.
Identity drift, halt ambiguity, or rollback failure fences the activation for
controller adjudication. Prior `.cursor/rules/*.mdc` and root-`AGENTS.md`
post-launch-trigger activation receipts are legacy, non-promotable evidence.

An activated Cursor receipt is activation-only and cannot promote. A terminal
qualification must reverify it beside a distinct ordinary Pass B control using
the same controller, campaign, goal, executable, adapter, protocol, compiler
policy, unresolved default-model selection, and exact private profile. It also
requires distinct workspaces, unchanged fixture fingerprints for both runs,
the structural native-view receipt, exact halts, activated rollback, and no
activation in the ordinary control. Source-only records and standalone ordinary
receipts are likewise non-promotable.

Grok qualification similarly begins with a body-free request bound to the
fresh doctor manifest, exact positive worktree/cockpit repository join,
controller campaign and goal, executable, and enrolled private profile. Pass B
derives the exact hash-named `.grok/rules` descriptor after compilation and
persists it before launch. The positive run receives only the fixed opaque
native trigger; its rule is create-only and removed by hash-guarded rollback
after exact halt. The ordinary run is launched later from a distinct fixture,
is immutably linked to the terminal positive receipt, receives the regular
compiled task directly, and proves zero namespaced rules before and after.

Every Grok member uses a fresh private-profile-contained leader socket,
canonical UUIDv4, and explicit absolute cwd. Qualification binds the same exact
logged-in profile and reported `grok-4.5` default while forbidding model/effort
selectors. The terminal pair requires distinct process/tmux/session/socket/
UUID/workspace/checkpoint/viewer identities, normal sequenced steering,
retained descendant ancestry, exact standalone tree halts, and equality of the
same protected target population before and after both members. Observe one
read-only native tmux client per member structurally; never capture its pane.
Only the independently rebuilt controller-attested terminal pair may close
Grok's mapping or authorize normal launch. Filesystem-only absence, either
member alone, a synthetic no-bleed flag, or the deferred shared-leader source
plan remains non-promotable.

The current product baseline is `regular` only. `/goal`, `/loop`,
`/teamwork-preview`, alternate models, and automatic routing remain separate,
versioned lifecycle qualifications and must not be silently injected.

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
