# Puppet GrillTrack decision record

Status: closed on 2026-07-21 with explicit operator confirmation

Public form: curated from the closed GrillTrack projection; raw machine paths,
event UUIDs/timestamps, private-repository identifiers, and personal checkout
state are intentionally omitted

The closed track contains 12 verified decisions, four superseded decisions,
and one deferred decision. This file is the public design authority for the
implementation campaign.

## Verified decisions

### `authority-001` — lifecycle and acceptance authority

Puppet is the authoritative lifecycle and acceptance recorder, not merely a
tmux transport. Explicit controller-only verdict commands record review,
rejection, blocking, and acceptance. A target cannot accept itself.

### `bootstrap-002` — immutable session supervisor

Every self-hosting session is pinned to a controller-owned immutable Puppet
release and hash. The target edits a separate candidate worktree. Status,
send, halt, sanitization, process validation, and verdict behavior never load
from the mutable candidate controlling that same session.

### `authority-002` — transcript-blind learning

Targets publish bounded structured handoffs containing claims, evidence
references, requested decisions, limitations, and exact candidate commit
identity. Puppet exposes only the validated reference and hash. The main
controller separately opens the artifact and inspects commits/evidence; it does
not learn from panes, transcripts, prompts, tool arguments, or chat stores.

### `kernel-001` — first live AGY stop condition

The first real AGY run proves only the read-only control loop: doctor, exact
launch identity, non-argv prompt delivery, nonce-bound ready checkpoint, one
sequenced follow-up acknowledgement, transcript-free status/wait, controller
verdict, zero protected-source drift, and exact graceful halt. It preserves the
tmux evidence session and performs no Puppet mutation, promotion, or close.

### `kernel-002` — minimum trusted Puppet N surface

Puppet N implements only:

```text
doctor
launch
send
status
wait
checkpoint
review
accept
attach-command
halt
```

`promote`, `close`, controller-side source-editing or delivery commands, and
unproved adapters return explicit `unsupported` results until later rungs
qualify them. After the read-only AGY and independent-review bootstrap gates
pass, `launch` may supervise a target contract that permits mutation and a
local commit only in that target's distinct candidate worktree.

### `evidence-001` — provenance-and-delta admission

Prior material counts only through an explicit matrix binding source identity,
revision, claim, proof strength, mechanism/version, portability, operator-local
assumptions, license/attribution, reuse decision, deterministic tests, and the
remaining live delta. Every extracted or reimplemented component reruns direct
tests. Fresh live proof covers changed mechanisms and the new end-to-end
composition. Stale, branch-only, terminal-derived, uncommitted,
operator-specific, or license-uncleared material remains design input.

### `probe-001` — two-pass real-adapter factory

Pass A is a zero-agent allowlisted census over exact executable path,
identity/hash, version/help, and prior evidence. It generates a fingerprinted,
hard-disabled doctor-only manifest. Pass B runs one standardized bounded
contract against one real harness at a time. Static declarations and target
self-reports may populate claims but cannot enable behavior; only
controller-verified observations bound to exact executable, adapter, and
protocol fingerprints graduate capabilities.

### `probe-002` — shared behavioral conformance contract

Every harness receives the same semantic prompt and strict handoff schema in a
disposable fixture. The target publishes a nonce-bound ready checkpoint,
remains available, acknowledges exactly one sequenced follow-up, and waits for
halt. The controller independently verifies executable/process/session
identity, non-argv transport, bounded artifacts, lifecycle legality, no source
drift, and exact graceful halt preserving tmux evidence. Only transport,
current YOLO flags, selected harness/model fields, and a required native
envelope may differ.

### `trust-001` — YOLO-only live execution

Puppet live execution is intentionally YOLO-only. Every adapter must prove the
current executable's permission-bypass/always-approve mapping and disable the
harness sandbox where exposed. Prompted, sandboxed, or partial-auto operation
is unsupported. Public documentation warns users prominently and local policy
must contain explicit acknowledgement. Unrestricted harness mechanics do not
authorize merge, push, deploy, publish, install, send, spend, deletion,
account/security, secret, or other external gated actions.

### `promotion-002` — bounded unattended internal promotion

One explicit campaign authorization replaces per-candidate approvals. The
immutable controller may promote only between sessions after binding exact
candidate head, tree, qualification root, and executable fingerprint; passing
deterministic tests and affected real probes; obtaining independent review
from a materially different proved harness/model; resolving required findings;
recording controller acceptance; and preserving the prior stable release plus
append-only promotion/rollback history. Ambiguous identity/proof, human gates,
unproved behavior, repeated repair failure, or scope expansion stops the
campaign. Internal promotion grants no external delivery authority.

### `bootstrap-003` — serial real-harness self-hosting ratchet

Manually scaffold the minimum kernel and doctor-only manifests, prove AGY with
the shared real contract, qualify an independent review rail, then let one
already-proved target at a time build a separate candidate while an immutable
controller release supervises it. No fake target qualifies an adapter or
end-to-end claim. Controller evidence, different-harness/model review, and the
campaign promotion gate decide acceptance between sessions.

### `diagnostics-001` — advisory diagnostics are not terminal truth

Maintain a version-scoped, provenance-backed diagnostic taxonomy separating
advisory UI state from controller-observed process, protocol, provider-error,
and terminal evidence. Never stop or diagnose from a banner alone. A dated
local AGY fixture records `Gemini 3.6 Flash · high · AI: Out of credits` as an
AI-overage-credit advisory, normalized as
`agy_ai_overage_credits_exhausted` only after current-surface validation. It is
not subscription exhaustion or task failure, and pane scraping remains
prohibited.

## Superseded decisions

Superseded records remain visible so later implementation cannot accidentally
revive them.

### `bootstrap-001` → superseded by `bootstrap-003`

The initial serial self-hosting idea correctly required one target/mutation
owner at a time, but its rationale contained a fake-harness graduation rung.
The final ratchet preserves serialization and removes fake target
qualification entirely.

### `promotion-001` → superseded by `promotion-002`

The initial rule required explicit operator approval for every candidate
promotion. The final bounded campaign authorization permits exact-gate internal
promotion without waking the operator for every rung while preserving all
external human gates.

### `kernel-003` → superseded by `probe-001`

The initial failure/recovery question assumed a fake-harness pass. Its required
failure classes—locks, collisions, wrong identity, busy/no-queue,
unacknowledged sends, malformed handoffs, illegal transitions, unexpected exit,
interrupted state writes, and exact halt—remain mandatory, but are now split
between direct kernel/fault tests and real-harness proof.

### `kernel-003-real` → superseded by `probe-001`

This intermediate record correctly prohibited fake targets from satisfying
adapter or product acceptance. The two-pass factory incorporates that rule
more completely and binds graduation to exact executable/adapter/protocol
fingerprints.

## Deferred decision

### `routing-001` — automatic harness/model routing

Auto mode is deferred. Every run must still record requested and
controller-observed harness/model/version/effort, task type/profile, latency,
safe native turn/tool counts or `unavailable`, checkpoint quality, repair
cycles, proof integrity, and controller verdict. Users can always select and
pin a harness/model. A later auto mode may switch only at declared task or
checkpoint boundaries, must explain exact-version outcome evidence, must not
hard-code permanent brand roles, and must never silently override the user.

## Closeout understanding

Puppet N must become a transcript-blind, YOLO-only controller kernel qualified
against real harnesses and built from admitted prior evidence through a
two-pass adapter factory. One bounded unattended orchestration campaign may
scaffold, test, real-probe, review, repair, and internally promote
immutable-between-session Puppet versions without per-rung operator approval,
while external gated actions stay excluded. The required terminal result is
either a locally committed, fully proved candidate or one precise
evidence-backed blocker.
