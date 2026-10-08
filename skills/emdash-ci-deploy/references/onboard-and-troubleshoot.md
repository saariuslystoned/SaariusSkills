# Onboarding and troubleshooting

## Adapt an existing site

1. Read the site contract, existing CI and deploy configuration. Identify the
   actual local, preview and production verification commands.
2. Map preview and production Workers, domains and resource bindings. Prepare
   configuration changes; obtain applicable authorization before provisioning.
3. Add a built-commit stamp and verifier expectation. Inspect the cache key and
   prove that verification observes the intended build.
4. Wire deterministic checks and credential-free dry-runs before live steps.
   Keep PR and untrusted branch builds restricted to these checks.
5. Wire preview deployment and verification, followed by production approval
   policy, deployment and verification. Serialize the whole release per site.
6. Use the approved secret provider and CI identity. Do not retrieve or install
   secrets as a side effect of documenting the pipeline.
7. Obtain required owner approval for pipeline changes and first live enablement.
   Verify an authorized release and capture its exact revision evidence.

## Deploy succeeds but content looks old

Inspect the observed revision and whether HTML came from an older cache entry.
A request header alone may not bypass Workers Cache. Check whether the chosen
unique query is retained in the cache key, then use the bounded stamp-and-crawl
pattern. Stop on timeout; do not repeatedly redeploy to mask an unexplained cache
or revision mismatch.

## Preview canonical or sitemap origin is wrong

Compare the effective target origin, `EMDASH_SITE_URL` where used, and generated
absolute URLs. Correct the target configuration and run checks again. Do not
change production domains to satisfy a preview assertion.

## Missing or wrong resources

Compare the effective Worker bindings with the approved target manifest. Missing
IDs should fail validation. Prepare the explicit configuration or authorized
resource provisioning needed; do not let the first deployment invent production
bindings. A dry-run still cannot prove remote resources exist or are accessible.

## Pipeline appears green before release verification

Ensure production verification is a dependency of the final success result and
is not allowed to fail softly. Confirm both the expected revision and crawl
result. Preview success and the deployment command's exit code alone do not
establish production success.
