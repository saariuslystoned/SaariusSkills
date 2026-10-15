# Qualification ledger

This file distinguishes supported, prepared, tested and observed capabilities. Do not infer full E2E from a provider smoke test. Private account/resource identities belong in the run profile, not this portable ledger.

## October 15, 2026

| Capability | Status | Evidence or missing proof |
| --- | --- | --- |
| Local upstream stable Crabbox | VERIFIED 0.78.0 | Official Homebrew release installed with runtime pack and Apple helper; prior keg preserved. |
| Hetzner configured provider readiness | VERIFIED readiness only | Native doctor reports broker-owned provider credentials ready, without returning values. |
| Hetzner actual execution on current setup | BLOCKED before lease creation | Current CLI's coordinator run admission received404; the deployed coordinator lacks the required endpoint. No VM or workload started. Requires qualified coordinator upgrade or a separately enrolled supported direct consumer. Do not replay the refused run or silently switch authentication. |
| Cloudflare configured provider readiness | VERIFIED readiness only | Native doctor reports delegated runner control plane, authentication and runtime ready. |
| Cloudflare headless browser and artifact retrieval | VERIFIED synthetic runner proof | Two fresh Chromium156 processes on the same prepared Linux lease passed an owned DOM interaction and external HTTPS200. PNG, public trace ZIP and JSON artifacts returned through ordinary CLI process stdout and passed size/SHA-256 checks. No provider fork or private provider API. |
| Dedicated test-account binding for CF runner | UNVERIFIED | Existing runner identity must be bound to an approved account before production of a persistent enrollment. |
| Repeatable authenticated merchant session | UNVERIFIED | Requires supported initial bootstrap and second unattended run. |
| Complete real-provider merchant acceptance | UNVERIFIED | Runner qualification does not establish checkout, label, PDF, tracking or completion. |

Crabbox0.78.0 advertises Hetzner SSH/browser and Cloudflare delegated Linux command execution. Cloudflare lacks native artifact download flags and interactive desktop access; browser-package execution and a supported artifact-return path must be proven. Its provider bypasses the coordinator by design. Check compiled CLI capabilities and exact deployed compatibility rather than relying only on current-main documentation.

Source references:

- [Crabbox stable release](https://github.com/openclaw/crabbox/releases/tag/v0.78.0)
- [Hetzner provider at stable tag](https://github.com/openclaw/crabbox/blob/v0.78.0/docs/providers/hetzner.md)
- [Cloudflare provider at stable tag](https://github.com/openclaw/crabbox/blob/v0.78.0/docs/providers/cloudflare.md)
- [Merchant acceptance source proposal](https://github.com/saariuslystoned/SaariusSkills/pull/135)

## Observed Cloudflare experiment

Client: upstream0.78.0. The existing deployed runner's source revision and dedicated test-account binding remain unverified. Public inputs only; no product source sync, merchant credentials, browser profile, or explicit provider-secret forwarding.

Initial dependency preparation took84.1s and installed Chromium. That command's probe then failed because its output parent directory was absent. The corrected next attempt launched Chromium and retrieved artifacts, but its assertion failed because a third-party public page's heading had changed. Both failures remain qualification evidence; neither was a provider/runtime failure.

One bounded final correction used an owned deterministic DOM fixture and limited the external page to a connectivity check. Two fresh browser processes passed on the same prepared environment, with distinct run identities and the same preparation marker. The combined final command took6.68s. Each PNG was40,281 bytes; both images were visually inspected, and both trace ZIPs passed integrity/event-stream inspection. This demonstrates warm dependency reuse, not a cold end-to-end runtime benchmark or authenticated session reuse.

The exact disposable lease's native stop returned0 and removed its local claim. A subsequent status refusal is not independent provider-side absence proof; retain the native stop receipt as the observed lifecycle outcome.

Stable0.78.0 rejects `--capture-stdout` and native download/artifact flags for this delegated provider. The tested path captures the normal CLI subprocess stdout locally and decodes a bounded public-artifact stream with run identity, ordered chunks, size and SHA-256 checks. Decoder negatives reject truncation, reordering, wrong run identity, and wrong hash. Authentication-bearing traces remain prohibited; this proof contains public synthetic traffic only.
