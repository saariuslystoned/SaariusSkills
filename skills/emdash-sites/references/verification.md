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

Run local checks before submitting changes, preview checks before a production
release and production checks after an authorized deployment. Record exact
candidate/environment, complete sanitized output and any inapplicable checks
with reasons. A missing required check is unrun or blocked, never a pass.

Use the active harness's supported instruction discovery when documenting the
command. Do not assume all harnesses share Cursor's project-skill layout or
claim that instructions were installed merely because the file exists.
