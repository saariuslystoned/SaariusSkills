---
name: dinkuskit-e2e
description: Prepare and prove DinkusKit merchant onboarding through a disposable Registry EmDash store, Stripe TEST checkout, Commerce order, and hosted Ship Pitney Bowes sandbox fulfillment. Use for this cross-service flow or its distinct practice-label and returning-merchant checks.
---

# DinkusKit E2E

**Draft — full E2E unverified.** Provisioning, TEST payment and the paid order have been observed; hosted fulfillment remains blocked. This skill is not a certified automation path. Read [status and promotion criteria](references/status.md) before making capability claims. Read [the run contract](references/run-contract.md) before preparing or executing a run.

## Outcome

A new merchant provisions a disposable Registry EmDash store, installs Commerce and Payments through Registry, connects Stripe in TEST mode, completes a real TEST checkout, and sees the paid TEST order in Commerce admin. The order then produces a hosted Ship Pitney Bowes sandbox shipment, a rendered provider PDF, and matching tracking/completed state.

Keep practice-label and returning-merchant checks as separate cases. Neither replaces the new-merchant order-to-shipment flow. Local tests, source merges, mocked checkout, a generated practice PDF, and service health responses do not establish this outcome.

## Working rules

- Use the assigned run's exact identities, environment and authority. Keep the merchant/plugin-user identity separate from the DinkusKit administrator identity.
- Confirm Stripe TEST and PB sandbox at each boundary. Stop before live charges, live postage, external sends, production changes or unapproved account/auth changes; obtain the applicable human authorization.
- Use native EmDash authentication. Cloudflare Access authentication has been observed for an isolated test admin; automated merchant authentication remains unverified. Do not bypass passkeys or change auth policy to make a run pass.
- Access exceptions must be narrowly scoped to current manifests and explicit authority. Never expose the entire admin surface. Public store-proof access and merchant checkout authorization are distinct checks.
- Preserve a successful payment and its durable order when return-page confirmation fails. Inspect the existing order before retrying; never infer that an error page means payment failed.
- Identify the deployed store and each hosted service independently: source revision, artifact/package digest, deployment/version identity, and observed configuration. An installed version label or merged commit is insufficient attestation.
- Keep credential values, cookies, tokens, private emails and private account details out of agent context and public artifacts. Use approved credential consumers; record safe identity aliases and redacted evidence.

For setup, recovery or a provider refusal, read the run contract’s [boundary recovery guidance](references/run-contract.md#boundary-recovery). It covers key-preserving configuration, installed package qualification and sandbox account ambiguity.

## Optional mailbox evidence

For an assigned merchant-email check, use the operator's [gogcli runbook](https://github.com/saari-co/x-api/blob/3c0f444968ddbfbce5130c70e13edb2a209cd610/docs/operations/dinkuskit-e2e-gogcli.md). This is a pinned proposal in [pending runbook PR](https://github.com/saari-co/x-api/pull/711), not a claim that it has landed; repository access is required. If inaccessible, obtain an approved operator runbook rather than guessing account or authentication setup.

Use the run's approved client/account and bounded read-only query. Broader provider OAuth grants do not authorize sends or mailbox/settings changes. Keep private runtime identities, mail contents and authentication material out of this reusable skill and public proof. Mailbox setup or an email match does not certify the merchant flow; a missing message remains an observation scoped to its query and time.

## Run and close

Record prerequisites before mutations. Execute only the authorized case, capture each user-visible transition, and join order, payment, shipment, PDF and tracking evidence using stable sanitized aliases. Missing evidence is `UNVERIFIED`, not an inferred pass.

Maintain `STATE.md`, `events.jsonl`, `heartbeat` and `PROOF.md` for a long run. Report exact source/deployment identities, per-case result, evidence paths, blockers and next safe action. Retain evidence for the intended 14-day window; teardown is a separately authorized exact-resource operation.

Promote this draft only after the full flow and both separate cases have inspectable runtime proof, with limitations retained. Do not invent readiness polling intervals or retry deadlines: use the current service contract and record them for the run.
