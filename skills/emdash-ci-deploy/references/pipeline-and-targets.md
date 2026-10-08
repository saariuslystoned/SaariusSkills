# Pipeline and targets

Inspect the repository's actual scripts; do not invoke or copy imaginary helpers.
A target manifest (for example `ci/deploy-targets.json`) can define preview and
production Worker names, site origins, domain exposure, and pinned D1/R2/KV
bindings. Keep account identifiers and resource configuration in the appropriate
project configuration, not in reusable skills. Resource creation is a separate
authorized step; a deployment should not guess missing bindings.

## Step dependencies

1. Run the repository's deterministic checks: install from lockfiles, types,
   unit checks, shell checks and any local site verification it requires.
2. Dry-run both target configurations without deployment credentials. This
   verifies build/configuration paths, not live permissions or resource health.
3. Deploy preview, then verify that its revision matches the built commit and
   run the preview site contract.
4. After successful preview checks and any required approval, deploy production.
5. Verify the production revision and run its site contract. A failure must fail
   the release result, even when the deploy command itself succeeded.

Serialize releases per site across the entire deploy-and-verify sequence so a
new deployment cannot replace a revision another release is still verifying.
Preserve repository policy for stale builds and cancellation. Do not cancel a
live deployment unless that operation is explicitly supported and authorized.

## Buildkite and GitHub Actions

Use the project's configured Buildkite agent queue and checkout mechanism.
Dependencies must enforce the sequence above; concurrency groups are site-scoped.
Buildkite's commit identifier can supply the expected revision, but verify that
it identifies the checkout actually built. Do not assume a custom forge checkout
hook exists.

GitHub Actions can implement the same dependency graph with jobs, environment
approvals and concurrency. Verify the built checkout identity, especially for PR
merge refs. Fork/PR checks must not receive production credentials. Use the
repository's approved credential provider and deployment identity; adding this
skill does not authorize installing tokens or changing permissions.

For either CI provider, use existing failure notification routing. A notification
configuration is not authorization to send a new external message during setup.

## Target configuration

Typical target fields include Worker name, site origin, custom domains,
`workers.dev` exposure, and binding names mapped to pinned resource IDs.
Preview and production should not accidentally share mutable resources. Where
sharing is deliberate, document and verify that decision before enabling deploys.

Set `EMDASH_SITE_URL` consistently with the selected target where the application
uses it. Ensure effective Wrangler configuration, the deployed Worker and the
verification base URL all select the same target. Do not treat a successful
credential-free dry-run as evidence that live bindings are correct.
