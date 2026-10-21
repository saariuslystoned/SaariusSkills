# DinkusKit live test runner

Saved Playwright journeys against a live test store and the live services. Each
journey is one spec file in [tests](tests/), tagged with its stage in the
journeys plan:

| Journey | Stage | What it covers |
| --- | --- | --- |
| [Buy and ship](tests/buy-and-ship.spec.mjs) | `@running` | A Stripe TEST order on the store, the order in Commerce, a Pitney Bowes sandbox label in Ship, and Commerce marking the order Completed with the same tracking number |
| [Storefront](tests/storefront.spec.mjs) | `@running` | A new shopper's first look: the homepage, the product list, a product page and its category page |
| [Cart](tests/cart.spec.mjs) | `@running` | A new shopper adds a product to the cart, changes its quantity and removes it, with the cart total right each time |
| [Manage products](tests/manage-products.spec.mjs) | `@running` | The owner adds a product, gives it a photo that stays after a reload and a published page in a new category that the store links to, changes its price and name, and archives and restores it, with the store following each change |
| [Full catalog](tests/full-catalog.spec.mjs) | `@running` | The store carries a catalog as big as a real shop's (3 categories of 8 products unless set otherwise), each product with its own price, weight, photo and page: the owner adds what's missing, the Shop list, every category page and every product page show the whole catalog, and the owner can still save a product with all of it in place |
| [Mark as completed](tests/mark-completed.spec.mjs) | `@running` | The owner marks a paid TEST order completed in Commerce Orders, typing a carrier and tracking number, and an agent completes another through Commerce's orders API, sending neither; both end Completed |
| [Problems](tests/problems.spec.mjs) | `@running` | A shopper's checkout going wrong: Stripe turns down a declined card, a card without enough funds and a card that fails the bank's security check, each with a clear message and no order; the shopper leaves Stripe for the cart, finds the way back to the same checkout and pays once with the test card, and the owner completes that one order |
| [Buy a label in the store admin](tests/store-admin-label.spec.mjs) | `@running` | The owner ships a paid Stripe TEST order from the store admin's Shipping page, which the Ship plugin draws from hosted Ship: See prices, Buy label at the quoted price and Print label, then, once Commerce has completed the order, Print label again and Cancel label, with the order staying Completed |
| [Install the Registry plugins](tests/install-plugins.spec.mjs) | `@next` | A DinkusKit beta the beta store does not already run is installed there (`dinkus-ship-beta` `0.1.0-beta.1` unless `DINKUS_E2E_INSTALL` names others), through the store's Registry verify and install routes, and Plugins lists it. A beta the store already runs is left as it is |
| [DinkusKit.com account and connect the store](tests/connect-dinkuskit.spec.mjs) | `@next` | The owner's DinkusKit.com account shows the beta store connected, or, when the account says to connect it, Payments status is used to approve Payments for that store only. The store key is never opened |
| [Commerce settings](tests/commerce-settings.spec.mjs) | `@next` | Commerce Settings shows Checkout settings and an empty Store key, with the Set up Commerce descriptions. The key is never typed |
| [Payments status](tests/payments-status.spec.mjs) | `@next` | On the beta store, dinkus-payments-beta's Payments status shows a connected Stripe test account, or walks Connect, Authorize Payments at DinkusKit, and Approve payments. Deny, Reconnect, and Stripe setup are not pressed |
| [Ship settings](tests/ship-settings.spec.mjs) | `@next` | Ship's settings show Store ID matching the store's site id and an empty Store key. The key is never typed, and no label is bought |
| [One product with a category](tests/onboarding-product.spec.mjs) | `@next` | The owner adds one product with a price, a weight, a photo, and a published page in a new category. Archive is only the tidy afterward, not the story |

`npm test` runs every `@running` journey. A new journey starts as `@next` and
moves to `@running` once it has passed on the test store. Manage products needs
a Commerce release that can rename and archive a product, and Full catalog one
whose product screens cope with a full catalog (0.3.0-beta.4 or later); on an
older Commerce, Manage products stops before adding anything and Full catalog
adds nothing, each saying why. Buy a label in the store admin needs the Ship
plugin installed and connected, as dinkus-ship-beta is on the beta store, where
it first passed on 20 Oct.

How a beta becomes that release is [Release a plugin](../SKILL.md#release-a-plugin).
Payments, Commerce and Ship each press `cut-beta`, then this workflow, then
`promote`. This runner proves. It does not
publish. **Update the store** does not install a plugin the store is not already
running. [Install the Registry plugins](tests/install-plugins.spec.mjs) does that,
and only on beta.sm0ky.dev. It never types a store key.

It runs in a visible Chrome window with its own saved profile
(`~/.dinkus-e2e/profile`), so sign-ins carry over between runs. DinkusKit.com
signs in with an emailed link, and the Cloudflare Access app in front of the
store admin (or of the whole test store) signs in with an emailed one-time PIN.
The test reads both emails itself through the mail command, so nobody has to
step in. It takes only Access emails that name the store's address, so it never
types a code another store sent to the same inbox. The Access app must offer
One-time PIN: the request filter below blocks other sign-in providers such as
Google, so a Google-only Access app can't be signed in to from a run, not even by
hand with `DINKUS_E2E_ADMIN_SIGNIN=wait`.

## Requests stay within the selected sites

Pages the canonical journeys open filter requests to the selected `DINKUS_E2E_STORE`,
the DinkusKit.com and Ship set by `DINKUS_E2E_ACCOUNT` and `DINKUS_E2E_SHIP` (the
live ones unless set), Stripe/Stripe CDN, and the exact Access origins
listed in `DINKUS_E2E_ACCESS_ORIGINS`. Other stores and lookalike domains are
blocked. Store photos may use any dimensions or query parameters; the filter
checks the origin, not a fixed image-size list. Service workers are disabled so
they cannot bypass the browser request filter, and WebSocket connections to other
hosts are closed before they connect.

When the store sends visitors to a Cloudflare Access sign-in that
`DINKUS_E2E_ACCESS_ORIGINS` doesn't list, the run stops before its first page and
names the origin to add, since the filter would block that sign-in. Shopper
windows check only the storefront, so a journey that never opens the admin isn't
stopped by an admin-only Access app.

Popups the site opens and cross-site frames (Stripe's) get the same origin check and
lose store headers on every request they start. Redirects are where they differ:
Chromium shows a cross-site frame's redirects to no interceptor the runner can attach,
and a popup's interceptor attaches only after its first request has left, so a redirect
answering a cross-site frame's request, or a popup's first one, is not checked. Later
requests and redirects in a popup are.

Store authorization headers are removed from requests to other allowed sites;
those sites use their own browser cookies. Chromium pauses every network hop, including redirects, for the origin check;
headers are scoped again at each destination. The filter never
adds credentials. Direct link, photo and PDF probes use the same origin policy and check each
redirect before following it. The agent's separate store API calls retain their
existing same-store URLs and manual-redirect behavior.

Playwright turns the browser's cache off while the filter is on, so each browser
the run opens keeps its own copy of each store file the store marks immutable (the
hashed scripts and styles under `/_astro/`) and answers repeat requests from it while
the store says it stays fresh, as a shopper's browser would. A new shopper's browser
starts with none. Without this, every page view fetches them all again, and a run
can cross the store's limit of 120 requests a minute per visitor.

That limit counts every request from one address, pages, photos and admin calls
alike, from every browser the run opens. So the run counts its own store requests
from the moment each is sent, and before a step that sends many (opening a store
page with its photos or a page of the store admin, reading each product's photo or
link, uploading a photo to the Media library, the owner's work on a product in Full
catalog) it waits until they fit under 100 in the last minute. The count carries on when Playwright starts
a new worker after a journey fails, and into a run started straight after another:
each store request's time also goes, as it's sent, in that minute's log
(`.store-requests-<store>-<minute>.log`) beside the run folders in
`DINKUS_E2E_PROOF`, which takes it back if the browser answered it from its own
copy. Each new worker counts the last minute's requests from those logs, and logs
older than the last minute are removed as the run goes. On a store with a few
products it never waits; with a large catalog it slows down rather than being
turned away.

Leave the window alone while it runs: the test drives it, and a click or a tab
of yours can get in its way. To see the label, look in the proof folder for
`label.pdf` and its picture; Buy and ship also shows the picture in the window.
Every click, page load and screenshot has a time limit, so nothing holds a run
for long: a step whose page stops answering fails within a minute or two.

## Run

```sh
npm ci
npm test                      # every @running journey; Buy and ship goes from checkout to Completed
npm run journey -- storefront # one journey, by its file name (storefront, cart, manage-products, full-catalog, mark-completed, problems, buy-and-ship, store-admin-label, install-plugins, connect-dinkuskit, commerce-settings, payments-status, ship-settings, onboarding-product)
npm run finish                # Buy and ship from an existing order (DINKUS_E2E_ORDER=1001, or the only unfinished TEST order)
npm run unit                  # the runner's own offline checks
npm run update-store          # beta.sm0ky.dev only: update its DinkusKit beta plugins to the newest betas
```

Storefront opens its own clean browser, with no sign-ins, cookies or saved
cart, so it sees exactly what a new shopper sees. When the test store keeps
every page behind Cloudflare Access, that browser first signs in to Access with
an emailed one-time PIN, as the admin sign-in does, and to nothing else. It
needs `DINKUS_E2E_STORE`, plus the mail command and `DINKUS_E2E_OWNER_EMAIL`
when Access fronts the store.

Cart opens its own clean browser the same way. It adds one product to that
browser's cart, changes it and removes it again, and never checks out, so it
places no order and leaves nothing behind in the store.

Manage products works in the store admin with the saved profile, as an owner
does: Commerce Products in one tab, EmDash's Media library and content editor in
another. After each change it checks the store in a clean shopper browser. Its
photo is one the browser draws for each run, labeled with the product's name, so
every run uploads a file of its own: the Media library keeps one copy of
identical files, under the first one's name. It needs a Commerce release that
can rename and archive a product
(dinkus-commerce-beta 0.3.0-beta.2 or later). On an older one it stops before
adding anything, judging from a product the store already has. It tidies up
after itself, but Commerce archives products rather than deleting them, so each
run leaves one archived product named "Live test product <date and time>
renamed" and its photo in the Media library. Its product page and category go
to EmDash's Trash.

Full catalog keeps a standing catalog on the store, so every journey runs
against a store with as many products as a real shop: categories named "Catalog
Tees", "Catalog Hoodies" and "Catalog Caps", each holding products named
"Catalog Tee 01" and so on, every one with its own price, weight, photo and
published page. `DINKUS_E2E_CATALOG` sets the size, as categories x products per
category (`3x8` unless set, up to `4x50`). The first run on a store adds the
whole catalog as an owner would, in Commerce Products, the Media library and
EmDash's content editor, which takes about a minute a product; later runs find
it there, add only what's missing, and spend about four minutes checking it. A
bigger catalog gets more time before the journey times out: ten seconds for
each product it checks, and two minutes for each it adds. The catalog stays on
the store: Commerce archives products rather than deleting
them, so taking it off each run would leave a pile of archived products behind.
Before Commerce 0.3.0-beta.4, each product screen read the whole catalog, so a
store with more than a handful of products couldn't save a product; on a store
running an older Commerce the journey adds nothing and says so.

Mark as completed places two Stripe TEST orders the way Buy and ship places
one, paying each once with the test card, and leaves both Completed. The owner
completes the first in Commerce Orders. For the second, the test makes an admin
key with the saved profile's admin sign-in, set to stop working after an hour,
and the agent completes the order with that key alone. The test deletes the key
at the end of the run, even after a failed step. The key only ever travels in
the test's own calls, never through the browser, so it can't reach the proof.
When Cloudflare Access fronts the store's API as well as
its admin, the agent's calls also carry the saved Access sign-in, as an agent's
Access service token would. To complete existing Processing TEST orders instead
of placing new ones, set `DINKUS_E2E_ORDERS_TO_COMPLETE` (the owner's order,
then the agent's).

Problems works in one Stripe TEST checkout and places one order. On Stripe's
hosted Checkout it tries three of Stripe's test cards that never take a payment:
4000 0000 0000 0002 (declined), 4000 0000 0000 9995 (not enough funds) and
4000 0027 6000 3184, which brings up Stripe's test bank check, where the test
presses Fail, and again if Stripe's test page is still open seconds later.
Then it leaves by Stripe's link back to the store, which Payments
points at the cart, follows the cart's way back to the same checkout and pays
once with the 4242 test card. The owner completes the order in Commerce Orders,
so the run leaves no order open. If Stripe takes a payment from a card it should
turn down, the test pays nothing more and checks and completes that order
instead. On a store whose cart offers no way back to an open checkout
(Template Store before #100), the cart step fails and the test pays through the
checkout's own Stripe page, as Buy and ship does with a checkout an earlier run
left open.

Buy a label in the store admin places one Stripe TEST order the way Buy and ship
does, paying once with the test card, and buys one Pitney Bowes sandbox label
for it on the store admin's Shipping page, which charges nothing. Commerce
completes the order with the label's tracking number, and the journey cancels
the label at the end, so the run leaves the order Completed and its label
cancelled, listed under Earlier labels. When a step before Cancel label stops
the journey, the label stays bought: it's a sandbox label, so nothing was
charged, and Commerce still completes the order with it. It needs the Ship
plugin installed and connected (the store's Store ID and store key in its
settings), and hosted Ship running on Pitney Bowes's sandbox, which is when Ship
gives TEST orders sandbox labels. It finds the Shipping page in the admin's menu;
when the menu has more than one, set `DINKUS_E2E_SHIPPING_ADMIN`.
Print label's link shows the label to anyone who has it, for five minutes, so
the test reads it with its own fetch and writes it in no note or error. For the
same reason the journey leaves a blank page behind it, so Playwright's notes on
a failure can't show the link either; its step screenshots and notes are its
proof.

The machine's settings come from `~/.dinkus-e2e/env`; see
[setup](../references/setup.md).

## Run on GitHub

The repository's **Live journeys** workflow (`.github/workflows/live-journeys.yml`) runs
the same journeys on a GitHub runner against the beta test store, beta.sm0ky.dev, with
no Mac. Press **Run workflow** on its Actions page; `@running` runs every Running journey. That store
belongs to the workflow alone. Runs go one at a time: a press while a run is going waits its
turn, and a further press replaces the waiting one.

Before the journeys, **Update the store** (`tests/update-store.spec.mjs`, `npm run update-store`)
moves each DinkusKit beta plugin the store runs (dinkus-commerce-beta, dinkus-payments-beta and
so on) to the newest beta the Registry has, one at a time and in place, as the Update button on
the admin's Plugins page does; the journeys run only once it has passed. It refuses any store
but beta.sm0ky.dev, leaves every other plugin alone, never moves a plugin back to an older
version or between its beta and release listings, and agrees to nothing the Update button would
ask about: an update that asks for new permissions, opens routes to visitors who aren't signed
in (which also need an exception in the store's Access app) or changes its agent tools stops the
run, naming the plugin and what it asked, for the owner to update by hand. It also stops when
EmDash couldn't check the Registry for a plugin, since a pass has to name the betas it really
tested. When a plugin's **Cut beta** presses Run workflow, it names the beta it just published
(the `beta` input, such as `dinkus-payments-beta 0.2.9-beta.3`, shown in the run's name), and the
update first waits up to 15 minutes for the Registry to offer it, then installs exactly that beta,
even if a later one is out (and stops if the store already runs a later one). Only `npm run update-store`
runs it; every other run leaves it out. Untick "update_store" on **Run workflow** to test what the
store already runs.

Chrome runs headless, so the runner fails at once wherever it would wait for a person. Sign-in emails are read with
`scripts/gmail-mail.mjs`, through the Gmail API with a read-only key, in place of gogcli.
The job log is public, so it shows only each journey's pass or fail, the plugin versions
the store ran ("Plugins tested"), so a release can check its own beta passed, and why the
store update stopped, if it did; the steps,
screenshots, console output and any video go to a private R2 bucket under
`runs/github-<run id>-<attempt>/`.

It needs these repository secrets:

| Secret | What it is |
| --- | --- |
| `DINKUS_E2E_GMAIL_CLIENT_ID`, `DINKUS_E2E_GMAIL_CLIENT_SECRET`, `DINKUS_E2E_GMAIL_REFRESH_TOKEN`, `DINKUS_E2E_OWNER_EMAIL` | The test inbox's read-only key. `node scripts/gmail-authorize.mjs <client_secret.json> <inbox>` makes it once, from a Google OAuth client of type "Desktop app", and saves all four with `gh secret set` without printing them |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | A private R2 bucket for the proof, and an R2 API token that can only read and write that bucket |

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
| `DINKUS_E2E_MAIL_CMD` | the gogcli script | Any command that prints the bodies of the messages matching `$DINKUS_MAIL_QUERY`, newest first, such as `node scripts/gmail-mail.mjs` with the Gmail key from "Run on GitHub" |
| `DINKUS_E2E_GMAIL_CLIENT_ID`, `DINKUS_E2E_GMAIL_CLIENT_SECRET`, `DINKUS_E2E_GMAIL_REFRESH_TOKEN` | none | The test inbox's read-only Gmail key, for `scripts/gmail-mail.mjs` |
| `DINKUS_E2E_ACCESS_MAIL_QUERY` | Cloudflare's senders, last hour, naming the store's address | The Gmail search for the Access code email; set it when your Access emails don't name the store's address |
| `DINKUS_E2E_ACCESS_ORIGINS` | none | Comma-separated exact HTTPS Cloudflare Access origins for this store (for example `https://your-team.cloudflareaccess.com`). Other Access tenants are blocked. |
| `DINKUS_E2E_SHOPPER_EMAIL` | the owner's address | The checkout contact |
| `DINKUS_E2E_PRODUCT_PATH` | the first shippable product | The product page to buy |
| `DINKUS_E2E_SERVICE` | `GA` | The label service (Ground Advantage) |
| `DINKUS_E2E_COMPLETE_WAIT_SECONDS` | `420` | How long to wait for Commerce's background check |
| `DINKUS_E2E_ORDERS_ADMIN` | the Registry Commerce plugin's Orders page | Commerce Orders in the store admin |
| `DINKUS_E2E_PRODUCTS_ADMIN` | the Products page beside `DINKUS_E2E_ORDERS_ADMIN` | Commerce Products in the store admin, for Manage products and Full catalog |
| `DINKUS_E2E_SHIPPING_ADMIN` | the admin menu's Shipping page | The Ship plugin's Shipping page in the store admin, for Buy a label in the store admin |
| `DINKUS_E2E_CATALOG` | `3x8` | For Full catalog, the standing catalog's size as categories x products per category, from `1x1` to `4x50` |
| `DINKUS_E2E_ORDERS_TO_COMPLETE` | new orders | For Mark as completed, one or two different Processing TEST orders for the owner and then the agent to complete (`1003,1004`) instead of placing new ones. Anything else stops the journey before it places or completes an order |
| `DINKUS_E2E_ADMIN_SIGNIN` | `skip` | `wait` lets a person sign in to the store admin |
| `DINKUS_E2E_PROOF` | `~/.dinkus-e2e/proof` | Where each run's proof folder goes |
| `DINKUS_E2E_PROFILE` | `~/.dinkus-e2e/profile` | The saved Chrome profile |
| `DINKUS_E2E_HEADLESS` | off | `1` hides the window |
| `DINKUS_E2E_VIDEO` | off | `1` records every browser window the run opens, as a video in its proof folder |

Without a mail command, the test waits for a person to sign in in the window.

## What it proves

### Buy and ship

| Step | What it proves |
| --- | --- |
| Place a Stripe TEST order on the store | A shopper can add a physical product to the cart and pay on Stripe's hosted Checkout with the test card |
| The thank-you page confirms the order and empties the cart | After Stripe sends the shopper back, the store's own page shows the confirmed order (pressing "Check status again" while it says pending, as a shopper would) and the header cart is empty. Recorded before the test asks Commerce itself, so the page gets no help |
| Commerce Orders shows the paid TEST order | Commerce recorded the order as TEST, provider-paid and Processing. Orders lists its orders by order ID, 25 to a page, so the test finds this checkout's order by its order ID on whichever page it is, as Mark as completed does. Skipped when Commerce's checkout status names no order; Ship's only unfinished TEST order then stands in |
| Ship has the order | Commerce sent the order to Ship |
| Make the Pitney Bowes sandbox label | Ship quotes sandbox prices and buys a sandbox label. The test works on Ship's own page for the order (`?view=full`), since once the store's Ship plugin has called Ship, the order's plain address goes on to the store admin's Shipping page |
| Label is a TEST SANDBOX label with a tracking number | The label is a sandbox label, not a practice one, and carries a tracking number |
| Label PDF downloads and renders | Ship serves the provider's PDF, and its first page draws as a picture of the label, shown in the browser for the step's screenshot and the video |
| Commerce's 5-minute check collects the label | Commerce's background check collects the label without anyone opening the store admin |
| Opening Commerce Orders collects the label | Runs only when the check above didn't: an owner opening Commerce Orders collects it |
| Commerce marks the order Completed with the same tracking | Ship shows Commerce completed the order with the label's tracking number |
| Commerce Orders shows Completed in the store admin | The store admin agrees: the order's page shows it Completed with carrier USPS and the label's tracking number |

### Storefront

Every step after the first is soft: a finding is recorded and the journey goes
on, so one run lists everything a shopper would trip over.

| Step | What it proves |
| --- | --- |
| A new shopper can open the store | The homepage answers HTTP 200 on the store's own address, after a Cloudflare Access sign-in when the test store keeps every page behind one. When it doesn't, the journey stops here, since nothing else can be checked |
| The homepage shows no developer notices | The homepage shows no error box: no "Storefront composition is unavailable", no unknown content block, no alert |
| The product list shows each product's name, price and photo | Every product in the Shop list shows shoppers a name, a price and its own photo that loads (the store's placeholder, "No image", or a name, price or photo the page hides fails) |
| Every product in the list opens its own page | Each product's link answers HTTP 200 |
| The product page shows the name, price and photo and offers Add to cart | The first product's page (or `DINKUS_E2E_PRODUCT_PATH`) shows its name, price and photo, and its Add to cart button is ready |
| A category page lists its products with name, price and photo | The product's category page (or the first one the homepage links) lists products with names, prices and their own photos, each opening its product page. Skipped when no category page is linked |
| No page says checkout is unavailable on a store that takes checkouts | When the store takes checkouts (its cart page admits guest checkout), the homepage, the product page, the category page and the empty cart don't tell shoppers they can't check out or buy. Skipped, with the reason, when the cart page says the store takes none; a cart page that won't open or doesn't say fails it |

### Cart

Once the product is in the cart every step is soft, so one run lists every
finding.

| Step | What it proves |
| --- | --- |
| A new shopper can open the store | As in Storefront. When it doesn't, the journey stops here |
| Add to cart puts the product in the cart | The first product in the Shop list with a working Add to cart (on its own page, or on its Shop card when it has no page; or `DINKUS_E2E_PRODUCT_PATH`) says "Added to cart", the header's cart shows 1 item, and the cart page lists the product once, under the name and at the price the shopper saw, quantity 1. When it doesn't, or the product shows no price to compare, the journey stops here, since the cart has nothing to check |
| The cart total matches the item's price | The cart shows a subtotal (or a total) equal to the line's price times its quantity |
| Changing the quantity updates the cart | Typing 2 in the quantity field and moving on updates the header's cart to 2 items, and the cart still shows 2 after a reload |
| The cart total follows the new quantity | The cart's subtotal (or total) is the price times 2 as soon as the quantity changes, before any reload |
| Removing the item empties the cart | Remove leaves no lines, the cart says it is empty and the header's cart shows no items, and all three still hold after a reload |

### Manage products

Its first two steps stop the journey when they fail, since nothing after them
can run; every later step is soft. After each change the journey reloads the
store's pages until they show it, for up to a minute, and says how long the store
took. The price, name and restore steps look for the photo too, until a step
finds the store showing the product wrong, so a photo the store lost fails the step
that first misses it while each later step still reports on its own change and
says it didn't look for the photo. Whatever the run added comes off the store at
the end, even after a failed step.

| Step | What it proves |
| --- | --- |
| The owner can open Commerce Products | Commerce Products opens in the store admin with its Add product form, and its product pages offer Rename and Archive product (or Restore). When they don't, the journey stops before adding a product it couldn't take off the store again. On a store with no products yet, the new product's page gets this check before it has a price, since the store doesn't list an unpriced product |
| The owner adds a product with a price and a weight | The owner adds a physical product in Commerce Products and saves its price ($12.00) and weight (8 oz). Commerce confirms each save and shows the product's ID. When it doesn't, the journey stops here |
| The owner uploads a photo and makes it the product's image | The owner uploads a photo to EmDash's Media library, then presses Choose image on the product's Commerce page and picks that photo, and Commerce says "Image saved" |
| The photo is still the product's image after a reload | After Commerce Products is opened afresh, the product's page shows the same photo under Images (the Media library file the owner picked), loaded, with Change image beside it ("No image", another image, or one that doesn't load, fails). Skipped when the photo wasn't chosen |
| The Shop list shows the new product with its name, price and photo | The homepage's Shop list shows the product's name, $12.00 and the photo the owner chose, loaded (the store's placeholder or another photo fails) |
| The owner gives the product its own page in a new category | The owner makes and publishes a category in EmDash, then a product page linked to the product by the Product ID Commerce shows, puts the page in the category and publishes it. EmDash's list of product pages then shows it as Published, with View published linking to its address |
| The product page and its category page show the product | The Shop card links to the new page, which shows the name, price and chosen photo, a ready Add to cart and a link to its category; the category page lists the product with its name, price and chosen photo. Skipped when the page wasn't published |
| The product's links open its page | Pressing the product's Shop card, and View details on its category page, opens its page, which answers HTTP 200 headed with the product's name. Skipped when the page wasn't published |
| A new price shows on the store | After the owner saves $13.50, the Shop list, the product page and the category page all show it |
| A new name shows on the store | After the owner renames the product in Commerce, the Shop list, the product page's heading and the category card all show the new name |
| Archiving the product takes it off the store | After the owner archives it, the Shop list and the category page stop listing it, and its page answers HTTP 404 saying the product is no longer available |
| Restoring the product puts it back on the store | After the owner restores it, the Shop list, its page and its category page show it again with its new name and price. Skipped when it wasn't archived |
| The test takes its product, page and category off the store | The test archives the product, under whatever name and state Commerce shows for it then, and moves its page and category to EmDash's Trash; within a minute the store lists none of them and their addresses stop answering HTTP 200. Runs whenever the journey added anything, or pressed Add product |

### Full catalog

Its first two steps stop the journey when they fail, since products need
Commerce Products and their pages need a category; every later step is soft, so
one run lists everything the store gets wrong with a full catalog. A big catalog
means many photos and admin calls, so this journey paces itself the most (see the
store's request limit under [Requests stay within the selected sites](#requests-stay-within-the-selected-sites)).

| Step | What it proves |
| --- | --- |
| Commerce Products opens and lists every product | Commerce Products opens in the store admin and every page of its list turns, however many products the store has |
| The catalog's categories are published | Each of the catalog's categories is a published category in EmDash, with a page on the store. The owner adds and publishes any that are missing, and publishes one an earlier run saved but didn't publish; two unpublished categories by one title stop the journey, since the test can't tell which to publish, and so does a list that doesn't answer the test's search, rather than having a category added twice. On a store running Commerce before 0.3.0-beta.4 a missing category stops the journey with nothing added |
| The owner adds what the catalog lacks | Every catalog product Commerce doesn't have, or the store doesn't show whole, gets what it lacks as an owner gives it: added in Commerce Products (or restored, when archived) with its price and weight, its own photo uploaded to the Media library and chosen as its image when Commerce shows none, and a published page in its category. A price or weight Commerce already has right isn't saved again, and a product Commerce already has whole, which the store shows wrong anyway, is named as such and left to the next steps. New products' photos go up together before they're added; when they don't all go up, that's reported and each of those products gets its photo uploaded as it's added. A product Commerce already has gets its photo uploaded only when its screen shows no image. A product the test can't complete is reported with what was done for it first. A page an earlier run saved but didn't publish is finished and published rather than added again; a published page the store doesn't show is reported and left for the owner, unless the product was just restored, since the store hid it while it was archived (the later steps check it). So is a product whose name Commerce Products lists more than once, archived products included, since the test can't tell which one is the catalog's. It decides only from what the store shows, so when the Shop list or a category page won't open, or the Shop list shows no products without saying it has none, it adds nothing and fails. Each product it adds gives the journey two more minutes before it times out. Passes with nothing to do once the store has the whole catalog. On a store running Commerce before 0.3.0-beta.4 it adds nothing and fails, since there the owner couldn't save products with a full catalog in place |
| The Shop list shows every catalog product with its own price and photo | The homepage's Shop list shows each catalog product once, at its own price, with its own photo, loaded (the store's placeholder, "No image", or one photo shown for two products fails), linked to its page |
| Each category page lists its products with their own price and photo | Each category's page lists its own products the same way, each linked to the page its Shop card links to, and none of the other categories' |
| Every catalog product's page opens with its name, price and Add to cart | The shopper opens every catalog product's page from its Shop link, one at a time and at the shopper's pace. Each answers HTTP 200, is headed with the product's name, shows its price, and has an Add to cart button wired to the cart that a shopper can press (the test never presses it). When the Shop list couldn't be read or showed none of the catalog's products, it fails with that one reason |
| The owner saves a product's weight with the whole catalog in place | With every page of Commerce Products read again and the whole catalog listed, the owner opens "Catalog Tee 01" and saves its weight, and Commerce keeps it. On Commerce 0.3.0-beta.3 this failed once a store had more than about six products |

### Mark as completed

The steps that place an order or make the agent's key stop the journey when
they fail, since nothing after them can run; every other step is soft. Whenever
the key was made, the last step deletes it.

| Step | What it proves |
| --- | --- |
| The owner can open Commerce Orders | Commerce Orders opens in the store admin. When it doesn't, the journey stops here |
| A shopper places a Stripe TEST order for the owner to complete | As in Buy and ship, a shopper pays for a physical product with the test card and Commerce records the payment. Skipped when `DINKUS_E2E_ORDERS_TO_COMPLETE` names an order |
| The owner marks the order completed with a carrier and tracking number | The owner opens the order in Commerce Orders, presses Complete order and types USPS and a tracking number made for the run; Commerce says "Order completed" and shows the order Completed with both. Only a Processing TEST order is completed; any other fails the step and is left alone |
| Commerce Orders keeps the owner's order Completed | Opened again from the list, the order is listed Completed and still shows its carrier and tracking number |
| The test makes a one-hour key for the agent | EmDash makes an admin key named "Live test agent <date and time>" for the signed-in owner, set to stop working after an hour. If EmDash makes a key but sends none the test can use, the test deletes it straight away and the journey stops |
| A shopper places a second Stripe TEST order for the agent to complete | As above, for the agent's order. Skipped when `DINKUS_E2E_ORDERS_TO_COMPLETE` names a second order |
| An agent marks the order completed through Commerce's orders API, sending no carrier or tracking number | With only the key, the agent reads the order and completes it at the version it read; Commerce answers "saved" with the order completed, its version raised and no carrier or tracking number. Only a processing TEST order is completed |
| Commerce Orders shows the agent's order Completed | In the store admin the agent's order is listed Completed, and its page shows "Not recorded" for the carrier and the tracking number |
| The test deletes the agent's key | EmDash deletes the key, and a call with it then gets HTTP 401. Runs whenever the key was made |

### Problems

The steps that open Commerce Orders, open the checkout and pay stop the journey
when they fail, since nothing after them can run; every other step is soft, so
one run reports every card's message. A captcha on Stripe stops the journey at
once, unpaid, since nobody answers it for the test.

| Step | What it proves |
| --- | --- |
| The owner can open Commerce Orders | Commerce Orders opens in the store admin, and the test notes the newest TEST order, so it can tell later that the refused cards made no order |
| A shopper opens Stripe Checkout for one product | As in Buy and ship, a shopper puts a physical product in the cart, gives a US delivery address and reaches Stripe's hosted Checkout in test mode; a session that isn't in test mode stops the journey here, before any card. A checkout an earlier run left open is reopened instead of starting another |
| A declined card is turned down with a clear message and no order | Stripe answers 4000 0000 0000 0002 with "Your card has been declined.", and Commerce still reports the checkout waiting for payment, with no order |
| A card without enough funds is turned down with a clear message and no order | The same for 4000 0000 0000 9995 and "Your card has insufficient funds." |
| A card that fails the bank's security check is turned down with a clear message and no order | 4000 0027 6000 3184 brings up Stripe's test bank check; the test presses Fail (again if the test page ignored a press), Stripe says it can't authenticate the payment method, and Commerce still waits for payment |
| The shopper leaves Stripe by its back link and lands on the cart | Stripe's link back to the store opens the store's cart page |
| The cart offers a way back to the same Stripe checkout | After "Check checkout status", the cart's "Return to secure checkout" link goes to the same Stripe checkout, and its checkout button stays locked, so the shopper can't start a second one |
| The shopper goes back to Stripe and pays once with the 4242 test card | The shopper follows that link (or, when the cart offers none, the test opens the checkout's own Stripe page) and pays once, and Commerce records the payment |
| The thank-you page confirms the order and empties the cart | As in Buy and ship |
| Commerce Orders lists one new order for the checkout, Processing | The order is listed Processing, and it is the only TEST order newer than the one noted at the start |
| The owner marks the order completed, so the run leaves no order open | As in Mark as completed, with no carrier or tracking number, since nothing was sent. Only a Processing TEST order is completed |

If Stripe takes a payment from a card it should turn down, that card's step
fails, the other cards and both cart steps are skipped, and "Commerce records the
payment Stripe took" checks that order in place of paying again.

### Buy a label in the store admin

The steps that open the Shipping page, place and list the order, see prices,
buy the label, wait for Commerce to complete the order and cancel the label stop
the journey when they fail, since what follows needs them; the other steps are
soft. The Ship plugin draws the Shipping page from hosted Ship's answer on every
press, so the journey tests the plugin and hosted Ship together. Since it may wait
up to `DINKUS_E2E_COMPLETE_WAIT_SECONDS` twice, it gets twice that on top of the
30 minutes every journey has.

| Step | What it proves |
| --- | --- |
| The Shipping page lists Ship's orders in the store admin | The store admin's menu has one Shipping page (or `DINKUS_E2E_SHIPPING_ADMIN`), and it opens on Ship's list of orders, the only page with a Refresh button, rather than on why it can't use Ship: no pass from DinkusKit.com, Ship out of reach, settings to fix, or a sign-in that isn't an Editor or Administrator. The proof notes the Ship plugin and its version. When it doesn't, the journey stops here |
| A shopper places a Stripe TEST order | As in Buy and ship, a shopper pays for a physical product with the test card and Commerce records the payment |
| Commerce Orders lists the order as Processing | Commerce Orders lists the order, TEST and Processing; opening it also sends Ship the paid orders it doesn't have yet |
| The Shipping page lists the order with no label | The Shipping list shows "#N (TEST)" with "No label" (opening the Shipping page again every 15 seconds, for up to `DINKUS_E2E_COMPLETE_WAIT_SECONDS`), and Open shows the order's page |
| The order's page offers a free sandbox label for the package's weight | The order's page says it's a TEST order, shows Ship to, Items, the items' weight and "No label", offers a free Pitney Bowes sandbox label as the label kind, and fills in the weight as the items' weight plus the chosen box's empty weight. When hosted Ship isn't on Pitney Bowes's sandbox, it offers a practice label instead and this step fails |
| See prices quotes USPS services for the package | The browser accepts the filled-in weight, See prices fills the Service list with Ship's prices, and one is for the service `DINKUS_E2E_SERVICE` names (Ground Advantage unless set). Before ship#45 the browser took only weights ending in .1 (1.1, 2.1 and so on), so with a weight such as 4 oz See prices did nothing |
| Buy label buys the sandbox label at the quoted price | Buy label says "Label bought, $X.XX sandbox. Tracking ..." at the quoted price, and the order's page shows the label's service, its tracking number marked "test, not trackable", its postage as "sandbox price, nothing charged" and Status "Label bought" |
| Print label opens the label's PDF from Ship | Print label opens Ship's print link in a new tab, and the link answers with the label's PDF, waiting up to two minutes while Ship fetches it from Pitney Bowes. Its first page draws as a picture of the label, shown in the browser for the step's screenshot |
| Opening Commerce Orders collects the label and completes the order | Commerce Orders shows the order Completed with carrier USPS and the label's tracking number, opened every 30 seconds for up to `DINKUS_E2E_COMPLETE_WAIT_SECONDS` |
| Print label still opens the same PDF once the order is Completed | With the order Completed, the Shipping list still shows "Label bought", the order's page still shows the label, and Print label opens the same PDF as before (the same SHA-256). Before ship#45 the Shipping page lost the label once Commerce completed the order, so it couldn't be printed or cancelled |
| Cancel label voids the sandbox label and the order stays Completed | Cancel label first asks, saying the sandbox label is voided with Pitney Bowes and the order stays as it is in Commerce. After the confirm the page says exactly "Label cancelled.", promising no refund for postage nobody paid, shows no live label and Status "Label cancelled", says the order is Completed in Commerce, and lists the label under Earlier labels as cancelled |
| Shipping lists the order as Label cancelled and Commerce keeps it Completed | The Shipping list shows "Label cancelled", and Commerce Orders still shows the order Completed with the label's carrier and tracking number |

## Proof

A journey's verdict is PASS only when every step passed or was skipped for a
stated reason; an error between steps (a page that won't open) or before the
first one (a saved profile another Chrome holds) fails it too. The run's verdict
is PASS only when every journey passed and the run wasn't interrupted, and
`npx playwright test` exits non-zero otherwise. The run prints each journey's
verdict, then `Verdict:` and the path to `PROOF.md`.

Each run writes `~/.dinkus-e2e/proof/<run>/`: `PROOF.md` and `report.json` (each
journey's verdict, the result and detail of every step, the order, tracking
number and PDF hash, and the plugins and versions the store ran, read from its
admin), a screenshot per step, `label.pdf` and its rendered first-page picture
`label.pdf.png`. Buy a label in the store admin saves its label as
`store-admin-label.pdf` with its picture, and the copy it printed once the order
was Completed as `store-admin-label-completed.pdf`. With `DINKUS_E2E_VIDEO=1` it also keeps a `.webm` video of each
browser window under `video/`. The saved profile's window stays open for the
whole run, so for one video per journey, run the journeys one at a time
(`npm run journey -- cart`). The test hides the code it types
into Cloudflare Access's sign-in, so neither screenshots nor videos show it,
and wipes it from the page when that sign-in fails. The run keeps no Playwright
trace, even for a failed journey: a trace holds every request's headers, the
sign-in cookies for the store's Cloudflare Access and DinkusKit.com among them.
For the same reason a failed step's error reaches the proof, the console and
Playwright's report as its first line alone. Below that line Playwright lists a
request's headers, the addresses a page went to, the elements a locator matched
and the values an assertion saw, and an assertion adds a snapshot of the page,
its links and what its fields hold; none of that is kept, and Playwright's notes
on a failure (`error-context.md`) take no snapshot of the page either. Each
address on that first line loses its query, where a sign-in link, a connect
address or Ship's sign-in code carries its secret, and a Ship print link loses
its token.

On Linux, label rendering requires Poppler's `pdftoppm`; macOS uses Quick Look.
A missing renderer, failed render or invalid picture fails the label-PDF step
rather than silently omitting visual proof. The run records image dimensions
and SHA-256; inspect the picture to verify the label is legible.
