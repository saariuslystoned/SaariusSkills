# Blackbox route and Cloudflare runner qualification

Status: synthetic runner qualified; authenticated merchant acceptance UNVERIFIED.
Branch: `codex/dinkuskit-e2e-blackbox-20261015`.
Fresh remote base: `cf3ccf3f9c0a7d83644e56505c5e9bdd853f23c1`.

## Result

Added a separate discoverable `dinkuskit-e2e-blackbox` skill, execution plan,
qualification ledger, and reproducible public Cloudflare browser probe. The
existing merchant-contract proposal [PR135](https://github.com/saariuslystoned/SaariusSkills/pull/135)
is a dependency; none of its files or ownership changed. Ordinary reruns reuse
the enrolled environment and identity; new-install/onboarding remains separate.

Upstream Crabbox0.78.0 was installed with its runtime pack and the previous
installation retained. Both provider doctors passed. The first actual Hetzner
admission was refused before lease creation because the configured older
coordinator lacks the current run-admission endpoint (HTTP404). No Hetzner VM
or workload was created. The result does not authorize a shared coordinator
upgrade or authentication fallback.

The independent Cloudflare experiment used the existing delegated runner and
only public fixtures, without product source sync, merchant identity or
explicit provider-secret forwarding. Two fresh Chromium156 browser processes
passed controlled heading/button assertions and external HTTPS200 on the same
prepared Linux lease. Playwright was pinned to1.64.1. Both results, PNGs and
trace ZIPs returned through supported process stdout with verified sizes and
SHA-256. Images were visually inspected and traces passed ZIP/event-stream
inspection. The final two-browser command took6.68s; first dependency preparation
took84.1s. This is a warm synthetic probe, not a merchant runtime benchmark.

Initial failures are preserved: a missing output parent directory, followed by
an assertion against a third-party page whose DOM had changed. The bounded final
correction uses an owned deterministic fixture and a pinned public upstream
source URL for connectivity. A pre-execution rejection also established that
the stable Cloudflare adapter does not support `--capture-stdout`; ordinary
subprocess stdout capture was used instead. No provider fork/private API.

The exact disposable lease's native stop returned0 and retired its local claim.
Subsequent status refusal is not independent proof of remote resource absence.
The deployed runner commit/image provenance and its binding to the intended
dedicated test account remain UNVERIFIED. Merchant authentication, unattended
renewal, and real payment-to-shipment acceptance also remain UNVERIFIED.

The requested Browser Run follow-up stopped at credential preflight. The
inspected capability registry has no approved fixed consumer for Browser Run;
the delegated container bearer is not Browser Run API authority. No managed
browser, new lease, authentication attempt or credential change occurred. This
does not prove that the intended Cloudflare account lacks access to Browser Run.

## Artifact identities

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Run1 PNG | 40,281 | `d6febb5d4439d4acb0841ee8c518431e9c471e914bd203b7370305ea4622f7b7` |
| Run2 PNG | 40,281 | `d6febb5d4439d4acb0841ee8c518431e9c471e914bd203b7370305ea4622f7b7` |
| Run1 trace | 198,429 | `bee07210ffa02d09bc58f50e26b6a05a845ab4d7b8def7a0b84c7bb1b279ca01` |
| Run2 trace | 176,435 | `2972ef95ed5541fa36544df33e011a22f426ee7759bedfa938711aebdc148201` |
| Run1 JSON | 745 | `4ec95551219e9cac1d798abfcda586d3ebaee92cc80adc997eca6115a9781364` |
| Run2 JSON | 745 | `e05c50993809b67af477e45c837a03b9e2f69d5afa3263a8af560054b1d27e87` |

Raw public artifacts and lifecycle receipts remain in the private task proof
packet. No screenshots, traces, raw stdout, account identities, session data,
or credentials are committed. On October15 Bobby assigned
`saari-co/public-oss-proof-assets` as this repository's PR-media shelf for the
required review preflight. This change performs no media publication.

## Verification

- Skill Creator quick validator: PASS using an existing Python with PyYAML.
- Repository suite before adding the artifact codec:177 tests PASS.
- Final packaging suite:21 tests PASS.
- Artifact integrity suite:6 tests PASS, including multichunk byte preservation,
  truncation, reordering, identity/hash mismatch, missing passing artifacts,
  unexpected paths, oversized records, ZIP expansion limits and existing-output preservation.
- The packaged decoder adds a bounded line reader and rejects over1,024 ZIP
  entries, over16MiB expanded per entry or over64MiB expanded in total before
  decompression. Replaying both real public
  captures through those final decoder bytes produced PASS and the exact hashes
  above, without another remote workload.
- Node syntax, shell syntax, local links, portable identity/path privacy and
  `git diff --check`: PASS. Final CI and exact-head review are recorded on the PR.
- This repository has no root `package.json`/`skills:check` script; native
  packaging/unit validation is used instead of claiming that npm command ran.

No full provider E2E success, persistent authentication, dedicated account
enrollment, production rollout, account/security change, merge or external send
is claimed. The next implementation gate is the enrolled target and supported
unattended merchant authentication, followed by the real acceptance contract.

## Review disposition

Comprehensive exact-head Spark/OpenClaw review of
`3bb0c7cae9bc0be1ccb9d006c1e8f354fb52fb84` reported one P2: trace ZIP expansion
was not bounded before `testzip()`. Disposition: `required_fix`. Added per-entry,
aggregate and entry-count checks before decompression, a regression proving
over-limit archives never reach decompression or create output, and replayed
both actual public captures with matching hashes. The repaired source requires
its own exact-head review; the earlier finding is not a clean verdict.
