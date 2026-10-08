# Cloudflare Hosting

Verify the target's resolved versions and chosen authentication mode. Adapter configuration,
bindings and deployment targets are documented upstream in
`building-emdash-site` (`references/configuration.md` in the vendored mirror);
this reference keeps the judgment. Use the target project's supported Cloudflare tools for platform operations;
this guidance grants no live authority.

## Initialize content deliberately

A successful deployment does not establish that the CMS has content. Inspect
the project's setup wizard, CLI, seed application and deployment scripts to
identify when initialization actually occurs. Smoke the built Worker on the
matching runtime against a fresh isolated D1 database before a live deployment.
Then separately prove the initialized CMS and publish flow.

For a starter landing page, an explicit seed fallback may be appropriate before
setup. Make that a product choice with a defined end condition, not the default
response to every missing CMS entry. Once initialized, deleted, unpublished,
unauthorized or wrong-locale content must not reappear from seed data. A database
failure must not silently masquerade as an empty first install.

Expose a non-sensitive content-source marker in proof where useful, and verify
the transition from starter content to published CMS content. Use the pinned
upstream rendering and safe-link interfaces, with site-specific components where
needed, rather than reintroducing retired block dependencies.

## Protect the intended routes

[EmDash authentication guidance](https://docs.emdashcms.com/guides/authentication/)
distinguishes normal EmDash login providers from Cloudflare Access authentication.
Choose the appropriate mode explicitly; Access is not mandatory for every site.
For Access deployments, restrict initial provisioning to the intended owner:
the first provisioned user becomes Admin. Verify later users receive their
intended roles and that setup cannot be taken over after initialization.

Build a route inventory before adding an outer guard: admin/setup, authenticated
API surfaces, authentication callbacks, public content, plugin endpoints and
provider webhooks. For Access, gate admin, setup and authenticated APIs on every
hostname (workers.dev, apex and www) before DNS points at the Worker. Anonymous
requests must be redirected to login or denied, never shown an open setup page.
Do not prescribe 404 for every `/_emdash` path: [plugin
routes](https://docs.emdashcms.com/plugins/creating-plugins/api-routes/) and
provider webhooks can intentionally be public. Keep an explicit inventory of
those exact-path exceptions, each with its own validation/signature rules, not
a broad API bypass. Access is one auth mode, not mandatory. Prove anonymous
admin denial, authorized editor access and the intended public/callback
behavior.

## Match the deployed runtime

Use the environment-loading API the installed adapter supports (the
`cloudflare:workers` module in current adapters); do not hide an obsolete
accessor behind a catch that turns configuration errors into unexplained
404s. Keep build-time and runtime auth configuration consistent. Diagnose with
non-sensitive stage/error categories, never credential values.

[Dynamic Workers pricing](https://developers.cloudflare.com/dynamic-workers/pricing/)
currently requires a Workers Paid plan. Verify current platform entitlement and
runner availability before promising Registry installation. If sandboxed plugins
are required, removing the runner or executing them natively does not satisfy
the requirement. Report the exact hosting decision; do not purchase or downgrade
capabilities by inference. Inventory generated bindings and resources before an
authorized deploy rather than assuming automatic provisioning is harmless.

## Configuration and deployment proof

Follow the target repo's classification of identifiers and production config.
Keep secret values out of source, command arguments, shell history, logs and
proof. Use approved secret injection; an ignored file or `printf` command alone
does not establish safe handling. If generating deployment configuration, verify
the effective result without exposing secrets. Audit proof and ledger content
too: allow legitimate non-secret identifiers narrowly, never exempt whole proof
directories from secret checks. A login redirect parameter is not a substitute
for verified application configuration and JWT signature/issuer/audience checks.

Within existing scoped approval, order work so dependencies are verified before
use: local fresh-database smoke, required storage, protected hosting/auth
configuration, deployment, domain routing, authorized setup, then CMS publishing.
Ask only for actions outside that approval; do not require a new confirmation
for each already-authorized substep. Never leave bootstrap exposed during staging.

Record candidate/build and deployment identities alongside sanitized screenshots.
Use the approved evidence destination; neither private asset uploads nor keeping
all captures out of Git is universal policy. For viewport/theme capture failures,
use supported browser emulation and verify the resulting dimensions/theme.

Test origin behavior, TLS/Host routing and DNS resolution separately. Public
resolvers or a controlled `curl --resolve` check can distinguish a stale local
resolver from a deployment defect; neither alone proves every user's DNS works.
Treat port hopping, daemon behavior and missing dev logs as version-specific
observations. Read the actual listening address and confirm the intended process
serves it before capturing proof.
