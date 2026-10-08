# Deploy stamp and verify-after-deploy

## Revision proof

A successful deploy command does not prove that requests observe the new build.
Applications using Workers Cache may serve HTML cached by a previous revision.
Inspect the installed application's cache wrapper and cache key before choosing
a bypass; behavior is application-specific.

One portable pattern is:

1. Bake the exact built commit into the Worker, for example as `DEPLOY_SHA`.
2. Emit a response header such as `x-deploy-sha` from that built artifact. Ensure
   the header represents the content being verified, not merely new middleware
   wrapped around stale content.
3. Pass that commit to the verifier as an expected revision.
4. Poll a known page with a unique query only if the actual cache key retains it.
   Use a bounded timeout (for example 90 seconds), then fail with a diagnostic
   mismatch if the revision never matches.
5. Crawl with the same proven cache-bypass mechanism. Normal visitor caching
   can remain enabled.

Request `Cache-Control` headers alone do not prove a miss in an application that
calls the Workers Cache API. If the application normalizes away the query,
choose a supported bypass or revision-aware key instead. Never weaken access
controls to obtain verification evidence.

## Target SEO checks

Preview should use the project's intended robots and page-level noindex controls.
Those controls discourage indexing; they do not make private previews access
controlled. Honor the project's authentication requirements separately.

Check sitemap locations and canonical origins against the chosen target policy.
When preview renders its own absolute URLs, configure its preview origin rather
than inadvertently emitting production URLs. Production uses its approved
canonical domain and `workers.dev` exposure policy.

## Release evidence

Use an already authorized release to prove the pipeline; do not merge a throwaway
change or deploy solely because this document describes a test. Record the built
commit, CI run, target, revision observed, crawl result and failure/timeout reason.
Both preview and production verification must cover the release commit. Distinguish
local checks, a dry-run, deployment success and observed production behavior.

Use the site's existing route/check inventory and verification commands. Example
names such as `bin/verify-site` are not universal EmDash commands. Preserve the
site's content and publishing authority while verifying it.
