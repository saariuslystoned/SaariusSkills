---
name: emdash-ci-deploy
description: Prepare and verify CI deployment pipelines for EmDash Astro sites on Cloudflare Workers, including isolated preview/production targets, commit stamps, cache-aware verification, and Buildkite or GitHub Actions wiring.
---

# EmDash CI Deploy

Use for CI deployment mechanics. Use `emdash-sites` for editable-site and content
ownership decisions, and the site's own verification contract for what must work.
Inspect the current pipeline, Worker configuration, cache behavior and scripts
before drafting changes; example names below are conventions, not installed tools.

## Authority and release order

Preparing a pipeline does not authorize merging it, provisioning resources,
retrieving secrets or deploying. Follow the repository's owner approvals for
pipeline changes and production enablement. An automatic main-branch deployment
chain is appropriate only after the owner has approved that operating policy;
preserve any existing production approval step.

For an authorized release, order dependent steps as:

`verify` → `deploy dry-run` → `deploy preview` → `verify preview` →
`deploy production` → `verify production`.

PRs and untrusted branches run verification and credential-free dry-runs only.
Require pre-deploy checks and preview verification before production deployment.
The production crawl verifies the newly deployed commit afterward; it is the
release success gate, never a prerequisite that prevents deploying its own fix.
A failed verification stops promotion and reports failure; it does not authorize
an automatic rollback, retry loop or further live mutation.

## Target and verification invariants

- Select an explicit preview or production target with distinct Worker names and
  intended resource bindings. Pin resource IDs; refuse missing or mismatched
  bindings rather than silently provisioning during deployment.
- Inject the exact commit being built into the Worker and expose a revision
  response header. Check that revision before the site crawl so cached content
  from an older deployment cannot masquerade as current proof.
- Inspect the application's cache key. A unique query can bypass old entries
  only when that query remains in the key; request `Cache-Control` alone does
  not establish a Workers Cache miss. Bound polling and fail on revision timeout.
- Preview indexing controls, canonical URLs and sitemaps must match the intended
  target. Apply the project's domain and `workers.dev` exposure policy.
- Keep deployment credentials in the approved CI secret provider, available only
  to trusted authorized deployment steps. Never include values in examples,
  logs, artifacts or dry-runs.

## Read next

- [Pipeline and targets](references/pipeline-and-targets.md): step dependencies,
  target configuration and CI-specific wiring.
- [Deploy stamp and verification](references/deploy-stamp-and-verify.md): cache
  behavior, revision checks, SEO checks and bounded evidence.
- [Onboarding and troubleshooting](references/onboard-and-troubleshoot.md):
  adapting an existing site and diagnosing failed gates.
