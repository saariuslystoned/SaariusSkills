# Puppet adapter contract

## Two-pass qualification

Pass A is a zero-agent allowlisted census. Record the resolved executable,
file identity and SHA-256, platform, bounded version/help hashes, declared
model/effort controls, prompt transport, resume surface, unrestricted mapping,
sandbox-off mapping, and prior-evidence references. Do not inspect auth,
configuration, environment files, sessions, transcripts, or credentials.

Pass A creates a doctor-only manifest. Static help, historical evidence, and
target self-report cannot enable launch, send, status, wait, checkpoint, resume,
or halt.

Pass B runs the shared contract against the exact real CLI. Bind the result to
the executable, adapter implementation, platform, and probe-protocol
fingerprints. An enabled manifest must reference a bounded accepted
real-harness receipt whose hash, exact verified-capability list, exact YOLO
mapping, instruction-policy fingerprint, sanitized effective-instruction
manifest, controller verdict, acceptance, halt receipt, and proof references
all verify. The persisted manifest is content-addressed and contains no task or
rendered instruction body. The probe must also resolve the separately supplied campaign ID and
repository/commit/path/SHA-256 goal tuple from the named local Git repository.
The accepted receipt requires exact inclusion in the fixed per-account
controller attestation ledger and is rechecked against the current executable,
adapter, platform, protocol, tmux executable/server, terminal state, and bound
artifacts.
Use `adapter_lab.py qualify` to bind that receipt; never toggle capability
states by hand. Any relevant drift disables the capability.

Pass B and normal live sessions share one checkout-independent lock and durable
lease per harness target, so changing a proof or state root cannot admit a
second same-target lane. Different targets can proceed independently. A legacy
global projection remains active while any per-target lane is active so an
older controller cannot overlap the new lease regime. If a probe is
interrupted, run `adapter_lab.py recover` with the same exact run and identity
inputs. Recovery never launches a target: it verifies an already complete
receipt or reconciles and gracefully halts only the exact persisted target.

During a live probe, the target-population guard admits only the exact
authorized pre-existing population, the exact registered pane process, and
bounded same-executable processes whose freshly sampled kernel-revalidated
parent edges and v2 birth identity reach that registered process. On Darwin,
bounded current-UID discovery uses `proc_listpids` plus `PROC_PIDTBSDINFO`;
other supported platforms may use `ps` only to find target `pid`/`comm` rows.
Ambient candidate names are prefiltered against fixed target names and the
declared final runtime basename before the controller binds the exact
process-owned mapped-vnode identity. Launcher and transient executable
identities are not ambient target-population authority. They are accepted only
during the bounded same-PID exec transition after the private pane, PID, and
kernel birth are already pinned; the final registered process must settle on
the declared runtime identity. Per-node parent edges and birth identity come
from Darwin `proc_pidinfo` `(sec,usec)` or Linux
`(kernel.boot_id,/proc/<pid>/stat_starttime_ticks)`. Discovery never reads argv
or terminal content. Missing ancestry, protected-process ancestry, PID reuse,
executable drift, cycles, or unrelated same-name processes fail closed. Keep
full historical ancestry evidence for transient descendants until verdict.
Descendants are evidence, never signaling authority:
non-AGY halt signals only the registered positive PID, AGY EOF targets only the
registered private pane, and accepted proof requires the post-halt target
population to equal the exact protected baseline.

The operational sequence is:

```text
adapter_lab.py probe --profile source-free-pass-b-v2 \
  --target TARGET --session-profile SESSION_PROFILE \
  --proof-root ROOT --manifest MANIFEST --mapping MAPPING \
  --authorization AUTH --controller CONTROLLER --campaign-id CAMPAIGN \
  --goal-repo GIT_ROOT --goal-repository REPOSITORY --goal-commit COMMIT \
  --goal-path PATH --goal-sha256 SHA256 \
  --subscription-profile-root PRIVATE_PROFILE \
  [--plane-descriptor DESCRIPTOR] [--codex-entry-plan PLAN] \
  [--codex-ordinary-worktree-descriptor DESCRIPTOR] [--run-id RUN]
adapter_lab.py verify --run ROOT/probes/RUN/receipt.json
adapter_lab.py qualify --manifest MANIFEST --mapping MAPPING \
  --receipt ROOT/probes/RUN/receipt.json --out QUALIFIED_MANIFEST
```

Claude's incomplete census tuple requires a controller-owned pair. After the
activation probe, run the ordinary control with
`--paired-activation-receipt ROOT/probes/ACTIVATION/receipt.json` and no plane
descriptor. While each exact probe is live and has one read-only viewer, record
only its structural native-view identity:

```text
adapter_lab.py observe-claude-view --proof-root ROOT --run-id RUN
```

Then create the fixed paired receipt:

```text
adapter_lab.py pair-claude --manifest MANIFEST --mapping MAPPING \
  --activation-receipt ROOT/probes/ACTIVATION/receipt.json \
  --control-receipt ROOT/probes/CONTROL/receipt.json
adapter_lab.py qualify --manifest MANIFEST --mapping MAPPING \
  --receipt ROOT/probes/CONTROL/claude-paired-receipt.json \
  --out QUALIFIED_MANIFEST
```

The pair command re-verifies exact receipt, controller-ledger, profile,
process, tmux, workspace, default-model-unavailable, structural view, and empty
pre/post population evidence. It captures no bodies. Activation-only and
unpaired-control receipts are intentionally non-promotable.

Codex never accepts a positive worktree receipt by itself. Its bounded paired
qualification substrate requires:

- a positive direct-worktree run and a later ordinary-control run, both
  `regular`, using the same exact Puppet-owned subscription profile and the
  the same current-default/no-selector launch vector, while resolved model and
  effort remain explicitly unavailable;
- distinct run, accepted checkpoint, workspace, target process, tmux
  socket/session/server, and controller lease identities, with empty
  same-target populations before both launches and after both exact halts;
- a real read-only native TUI client observed structurally while the positive
  target is alive, with distinct target process, tmux server, and viewer
  client/process identity and no pane body, prompt, transcript, scrollback, or
  auth/config content retained; and
- the hash-verified operator plan supplied to the positive probe before launch,
  recompiled against its exact full field set and persisted in the positive
  receipt/controller attestation, whose exact `direct_git_root` or
  `cockpit_explicit` entry mode, repository, branch, and head match the positive
  worktree receipt.

Run the ordinary control with both
`--paired-codex-positive-receipt POSITIVE_RECEIPT` and
`--codex-ordinary-worktree-descriptor CONTROL_DESCRIPTOR`. The descriptor must
prove a distinct clean linked worktree from the same Git common repository and
exact head as the positive member, with no `AGENTS.md`; a synthetic or unrelated
Git repository is not a valid control. Recovery must receive both exact inputs.
Positive recovery must also receive the same persisted `--codex-entry-plan`;
pair-time entry-plan input is rejected. The ordinary receipt core and
controller attestation bind the exact positive source and control descriptor,
so a completed control cannot be relinked by editing `state.json`. After both
exact halts, `pair-codex` creates one new controller-attested
`paired_evidence_only` receipt and refuses any existing destination.
`verify-codex-pair` reopens both terminal receipts and all bound artifacts
against the current doctor-only manifest and profile. Neither pair command
authorizes launch. A later `adapter_lab.py qualify` must independently perform
the same rebuild against the exact current doctor manifest; only the resulting
qualified manifest may enter public doctor/launch, where the same private
profile/status binding is checked again. The pair retains
`public_launch_authorized=false` and `promotion_authorized=false` because it is
evidence, not runtime authority.

Grok uses a promotable paired-runtime contract, not its older filesystem-only
matched-control precheck. Build one body-free positive request with
`grok-request`; it binds the fresh doctor manifest, candidate worktree,
cockpit/common-repository identity, controller/campaign/goal, exact executable,
and enrolled private profile without carrying the eventual rule path or body.
Positive Pass B compiles the randomized conformance task, derives and persists
the exact `.grok/rules/puppet-<rendered-sha256>.md` descriptor before target
start, materializes create-only, and sends only the fixed opaque native trigger.
The later ordinary Pass B supplies
`--paired-grok-positive-receipt POSITIVE_RECEIPT`, carries no positive
descriptor, uses a distinct workspace, and proves zero namespaced Puppet rules
before and after its normal direct task delivery.

Each member's canonical runtime vector is:

```text
grok-0.2.111-macos-aarch64 --always-approve --sandbox off \
  --no-leader --trust \
  --cwd ABSOLUTE_WORKSPACE --leader-socket NEW_PRIVATE_SOCKET \
  --session-id CANONICAL_UUIDV4
```

The vector is rebuilt from the exact logged-in private-profile binding; its
status must report default `grok-4.5`. Model and effort selectors are forbidden.
The two members share controller/campaign/goal/executable/adapter/protocol/
compiler/profile/mapping authority but must have distinct run, session,
workspace, process, tmux, socket, UUID, checkpoint, and viewer identities.
Both runs require the normal sequenced follow-up checkpoint and exact
registered-root halt, retained descendant ancestry, and identical protected
pre/post populations. The positive rule must be hash-guardedly rolled back.
Its current materialization receipt binds the workspace identity before and
after create plus every `.grok` parent's inode and created-vs-preexisting
status. Rollback removes only the matching artifact and recorded Puppet-created
empty parents, deepest-first, then proves the workspace identity returned to
its pre-create value; preexisting parents are never removed. Parent drift,
symlink substitution, non-empty created parents, and legacy receipts without
parent ownership are non-promotable.

Record each live read-only view with
`observe-grok-view --run-root RUN_ROOT`; it observes one tmux client attach and
detach structurally and performs no pane capture. Build the terminal receipt
with `pair-grok`, then use `verify-grok-pair` to reopen both receipts, views,
profile/launch/evidence/halt artifacts, positive materialization/rollback, and
ordinary absence proof and to rebuild the matched-control digest and
controller-ledger projection. Only that exact terminal schema may close Grok's
mapping through `qualify`. A positive receipt, ordinary receipt, boolean absence
claim, sibling filesystem check, source-only shared-leader plan, or forged
doctor result is non-promotable.

On interruption, replace `probe --profile ...` with `recover`, retain the
shared identity arguments, omit `--subscription-profile-root`, and supply the
original required `--run-id`. Recovery never relaunches a target. There is no
`puppet.py recover`. A complete run is reverified without target mutation. For
Claude matched activation, recovery may reconstruct a missing body-free signal
observation receipt and refresh its state hash from the canonical controller
journal. An incomplete run is either exactly halted and permanently marked
non-qualifying, or remains fenced when control delivery or identity is
ambiguous.
Claude ordinary-control recovery must also repeat the exact
`--paired-activation-receipt`.
Grok positive recovery repeats the exact `--plane-descriptor` request. Grok
ordinary recovery repeats the exact `--paired-grok-positive-receipt`. If a
positive rule had been materialized, recovery hash-verifies and removes only
that namespaced rule after the exact owned process is gone; ambiguity remains
fenced.

Qualification is capability-granular. The shared two-turn probe verifies
`launch`, `send`, `status`, `wait`, `checkpoint`, and `halt`. It does not prove
cross-process `resume`; keep `resume` explicitly `unsupported` until a separate
real resume contract exists and passes for that exact harness identity.

Regular qualification fails closed unless `PRIVATE_PROFILE` is the exact
authenticated Puppet-owned profile bound to the adapter executable. The probe
rechecks its body-free native auth status and closed launch environment
immediately before target start. Claude native-plane activation uses that same
profile's exact config directory while keeping its create-only instruction
artifact and transaction in separate FD-bound roots. The activation and
profile identities are joined in the receipt and reverified together. These
activation-lifecycle results remain non-promotable until matched no-bleed
evidence is implemented and accepted.

AGY 1.1.5 has one source-owned workspace custom-agent descriptor for the
documented `.agents/agents/<name>/agent.md` plus `--agent` surface. The candidate
is hash-namespaced, create-only, workspace-root-only, and explicitly
activation-disabled. A separate immutable source-only binding rederives the
compiler manifest and bytes, Pass-B contract/run identities, no-follow
current-UID `0700` workspace inode, exact doctor manifest and current
adapter/protocol/execution tuple, and the regular-session verdict. Its body-free
record fixes materialization, activation, launch, and qualification authority
to false. No AGY launch, probe, session, materialization, or qualification path
consumes it, and all config-isolation, sandbox-off, model, native-plane, and
ordinary-session no-bleed blockers remain.
AGY authority fences also require the exact session profile: `goal`,
`teamwork-preview`, invalid, and unbound profiles receive an additional blocker
and can never inherit a future `regular` qualification implicitly.

Claude's matched-control substrate also revalidates the source-owned compiled
marker and can join its body-free hashes to one exact native activation plan,
descriptor, and current doctor-only, unqualified adapter
manifest/implementation/execution-file/mapping tuple. That schema-v2
`activation_plan_join_only` record identifies the fenced activation-lifecycle
delivery scope but explicitly leaves delivery unauthorized. Schema v1 is
rejected. The record makes no controller, campaign, goal, checkpoint,
runtime-scan, no-bleed, qualification, or promotion claim. The Claude activated
Pass-B probe consumes it only through fixed controller attestation and one-use
signal reservation.

The controller can now rebuild that join and append one idempotent pre-delivery
attestation to its fixed private authority journal. The event retains only the
join and plan/descriptor/adapter identity hashes plus session/run identifiers;
it contains no marker digest, instruction body, or transcript content. The
public producer accepts no caller event, marker, digest, or journal. The
activated probe requires this attestation before reservation and
materialization. It still fixes delivery, runtime scan, qualification, and
promotion to false and is not a matched no-bleed or qualification receipt.

Claude's compile-only marker binding uses a fixed one-use ephemeral sidecar,
not a durable handoff claim. Its v2 binding commits the exact sidecar protocol:
exact marker bytes without a terminator, create-only mode 0600, controller
directory-FD/no-follow consumption, unlink before journaling, and hash-only
retention. Ready and follow-up JSON remain exact marker-free acknowledgements.
The activated probe orders exact matched-ready compilation, activation plan,
fixed-authority attestation, one-use reservation, materialization/launch,
validated ready plus sidecar, unlink/hash-only observation, follow-up, exact
halt, terminal no-recreation check, and rollback. The FD-bound guard pins the
workspace and private handoff directory, validates exact source-derived bytes,
and unlinks before observation journaling. Recovery rederives the source,
rejoins the spent reservation, and may consume an exact stranded signal only
after target death; a recreated or ambiguous leaf fails closed. The signal
event expressly proves neither delivery, target authorship, checkpoint
observation, lease ownership, nor no-bleed.
Paired ordinary-session no-bleed verification remains separate work.

## Interface

An adapter must provide detection and fingerprinting, current unrestricted and
sandbox-off mapping, argv construction without prompt bodies, initial and
follow-up envelopes, process/pane validation, proved queue behavior, and exact
graceful halt behavior. Use exact positive PID `SIGINT` for non-AGY halt; AGY
halts through private-pane EOF only. Never send tmux `C-c` or process-group
signals. Return `unsupported` when any piece is unknown.

The current major long-running session profiles are deliberately small:

`session_profile` is Puppet's native session-mode selector; it is distinct from
the task profile, the probe contract's `--profile`, and provider config profiles.

| Target | Mapped profiles | Initial native command |
| --- | --- | --- |
| AGY | `regular`; deferred: `goal`, `teamwork-preview` | none; deferred: `/goal`, `/teamwork-preview` |
| Codex | `regular`; deferred: `goal` | none; deferred: `/goal` |
| Claude | `regular`; deferred: `loop`, `goal` | none; deferred: `/loop`, `/goal` |
| Cursor | `regular` | none |
| Grok | `regular` | none |

The regular baseline is the only profile enabled by the current campaign.
Native-command mappings remain preserved but unqualified and must not be used
without a later command-specific lifecycle receipt. The contract pins one
`session_profile`. Launch the bare YOLO CLI with no instruction body in argv,
wait through the declared bounded structural settle, revalidate the exact pane
and process, then deliver the fingerprint-bound regular wrapper. Literal paste
and Enter are separated by their own bounded settle and pane recheck because
current TUIs can discard an immediate submit. These settles are race
mitigations, not readiness claims; only the strict handoff proves consumption.
Do not generalize initial-only or repeated-prefix behavior to native commands:
each command must separately prove activation, continuation, steering, resume,
and termination envelopes.

Codex's disabled workspace-plane plan composes the exact unrestricted base argv
with the exact absolute `-C` workspace into one standard admitted-launch plan.
That plan binds the source-owned session/run identity and a closed environment
whose only name is `CODEX_HOME`; ambient home, path, credential, model, effort,
profile, and config selectors cannot enter it. This is launch-context evidence,
not launch authority: every existing blocker and disabled lifecycle entry point
remains in force.

Codex may present a first-use workspace-trust gate before its composer exists.
That is a human-present security/configuration gate, not input readiness. Puppet
must not answer it, edit or inspect Codex configuration, or paste a task into
the gate. Qualify Codex only in an already trusted exact fixture root; otherwise
stop with the trust gate as the blocker.

Cursor's source-only workspace binding uses an exact reserved descriptor and a
contract-hash-named `.cursor/rules` candidate. It rejoins the shipped compiler
manifest, contract/run/workspace identities, current doctor-only adapter and
execution tuple, and the disabled workspace plan. Its public record is
body-free and fixes activation, launch, and qualification authority to false;
the older generic planner input is not itself binding or qualification proof.
That record remains unchanged and non-promotable.

The separate Cursor qualification-only descriptor is consumed only by the
shared Pass B controller. It requires the exact current doctor tuple and
authenticated private HOME/config/data/file-store profile, requires an absent
root `AGENTS.md`, and creates that one deterministic qualification wrapper
mode 0600 with no-follow `O_EXCL`. The descriptor assertion, plan, receipt, and
terminal rejoin bind both the wrapper SHA-256 and the underlying
effective-contract SHA-256. Preexisting regular files and symlinks fail closed;
Puppet never overwrites or appends to repository instructions. The controller
composes exactly one absolute `--workspace` selector followed by one exact
fixed, non-secret opaque positional activation trigger. Its literal, SHA-256,
final position, and full launch vector are bound after one allowlisted
descriptor symbol resolves it; compiled contracts, task bodies, and
arbitrary/operator-provided prompts are forbidden from argv. The
ordinary control and post-qualification regular launcher remain prompt-free.
The controller revalidates the file, profile, launch plan, executable, and
process boundary immediately before start. After accepted exact registered-PID
halt it removes only the
receipt-bound root `AGENTS.md` and commits terminal rollback proof.
Failure cleanup may roll back the same exact artifact only after an exact
failed-run halt and protected-population baseline restoration. Ambiguous halt
or rollback remains fenced with the artifact preserved.
The former qualification-only `.cursor/rules/*.mdc` descriptor/receipts and the
root-`AGENTS.md` post-launch-trigger descriptor/receipts are legacy,
non-promotable evidence; the separate activation-disabled source-binding record
remains non-promotable and cannot substitute for this root-AGENTS lifecycle.
That activated receipt still cannot promote. Cursor promotion requires a
controller-attested terminal join with a distinct ordinary Pass B control on
the same private profile and authority tuple. The ordinary control has no rule
or descriptor but uses the same qualification-only dynamic absolute-workspace
composer against its distinct fixture. Both workspaces must remain unchanged;
the join also requires a structurally observed read-only native-view
attach/detach, both accepted halt receipts, and the activated rollback. The
current default selector remains explicitly unresolved; no `--model` or effort
selector is injected.

AGY launches require exactly one help-proved `--new-project` flag in a
separately declared and fingerprinted project-isolation bucket. This prevents a
qualification run from silently joining the default AGY project; it does not
claim a separate credential or global data store. It also does not prove
sandbox-off; current AGY qualification stays blocked until a positive native
override or safe isolated config root is proved. Cursor's standalone and
application subcommand entrypoints remain separate until process and fingerprint
equivalence is controller-proved.

The local controller ledger is deliberately proof-root and checkout
independent, but it is cooperative same-UID authority rather than a signature
service or hostile-user security boundary. Do not claim otherwise.

Halt delivery is crash-aware and journaled: each action records its target PID,
v2 identity digest, index, action, intent, and submitted state. An interrupted
intent is ambiguous and must never be resent. A provisional target that cannot
be fully bound before input must remain fenced and non-qualifying without any
halt action.

## Transcript blindness

Never implement status with `capture-pane`, `pipe-pane`, scrollback, raw logs,
or conversation stores. Use process identity, an explicit bounded event hook,
and structured checkpoint files. When no safe status channel exists, return
reduced structural status and wait for a checkpoint.
