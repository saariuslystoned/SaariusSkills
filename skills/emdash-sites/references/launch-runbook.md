# CMS Launch Runbook

Apply these checks to the resolved version and the site's route/auth decisions.
This runbook does not authorize deployment.

## Routes and menus

- Set `urlPattern` on every collection. Without it, EmDash uses
  `/{collection}/{slug}`, so `pages` appear as `/pages/<slug>` in admin view
  links and per-collection sitemaps. Match the real route, verify the admin
  view link returns 200, and add a 301 from `/{collection}/*` as a safety net.
- For editor-owned navigation, use EmDash menus. Each header, footer, and mobile nav
  calls `getMenu()`. Declare menus and content-entry items in `seed/seed.json`
  `menus[]`; bootstrap creates missing menus only. Never overwrite or reorder
  an existing menu: the owner owns it. A cold-start code fallback must be
  marked `data-nav-source="cms"|"fallback"`, and the project's navigation check fails when a
  rendered editor-owned nav has no CMS menu. Link every important page from the homepage.
- Keep page slugs flat: never put `/` in a slug. EmDash URL-encodes that slash
  as `%2F` when resolving menu page references and sitemap URLs under a
  `/{slug}` pattern. Express hierarchy with a collection pattern such as
  `/products/{slug}` and catch the error with the full-link crawl in
  [the verification contract](verification.md).

## Initialization and identities

- Generate `EMDASH_ENCRYPTION_KEY` with `emdash secrets generate`; hand-made
  values are rejected as malformed. Use a separate key per environment.
- A service token needs its own Access policy with decision `non_identity`;
  `allow` redirects service-token requests to login. Poll after create/rotate
  because propagation takes seconds. The JWT `common_name` is the client ID.
  Keep machine client IDs in a separate site-guard allowlist from human
  operators, and use the project's approved secret lifecycle.
- When explicitly authorized for the source and destination, a set-up preview
  D1 may be copied into an empty production destination to carry setup and the
  first admin across. Follow the version-matched [backup and recovery
  procedure](https://docs.emdashcms.com/guides/backups/), including D1 export
  limits and restore order; never import a dump over a populated live database.
  Database exports omit media binaries and runtime encryption keys. Transfer
  media separately and verify it alongside content and sign-in.
- With separate environment keys, copied encrypted plugin settings cannot be
  read using only the destination key. Plan an approved, version-supported
  key/re-encryption migration or credential replacement before the copy. The
  [secrets guidance](https://docs.emdashcms.com/deployment/secrets/) describes
  retaining referenced old keys while re-saving settings under the new key;
  verify integrations with only the destination key before retiring old keys.
  Keep key backups and transfers in approved secret facilities, never in source
  or proof. Re-verify runtime initialization; never hand-insert system `options`
  or `users` rows.

## Access boundary

Access is one auth mode, not mandatory. When selected, gate admin, setup, and
authenticated API surfaces on workers.dev, apex, and www before DNS cutover.
Keep an explicit inventory of reviewed public plugin routes and provider
webhooks; only exact paths bypass the outer gate, and each has its own
signature/validation. Never use a broad `/_emdash/api/*` bypass or leave setup
open.

## Troubleshooting and cutover

- If `/_emdash/api/*` returns 500 `NOT_CONFIGURED` ("EmDash is not
  initialized"), including in the wizard, runtime initialization threw.
  Middleware logs `EmDash middleware error:` and continues without
  `locals.emdash`, so some routes can misleadingly answer. Run
  `wrangler tail` while requesting setup status and do not claim the wizard
  fixes it unless setup status returns 200.
- Never partially reset D1. Deleted rows with migration tables retained can
  cause `no result at findActivation / advanceMediaUsageActivation`. Dropping
  all tables or recreating D1 is a shortcut only for an explicitly disposable,
  isolated database, with approval for that exact target. For a populated or
  live database, stop destructive work until a restorable database backup or
  recovery point, matching media and keys, a verified recovery plan, and approval for the exact database,
  environment, and operation exist. Follow the [recovery
  guidance](https://docs.emdashcms.com/guides/backups/) and verify an isolated
  restore before controlled cutover; an EmDash JSON backup is not restorable.
- Before DNS cutover, record current apex/www records for rollback. Leave
  MX, SPF, DKIM, DMARC, and other TXT records untouched. Verify every page
  returns 200 with the CMS marker, nav links resolve, sitemap/robots/canonical
  output is correct, the single-host redirect works, and anonymous admin is
  denied.
- For a migrated domain, find old URLs in its sitemap, analytics, or search
  console before adding 301s. Do not assume subpages existed.
