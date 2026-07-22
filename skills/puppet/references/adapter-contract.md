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
mapping, controller verdict, acceptance, halt receipt, and proof references all
verify. The probe must also resolve the separately supplied campaign ID and
repository/commit/path/SHA-256 goal tuple from the named local Git repository.
The accepted receipt requires exact inclusion in the fixed per-account
controller attestation ledger and is rechecked against the current executable,
adapter, platform, protocol, tmux executable/server, terminal state, and bound
artifacts.
Use `adapter_lab.py qualify` to bind that receipt; never toggle capability
states by hand. Any relevant drift disables the capability.

Pass B and normal live sessions share one checkout-independent controller lock
and durable session lease, so changing a proof or state root cannot admit a
parallel target. If a probe is interrupted, run `adapter_lab.py recover` with
the same exact run and identity inputs. Recovery never launches a target: it
verifies an already complete receipt or reconciles and gracefully halts only
the exact persisted target.

During a live probe, the target-population guard admits only the exact
authorized pre-existing population, the exact registered pane process, and
bounded same-executable processes whose freshly sampled PPID chain reaches
that registered process. The sample uses `pid`, `ppid`, `lstart`, and `comm`;
it never reads argv or terminal content. Missing ancestry, protected-process
ancestry, PID reuse, executable drift, cycles, or unrelated same-name
processes fail closed. Descendants are evidence, never signaling authority:
halt controls still address only the registered private pane, and accepted
proof requires the post-halt target population to equal the exact protected
baseline.

The operational sequence is:

```text
adapter_lab.py probe --profile source-free-pass-b-v1 \
  --target TARGET --proof-root ROOT --manifest MANIFEST --mapping MAPPING \
  --authorization AUTH --controller CONTROLLER --campaign-id CAMPAIGN \
  --goal-repo GIT_ROOT --goal-repository REPOSITORY --goal-commit COMMIT \
  --goal-path PATH --goal-sha256 SHA256 [--run-id RUN]
adapter_lab.py verify --run ROOT/probes/RUN/receipt.json
adapter_lab.py qualify --manifest MANIFEST --mapping MAPPING \
  --receipt ROOT/probes/RUN/receipt.json --out QUALIFIED_MANIFEST
```

On interruption, replace `probe --profile ...` with `recover`, retain every
identity argument, and supply the original required `--run-id`. There is no
`puppet.py recover`. A complete run is reverified without mutation; an
incomplete run is either exactly halted and permanently marked non-qualifying,
or remains fenced when control delivery or identity is ambiguous.

Qualification is capability-granular. The shared two-turn probe verifies
`launch`, `send`, `status`, `wait`, `checkpoint`, and `halt`. It does not prove
cross-process `resume`; keep `resume` explicitly `unsupported` until a separate
real resume contract exists and passes for that exact harness identity.

## Interface

An adapter must provide detection and fingerprinting, current unrestricted and
sandbox-off mapping, argv construction without prompt bodies, initial and
follow-up envelopes, process/pane validation, proved queue behavior, and exact
graceful halt behavior. Return `unsupported` when any piece is unknown.

AGY substantive messages receive exactly one literal `/teamwork-preview`
prefix. Cursor's standalone and application subcommand entrypoints remain
separate until process and fingerprint equivalence is controller-proved.

The local controller ledger is deliberately proof-root and checkout
independent, but it is cooperative same-UID authority rather than a signature
service or hostile-user security boundary. Do not claim otherwise.

## Transcript blindness

Never implement status with `capture-pane`, `pipe-pane`, scrollback, raw logs,
or conversation stores. Use process identity, an explicit bounded event hook,
and structured checkpoint files. When no safe status channel exists, return
reduced structural status and wait for a checkpoint.
