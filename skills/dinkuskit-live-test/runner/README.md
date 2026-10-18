# DinkusKit live test runner

Saved Playwright journeys against a live test store and the live services. Each
journey is one spec file in [tests](tests/), tagged with its stage in the
journeys plan:

| Journey | Stage | What it covers |
| --- | --- | --- |
| [Buy and ship](tests/buy-and-ship.spec.mjs) | `@running` | A Stripe TEST order on the store, the order in Commerce, a Pitney Bowes sandbox label in Ship, and Commerce marking the order Completed with the same tracking number |
| [Storefront](tests/storefront.spec.mjs) | `@next` | A new shopper's first look: the homepage, the product list, a product page and its category page |
| [Cart](tests/cart.spec.mjs) | `@next` | A new shopper adds a product to the cart, changes its quantity and removes it, with the cart total right each time |
| [Manage products](tests/manage-products.spec.mjs) | `@next` | The owner adds a product, gives it a photo that stays after a reload and a published page in a new category that the store links to, changes its price and name, and archives and restores it, with the store following each change |
| [Mark as completed](tests/mark-completed.spec.mjs) | `@next` | The owner marks a paid TEST order completed in Commerce Orders, typing a carrier and tracking number, and an agent completes another through Commerce's orders API, sending neither; both end Completed |
| [Problems](tests/problems.spec.mjs) | `@next` | A shopper's checkout going wrong: Stripe turns down a declined card, a card without enough funds and a card that fails the bank's security check, each with a clear message and no order; the shopper leaves Stripe for the cart, finds the way back to the same checkout and pays once with the test card, and the owner completes that one order |

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
npm run journey -- storefront # one journey, by its file name (storefront, cart, manage-products, mark-completed, problems, buy-and-ship)
npm run finish                # Buy and ship from an existing order (DINKUS_E2E_ORDER=1001, or the only unfinished TEST order)
npm run unit                  # the runner's own offline checks
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

Mark as completed places two Stripe TEST orders the way Buy and ship places
one, paying each once with the test card, and leaves both Completed. The owner
completes the first in Commerce Orders. For the second, the test makes an admin
key with the saved profile's admin sign-in, set to stop working after an hour,
and the agent completes the order with that key alone. The test deletes the key
at the end of the run, even after a failed step. The key only ever travels in
the test's own calls, never through the browser, so it can't reach the proof or
the browser's trace. When Cloudflare Access fronts the store's API as well as
its admin, the agent's calls also carry the saved Access sign-in, as an agent's
Access service token would. To complete existing Processing TEST orders instead
of placing new ones, set `DINKUS_E2E_ORDERS_TO_COMPLETE` (the owner's order,
then the agent's).

Problems works in one Stripe TEST checkout and places one order. On Stripe's
hosted Checkout it tries three of Stripe's test cards that never take a payment:
4000 0000 0000 0002 (declined), 4000 0000 0000 9995 (not enough funds) and
4000 0027 6000 3184, which brings up Stripe's test bank check, where the test
presses Fail. Then it leaves by Stripe's link back to the store, which Payments
points at the cart, follows the cart's way back to the same checkout and pays
once with the 4242 test card. The owner completes the order in Commerce Orders,
so the run leaves no order open. If Stripe takes a payment from a card it should
turn down, the test pays nothing more and checks and completes that order
instead. On a store whose cart offers no way back to an open checkout
(Template Store before #100), the cart step fails and the test pays through the
checkout's own Stripe page, as Buy and ship does with a checkout an earlier run
left open.

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
| `DINKUS_E2E_PRODUCTS_ADMIN` | the Products page beside `DINKUS_E2E_ORDERS_ADMIN` | Commerce Products in the store admin, for Manage products |
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
| A card that fails the bank's security check is turned down with a clear message and no order | 4000 0027 6000 3184 brings up Stripe's test bank check; the test presses Fail, Stripe says it can't authenticate the payment method, and Commerce still waits for payment |
| The shopper leaves Stripe by its back link and lands on the cart | Stripe's link back to the store opens the store's cart page |
| The cart offers a way back to the same Stripe checkout | After "Check checkout status", the cart's "Return to secure checkout" link goes to the same Stripe checkout, and its checkout button stays locked, so the shopper can't start a second one |
| The shopper goes back to Stripe and pays once with the 4242 test card | The shopper follows that link (or, when the cart offers none, the test opens the checkout's own Stripe page) and pays once, and Commerce records the payment |
| The thank-you page confirms the order and empties the cart | As in Buy and ship |
| Commerce Orders lists one new order for the checkout, Processing | The order is listed Processing, and it is the only TEST order newer than the one noted at the start |
| The owner marks the order completed, so the run leaves no order open | As in Mark as completed, with no carrier or tracking number, since nothing was sent. Only a Processing TEST order is completed |

If Stripe takes a payment from a card it should turn down, that card's step
fails, the other cards and both cart steps are skipped, and "Commerce records the
payment Stripe took" checks that order in place of paying again.

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
admin), a screenshot per step, `label.pdf` and, on macOS, its picture
`label.pdf.png`. With `DINKUS_E2E_VIDEO=1` it also keeps a `.webm` video of each
browser window under `video/`. The saved profile's window stays open for the
whole run, so for one video per journey, run the journeys one at a time
(`npm run journey -- cart`). The test hides the code it types
into Cloudflare Access's sign-in, so neither screenshots nor videos show it.
