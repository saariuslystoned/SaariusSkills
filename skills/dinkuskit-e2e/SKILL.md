---
name: dinkuskit-e2e
description: Prepare and prove DinkusKit merchant onboarding through a disposable Registry EmDash store, Stripe TEST checkout, Commerce order, and hosted Ship Pitney Bowes sandbox fulfillment. Use for this cross-service flow or its distinct practice-label and returning-merchant checks.
---

# DinkusKit E2E

**Draft — runtime unverified.** This skill defines the intended proof, not a certified automation path. Read [status and promotion criteria](references/status.md) before making capability claims. Read [the run contract](references/run-contract.md) before preparing or executing a run.

## Outcome

A new merchant provisions a disposable Registry EmDash store, installs Commerce and Payments through Registry, connects Stripe in TEST mode, completes a real TEST checkout, and sees the paid TEST order in Commerce admin. The order then produces a hosted Ship Pitney Bowes sandbox shipment, a rendered provider PDF, and matching tracking/completed state.

Keep practice-label and returning-merchant checks as separate cases. Neither replaces the new-merchant order-to-shipment flow. Local tests, source merges, mocked checkout, a generated practice PDF, and service health responses do not establish this outcome.

## Working rules

- Use the assigned run's exact identities, environment and authority. Keep the merchant/plugin-user identity separate from the DinkusKit administrator identity.
- Confirm Stripe TEST and PB sandbox at each boundary. Stop before live charges, live postage, external sends, production changes or unapproved account/auth changes; obtain the applicable human authorization.
- Use native EmDash authentication. Cloudflare Access authentication has been observed for an isolated test admin; automated merchant authentication remains unverified. Do not bypass passkeys or change auth policy to make a run pass.
- Access exceptions must be narrowly scoped to current manifests and explicit authority. Never expose the entire admin surface. Public store-proof access and merchant checkout authorization are distinct checks.
- Identify the deployed store and each hosted service independently: source revision, artifact/package digest, deployment/version identity, and observed configuration. An installed version label or merged commit is insufficient attestation.
- Keep credential values, cookies, tokens, private emails and private account details out of agent context and public artifacts. Use approved credential consumers; record safe identity aliases and redacted evidence.

## Run and close

Record prerequisites before mutations. Execute only the authorized case, capture each user-visible transition, and join order, payment, shipment, PDF and tracking evidence using stable sanitized aliases. Missing evidence is `UNVERIFIED`, not an inferred pass.

Maintain `STATE.md`, `events.jsonl`, `heartbeat` and `PROOF.md` for a long run. Report exact source/deployment identities, per-case result, evidence paths, blockers and next safe action. Retain evidence for the intended 14-day window; teardown is a separately authorized exact-resource operation.

Promote this draft only after the full flow and both separate cases have inspectable runtime proof, with limitations retained. Do not invent readiness polling intervals or retry deadlines: use the current service contract and record them for the run.
