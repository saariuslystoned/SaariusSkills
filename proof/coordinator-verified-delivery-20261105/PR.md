## Summary

Small portable `smoky-coordinator` refinement, preserving its existing structure:
- Bind communication authority to the destination/account/sending identity.
- Separate execution acceptance, delivery completion and follow-up consumption.
- Reconcile uncertain sends before retrying; cancellation is not rollback.
- Allow supported lightweight acknowledgments without hiding owed answers.
- Preserve original verified human authorization; emoji or relayed prose add none.

No new runtime, adapter, scheduler, queue, ledger, installation or merge authority.

## Validation

- Full repository suite: **227 passed**.
- Packaging: **31 passed**; portable metadata/link/license/privacy: **5 passed**.
- Structural audit: metadata verified, no packaging errors; body-length advisory
  retained to keep the bounded rules together.
- Diff, changed-scope privacy and proof link/JSON checks passed.
- Six synthetic scenario walkthroughs; **static reasoning, not deployed runtime
  or independent behavior proof**.

Tracked proof: `proof/coordinator-verified-delivery-20261105/PROOF.md` and
`SCENARIOS.md`. Base: `42eaec2d62fa15bda220ae46a4feaf788380205e`;
skill checkpoint: `a27fe4be2b80eedbf89c24d6f102c3c56451b79d`.
Final head is the PR head; later commits before opening are proof-only.

## Reviews and gates

Current-head CI and comprehensive exact-tuple review are pending. Native review
is unavailable: this repository is not enrolled. No native clearance or earlier
PR's scoped exception is assumed. The assigned Pi lead retains review waiting
and scoped repair ownership. Review findings and exact request/run identities
will be recorded in PR closeout. No merge; human landing remains separate.
