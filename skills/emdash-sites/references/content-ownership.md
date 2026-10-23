# Content Ownership And Draft Safety

Declare the owner of each kind of data before building a synchronization path.
For an editable CMS site, content normally belongs to the CMS after bootstrap;
components, block schemas and deployment configuration belong to the repository.
An editor's published changes must survive the next deployment. An empty local
seed render does not prove what the live CMS serves: inspect a non-sensitive
content-source marker or compare the actual persisted record.

Two writers of the same copy with no declared winner fail in both directions.
If the seed changes in the repository but not in the CMS, the live site keeps
the old copy while every check that renders the seed fallback on an empty
database still passes. If a seed-to-CMS sync fixes that, every admin edit loses
on the next run; editors who publish expect the change to persist. Decide per
kind before building either path:

- **Content** belongs to the CMS: an edit published in the admin is live and
  stays. After the one-time bootstrap nothing writes copy from the seed into the
  CMS. A sync that only writes block types is fine.
- **Structure** (block types, components, image slugs, the Worker) belongs to
  the repository and ships by deploy. Removing a select option is a breaking
  block-type change: a new version is created or reused, then activated, and
  entries migrate with `migrateBlocks`.
- **The record** follows content: the site mirrors itself into the repository,
  not the other way round.

## Optional repository mirror

If the project requires a repository copy of published content, mirror from the
CMS to the repository, rather than overwriting editor changes from seed files.
Cover every supported publish/unpublish/restore/delete path, including scheduled
publishes. Event-driven mirroring avoids waiting for the next scheduled poll;
a manual read-only comparison provides a recovery check.

Trigger the mirror from the requests that change what is live (publish,
unpublish, restore, trash, permanent delete, the visual-editing toolbar's
publish), after the response is sent (`waitUntil`). A scheduled publish fires
from the cron, not a request: hook the scheduled handler or record that limit.
Rebuild the seed from live rows (EmDash keeps a collection's live data in
`ec_<collection>`, one column per field; drafts live in revisions), on top of
the default branch, and open or update one labelled pull request. Close it when
live content returns to what the branch already holds.

Keep draft data out of public mirrors. Use least-privilege repository access and
an explicit review/merge policy: the mirror's token may push a branch and open
or update a pull request, never merge. If the project authorizes auto-merge,
limit it to pull requests that change only the seed file and let a required
status check decide, so a published edit that breaks a content rule stays open
and red instead of failing silently or blocking the editor. Report failures
through an independently working channel under the project's notification
authorization (for example an email binding, not an issue in the repository the
mirror writes to). Run the mirror only when both its token and that channel are
configured; otherwise log what is missing and do nothing. Do not introduce
sends, auto-merge or background writers merely by selecting this design.
Session startup can run a read-only comparison; it does not authorize pushes or
PR mutations.

Prove a local publish-to-mirror round trip, stale-state detection and a forced
failure notification with test substitutes before authorized live verification.
After the owner's gates are in place (token, merge policy, required check,
notification channel), record one real edit and one forced failure in
production with the deployed identity.

## Agent drafts and human publishing

When the project's permission boundary is draft-only, restrict machine identities
to reading and staging drafts. Do not allow publishing, scheduling, deletion,
schema mutation, edit-lock overrides or live metadata writes through the draft
path. A `status` field on save can change live publication state and is not a
safe draft field: `status: "draft"` on a published page unpublishes it.

Give CMS bots two identities, each with its own access policy and allowlist: an
author-level token (EmDash role 30) for everything, so work starts as a draft,
and a separate editor-level token (role 40, can publish and edit menus) used
only when the owner explicitly asks for a specific publish. A publish mode must
name pages one by one and dry-run first. That exception does not cover
unpublishing, scheduling, deletion, schema writes or edit-lock overrides; each
needs its own explicit authorization.

At the bundled EmDash skill pin, CLI `create` and `update` automatically issue a
follow-up publish call unless `--draft` is supplied. Always use `--draft` for a
draft-only interaction. However, **`--draft` does not isolate unversioned writes**:

- `packages/core/src/cli/commands/content.ts` calls `client.update(data, _rev)`
  before considering publication.
- `packages/core/src/database/repositories/content.ts` updates the live collection
  table directly when the collection's `supports` excludes `revisions`.
- A draft-only update therefore requires revision support, the current `_rev`
  concurrency token (so stale writes answer 409), and CLI `--draft` when using
  the CLI. Reject a non-revision collection update unless existing explicit
  live-content authorization covers it.
- A direct API call that omits publish still has the same revision-isolation
  requirement. Verify the resolved implementation before relying on a newer version.

EmDash roles have no edit-without-publish tier, and API tokens belong to the
user who creates them, so enforce the permission boundary in the site's own
route and body validation. Return preview and admin links for review; the human
edits in the editor and publishes. Do not confuse a saved draft with published
content.

## Editable images

The admin is the editor's whole view of the site: anything a visitor sees that
the editor cannot find there reads as broken and cannot be changed. Prefer the
Media Library for images editors need to change. Uploads go to the storage
adapter (R2 on Cloudflare); store references in `image` fields, use
`darkVariant` for paired images where supported, and serve them from
`/_emdash/api/media/file/<key>` or the storage's configured public URL. Verify
that serving path stays public (`GET`/`HEAD` on `/_emdash/api/media/file/<safe-key>`)
through the selected auth boundary: a blanket 404 or Access challenge over all
`/_emdash/*` paths breaks every Media Library image and `getSiteSettings()`
logo/favicon on the public site. Bootstrap media explicitly in `seed/seed.json`
via `$media` so a clean install starts complete. When an Access-gated site
intentionally denies anonymous `/_emdash/api/media/file/*` on public production,
have its authenticated import script (`POST /_emdash/api/media` with
`deduplicate=true` and `alt`) register the repository's 2D `.webp` brand/poster
assets into `/_emdash/admin` Media Library (deduplicated by SHA-1
`contentHash`) while public templates continue to render static `/brand/*.webp`.
Static repository assets remain appropriate for deliberately code-owned imagery
and runtime binary assets (such as 3D glTF `.glb` models in `public/models/...`,
which EmDash's upload allowlist and inline media responder do not serve inline);
pair every 3D `.glb` stage with a 2D `.webp` fallback poster in the Media
Library (kept visible until the `.glb` finishes loading in `onModelLoaded`) and
record that split rather than leaving an apparently editable page with an
unexplained empty Media Library.

Keep alt text, dimensions and any required provenance checks with the media
workflow; when imagery moves into the library, move those rules to a check on
the library and the human upload rather than dropping them. For sites hosted on
Cloudflare that use Cloudflare Images (`imagedelivery.net`), register the
first-party `cloudflareImages({})` provider from `@emdash-cms/cloudflare`
(`emdash({ mediaProviders: [cloudflareImages({})] })`, reading `CF_ACCOUNT_ID`,
`CF_IMAGES_ACCOUNT_HASH`, and `CF_IMAGES_TOKEN`) so editors can browse, upload,
delete, and insert responsive `w=...,h=...,f=...,fit=scale-down` transforms
through `/_emdash/admin` Media Picker instead of hardcoding raw
`https://imagedelivery.net/...` URL strings in source.

## Commerce media reference model

WooCommerce's documentation and source (the product images document, the v3
REST products controller, the product importer, `WC_Regenerate_Images`, the
Store API image schema) show a commerce layer that owns no files:

- A product references the platform library: one featured image, an ordered
  gallery, and a variation image that falls back to the parent's and then to a
  store-level placeholder.
- Alt text lives on the media item, with a render-time fallback chain (alt,
  caption, title).
- Sizes are named presets, regenerated in the background when settings change
  and made on demand when missing; a resizing CDN replaces regeneration.
- Every import path sideloads into the library, matches an existing item by
  path or recorded source URL before downloading, records the source, and fails
  loudly when a fetch fails.

Apply the same shape on EmDash: product fields reference the Media Library
(`image`, gallery, a variation image with fallback, a placeholder setting, size
presets through the image endpoint, API shapes with `src`, `srcset`, `sizes`
and `alt`). A media extension adds import deduplication by source and hash,
offload, regeneration or video on top of the library's API, never a second
competing image store.
