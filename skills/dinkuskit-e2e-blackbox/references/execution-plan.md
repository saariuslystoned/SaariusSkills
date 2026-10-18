# Execution and admission

Read [current status](current-status.md) first. Source/identity changes require
fresh proof; this procedure does not activate a capability or grant spend.

## Routine synthetic fixture

The selected route is Chromium/Playwright inside upstream Crabbox Cloudflare,
through the enrolled CP-1 fixed consumer. The runner manages disposable compute
under its own admission and lifecycle contract. The synthetic developer fixture
ships a reviewed, pinned source/test bundle and builds it; it is not a
source-inaccessible product acceptance run. The independent validator is
source-blind. Never copy host credentials or desktop browser profiles.

Before invoking, inspect the existing consumer's preflight and sanitized state
evidence for policy, expiry, request ledger and fixed profile binding. Confirm this is the synthetic case
already admitted, not hosted Storefront or Buy and ship. Choose one stable
request ID, record it in task state, then use the selected facade **on CP-1**:

```sh
/Users/cp-1/Developer/worktrees/x-api-routine-fixture-f3075215-20261017/bin/smoky runner-e2e campaign --execute --no-input --json --request-id <stable-id>
```

That observed checkout is at `f3075215452f70bc6410d3191fd09d4fbcf4876d`.
Reconfirm the active profile/source before future use; do not silently select
an arbitrary checkout. The existing unattended service-account consumer owns
credential resolution. No bare `op`, operator-shell bootstrap, copied env,
credential-store inspection or manual account fallback belongs in this flow.

On duplicate identical input, reuse the same ID and consume the existing
receipt. If output is lost, execution fails or lease creation is uncertain,
inspect that ID's receipt/ledger/lifecycle before further action. Never create
a new ID to bypass the outcome, reservation or refusal. A changed request needs
its own admission; an expired policy needs its owner, not an invented allowance.

Collect original reports/screenshots and verify artifact sizes/hashes. Inspect
relevant images; receipt prose alone is insufficient. Separate preparation,
smoke, journey and total times. Record exact lease stop and
`provider_absence_verified` independently. Neither a reservation nor runtime
stop proves actual billing.

## Canonical journeys and prepared Storefront

`dinkuskit-live-test` owns journey semantics. Select its immutable revision,
explicit spec, original assertions/proof helpers and package lock. Retain hashes
and identify each reviewed transport override; do not rewrite the journeys here
or relax failing assertions. Preserve fresh shopper, returning merchant and
new-installation distinctions, and each journey's hard/soft step behavior.

The x-api Storefront package introduced in [PR723](https://github.com/saari-co/x-api/pull/723)
remains an **offline-only preparation surface**. Its refreshed exact-source
[operator contract](https://github.com/saari-co/x-api/blob/6f64659d083c9343fcb8556efb65b2d58e5ba8a7/docs/operations/storefront-port.md)
owns plan/prepare/verify/offline-proof commands. It preserves Storefront's
spec/assertions, overlays env/browser/mail transports, runs one spec with
workers=1/retries=0 and disables auth-bearing traces. It does not itself launch hosted
Storefront; the fixed caller has a separate activation and admission boundary.

PR723 merged this inactive helper under the owned Smoky CLI; SaariusSkills
owns canonical assertions and upstream Crabbox owns lifecycle. PR724 adds the
separate fixed public-beta caller; PR725 refreshes its canonical pin/helper
closure. Source qualification alone is not activation or a passing hosted run. The
first admitted caller execution and genuine product FAIL are dated in current
status. Select a reviewed exact source only through the existing
consumer/lifecycle/exporter and separate admission.

Before hosted activation, its owner must bind source/lock/archive/browser hashes,
account/Worker/version/origin, explicit target, route/asset allowlists, inbox
posture, proof privacy, budget/lifetime and cleanup. Internal `site_id` is
optional for Storefront because the canonical journey does not read it.
Record configured source pin and observed deployment-trigger provenance
separately; neither alone proves compiled source. Keep unknowns explicit. The synthetic allowance
does not cover this new capability. Keep v2 and beta separate; never substitute
a public origin to get past Access.

Public beta needs no inbox only if all required routes are proved public under
explicit admission. Any authentication redirect fails that mode. The v2 Access
path requires a qualified read-only inbox consumer; the prepared adapter fails
closed. Never inherit a host mail command or saved browser session. Linux PDF
support is a later Buy and ship gate, not a Storefront prerequisite.

For a future paid TEST journey, preflight current packages, TEST mode, provider
readiness, approved sandbox recipient and automatic email effects before the
dependent operation. Follow canonical existing-order/finish behavior after
payment; join checkout, order, label, PDF, tracking and completion for that same
identity. A fixture, quote or practice label cannot replace a provider result.

## Failure and remaining-slot handling

Report a genuine hosted product FAIL separately from a failed runner, the
synthetic fixture result and a canonical SKIP. Preserve the original failure
report, source/pair/target binding and terminal lease evidence while the owner
repairs the identified product or deployment boundary. A repaired image or
saved draft is not proof that the full journey passes.

When dashboard trigger metadata and behavior disagree, inspect the effective
build pin and deployed version through the existing owner before proposing
another product-code fix. A build attempt, local build or trigger label cannot
prove a successful deployment or page publication.

If a deployment changes the target version, do not reuse the old remaining-slot
admission or mint a fresh unlinked request to bypass it. Preserve the original
policy, ledger row, failed receipt, terminal lease and absolute batch allowance.
Any explicitly approved transfer must bind the old and new target generations
through reviewed source and current activation; a pending PR is insufficient.
Use the existing consumer/lifecycle/exporter, not a new runner or ledger reset.

## Shared-store batch discipline

- Run the same canonical tests locally, then in Cloudflare. Keep the selected
  assertions and helper closure unchanged across both; a local pass is not a
  Cloudflare pass.
- Use the shared authenticated beta store one run at a time. Freeze the latest
  published beta pair and its verified installed identities for the whole batch.
  If a required beta is unpublished or the installed pair differs, report that
  readiness gap before execution rather than substitute a stable release.
- Reuse persistent authentication and connections through their owned consumers;
  do not recreate accounts/connections or export credentials for each run.
- Isolate each run's data and leave existing records untouched. Save proof before
  cleaning only that run's passing data within its authorized scope. Retain
  failing data until the fix is verified. Read-only Storefront creates no
  business records to clean up.
- Count failed reviews across the assigned task. After the **second failed
  review total**, stop and return the concrete issue plus a recommendation.
  This is not permission for two additional repair cycles.

## Historical public probe

The bundled `scripts/cloudflare-probe/` files preserve the October 15 public
qualification with frozen Playwright dependencies. They do not implement the
current fixture campaign or a merchant journey. Reuse needs its own assigned
public-probe case and current admission, not a routine campaign fallback.

`render_commands.py` renders public-only `run1`/`run2` shell inputs for upstream
Crabbox `--no-sync --shell`. The first prepared a disposable environment; the
second used its exact lease. Ordinary subprocess stdout carried artifacts
because that stable adapter rejected native capture/download flags.
`decode.py CAPTURE NEW_OUTPUT_DIR run1` (or `run2`) validates fixed filenames,
identity, ordered chunks, sizes/hashes, PNG headers and bounded trace ZIPs before
writing. Output directories refuse reuse. These traces contain only public
synthetic traffic; never apply that capture policy to authenticated journeys.
See [qualification](qualification.md) for the original results and limits.
