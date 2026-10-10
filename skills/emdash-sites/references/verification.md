# Site Verification

Agree on verification scope using the target repository's contracts. Maintain a
route inventory and a repeatable command that accepts local, preview and
production base URLs. Existing equivalents are preferable to inventing parallel
checks; `FEATURE_MAP.md` and `bin/verify-site` are example names, not required
repository structure.

For the affected surface, check:

- Public pages and same-origin links in navigation, footer and body return the
  intended status and content after redirects. A page containing EmDash's
  `There is no page at this address` error is not success even with HTTP 200.
- Menu and sitemap URLs do not contain `%2F` from nested slugs. Sitemap entries
  resolve, and `robots.txt` points to the intended sitemap.
- Canonical tags, trailing-slash policy and redirect behavior agree. Apply
  production-host redirects only on the declared production hosts, not locally.
- Protected admin/setup content rejects anonymous requests under the selected
  authentication mode, while authorized editors and deliberately public plugin
  endpoints still work. Check Access only where configured.
- Editor-owned navigation renders the CMS menu, and a permitted editor change
  survives deployment. Mark fallback navigation distinctly during bootstrap.
- Navigation holds at its real item count: keep any call to action in its own
  layout area rather than absolutely positioned, and check widths from 1024 to
  1920 pixels as well as mobile.
- Right after a CMS publish, the plain homepage URL may serve a cached copy
  for about a minute. Check a cache-busted URL first, and fail the plain URL
  only if it is still stale after a few retries.

Run local checks before submitting changes, preview checks before a production
release and production checks after an authorized deployment. A deployment is
done only when the production check passes. Record exact candidate/environment,
complete sanitized output and any inapplicable checks with reasons. A missing
required check is unrun or blocked, never a pass. Pass counts pasted into a
pull request are not behavior proof: keep the check's log for the deployed
commit and screenshots of the changed pages.

Keep the verification contract and its commands in the repository being
verified, beside its feature map, rather than in a separate agent skill that
can drift from the code.

Use the active harness's supported instruction discovery when documenting the
command. Do not assume all harnesses share Cursor's project-skill layout or
claim that instructions were installed merely because the file exists.
