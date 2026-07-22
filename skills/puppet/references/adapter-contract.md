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
verify.
Use `adapter_lab.py qualify` to bind that receipt; never toggle capability
states by hand. Any relevant drift disables the capability.

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

## Transcript blindness

Never implement status with `capture-pane`, `pipe-pane`, scrollback, raw logs,
or conversation stores. Use process identity, an explicit bounded event hook,
and structured checkpoint files. When no safe status channel exists, return
reduced structural status and wait for a checkpoint.
