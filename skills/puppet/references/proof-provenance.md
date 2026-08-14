# Puppet proof and provenance

Start with `plans/puppet/prior-proof-provenance.md`. Admit each prior source by
exact identity and revision, narrow invariant, proof strength, mechanism and
version match, portability assumptions, license path, reuse decision,
deterministic tests, and remaining live delta.

Use one of: `reuse_contract`, `extract_with_attribution`, `reimplement`,
`design_input_only`, or `fresh_live_proof`. Private access does not grant a
license to copy code. Reimplement private patterns unless an explicit rights
and attribution path permits extraction.

Rerun deterministic tests for every extracted or reimplemented component.
Freshly prove changed mechanics and the composed product. A fake target can
exercise pure kernel faults but cannot qualify an adapter or end-to-end claim.

Commit only sanitized proof. Keep machine paths, host topology, private source
identities, raw prompts, transcripts, auth data, and credentials outside the
public packet.
