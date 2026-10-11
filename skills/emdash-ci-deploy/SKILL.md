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

## Must-do release checks

Before a first or changed deployment:

- Check the deployment token before spending time on builds or database work.
- Compare repository configuration and the live target: runtime settings,
  domains, bindings and resource IDs must be declared and present. Secrets are
  the exception: they live only in the secret store, and the repository lists
  their names, never their values. Missing resources are an explicit first-launch/provisioning decision, not a reason to
  let deployment invent them.
- Dry-run the exact documented deploy command (in CI, or with the same command
  and config the deployer will run) and inspect its effective
  bindings and domains. Record the exact rollback command, including overrides,
  before changing a domain or address.
- Search every caller before changing or disabling a Worker hostname. Put
  authentication in front of administrative paths before deployment.
- Write setup and seed as one ordered first-launch step, protect migrations with
  a named database restore point, and deploy only from a commit that already
  contains any newly created resource IDs. When the first person through a setup
  screen becomes the site's administrator, the owner does that step, not an agent.
- When a change adds a value one service issues and another requires, deploy the
  issuing service first and check it before deploying the one that requires it.
- Prove the built artifact with a production crawl, page-content checks and one
  real user path on desktop and mobile. A merge approval is not deployment
  approval; deployment approval applies to the exact commit and expires when it
  changes.

See [Deploy stamp and verification](references/deploy-stamp-and-verify.md) for
the complete release checklist, evidence requirements and local-state recovery
guidance.

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
