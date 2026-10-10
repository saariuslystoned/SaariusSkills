# Site Verification

Agree on verification scope using the target repository's contracts. Every
EmDash site repository carries its own repeatable route proof: local runtime
proof, then preview proof, then the owner-approved production deploy loop. Use
Wrangler for Cloudflare targets and the repository's supported runtime for other
hosts. Existing equivalents are preferable to inventing parallel checks; when a
repository has none, start with these two artifacts:

1. `FEATURE_MAP.md` lists every public route, navigation menu, `sitemap.xml`,
   `robots.txt`, redirect and configured `/_emdash` auth gate, with the command
   or observation that verifies each one. Record the selected auth mode, the
   canonical-host policy, and which checks apply to local, preview or production.
2. `bin/verify-site` accepts any base URL (the local runtime, a preview URL such
   as `workers.dev`, or production), crawls the homepage and follows every
   same-origin link in navigation, footer and body. It exits non-zero on any
   failed check below.

For the affected surface, check:

- Public pages and same-origin links in navigation, footer and body return the
  intended status and content after redirects. A page containing EmDash's
  `There is no page at this address` error is not success even with HTTP 200.
- Menu and sitemap URLs do not contain `%2F` from nested slugs. Sitemap entries
  resolve, and `robots.txt` points to the intended sitemap.
- Canonical tags, trailing-slash policy and redirect behavior agree. Apply
  production-host redirects (for example apex to canonical 301) only on the
  declared production hosts, not locally or on a preview host.
- Protected admin/setup content rejects anonymous requests under the selected
  authentication mode, while authorized editors and deliberately public plugin
  endpoints still work. Check Access only where configured, and verify
  authorized editor access separately.
- Editor-owned navigation renders the CMS menu, and a permitted editor change
  survives deployment. Mark fallback navigation distinctly during bootstrap.
- Navigation holds at its real item count: keep any call to action in its own
  layout area rather than absolutely positioned, and check widths from 1024 to
  1920 pixels as well as mobile.
- Right after a CMS publish, the plain homepage URL may serve a cached copy
  for about a minute. Check a cache-busted URL first, and fail the plain URL
  only if it is still stale after a few retries.

## Deploy gate

Run the local check before pushing, the preview check before requesting a
production deploy, and the production check after every authorized deployment.
Show the owner the verified preview before production. A deployment is done only
when the production check passes for the deployed commit; include its complete
output in the report. Record exact candidate/environment, complete sanitized
output and any inapplicable checks with reasons. A missing required check is
unrun or blocked, never a pass. Pass counts pasted into a pull request are not
behavior proof: keep the check's log for the deployed commit and screenshots of
the changed pages.

Keep the verification contract and its commands in the repository being
verified, beside its feature map, rather than in a separate agent skill that
can drift from the code.

## Instructions and credentials

Document how to run the command through the active harness's supported
instruction discovery, and say where complete output is recorded. Do not assume
all harnesses share Cursor's project-skill layout or claim that instructions
were installed merely because the file exists; when discovery is unavailable,
point to the repository guide instead.

Use the credential consumer and authentication path the project approves. Never
directly source, execute, inspect or print secret environment files; a subshell
does not sandbox that. Without credentials or auth logs, include only sanitized
output. If the approved consumer is unavailable, report the dependency rather
than loading or parsing environment files yourself.
