# Puppet pre-implementation bundle

Status: historical GrillTrack design-closeout snapshot. Bootstrap source now
lives under `skills/puppet/`; current implementation proof is tracked
separately under `proof/puppet-v01/`. The live five-harness campaign remains
in progress until that newer proof says otherwise.

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

- [`codex-goal.md`](codex-goal.md) is the self-contained goal packet used by
  the implementation campaign.
- [`implementation-seed.md`](implementation-seed.md) is the complete product,
  CLI, adapter, lifecycle, trust, test, and acceptance contract.
- [`prior-proof-provenance.md`](prior-proof-provenance.md) maps the existing
  public and operator-local evidence families to what Puppet may admit,
  reimplement, or must prove again.
- [`DECISIONS.md`](DECISIONS.md) preserves all 12 verified, four superseded,
  and one deferred GrillTrack decisions in a public-safe form.
- [`PROOF.md`](PROOF.md) records document verification, public artifact hashes,
  non-claims, redactions, and residual runtime risks.

The raw local ledger/event stream and private-repository identifiers are not
published. Their material decisions, supersessions, deferments, limitations,
and implementation gates are preserved in the curated files above.

## Validate the bundle

Run the repository tests plus the structural and hash checks recorded in
[`PROOF.md`](PROOF.md). The public bundle is intentionally not a resumable raw
`.grilltrack` state directory.

The closed track contains 12 verified decisions, four superseded decisions,
and one intentionally deferred decision: evidence-based automatic harness/model
routing. The goal captures routing telemetry now but keeps explicit user
selection authoritative.

## Implementation boundary

The first implementation campaign must start in a fresh isolated worktree. It
may create local commits and run the serial real-harness proof ladder described
in the goal, but the packet itself grants no push, pull-request, merge, deploy,
publication, global-install, external-send, spending, destructive-cleanup,
account/security, or secret authority.

No target terminal, transcript, conversation store, pane capture, credential,
or auth log was copied into this bundle. The current CLI versions and AGY
overage-credit interpretation are dated evidence inputs; the implementation
must re-census and revalidate them before enabling behavior.
