# Puppet YOLO contract

Puppet supports one live trust profile: unrestricted, always approve, with the
harness sandbox disabled wherever that control exists. Prompted, sandboxed, or
partly automatic modes are unsupported.

Before launch, require a local uncommitted acknowledgement naming the campaign,
operator, exact harnesses, bounded task scope, and hard gates. Map the exact
current executable fingerprint to the permission-bypass, sandbox-off, and any
required project-isolation controls. AGY requires exactly one help-proved
`--new-project` launch flag so a live qualification does not silently reuse its
default project. This is project-level isolation, not a separate credential or
global-store claim. Unknown, partial, or drifted mappings fail closed.

YOLO is cooperative same-user execution, not hostile containment. It changes
harness mechanics only. It never authorizes delivery, external effects,
spending, destructive operations, account/security/device changes, secret
access, or interference with work owned by another operator.

The disposable conformance fixture bounds and detects drift; it is not an OS
security boundary. Preserve this warning in public docs, doctor output, and
install guidance.

The fixed controller ledger prevents another checkout or caller-selected proof
root from independently minting qualification, and its private ownership blocks
ordinary other UIDs. It is a hash-chain inclusion authority, not a cryptographic
signature service. Hostile code already running as the operator UID can alter
operator-owned state; Puppet coordinates cooperative YOLO execution rather than
containing it.
