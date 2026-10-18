# Set up a machine

Do this once per machine. The test keeps its Chrome profile, settings and proof
in `~/.dinkus-e2e/`.

## The machine

- Google Chrome. The test drives the installed Chrome, so Playwright downloads no
  browser. To use another Chromium, set `DINKUS_E2E_CHANNEL=chromium` and
  `DINKUS_E2E_CHROME_PATH`.
- Node 22 and npm. Run `npm ci` in the runner folder. For videos of a run
  (`DINKUS_E2E_VIDEO=1`), also run `npx playwright install ffmpeg` there once:
  Playwright records with its own copy of ffmpeg.
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
- For Cart, at least one listed product with a price that shoppers can add to
  the cart. Cart adds it to its own clean browser's cart and removes it again.
- For Manage products, Commerce with rename and archive (dinkus-commerce-beta
  0.3.0-beta.2 or later), Template Store's products and categories collections,
  and a store admin sign-in allowed to add products, upload media and publish
  content. A store whose admin asks for EmDash's own sign-in (a passkey or an
  emailed link) needs it made once by hand: run with
  `DINKUS_E2E_ADMIN_SIGNIN=wait`. Each run leaves one archived product named
  "Live test product <date and time> renamed" and its photo in the Media library;
  its product page and category go to EmDash's Trash. Empty the Trash or delete
  the photos by hand whenever you like.
- For Mark as completed, Commerce 0.2.0 or later and a store admin sign-in with
  the Administrator role, which the test uses to make the agent's one-hour key.
  Each run places two Stripe TEST orders and leaves both Completed. When
  Cloudflare Access fronts the store's API as well as its admin, the agent's
  calls carry the saved Access sign-in.
- For Problems, Buy and ship's Stripe TEST checkout and a store admin sign-in
  that can complete orders in Commerce Orders. Each run places one Stripe TEST
  order and leaves it Completed; the test cards Stripe turns down make no order.
- Ship turned on for the store, with a ship-from address and at least one box size
  in Ship Settings. Ship makes free Pitney Bowes sandbox labels for TEST orders.
- The Cloudflare Access app in front of the store admin, or of the whole test
  store, offers One-time PIN with Instant Auth off, and its policy allows the test
  inbox's address. When it fronts every page, the clean browsers of Storefront and
  Cart sign in to it the same way. If the app offers only Google, run once with
  `DINKUS_E2E_ADMIN_SIGNIN=wait` and sign in by hand in the test's window. The
  saved profile keeps that sign-in until Access ends the session, but Storefront
  and Cart can't open a store behind a Google-only app.

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
