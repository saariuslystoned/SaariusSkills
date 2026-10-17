---
name: dinkuskit-e2e-blackbox
description: Run or prepare DinkusKit acceptance on the enrolled Crabbox Cloudflare runner, reusing canonical dinkuskit-live-test journeys and reporting revision-bound proof. Use for isolated runner qualification or repeatable black-box execution; the canonical skill owns journey steps and assertions.
---

# DinkusKit E2E Blackbox

Use Chromium/Playwright inside upstream Crabbox Cloudflare for the selected
isolated execution route. Reuse the canonical `dinkuskit-live-test` journeys;
this skill owns runner admission and evidence, not a second acceptance suite.

## Choose the case before running

Read [current status](references/current-status.md) and the linked canonical
skill, runner README and status at the selected immutable revision. Refresh
source and PR state before using a dated result as current authority.

- **Routine synthetic fixture:** the enrolled CP-1 campaign can run unattended
  within its fresh policy. It proves runner/fixture behavior only.
- **Canonical journey on this runner:** select the explicit journey and target.
  Storefront is prepared and tested offline; its hosted capability is not yet
  active. Preparation does not authorize a hosted run.
- **Canonical local/live test:** follow `dinkuskit-live-test` for its supported
  local runner and journey semantics. Its live history does not qualify the
  Cloudflare port. Do not run the default all-`@running` command when assigned
  only Storefront, Cart or another bounded case.
- **Public runner probe:** the bundled helpers are historical October 15
  qualification probes, not the routine campaign or merchant tests. Read
  [historical qualification](references/qualification.md) only when needed.

Managed Browser Run is optional/deferred; Hetzner is historical. Neither is a
prerequisite or silent fallback. See [execution](references/execution-plan.md)
for admission and invocation. Read [browser options](references/browser-options.md)
only for an explicitly assigned alternative-browser investigation.

## Execute within the existing authority

1. Resolve the profile, case, exact source/package/deployment identity, target,
   identity capability, allowed effects and proof destination. Read current
   policy and ledger; a dated allowance is not authority for another case or
   expired policy.
2. Choose a stable request ID before dispatch. An identical redelivery reuses
   that ID. After failure or an unknown outcome, inspect that request's receipt,
   ledger and lease; never use a fresh ID to retry uncertain work.
3. Use the owned consumer and runner facade. No bare credential extraction,
   host bootstrap, copied environment, browser profile export or account
   fallback. Missing/expired admission is a blocker, not permission to weaken
   authentication or change settings.
4. Preserve canonical spec/assertion bytes and record their hashes. Adapt only
   explicitly reviewed transports/configuration. Never use mocks, privileged
   source hooks or fixture results as proof of required hosted providers.
5. Follow the selected journey's hard-stop, soft-assertion and recovery rules.
   Preserve paid order identity; never restart checkout after a later failure.
   The runner does not repair, deploy or mutate settings to make a test pass.
6. Return each case's PASS/FAIL/BLOCKED/UNVERIFIED, source and target identities,
   original reports, inspected evidence and hashes, first failing boundary,
   timing, lifecycle outcome and next owner. Separate runtime stopped from
   provider absence, reserved allowance from actual billing, and prior
   enrollment from observed unattended invocation.

Keep credentials, sign-in codes/links, cookies and authenticated traces out of
retained artifacts. Long runs keep `STATE.md`, `events.jsonl`, `heartbeat` and
`PROOF.md`. Use only assigned resources and retention authority. New capability,
account/security changes, real charges/postage, external sends, production
and destructive cleanup retain their human gates.

## Closeout and synchronization

When runner profile/authentication, journey revision, proof or activation changes,
update [current status](references/current-status.md) and PR152's description in
the same milestone closeout. Record observed date, exact source, evidence and
remaining gate; include this handoff in the next worker assignment. Preserve
historical results and never promote prepared/offline proof to live acceptance.
This is a closeout responsibility, not a scheduler or automation.
