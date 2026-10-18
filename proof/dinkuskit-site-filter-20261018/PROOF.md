# Canonical browser site-list filter

Base: bdd71b7bb1f113a288d12223fccff7a2f26e1e58 (fresh canonical main).
Branch: codex/dinkuskit-site-filter-20261018.

The saved canonical journeys now create their browser pages with an origin
filter. It permits the configured store, DinkusKit.com, Ship, Stripe/Stripe CDN,
and explicitly configured Cloudflare Access origins. Sibling stores, other
Access tenants, lookalikes and non-HTTPS remote origins are refused. Loopback
HTTP is allowed only when explicitly chosen as the store for offline testing.
Media dimensions and query parameters do not affect store-origin admission.

Chromium's Fetch interception checks each request hop, including redirects.
Store credential headers are removed before another allowed origin is contacted;
that origin receives only its own browser cookies. No credentials are added.
Service workers are blocked. Existing direct agent API calls retain their
same-store construction and manual redirect handling. No journey was copied,
no assertion relaxed, and no store/credential/provider setting was changed.

## Proof

- `node --test skills/dinkuskit-live-test/runner/unit/*.test.mjs`: 30 PASS.
  Includes allowed origins, sibling/Access/lookalike denial, variable photo
  sizes, credential header stripping, per-hop checks and one interceptor per
  reused persistent page. Direct link/photo/PDF probes apply the same origin
  rules and follow redirects only after validating the next destination.
- Real installed Chromium, disposable context, two loopback hostnames: a
  photo request with width3471 decoded; a request bearing a synthetic header
  redirected to the off-list hostname and was blocked before any destination
  request. One original browser redirect request and one direct-client redirect request,
  zero off-list requests. The initial
  Playwright route implementation failed this check and was replaced before
  commit; no false-pass evidence is retained as successful proof.
- No live-store request, sign-in, mailbox access, real secret, checkout or label
  was involved. This is filter qualification, not a live journey PASS.

Raw local run: runs/site-filter-runs/20261018/. Unit and browser result hashes
are recorded in verification.json. Normal repository CI/review gates remain;
human merge approval is required.

## Review follow-up

The hashes and browser proof above cover the first revision (9417689) only.
Review then changed the filter: popups, cross-site frames, workers and
WebSockets are checked at the context, store headers are removed from every
non-store request, the run stops early when the store sends visitors to an
Access origin `DINKUS_E2E_ACCESS_ORIGINS` doesn't list, and a Google-only Access
app is documented as unsupported. `review_follow_up` in verification.json
records the changed files' hashes and what was re-run on them: 32 unit tests,
and loopback Chromium checks that an off-list host gets nothing from a main-page
redirect, a cross-site frame's fetch or image, a worker, a WebSocket or a popup,
and that a context-level `CF-Access-Client-Secret` never reaches a frame's host.
Two gaps remain and are in the README: a redirect inside a cross-site frame and
a popup's first redirect still reach an off-list host. No live store was used.

