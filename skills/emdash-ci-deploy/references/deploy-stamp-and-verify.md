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

## Preflight and release safety

Treat the following as release gates, not optional operational advice:

1. Check the deployment credential before running the build or any database
   operation. Keep it restricted to the trusted deployment step.
2. Verify the production build itself before the first deploy. A dev-server
   crawl is insufficient; crawl the built artifact in a production-like
   runtime so bundling failures, such as circular chunks, are exercised.
3. Keep every build and runtime setting in repository configuration. Pin the
   required Node version and declare bindings, domains, site URLs and other
   target variables there. Refuse deployment when the live Worker has settings
   that the file does not declare. Secrets are the exception: they live only in
   the secret store, never in the file, and the repository's deploy notes list
   their names (never values) so a missing one is caught.
4. Before every deploy, diff the expected configuration against Cloudflare.
   Missing Worker, database, bucket, secret or other resources require an
   explicit first-launch decision. Create resources in the same recorded step
   as their IDs, then deploy only from a commit that already contains those
   IDs.
5. Dry-run the exact documented deploy command in CI, or, where deployment is
   run by hand, with the same command and configuration the deployer will run.
   Read the effective
   bindings and domains from its output rather than assuming the configuration
   was honored; deployment tools can create or move resources implicitly.
   Write the exact rollback command, including overrides, before switching a
   domain or Worker address.
6. Before changing or disabling a Worker hostname, search all callers for it.
   Administrative paths must redirect to the approved access login before
   deployment rather than returning the application's own success or denial
   response.
7. Make first-launch setup and seed an explicit ordered step. Use one reset +
   seed operation where appropriate, or complete it before enabling a cron that
   could mutate the database during seeding. Provide a wipe-and-reseed command
   when local `.wrangler/state` can make an empty catalog look like a remote
   data failure. When an EmDash setup screen makes its first user the site's
   administrator, the owner completes it, not an agent. A new database can
   serve a placeholder or "content not available" homepage until that step is
   done, so check the homepage content after it and after every later deploy.
8. Take a named D1 Time Travel restore point before migrations. Rolling back
   code does not roll back database state; include the restore point in the
   deployment request.
9. Read page content, not only status codes. Fail on known error or placeholder
   text, empty lists, and broken navigation links, including encoded-path
   mistakes. Use the site's actual verification inventory rather than
   hard-coding one project's route names.
10. Walk one real user path from entry page through the site's meaningful
    success state. Capture desktop and mobile screenshots and have a person
    inspect them before calling the release done.
11. The deployment request must name configuration values (secret names only,
    never values), migrations,
    setup/seed steps, access status, restore point and proving check. Missing
    any of these means the request is not ready.
12. Tie approval and verification to the exact commit. A merge approval is not
    deployment approval, and a deployment approval lapses if the commit
    changes. The last production crawl that passed for that commit is the
    rollback point.
13. When one change spans services, such as a new claim one service signs and
    another requires, deploy and verify the issuing service first. Deploying the
    consumer first breaks the live path until the issuer catches up.
14. Keep reviews isolated: one agent per branch, small pull requests, and no
    edits while a review is in progress.

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
