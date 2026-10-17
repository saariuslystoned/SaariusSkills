# Set up a machine

Do this once per machine. The test keeps its Chrome profile, settings and proof
in `~/.dinkus-e2e/`.

## The machine

- Google Chrome. The test drives the installed Chrome, so Playwright downloads no
  browser. To use another Chromium, set `DINKUS_E2E_CHANNEL=chromium` and
  `DINKUS_E2E_CHROME_PATH`.
- Node 22 and npm. Run `npm ci` in the runner folder.
- A desktop session, because the test opens a visible window.
  `DINKUS_E2E_HEADLESS=1` hides it, but then nobody can step in if a sign-in ever
  needs a person.

## The test inbox

One mailbox receives both sign-in emails: DinkusKit.com's "Sign in to DinkusKit"
link for the store owner, and Cloudflare Access's one-time PIN for the store admin
(or the whole store, when Access fronts every page).

- Sign gogcli in to that inbox. The bundled `scripts/gog-mail.sh` runs
  `gog --readonly --gmail-no-send` searches for the two sign-in emails and reads
  the matching messages, nothing else.
- To check it without printing any mail, run this from the runner folder:
  `DINKUS_E2E_MAIL_ACCOUNT=<inbox> DINKUS_MAIL_QUERY='from:accounts@dinkuskit.com newer_than:7d' scripts/gog-mail.sh > /dev/null && echo mail ok`
- Another mail tool works too. Set `DINKUS_E2E_MAIL_CMD` to a command that prints
  the bodies of the messages matching `$DINKUS_MAIL_QUERY`, newest first.

## The store

- An EmDash store with Commerce and Payments installed from the Registry, Stripe
  connected in TEST mode, and at least one physical product with a weight. To
  name the product, set `DINKUS_E2E_PRODUCT_PATH` to its page.
- The owner's DinkusKit.com account uses the test inbox's address. It signs in
  with an emailed link, so it has no password.
- For Storefront, at least one product with its own photo, a published product
  page and a category. A Commerce product gets its own page only when a published
  products entry links to it; otherwise its Shop card has no page to open.
- Ship turned on for the store, with a ship-from address and at least one box size
  in Ship Settings. Ship makes free Pitney Bowes sandbox labels for TEST orders.
- The Cloudflare Access app in front of the store admin, or of the whole test
  store, offers One-time PIN with Instant Auth off, and its policy allows the test
  inbox's address. When it fronts every page, Storefront's clean browser signs in
  to it the same way. If the app offers only Google, run once with
  `DINKUS_E2E_ADMIN_SIGNIN=wait` and sign in by hand in the test's window. The
  saved profile keeps that sign-in until Access ends the session, but Storefront
  can't open a store behind a Google-only app.

## Settings file

Write `~/.dinkus-e2e/env`, or set `DINKUS_E2E_ENV_FILE` to another file. Put one
`KEY=value` per line. The runner reads only `DINKUS_E2E_` keys from it, and a
variable already set in the environment wins.

```sh
DINKUS_E2E_STORE=https://your-test-store.example
DINKUS_E2E_SITE_ID=<the store's DinkusKit site id>
DINKUS_E2E_OWNER_EMAIL=<the owner's DinkusKit.com address, delivered to the test inbox>
DINKUS_E2E_MAIL_ACCOUNT=<the inbox gogcli reads>
# Only when gogcli needs a named OAuth client for that inbox:
DINKUS_E2E_GOG_CLIENT=<client name>
```

The site id appears in Ship's address bar:
`https://ship.dinkuskit.com/stores/<site id>/orders`. The
[runner's README](../runner/README.md#settings) lists the optional settings.
