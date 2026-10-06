# Historical retention through validated references

Repository: saariuslystoned/SaariusSkills. Branch:
`codex/grilltrack-cas-retention-20261006`. Base:
`3db23c27489910b57a562f214c16cbaca4d0b9a8`.

## Problem and representation

A reconciliation copied each source's entire prior lineage into another
snapshot and repeated the expanded paths in its manifest. Nested joins could
therefore multiply historical bodies without adding new information.

New v2 plans bind source lineage Merkle roots. Immutable SHA-256 objects store
raw file bytes and canonical directory descriptors; identical bodies and
subtrees share addresses. A compact source index references prior definitions.
A per-plan root pointer and a transaction-final receipt marker identify the
published logical root. Historical raw bytes, role-specific bodies, provenance,
explicit adjudication, original event streams and deterministic projections
remain reconstructible and subject to exact-source recomputation.

## Acceptance evidence

Public tests construct fresh neutral histories inside temporary repositories.
They cover binary/text/empty roundtrips, deterministic hashes, shared subtrees,
missing/corrupt objects, unsafe paths, duplicate JSON keys and traversal depth;
validly rehashed foreign artifacts still fail source/provenance checks.

Integration coverage includes six committed nested joins, exact reconstruction
of every prior root and role history, one object per distinct byte sequence,
compact per-plan files, deterministic planning and byte-identical retries.
The neutral six-join run added `[81, 16, 16, 16, 16, 16]` objects: 161
unique objects totaling 949,552 bytes, with every earlier logical root preserved.
Existing transaction tests still inject staging, ledger/event publication and
receipt failures; completed retries preserve subsequent canonical progress.
Mixed v1/v2 histories and interrupted original v1 journals remain readable and
recoverable. Malformed legacy plan JSON fails cleanly before canonical writes.
An unapplied v1 digest cannot approve v2 storage.

The owner-private immutable regression corpus is checked read-only outside
tracked proof. Its bodies, source paths and manifests are not public fixtures.

## Compatibility and gates

Existing v1 raw files remain unchanged. The additive transition can retain
legacy physical duplicates; this change prevents further recursive copying and
does not delete or rewrite already committed history. Older reconcilers cannot
read v2 lineage. A product must use the storage-aware version after its normal
owner-approved installation and approve a newly generated v2 plan.

This source repair does not apply a reconciliation to a product, install a
plugin, merge its PR or resume paused product work. CI and qualified review
results belong to the final PR's immutable source tuple; native review coverage
must be recorded separately rather than inferred from passing tests.
