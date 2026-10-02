# ACP lifecycle recovery

Logical binding ownership survives a broker restart. The default binder uses
an existing Grok-compatible state-root namespace; configured host binders keep
precedence. Process-local runtime custody remains separate. Reusing the same
conversation starts a fresh model session only after the previous job is
terminal and its cleanup is proven; this does not resume model history.

Receipts separate `taskComplete`, `cleanupReady`, `complete`,
`admissionEligible`, and `remediation`. `complete` requires terminal outcome
and cleanup. `admissionEligible` reports the job cleanup gate, not permission
to replace a successor or foreign conversation. A broker-death error marks an
interrupted task and leaves worker cleanup unproven. Task timeouts remain one
hour by default with an explicit maximum of four hours. Permission setup is
independent of lifecycle recovery.

## Supported operator path

Use the unchanged host conversation ID and the exact original job and binder
from canonical state. First observe a nonterminal interrupted job through
`status`/`result`: only a demonstrably gone owner with matching persisted lease
may be marked `BRIDGE_RESTARTED`. Do not turn that receipt into cleanup proof.

From the installed plugin or a checkout matching its prepared runtime, request a plan.
The utility resolves the integrity-checked persistent runtime, just like the MCP
launcher; it does not require dependencies inside the plugin cache. If that
runtime is missing or invalid, prepare the selected bridge using the reported
setup command before retrying:

```sh
node bridge/acp-runtime/recover.mjs --lane cursor \
  --state-root /absolute/host-controlled/state-root \
  --job ORIGINAL-JOB-UUID --conversation GENUINE-CONVERSATION-ID \
  --expected-binder ORIGINAL-BINDER-ID
```

The utility reads one exact binding/job/lease, holds the ordinary conversation
lock during validation, and reports ownership observations. It does not
initialize/reconcile the whole job store or start a provider. Planning leaves
job and binding records unchanged, though it takes/releases their binding
lock. Existing stale locks remain subject to the normal fail-closed reclaim
contract. Run with the same host environment and canonical state root used by
the bridge; `--expected-binder` is a compare-and-swap precondition, never the
new owner identity.

After human approval of the exact proposed action and evidence, rerun the same
command with `--apply`. It preserves the task error/outcome, original owner,
job binding, old cleanup record, event log, and prior binding snapshot.
Publication records the new binder and recovery provenance. Ordinary later
binding replacements carry the recovery trail. Cleanup publication precedes
binder publication; an interruption can safely retry the same exact binding.
A successful repeat does not duplicate the migration. A successor job causes
the old request to fail. No processes are signalled and no raw model history
or credentials are inspected.

Only an obsolete process-default binder equal to the job's recorded broker ID
can migrate to the current host-controlled binder. A configured foreign binder
remains denied. The old broker must be observably gone with a matching lease.
Already-proven terminal cleanup can support a legacy binding migration without
new worker metadata. Uncertain cleanup requires every recorded launch to match
the job's exact session locator and have an independently observed missing PID
or a definite process start-time mismatch. Live, unknown, missing metadata,
foreign-session and ambiguous records are refused without mutation.

New jobs persist minimal launch receipts (session scope, launch ID, PID, launch
time and observed OS process start time) before session startup returns. The
unsupported-close fallback requires matching exit events for every owned
launch, and reports backend session discard as unsupported. Physical cleanup
of that local child does not prove provider-side history deletion or detached
descendant cleanup. Detached descendants are outside this narrow local-child
contract; an old job without sufficient receipts stays fenced for a separately
approved ownership investigation.

## Reference and proof limits

Design reference: upstream [OpenClaw ACPX source](https://github.com/openclaw/openclaw/tree/b725cc7b27f64ae1b1cf72eccc0bd5959d982839/extensions/acpx/src)
at `b725cc7b27f64ae1b1cf72eccc0bd5959d982839`. `session-resource.ts` derives
logical resources from owner/session identity. `session-owner.ts` requires
verified persisted locators or explicit migration. `runtime.ts` captures
physical cleanup before backend close and runs cleanup in `finally`;
`runtime-process-cleanup.ts` checks exact leases and handles ambiguity;
`runtime-generations.ts` separates logical resources from process-local
custody. [Its setup guide](https://github.com/openclaw/openclaw/blob/b725cc7b27f64ae1b1cf72eccc0bd5959d982839/docs/tools/acp-agents-setup.md)
describes an offline history-preserving ownership repair. Running OpenClaw
Doctor does not repair SaariusSkills state.

This implementation adapts those ownership distinctions to SaariusSkills'
existing ephemeral ACpx sessions, owner leases and binding locks. It does not
adopt OpenClaw's wrapper lease machinery, generations or history migration.
Deterministic harnesses and a real local synthetic ACP peer prove the bounded
contract; they do not prove production recovery of installed stranded jobs.


## Timezone-independent process identity

New broker owners and recorded workers use `ps-utc-v1:<UTC ISO timestamp>`.
The shared probe forces `TZ=UTC` and `LC_ALL=C`, validates the timestamp, and
compares only identities of that known format. A genuinely different comparable
birth still proves PID reuse. Probe failures, missing birth values, malformed
identities and incompatible formats remain unknown and keep the fence.

Older `lstart` strings have no recorded timezone. A live legacy owner or worker
cannot be automatically reinterpreted as UTC or admitted for recovery by string
mismatch, even if a local display happens to match. Obtain genuine terminal and
owned-exit evidence through the original owner; do not refresh a live broker,
rewrite records or apply recovery to bypass this ambiguity. Definite process
absence retains the existing narrow recovery path. The timestamp has the same
one-second precision as `ps lstart`; this repair adds timezone stability, not
subsecond PID-reuse guarantees. Installed adoption remains a separate action.
