# Content Ownership And Draft Safety

Declare the owner of each kind of data before building a synchronization path.
For an editable CMS site, content normally belongs to the CMS after bootstrap;
components, block schemas and deployment configuration belong to the repository.
An editor's published changes must survive the next deployment. An empty local
seed render does not prove what the live CMS serves: inspect a non-sensitive
content-source marker or compare the actual persisted record.

## Optional repository mirror

If the project requires a repository copy of published content, mirror from the
CMS to the repository, rather than overwriting editor changes from seed files.
Cover every supported publish/unpublish/restore/delete path, including scheduled
publishes. Event-driven mirroring avoids waiting for the next scheduled poll;
a manual read-only comparison provides a recovery check.

Keep draft data out of public mirrors. Use least-privilege repository access and
an explicit review/merge policy. Report failures through an independently working
channel under the project's notification authorization. Do not introduce sends,
auto-merge or background writers merely by selecting this design. Session startup
can run a read-only comparison; it does not authorize pushes or PR mutations.

Prove a local publish-to-mirror round trip, stale-state detection and a forced
failure notification with test substitutes before authorized live verification.

## Agent drafts and human publishing

When the project's permission boundary is draft-only, restrict machine identities
to reading and staging drafts. Do not allow publishing, scheduling, deletion,
schema mutation, edit-lock overrides or live metadata writes through the draft
path. A `status` field on save can change live publication state and is not a
safe draft field.

At the bundled EmDash skill pin, CLI `create` and `update` automatically issue a
follow-up publish call unless `--draft` is supplied. Always use `--draft` for a
draft-only interaction. However, **`--draft` does not isolate unversioned writes**:

- `packages/core/src/cli/commands/content.ts` calls `client.update(data, _rev)`
  before considering publication.
- `packages/core/src/database/repositories/content.ts` updates the live collection
  table directly when the collection's `supports` excludes `revisions`.
- A draft-only update therefore requires revision support, the current `_rev`
  concurrency token, and CLI `--draft` when using the CLI. Reject a non-revision
  collection update unless existing explicit live-content authorization covers it.
- A direct API call that omits publish still has the same revision-isolation
  requirement. Verify the resolved implementation before relying on a newer version.

Enforce the permission boundary in route/body validation when built-in roles do
not provide an edit-without-publish tier. Return preview and admin links for
review; do not confuse a saved draft with published content.

## Editable images

Prefer the Media Library for images editors need to change. Store references in
`image` fields, use `darkVariant` for paired images where supported, and verify
the media serving path is public through the selected auth boundary. Bootstrap
media explicitly for clean installs. Static repository assets remain appropriate
for deliberately code-owned imagery; document that ownership rather than leaving
an apparently editable page with an unexplained empty Media Library.

Keep alt text, dimensions and any required provenance checks with the media
workflow. For commerce, reference the platform library for the featured image,
gallery and variation images; a media extension should add import/deduplication,
offload or transformations rather than creating a second competing image store.
