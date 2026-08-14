# Puppet pre-implementation bundle

Status: the original GrillTrack design-closeout snapshot is preserved here.
Bootstrap source now lives under `skills/puppet/`. The regular/default
five-harness v0.1 campaign completed at implementation head
`544a347117a9423d53f1975ab0d0176116e2e80c`; its curated, transcript-free
closeout is recorded in
[`five-harness-closeout-20260727.md`](five-harness-closeout-20260727.md) and
[`live-proof/five-harness-544a347-20260727.json`](live-proof/five-harness-544a347-20260727.json).
Machine-private proof remains outside the public branch.

The completed 2026-07-25 dogfood goal is
[`codex-goal-four-harness-dogfood.md`](codex-goal-four-harness-dogfood.md).
It reopens PR #5 after its standalone core closeout to collect real,
subscription-backed Codex, Claude, Cursor, and Grok implementation and
cross-review evidence. AGY was added to the final exact-head closeout. The
broader 2026-07-22 qualification packet remains the longer-term product
contract.

The active design amendment remains
[`instruction-qualification.md`](instruction-qualification.md). It narrows the
first portable baseline to regular sessions, adds instruction-plane safety and
qualification, and permits isolated per-harness qualification lanes. Where it
conflicts with the historical packet, the amendment wins for new work.

At the time of this snapshot, Puppet was a proposed skill and CLI for
supervising real coding-agent harnesses
through durable, transcript-blind checkpoints. This directory preserves the
curated public design packet produced during its first GrillTrack campaign so the
implementation can begin from explicit decisions instead of reconstructing the
conversation.

> **Mandatory operating warning:** the proposed live runtime is YOLO-only. A
> future Puppet launch must use each harness's unrestricted/always-accept mode
> and disable its sandbox where that control exists. That runtime posture does
> not authorize pushes, merges, deploys, sends, spending, deletion, account or
> security changes, secret access, or any other separately gated action.

## Start here

- [`v0.2-fast-launch-20260727.md`](v0.2-fast-launch-20260727.md) defines the
  current mixed-target operator-latency slice and its remaining live proof.
- [`five-harness-closeout-20260727.md`](five-harness-closeout-20260727.md)
  is the final v0.1 evidence matrix and acceptance summary.
- [`codex-goal-four-harness-dogfood.md`](codex-goal-four-harness-dogfood.md)
  is the completed dogfood-first Codex goal packet.
- [`codex-goal-regular-qualification.md`](codex-goal-regular-qualification.md)
  is the broader superseded campaign packet and longer-term qualification
  reference.
- [`instruction-qualification.md`](instruction-qualification.md) records the
  post-closeout decisions on instruction composition, workspace ownership,
  regular-session scope, concurrency, models, and deferred native commands.
- [`instruction-plane-descriptors.md`](instruction-plane-descriptors.md)
  defines the hash-bound native-plane descriptor and records the current
  capability matrix without mistaking the fallback initial-message wrapper for
  native-plane qualification.
- [`harnesses/`](harnesses/) contains exact-version static maps and live-test
  deltas for the five independent regular-session lanes.
- [`codex-goal.md`](codex-goal.md) is the historical bootstrap goal packet. Its
  unchanged safety, evidence, and controller-authority clauses still apply,
  but its serial/profile-specific requirements are superseded by the active
  amendment.
- [`implementation-seed.md`](implementation-seed.md) is the complete product,
  CLI, adapter, lifecycle, trust, test, and acceptance contract.
- [`prior-proof-provenance.md`](prior-proof-provenance.md) maps the existing
  public and operator-local evidence families to what Puppet may admit,
  reimplement, or must prove again.
- [`DECISIONS.md`](DECISIONS.md) preserves all 12 verified, four superseded,
  and one deferred GrillTrack decisions in a public-safe form.
- [`PROOF.md`](PROOF.md) records document verification, public artifact hashes,
  non-claims, redactions, and residual runtime risks.
- [`herdr-puppet.md`](herdr-puppet.md) is an adjacent discovery-backed plan for
  proving Herdr as a human-visible, transcript-blind remote-agent transport
  before proposing it as an optional Puppet backend. Its redacted discovery
  evidence is in [`herdr-puppet-proof.md`](herdr-puppet-proof.md).

The raw local ledger/event stream and private-repository identifiers are not
published. Their material decisions, supersessions, deferments, limitations,
and implementation gates are preserved in the curated files above.

## Validate the bundle

Run the repository tests plus the structural and hash checks recorded in
[`PROOF.md`](PROOF.md). The public bundle is intentionally not a resumable raw
`.grilltrack` state directory.

The initial closed track contains 12 verified decisions, four superseded
decisions, and deferred evidence-based automatic harness/model routing. The
2026-07-22 amendment keeps automatic routing deferred, preserves explicit user
selection, and records the new instruction-plane and regular-baseline policy.

## Implementation boundary

Mutating work must use isolated worktrees. The active campaign may create local
commits and run isolated real-harness proof lanes under the submitted goal. It
may not modify live operator-global harness files or interfere with sessions it
did not create. Repository text by itself grants no push, pull-request, merge,
deploy, publication, global-install, external-send, spending,
destructive-cleanup, account/security, or secret authority. A deliberately
submitted goal may record separate operator authority for one named draft PR;
the active goal permits updates to PR #5 but still forbids merge.

No target terminal, transcript, conversation store, pane capture, credential,
or auth log was copied into this bundle. The current CLI versions and AGY
overage-credit interpretation are dated evidence inputs; the implementation
must re-census and revalidate them before enabling behavior.
