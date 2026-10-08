# Service Connections And Bounded Diagnosis

## Locate one failing stage

“Connection cannot be confirmed” is a symptom, not a root cause. The admin shell
can work while the plugin or its service request fails. Trace one interaction:

`admin action → plugin dispatcher → capability/host validation → DNS/transport
→ service authentication/authorization → response validation → rendered state`

Capture a small sanitized observer artifact before repeating a long bootstrap.
Record the stage reached, operation, safe status/error category and correlation
identity. Exclude tokens, cookies, signed URLs, private payloads and auth logs.
HTTP 200 containing an error state is still a failure.

Inspect the actual runner boundary. A process-global fetch mock may not intercept
a workerd request. Declared-host, DNS, private-address or redirect checks may run
before an injected HTTP adapter. A synthetic `.invalid` hostname can therefore
fail before the intended test transport is called. Prove where rejection occurs;
do not disable guards to make a fixture pass.

If a bounded attempt produces neither an observer nor a trace, preserve its
outcome and change the executable path before retrying. A finite test adapter
must be explicitly test-only, narrow in mapping, fail closed, and separately
identified in proof. Local adapted transport is not public network proof.

## Keep identities separate

Distinguish the CMS administrator, service merchant, stable site identity,
origin/callback URL, and authorized tenant/pool. Validate their contracts at
each boundary. An opaque site identifier is not interchangeable with a URL;
do not silently rewrite or rebind existing identities to pass validation.

For a requested merchant connection, prove the actual installed flow: authorized
start, challenge, merchant signin/consent, callback validation, scoped grant and
successful service operation. Preserve the protocol's state/PKCE, origin and
key-discovery requirements. Verify membership server-side; the browser choosing
a pool does not establish authority over it.

A seeded session, directly minted token, or direct service API test can prove a
component, but not the merchant consent flow. Document the tested boundary and
what remains before claiming “Connect” works.

## Keys, revocation, and restart proof

Use approved secret-handling facilities; keep credentials out of proof and
screenshots. “Ignored by Git” does not mean memory-only: writing test signing
material into generated configuration persists it. If the contract requires
memory-only material, use a compatible owned runner and document its lifetime.

State exactly what revocation invalidates. Blocking future grants is not the
same as invalidating already-issued tokens. Test the promised semantics rather
than assuming immediate revocation.

For persistence, identify the process and storage boundary, restart it without
reseeding, and compare the authoritative record and displayed result. Keeping a
controller/key alive while restarting a child is valid scoped evidence; it is
not a complete service-restart proof. Production endpoints, access grants and
permission changes still follow the user's scoped authorization.
