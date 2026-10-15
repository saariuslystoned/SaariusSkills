# Execution plan

## Decisions established for this route

- Start qualification on upstream Crabbox Hetzner Linux; independently qualify Cloudflare Containers. Cloudflare is a preferred possible destination if the real browser and evidence transport work without a provider fork. Parallels remains an upstream-supported option for a genuinely native macOS requirement.
- The application and its hosted services retain their intended Cloudflare runtime. Runner placement is an independent decision.
- Reuse setup and identities. The intended daily operation is one natural-language request followed by an autonomous result. Fresh onboarding is separately required acceptance coverage.
- Use a qualified stable Crabbox release by default. Upgrade main only for an identified upstream feature or fix and record its exact commit. Qualify client, deployed coordinator/runner, browser, and artifact path together.
- Keep this route separate from the existing merchant E2E skill and its source owner.

## Milestone 1: qualify execution before touching a merchant

Use a small public browser fixture with no credentials and no product source. Test creation/reuse of the execution environment; pinned browser installation; external HTTPS navigation; an asserted page result; PNG capture; structured result retrieval; SHA-256 verification; a second execution reusing the prepared dependencies; and owned lease expiry/release behavior. Record any separately qualified trace/PDF/video capability.

Use one short-lived lease per provider with an explicit small instance type, TTL, idle policy, and owner. Do not let a global expensive default choose the experiment's machine size. Check local claims after an ambiguous create; never replay provisioning just because output was lost. Classify a refusal before lease creation separately from a workload failure.

Hetzner uses upstream SSH execution and native artifact retrieval. Cloudflare uses upstream delegated command execution; lack of a desktop feature does not establish that headless Chromium cannot run. The stable adapter may reject SSH-specific capture/download flags. If a qualified route uses ordinary process stdout to return public artifacts, bound encoded size, validate hashes and safe filenames before writing files, reject missing/duplicate chunks, and keep it separate from CLI lifecycle output. Do not enable a private provider API to get around a missing upstream feature.

Promote only the capabilities actually demonstrated twice. A static provider catalog is support evidence, not live readiness. Doctor may pass while an older coordinator rejects the current client's admission protocol. A fixed dependency cache is disposable; a retained merchant account is not.

### Reproduce the public Cloudflare probe

The bundled [probe renderer](../scripts/cloudflare-probe/render_commands.py) embeds only public fixture files, a frozen Playwright lockfile, and a headless browser script. From an isolated proof workspace, render `run1` and `run2` commands into local files. Execute the first command through upstream `crabbox run --provider cloudflare --no-sync --keep --shell` with the enrolled small type, TTL and idle policy. Capture CLI stdout using the calling process's ordinary file redirection, not the unsupported `--capture-stdout` flag. Resolve the exact native lease claim and execute the second command with `--id` on that lease. Do not sync the product checkout.

Use [decode.py](../scripts/cloudflare-probe/decode.py) as `python3 decode.py CAPTURE NEW_OUTPUT_DIR run1` (or `run2`). It validates the fixed artifact names, run identity, ordered chunks, bounded size, SHA-256, PNG header and Playwright trace ZIP before writing the result. Inspect both PNGs and result/trace content. Compare the preparation UUID and versions, then perform only the enrolled exact-lease release. Probe output directories intentionally refuse reuse; a failed attempt remains evidence. A provider status refusal after release does not independently prove remote resource absence.

The probe visits a pinned public upstream file for HTTPS connectivity, then asserts a controlled inline page and button interaction. It has no merchant identity and cannot count as any real-provider merchant acceptance case. Its public network traces are safe only because it never authenticates; do not reuse this capture policy for authenticated merchant traffic.

## Milestone 2: enroll the target once

Create a private, nonsecret profile binding:

- Profile ID, owner, closer, allowed mode, case, and exact target origins.
- Expected EmDash/template and service deployment identities; installed Registry package IDs, versions and official archive/provenance digests. Resolve these freshly; do not copy an old test's frozen candidate version into a newer release check.
- Runner provider, qualified Crabbox version, dependency image/browser versions and one current lease or supported preparation reference.
- Approved credential capability and its authentication/renewal contract, never values. Initial identity bootstrap and recurring authentication are separate proofs.
- Synthetic product/address/merchant aliases, allowed TEST provider operations and any approved email recipient.
- Spend/lifetime limits, proof destination, retention owner and resource teardown authority.

Use the existing owned credential consumer. No credential-store enumeration, account switching, raw secret extraction, or desktop fallback when the unattended broker is unavailable. Missing consumer access is BLOCKED with its exact capability name. Any new deployment, permission, token, or credential enrollment gets its own concrete authority before activation.

Keep secrets and browser session stores out of copied worktrees, artifacts and snapshots. A prepared runner image contains dependencies, not authenticated identities. Use the supported identity/session mechanism within its own trust boundary; do not export a desktop profile to achieve unattended testing.

## Milestone 3: implement the real acceptance journey

Take scenario steps and acceptance criteria from the revision-bound merchant contract. Stable browser assertions use visible roles, labels, URLs and normal app state. CLI/API checks must be existing public/supported product interfaces for that identity; source imports, database edits and custom privileged readiness endpoints are outside the black-box boundary.

Preflight must prove every prerequisite before payment or shipment effects. For each case, record which exact target, release, fixture and identity are in use. Refresh readiness at boundaries where the current service contract requires it. Service health, a displayed version, a quote, a closed403, or a practice PDF cannot replace the required installed/paid/provider outcome.

Follow the same checkout/payment/order/shipment/PDF/tracking identity across the journey. Render and inspect the real provider PDF; assert its expected synthetic fixture and provenance. When a page return fails after payment, preserve the paid order and continue only through supported recovery. Automatic email behavior must be enrolled before the label action, not after.

## Milestone 4: prove a normal rerun

Run the complete authorized case twice without another environment or credential setup. Each run has unique fixture/idempotency identity while retaining the merchant connection. Preserve the first successful order and artifacts. Both runs must independently join the required evidence; a second run cannot borrow the first run's label or payment as its own success.

Record cold preparation time, warm preflight time, each interaction, external-provider waiting, and artifact transfer separately. Report total elapsed time and human interventions. Compare providers on the same assertions and distinguish missing capability from infrastructure or product failure.

## Milestone 5: close and use

The user-facing result gives case, target/release, PASS/FAIL/BLOCKED/UNVERIFIED, first failed boundary, evidence links and next action. Do not turn a failed run into an open-ended repair campaign or silently select a different provider/account. Delegate a concrete defect to its existing source owner, then rerun only after the new revision is explicitly selected.

Required pre-promotion evidence: qualified runner and artifacts; authenticated unattended reuse; the contract's full real-provider journey; separate fresh-install/practice/returning-merchant coverage as required; no unreported human setup on a normal rerun. Until then preserve the route's experimental status.
