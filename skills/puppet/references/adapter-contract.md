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
Candidate names are prefiltered against every declared launcher, transient
executable, and final runtime basename before the controller binds the exact
process-owned mapped-vnode identity. Per-node parent edges and birth identity
come from Darwin `proc_pidinfo` `(sec,usec)` or Linux
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
  [--plane-descriptor DESCRIPTOR] [--run-id RUN]
adapter_lab.py verify --run ROOT/probes/RUN/receipt.json
adapter_lab.py qualify --manifest MANIFEST --mapping MAPPING \
  --receipt ROOT/probes/RUN/receipt.json --out QUALIFIED_MANIFEST
```

On interruption, replace `probe --profile ...` with `recover`, retain the
shared identity arguments, omit `--subscription-profile-root`, and supply the
original required `--run-id`. Recovery never relaunches a target. There is no
`puppet.py recover`. A complete run is reverified without mutation; an
incomplete run is either exactly halted and permanently marked non-qualifying,
or remains fenced when control delivery or identity is ambiguous.

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
rejected. The record makes no
controller, campaign, goal, checkpoint, runtime-scan, no-bleed, qualification,
or promotion claim and is not yet consumed by the live probe.

The controller can now rebuild that join and append one idempotent pre-delivery
attestation to its fixed private authority journal. The event retains only the
join and plan/descriptor/adapter identity hashes plus session/run identifiers;
it contains no marker digest, instruction body, or transcript content. The
public producer accepts no caller event, marker, digest, or journal. This
attestation still fixes delivery, runtime scan, qualification, and promotion to
false and is not a live-probe or matched-control receipt.

Claude's compile-only marker binding uses a fixed one-use ephemeral sidecar,
not a durable handoff claim. Its v2 binding commits the exact sidecar protocol:
exact marker bytes without a terminator, create-only mode 0600, controller
directory-FD/no-follow consumption, unlink before journaling, and hash-only
retention. The existing probe does not consume this sidecar, and the current
conformance handoffs remain exact marker-free acknowledgements. Signal
consumption now has a source-only FD-bound guard that proves the leaf absent,
pins the plan's workspace and private handoff-directory identities, consumes
exact source-derived bytes, and writes a body-free one-use reservation for the
activation join before exposing the guard. The fixed controller lock and
reservation prevent an abandoned guard or post-unlink journal failure from
authorizing a second attempt. Consumption unlinks before observation
journaling, proves through the still-open descriptor that the exact signal
inode has no retained link, and binds the verified hash-only event to the
reservation. It is not imported by the probe, handoff, adapter, or
qualification paths and expressly proves neither delivery, target authorship,
checkpoint observation, lease ownership, nor no-bleed.
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
