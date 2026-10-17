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

The x-api Storefront package in [PR723](https://github.com/saari-co/x-api/pull/723)
is an **offline-only preparation surface**. Its exact-source
[operator contract](https://github.com/saari-co/x-api/blob/8ba255dae698208fa3cc78ecc0c264978c71d28f/docs/operations/storefront-port.md)
owns plan/prepare/verify/offline-proof commands. It preserves Storefront's
spec/assertions, overlays env/browser/mail transports, runs one spec with
workers=1/retries=0 and disables auth-bearing traces. It does not launch hosted
Storefront and is not installed as an active CP-1 capability.

Before hosted activation, its owner must bind source/lock/archive/browser hashes,
actual deployment/site identity, explicit target, route/asset allowlists, inbox
posture, proof privacy, budget/lifetime and cleanup. The synthetic allowance
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
