---
name: dinkuskit-e2e-blackbox
description: Run repeatable DinkusKit merchant acceptance tests from an isolated upstream Crabbox runner against deployed EmDash, Payments, Commerce and Ship. Use for the black-box E2E route or requests to rerun its established test environment; use dinkuskit-e2e for the merchant acceptance contract and initial onboarding.
---

# DinkusKit E2E Blackbox

**Experimental route.** A provider readiness check is not execution proof, and a browser probe is not merchant E2E success. Read [qualification](references/qualification.md) before choosing a provider. Follow the concrete [execution plan](references/execution-plan.md) for setup, reruns, and promotion.

## Intended operator experience

After one approved setup, a request such as “run the end-to-end test” reuses the enrolled environment and identity. Do not require a canned prompt, repeat credential entry, or recreate infrastructure for every run. Renew authentication only through the enrolled consumer's supported flow; an unavoidable human authentication step is a named blocker, not permission to weaken authentication.

## Scope and ownership

- Load the current `dinkuskit-e2e` merchant acceptance contract and record its exact revision. While that skill is pending, use the reviewed source in [PR135](https://github.com/saariuslystoned/SaariusSkills/pull/135); record that dependency as pending. Do not modify the other route or copy its evolving recovery rules here.
- This route owns runner qualification, preflight, repeatable execution, and joined evidence. The product remains deployed on its intended Cloudflare runtime regardless of runner provider.
- Use upstream Crabbox providers and lifecycle commands. Inspect the installed version and actual flags; do not assume documentation for main applies to a stable release or deployed runner.
- Keep product source, implementation notes, expected fixes, and debugging credentials out of the execution workspace. Test through supported merchant/browser/API surfaces. A repair owner may inspect source separately; the acceptance result remains independently reproducible.
- The test runner never edits, deploys, publishes, or repairs the product to make the current run pass. Report the first failed boundary to its existing owner, preserving successful payment/order identities.

## Setup once, run many times

1. Enroll a private nonsecret run profile: exact target origins, installed package/provenance expectations, provider and execution image/version, approved identity capability, test fixtures, permitted actions, proof root, retention, and spend/lifetime policy. Credentials and browser sessions stay with the owned consumers; never serialize or export cookies, browser profiles, tokens, or authentication state into the profile or snapshots.
2. Qualify the runner with a harmless public fixture twice on the same prepared environment. Retrieve and verify screenshots and structured results; qualify other artifact types separately. A passing doctor alone is insufficient.
3. Separately prove one supported initial login/bootstrap and unattended reuse/renewal. Never label the route unattended until a second run succeeds without another credential or environment setup.
4. Execute the authorized merchant case from the existing acceptance contract. Keep routine release regression, fresh installation/onboarding, practice label, and returning merchant as distinct results. A prepared merchant does not prove new-merchant onboarding.

## Each invocation

- Resolve the enrolled profile and exact case from task context. Ask only for a missing consequential decision; do not ask again for already authorized routine test actions.
- Check source/package/deployment identity, native admin protection, installed plugin readiness, TEST payment mode, PB sandbox readiness, issuer/Ship recipient/generation, and the approved fixture/recipient before dependent actions. Use current service deadlines and idempotency rules; do not invent retries.
- Reuse the qualified execution environment or recreate its dependency image automatically within the enrolled policy. Recreating compute must not recreate merchant accounts, replace secrets, erase orders, or claim that a VM snapshot resets external provider state.
- Use deterministic browser automation for stable steps; use computer use for initial exploration and bounded independent visual inspection. Do not substitute mocks, direct database writes, fabricated provider responses, or privileged source hooks for a required real-provider result.
- Stop dependent steps at the first failure. Preserve a known paid order and inspect its current supported state before any authorized retry. Never restart the whole checkout because a return page or evidence download failed.
- Capture safe per-step timings and joined outcome evidence. Authenticated network traces can contain cookies/tokens; omit them unless an approved capture path prevents sensitive material from entering retained output. Never retain raw auth exchanges as debugging proof.
- Return PASS, FAIL, BLOCKED, or UNVERIFIED for each case, with the first failing boundary, expected/observed behavior, artifact paths and hashes, and the next owner/action. Separate runner proof from product acceptance.

Long runs maintain `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md`. Preserve evidence under its retention policy; lease expiry and exact resource cleanup follow the enrolled authorization. Never clean unrelated leases, processes, stores, or proof.

Human involvement remains appropriate for an unrenewable authentication challenge, new account/security permission, production action, live charge/postage, external send, or change outside the enrolled test/spend policy. Prepare the concrete action before requesting its missing authority. Routine reruns within existing authority proceed autonomously.
