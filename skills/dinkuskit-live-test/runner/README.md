# DinkusKit live test runner

Saved Playwright journeys against a live test store and the live services. Each
journey is one spec file in [tests](tests/), tagged with its stage in the
journeys plan:

| Journey | Stage | What it covers |
| --- | --- | --- |
| [Buy and ship](tests/buy-and-ship.spec.mjs) | `@running` | A Stripe TEST order on the store, the order in Commerce, a Pitney Bowes sandbox label in Ship, and Commerce marking the order Completed with the same tracking number |
| [Storefront](tests/storefront.spec.mjs) | `@next` | A new shopper's first look: the homepage, the product list, a product page and its category page |

`npm test` runs every `@running` journey. A new journey starts as `@next` and
moves to `@running` once it has passed on the test store.

It runs in a visible Chrome window with its own saved profile
(`~/.dinkus-e2e/profile`), so sign-ins carry over between runs. DinkusKit.com
signs in with an emailed link, and the Cloudflare Access app in front of the
store admin (or of the whole test store) signs in with an emailed one-time PIN.
The test reads both emails itself through the mail command, so nobody has to
step in. If the Access app offers only Google, set
`DINKUS_E2E_ADMIN_SIGNIN=wait` and sign in once in the window.

## Run

```sh
npm ci
npm test                      # every @running journey; Buy and ship goes from checkout to Completed
npm run journey -- storefront # one journey, by its file name
npm run finish                # Buy and ship from an existing order (DINKUS_E2E_ORDER=1001, or the only unfinished TEST order)
npm run unit                  # the runner's own offline checks
```

Storefront opens its own clean browser, with no sign-ins, cookies or saved
cart, so it sees exactly what a new shopper sees. When the test store keeps
every page behind Cloudflare Access, that browser first signs in to Access with
an emailed one-time PIN, as the admin sign-in does, and to nothing else. It
needs `DINKUS_E2E_STORE`, plus the mail command and `DINKUS_E2E_OWNER_EMAIL`
when Access fronts the store.

The machine's settings come from `~/.dinkus-e2e/env`; see
[setup](../references/setup.md).

## Settings

Set these in `~/.dinkus-e2e/env` (or the file `DINKUS_E2E_ENV_FILE` names), or in
the environment, which wins.

| Setting | Default | What it is |
| --- | --- | --- |
| `DINKUS_E2E_STORE` | required | The store's address |
| `DINKUS_E2E_SITE_ID` | required | The store's DinkusKit site id |
| `DINKUS_E2E_OWNER_EMAIL` | required | The owner's DinkusKit.com address; the test asks for sign-in emails to it |
| `DINKUS_E2E_MAIL_ACCOUNT` | none | The test inbox; picks the bundled read-only `scripts/gog-mail.sh` |
| `DINKUS_E2E_GOG_CLIENT` | gogcli's default | A named gogcli OAuth client for that inbox |
| `DINKUS_E2E_MAIL_CMD` | the gogcli script | Any command that prints the bodies of the messages matching `$DINKUS_MAIL_QUERY`, newest first |
| `DINKUS_E2E_ACCESS_MAIL_QUERY` | Cloudflare's senders, last hour | The Gmail search for the Access code email |
| `DINKUS_E2E_SHOPPER_EMAIL` | the owner's address | The checkout contact |
| `DINKUS_E2E_PRODUCT_PATH` | the first shippable product | The product page to buy |
| `DINKUS_E2E_SERVICE` | `GA` | The label service (Ground Advantage) |
| `DINKUS_E2E_COMPLETE_WAIT_SECONDS` | `420` | How long to wait for Commerce's background check |
| `DINKUS_E2E_ORDERS_ADMIN` | the Registry Commerce plugin's Orders page | Commerce Orders in the store admin |
| `DINKUS_E2E_ADMIN_SIGNIN` | `skip` | `wait` lets a person sign in to the store admin |
| `DINKUS_E2E_PROOF` | `~/.dinkus-e2e/proof` | Where each run's proof folder goes |
| `DINKUS_E2E_PROFILE` | `~/.dinkus-e2e/profile` | The saved Chrome profile |
| `DINKUS_E2E_HEADLESS` | off | `1` hides the window |

Without a mail command, the test waits for a person to sign in in the window.

## What it proves

### Buy and ship

| Step | What it proves |
| --- | --- |
| Place a Stripe TEST order on the store | A shopper can add a physical product to the cart and pay on Stripe's hosted Checkout with the test card |
| The thank-you page confirms the order and empties the cart | After Stripe sends the shopper back, the store's own page shows the confirmed order (pressing "Check status again" while it says pending, as a shopper would) and the header cart is empty. Recorded before the test asks Commerce itself, so the page gets no help |
| Commerce Orders shows the paid TEST order | Commerce recorded the order as TEST, provider-paid and Processing |
| Ship has the order | Commerce sent the order to Ship |
| Make the Pitney Bowes sandbox label | Ship quotes sandbox prices and buys a sandbox label |
| Label is a TEST SANDBOX label with a tracking number | The label is a sandbox label, not a practice one, and carries a tracking number |
| Label PDF downloads and is a real PDF | Ship serves the provider's PDF |
| Commerce's 5-minute check collects the label | Commerce's background check collects the label without anyone opening the store admin |
| Opening Commerce Orders collects the label | Runs only when the check above didn't: an owner opening Commerce Orders collects it |
| Commerce marks the order Completed with the same tracking | Ship shows Commerce completed the order with the label's tracking number |
| Commerce Orders shows Completed in the store admin | The store admin agrees, with carrier and tracking |

### Storefront

Every step after the first is soft: a finding is recorded and the journey goes
on, so one run lists everything a shopper would trip over.

| Step | What it proves |
| --- | --- |
| A new shopper can open the store | The homepage answers HTTP 200 on the store's own address, after a Cloudflare Access sign-in when the test store keeps every page behind one. When it doesn't, the journey stops here, since nothing else can be checked |
| The homepage shows no developer notices | The homepage shows no error box: no "Storefront composition is unavailable", no unknown content block, no alert |
| The product list shows each product's name, price and photo | Every product in the Shop list has a name, a price and its own photo that loads (the store's placeholder or "No image" fails) |
| Every product in the list opens its own page | Each product's link answers HTTP 200 |
| The product page shows the name, price and photo and offers Add to cart | The first product's page (or `DINKUS_E2E_PRODUCT_PATH`) shows its name, price and photo, and its Add to cart button is ready |
| A category page lists its products with name, price and photo | The product's category page (or the first one the homepage links) lists products with names, prices and their own photos, each opening its product page. Skipped when no category page is linked |
| No page says checkout is unavailable on a store that takes checkouts | When the store takes checkouts (its cart page admits guest checkout), the homepage, the product page, the category page and the empty cart don't tell shoppers they can't check out or buy. Skipped, with the reason, when the store takes none |

## Proof

A journey's verdict is PASS only when every step passed or was skipped for a
stated reason; an error between steps (a page that won't open) or before the
first one (a saved profile another Chrome holds) fails it too. The run's verdict
is PASS only when every journey passed, and
`npx playwright test` exits non-zero otherwise. The run prints each journey's
verdict, then `Verdict:` and the path to `PROOF.md`.

Each run writes `~/.dinkus-e2e/proof/<run>/`: `PROOF.md` and `report.json` (each
journey's verdict, the result and detail of every step, the order, tracking
number and PDF hash, and the plugins and versions the store ran, read from its
admin), a screenshot per step, `label.pdf` and, on macOS, its picture
`label.pdf.png`.
