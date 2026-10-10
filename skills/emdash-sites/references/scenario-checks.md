# Scenario Checks

Use these to evaluate revisions of this skill. They are routing and acceptance
checks, not claims that product tests were run.

| Prompt or evidence | Expected next action | Incorrect shortcut |
| --- | --- | --- |
| "The React coupon screen works; every plugin must install from the Registry." | Identify the missing sandbox/Block Kit path and real packaged install proof. | Declare Registry readiness from React screenshots. |
| "Make the native shipping screen look like EmDash." | Inspect the real admin surface, use compatible Kumo/Lingui and exercise the action. | Restyle a standalone lab and call it native. |
| "Retire our old blocks after the framework upgrade." | Inventory stored content and all consumers; migrate and verify native editing and rendering. | Remove the dependency or archive first. |
| "Admin returns 200, but the inventory service says disconnected." | Observe one request across dispatcher, network validation and service response. | Repeat bootstrap or disable SSRF checks. |
| "The Stripe test dashboard is ready." | Verify the site binding, an actual guest TEST purchase and the durable order and recovery. | Report a completed purchase from account setup. |
| "The homepage is live; is the CMS done?" | Prove authenticated edit, save, publish and persisted public content. | Treat static HTTPS success as CMS proof. |
| "Publish this approved candidate." | Apply the exact existing approval after artifact and route preflight, and preserve other gates. | Ask for identical approval again or infer permission for new live accounts. |
| "The Worker deployed, but pages are empty." | Identify initialization state and the real content source; test starter and published content separately. | Resurrect deleted or unpublished entries from seed or hide database failures. |
| "The editor returns 404 after enabling Access." | Check adapter bindings, the selected auth mode and validated application configuration without exposing secrets. | Remove authentication or block required public or callback routes. |
| "The free host cannot run our Registry plugin." | Report the supported runner or entitlement decision while continuing independent work. | Remove isolation and call native execution Registry proof. |
| "We changed the seed and merged; why does the site still show the old copy?" | Check the live page's content-source marker; identify the declared content owner and any path from repository to CMS. | Verify on a fresh database and call the seed render proof of the live site. |
| "Keep the CMS equal to the seed after every deploy." | Surface the ownership decision: a seed-to-CMS sync makes every admin edit lose; propose CMS-owned content with an event-driven mirror back into the repository. | Build the sync because it is the shortest path. |
| "None of the site's images show up under Media in the admin." | Treat it as a design smell: move imagery to the Media Library with `image` fields unless a recorded reason keeps it in the repository, and move the imagery rules to a check on the library. | Call it an EmDash bug or upload the files without moving the rules. |
| "Let the agent edit the live CMS directly." | Keep pre-publish review: the agent stages a draft against the revision it read and hands over preview and admin links; a human publishes. | Grant a machine identity publish rights or let it send status, lock overrides or live metadata on a save. |
| "Update the navigation banner via CLI `--draft`." | Check revision support; refuse a machine update without revisions and the `_rev` token unless live-content authorization exists. | Assume `--draft` prevents live writes on non-revision collections. |
| "The admin view link says `/pages/about`, but the route is `/about`." | Set a matching `urlPattern`, verify 200, and keep a collection-path 301 safety net. | Assume the admin link is cosmetic. |
| "The owner changed the header order in the admin." | Render every nav from its CMS menu; create missing menus only and never overwrite owner order. | Re-seed or reorder menus on each deploy. |
| "Setup status and another EmDash API route return 500 `NOT_CONFIGURED`." | Tail the Worker while requesting setup status and fix runtime initialization; require setup status 200 first. | Claim the wizard will repair an init failure. |
| "D1 rows were cleared but migration tables remain." | Identify the exact database and environment. Rebuild only an explicitly disposable target with scoped approval; populated targets need a restorable recovery point and exact-operation approval. | Drop live tables, partially reset rows, or hand-insert `options` or `users`. |
| "A service token is redirected to login or rejected after Access." | Use a `non_identity` policy, poll propagation, verify the JWT `common_name`, and check a machine-only allowlist. | Add the machine ID to the human allowlist or store the token. |
| "We are ready to cut DNS to production." | Preserve apex/www rollback records and mail/TXT records, then run page, nav, SEO, redirect and anonymous-admin checks. | Treat DNS cutover as independent of web and email rollback. |
| "A migrated URL should probably still redirect." | Find the old site's real URLs from sitemap, analytics or search console before adding 301s. | Invent redirects for assumed subpages. |
| "The whole `/_emdash` namespace should be public or private." | Gate admin, setup and authenticated APIs on every hostname and inventory exact public plugin or webhook exceptions with independent validation. | Blanket-404 the namespace or add a broad API bypass. |
| "Can `allowedHosts` contain `*`?" | No: bare hosts or `*.`-prefixed subdomains; unrestricted access is the separate `network:request:unrestricted` capability. | Add `*` to unblock a request. |
| "The review bot's pickup comment is green; merge it." | Wait for the final review on the live head commit. | Treat delivery or pickup as clearance. |
| "`pnpm install` gets a 403 from codeload in a cloud session." | Attach the `github:` dependency's repository to the session, then reinstall. | Regenerate the lockfile or swap the dependency. |

## Failure patterns to check

These came from debugging and verification handoffs. Check them when relevant;
they are not presumed defects in the next project.

- Reused export output retained files from an earlier run.
- Fixture DNS rejected a plugin request before it reached the intended adapter.
- Persisted signing configuration contradicted a memory-only test contract.
- Summaries of passing logic tests claimed more than the user-visible proof
  justified.
- A fixture port collision or a native-module ABI mismatch looked like a product
  defect at startup.
