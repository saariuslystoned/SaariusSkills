---
name: emdash-sites
description: Build and verify EmDash sites, templates, and plugins. Use for Registry readiness, Block Kit versus native React, Kumo/Lingui admin UX, CMS publishing and content ownership, Cloudflare hosting, block migration, or connected commerce services. Does not authorize deployment or publishing.
---

# EmDash Sites And Plugins

Deliver EmDash experiences through real runtime paths. A rendered page,
installed plugin, editable CMS, and published service are separate claims.

## Mechanics live upstream

EmDash release skills define mechanics; this skill defines decisions and
proof. The companion skills are packaged alongside this one:
`building-emdash-site`, `creating-plugins`, `emdash-cli`, `upgrading-emdash`.
The project's resolved package version takes priority over the bundled pin.
Read these corrections before copying examples from that pin:
- For draft-only permissions, CLI create/update must pass `--draft`; publishing
  stays with the authorized human.
  Updates without revisions write live; require revision capability plus `_rev`
  (`references/content-ownership.md`).
- Route handlers: sandboxed handlers require `async (routeCtx, ctx)` with input
  from `routeCtx.input` and storage from `ctx.kv`/`ctx.storage`. Native handlers
  receive one combined context `async (ctx)` reading `ctx.input` and `ctx.storage`
  (`references/plugin-surfaces.md`).
- Email deliver hook: `email:deliver` requires configured verified sender `from`,
  verifies HTTP `response.ok`, and throws sanitized errors without leaking body,
  tokens, or addresses (`references/plugin-surfaces.md`).

## Establish the slice

1. Read target repo instructions and decision records. Confirm source owner,
   branch/worktree, requested behavior, and authorization. Reuse progressing
   work; avoid competing writers.
2. Identify required surfaces: public site/theme, native plugin, sandboxed
   Registry plugin, or external service. If Registry support is needed, include
   sandbox installation and admin paths from the start.
3. Inspect resolved EmDash/package versions, host adapter, runner, persistence,
   and content. Consult shelf corrections in `references/plugin-surfaces.md`
   and `references/content-ownership.md` before copying upstream mechanics; an
   old pin is not a recommendation, and dependency bumps migrate no content.
4. Validate sandbox packages before implementation. Record baseline sizes and
   headroom using the pinned packager (see [plugin surfaces](references/plugin-surfaces.md)).
5. Define one observable user outcome and the evidence that will establish it.
   Resolve only missing decisions that block that outcome; keep optional work
   outside its completion criteria.

## Choose the supported surface

| Need | Implementation direction | Evidence required |
| --- | --- | --- |
| Registry-installed admin feature | Sandboxed plugin with Block Kit UI | Actual packaged install, configured runner, user action and durable result |
| Native admin integration | Supported React or Block Kit extension; Kumo and Lingui for native React | Real host navigation, authorization, form/error behavior and locale/layout proof |
| Editable public pages | Upstream content/page blocks plus site rendering; declare content ownership; normally the CMS owns content and the repository owns structure | Editor save/publish and the public page; the live content-source marker; the mirrored record when configured |
| Connected service | Server-owned identity, scoped authorization and transport | Actual installed-plugin request and service result; fixtures labeled separately |
| Cloudflare-hosted site | Version-matched Workers adapter, explicit content initialization and chosen auth mode | Fresh-database smoke, protected admin, intended public routes and published CMS content |

For commerce, read [URLs and commerce](references/urls-and-commerce.md).
Agree on the [verification scope](references/verification.md) before deployment.
Prefer supported site-level workarounds to patching generated framework bundles.

Read only the references needed for the slice:

- [Plugin surfaces and admin UX judgment](references/plugin-surfaces.md):
  Registry column, native admin UX, mounting capabilities, and pinned upstream
  corrections (route handler signatures and email transport verification).
- [Sites, migrations, and demos](references/site-proof.md): editable CMS proof,
  content migration, matched artifacts, and deployable output.
- [Content ownership and the mirror](references/content-ownership.md): who
  owns content and media once the CMS is live, the event-driven mirror,
  agents draft and humans publish.
- [Service connection diagnosis](references/service-connections.md): identity,
  transport, request tracing, test boundaries, and persistence.
- [Commerce behavior proof](references/commerce-proof.md): payments, stock,
  shipping, and truthful completion states.
- [Cloudflare hosting](references/cloudflare-hosting.md): content
  initialization, Access boundaries, the route inventory, deployment and
  DNS evidence.
- [CMS launch runbook](references/launch-runbook.md): URL patterns, owned
  menus, first setup, Access machine identities, troubleshooting, cutover,
  and migrated-domain links.
- [Site verification](references/verification.md): route inventory, repeatable
  checks, environment-specific expectations, and deployment evidence.
- [URLs and commerce](references/urls-and-commerce.md): EmDash URL constraints,
  SEO canonicals, product identity/data, feeds, policies, redirects, and
  channel compliance.

## Implement and prove

Apply this guidance through the active harness's tools and skill discovery;
repository instructions and proof scripts are canonical. Use requested
tools, verify model, permissions and path, and report unavailable
capabilities rather than inferring expanded access.

Use the real host early and mount authorized handlers and storage with the
page. Before polishing a plugin, prove package → installation → authorized
navigation → handler → canonical storage → rendered result, with sanitized
screenshots and persisted state (read-only features need not invent writes).
HTTP 200 and component tests alone do not prove success. For defects,
capture one failing stage, repair the proven cause, and repeat behavior with
regression evidence.

## Close out precisely

Report source revisions, package digest, resolved toolchain, host, proof
commands, result, evidence, and omitted surfaces. Revalidate after changes
affecting the packaged artifact; predecessor captures do not prove a new build.
Distinguish fixture, local, hosted, and production proof. Stop when agreed
outcomes and required checks are satisfied.

Use the repository's required review path on the frozen candidate. A dispatched
review is not completed review evidence; a merge is not deployment, Registry
publication, or a successful transaction. Honor existing scoped approvals
without asking again, and do not extend them to new live actions.

This skill owns EmDash implementation judgment. Follow the target project's
worktree, review, credentials, and deployment contracts. It grants no authority
to merge, publish, deploy, provision accounts, spend, or retrieve secrets.
