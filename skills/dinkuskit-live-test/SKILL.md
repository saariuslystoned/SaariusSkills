---
name: dinkuskit-live-test
description: Run the saved DinkusKit live test journeys (Buy and ship - Stripe TEST order, Commerce order, Pitney Bowes sandbox label in Ship, Completed; Storefront - homepage, product list, product page, category page; Cart - add, change quantity, remove, cart total; Manage products - add a product with a photo, page in a category, new price and name, archive and restore; Full catalog - a standing catalog of several categories of products, each with its own price, photo and page, shown whole on the Shop list, category pages and product pages; Mark as completed - the owner and an agent each complete a paid TEST order without a label; Problems - declined, insufficient-funds and failed bank check test cards turned down with no order, leaving Stripe for the cart and coming back, paying once) and hand back their proof. Use when the owner says "run the test", asks to prove a DinkusKit release or plugin update works on a live store, asks for one journey, or wants a stuck TEST order finished. Beta Registry listings are proved on beta.sm0ky.dev by Live journeys before a real Registry release. Payments is the reference procedure.
---

# DinkusKit live test

Saved Playwright journeys prove the DinkusKit stack works on a live test store.
In Buy and ship, a shopper pays with Stripe's test card, the order shows up in
Commerce, Ship makes a Pitney Bowes sandbox label with a real PDF and tracking
number, and Commerce marks the order Completed with the same tracking number. In
Storefront, a new shopper's homepage, product list, product page and category
page show no developer notices and every product's name, price and photo. In
Cart, a new shopper adds a product, changes its quantity and removes it, and the
cart's count and total follow each change. In Manage products, the owner adds a
product, gives it a photo that is still its image after a reload and a published
page in a new category that the store links to, changes its price and name, and
archives and restores it, and the Shop list, product page and category page
follow each change. In Full catalog, the store carries a catalog as big as a real
shop's, several categories of products that each have their own price, weight,
photo and page; the test adds what's missing and leaves it there, then checks
that the Shop list, every category page and every product page show all of it,
and that the owner can still save a product with all of it in place. In Mark as
completed, the owner marks a paid TEST order completed in Commerce Orders with a
carrier and tracking number, and an agent marks another completed through
Commerce's orders API with neither, using an admin key the test makes for an
hour and deletes at the end. In Problems, Stripe
turns down three of its test cards that never pay (declined, not enough funds,
a failed bank security check) with a clear message and no order, the shopper
leaves Stripe for the cart and finds the way back to the same checkout, pays
once with the test card, and the owner completes that one order.

Each journey has a stage. `@running` journeys run on every `npm test` and must all
pass on the beta store, beta.sm0ky.dev, before a real Registry release. A new
journey starts as `@next` and moves to `@running` once it has passed there. The
[runner README](runner/README.md) lists the journeys and their stages. Buy a
label in the store admin, the Ship plugin's journey, became `@running` after it
first passed on the beta store (20 Oct).

## Release a plugin

The reference procedure is
[payments `RELEASING.md`](https://github.com/dinkuskit/payments/blob/main/RELEASING.md),
steps 1 to 5. The locked decision is `release-beta-cut-071` in
[dinkuskit `docs/plans/release-process.md`](https://github.com/dinkuskit/dinkuskit/blob/main/docs/plans/release-process.md).
Do not publish by hand, and do not hand-push a tag. Do not use `npm view` as the
release check. The release check is the Registry listing.

Payments, Commerce and Ship all run that procedure with the same **Release**
workflow (`.github/workflows/release.yml`), which has two actions, `cut-beta` and
`promote`. `emdash-release.yml` has no button of its own. None of the three uses
Changesets pre mode any more.

1. Every pull request to `main` adds a changeset. Merging it does not publish.
2. **Cut beta.** On the plugin's repository, press **Run workflow** on **Release** with
   `action: cut-beta`. That publishes `dinkus-<plugin>-beta` at `X.Y.Z-beta.N`
   from `main`, then presses **Live journeys** in this repository with `beta` set
   to `dinkus-<plugin>-beta X.Y.Z-beta.N`. The press uses the `LIVE_JOURNEYS_TOKEN`
   secret. Without that secret the beta is still published, and the same workflow
   can be pressed by hand with the same `beta`.
3. **Proof** is this repository's **Live journeys** workflow, on
   **https://beta.sm0ky.dev** only. It first runs **Update the store**
   (`npm run update-store`, tag `@update`). That moves each DinkusKit beta plugin
   the store already runs to the newest Registry beta, in place, the way the
   admin's **Update** button does. A run a release started waits up to 15 minutes
   for the Registry to offer the named beta, then installs that one. It stops if
   an update asks for new permissions, opens routes to visitors who are not signed
   in, or changes agent tools. The owner then updates that plugin by hand from
   **Plugins** and presses the workflow again with the same `beta`. It does not
   install a plugin the store is not already running (that is the `@next` journey
   Install the Registry plugins), and it does not switch a
   plugin between its beta listing and its release listing. After the update
   passes, the workflow runs every `@running` journey, headless. One run uses the
   store at a time. The run page shows pass or fail, the plugin versions tested,
   and why an update stopped. Screenshots go to the private R2 bucket. The
   `proof_ref` is that run's address followed by `(X.Y.Z-beta.N @running pass)`.
4. **Promote.** After that recorded pass, press **Run workflow** on **Release**
   with `action: promote`, `beta_version` set to `X.Y.Z-beta.N`, and that
   `proof_ref`. If `main` has moved since the beta was cut, the gate refuses it.
   Cut a new beta first. Promote opens the `ci: release vX.Y.Z` pull request. It
   does not publish.
5. On that pull request, run `@clawsweeper review`. Payments' `RELEASING.md` says
   Ryan's merge of that reviewed pull request publishes `dinkus-<plugin>` at
   `X.Y.Z`. This runner does not merge it and does not publish it.

A pass on any other store is not this gate. After a Live journeys pass on
beta.sm0ky.dev, no Mac runs journeys on that store.

The test runs unattended. DinkusKit.com and the Cloudflare Access login in front
of the store admin (or of the whole test store) both sign in with emailed links or
codes, and the test reads them from the test inbox itself. Nobody types a password, opens a password manager or approves
anything during a run. Read-only access to that inbox is the one standing
authorization the test needs.

## Run the test

Before local setup, choose the store. **beta.sm0ky.dev belongs to the GitHub
Live journeys workflow alone**; see the [runner's GitHub route](runner/README.md#run-on-github).
For beta release proof, first inspect existing runs for the requested beta.
Bind the repository/workflow, beta store, requested beta, runner commit, and
run ID plus attempt. Check that the workflow and journey source applies to the
current required `@running` roster and that the selection covers it; once the
run completes, compare its recorded results with that roster.

- Reuse a completed full pass only when every required journey actually passed,
  **Plugins tested** includes the requested plugin version, and its applicable
  `PROOF.md`, `report.json`, browser screenshots, and required label evidence
  can be inspected. A green subset, wrong version, or missing evidence is not
  a full-release pass; name the gap.
- If a matching run is queued or running, retain its exact run ID/attempt and
  follow it with a supported completion notification or bounded wait. Do not
  dispatch a duplicate or run a repeated CI polling loop.
- Start a new run through that existing workflow only when no applicable run
  exists or the owner requests a fresh rerun, under the existing action gates.
  Do not run journeys on the beta store locally.

Existing proof establishes what that run observed, not what a mutable store
still has deployed now. For other test stores, use the local steps below.

1. Work in this skill's [runner](runner/) folder. Run `npm ci` the first time. If
   the skill folder is read-only, copy `runner/` to `~/.dinkus-e2e/runner` and work
   there.
2. Check that `~/.dinkus-e2e/env` names the store, its site id and the test inbox.
   If it doesn't, set the machine up once from [setup](references/setup.md). Ask the
   owner only for values you can't find yourself.
3. Start the run and let it finish. It opens a Chrome window with its own saved
   profile. Nobody should click in that window while it runs; the label and its
   picture are in the proof folder.
   - `npm test` runs every `@running` journey: Buy and ship, Storefront, Cart,
     Full catalog, Manage products, Mark as completed and Problems, in about 35
     minutes, plus about 40 the first time on a store that doesn't carry the
     catalog yet. Buy and ship goes from a new Stripe TEST checkout to Completed.
     The run places four TEST orders and leaves each one Completed. Full catalog
     runs before Manage products, so Manage products works with the whole
     catalog in place.
   - `npm run journey -- storefront` runs one journey, named by its file in
     `runner/tests`. Storefront only reads the pages a shopper sees and places
     no order. Cart fills and empties a new shopper's cart and never checks out.
     Manage products works in the store admin and takes its product, page and
     category off the store again, leaving one archived product and its photo.
     Full catalog adds whatever the standing catalog lacks and leaves it on the
     store for later runs.
     Mark as completed places two Stripe TEST orders and leaves both Completed.
     Problems tries three refused test cards and the way back from the cart in
     one Stripe TEST checkout, pays it once and leaves that order Completed.
     Buy a label in the store admin (`store-admin-label`) places one Stripe TEST
     order, buys and prints a Pitney Bowes sandbox label for it on the store
     admin's Shipping page, and cancels the label once Commerce has completed the
     order.
     Install the Registry plugins (`install-plugins`) installs a named DinkusKit
     beta the beta store does not already run, `dinkus-ship-beta` `0.1.0-beta.1`
     unless `DINKUS_E2E_INSTALL` names others, and leaves one the store already
     runs as it is. It does not type a store key.
   - `npm run finish` finishes a Buy and ship order that already exists. Set
     `DINKUS_E2E_ORDER=1001` to pick one, or leave it unset to pick the only TEST
     order still waiting for a label.
   - When the owner wants to watch a run, set `DINKUS_E2E_VIDEO=1`. Every browser
     window the run opens is recorded into the proof folder's `video/`, with the
     Cloudflare Access code hidden as it's typed. Run the journeys one at a time
     for a video of each.

   Buy and ship takes about 15 minutes, because it gives Commerce's 5-minute
   background check up to 7 minutes to collect the label on its own. Storefront
   and Cart each take about a minute, and Manage products about two, plus up to a
   minute for each change the store is slow to show. Full catalog takes about
   four once the store has the catalog; the run that first adds it takes about a
   minute a product, because it keeps under the store's request limit. Mark as
   completed takes about four, most of it in its two checkouts, and Problems
   about three.
4. Read the proof. The run prints each journey's verdict, then `Verdict: PASS` or
   `Verdict: FAIL` and the path to its `PROOF.md`. Read `PROOF.md` and
   `report.json`, and actually look at `label.pdf.png` (macOS draws it from the
   label PDF) when Buy and ship ran.
5. Hand back the verdict first, with each journey's verdict. Then give one line per
   step with its result and detail, the order number, the tracking number and the
   proof folder, and show the label picture. When the run was recorded, say where
   each video is. On FAIL, lead with the failing steps and their reasons.

## For a new plugin release

For beta.sm0ky.dev, use the existing-run route in [Run the test](#run-the-test)
and follow [Release a plugin](#release-a-plugin). The proof's "plugins" line is
the versions that run tested. Hand those back with the verdict. A real Registry
release waits on promote and the reviewed merge. This runner does not do either.

On a store the Live journeys workflow is not running, `npm test` still runs every
`@running` journey with that store's settings file:
`DINKUS_E2E_ENV_FILE=<that store's settings file> npm test`. That pass is not the
release gate. On a store whose Commerce can't rename and archive a product,
Manage products stops at its first step; on one older than 0.3.0-beta.4, Full
catalog adds nothing. See the runner README's "Run on GitHub".

## Rules

- TEST mode only. The checkout pays only with Stripe's test card
  4242 4242 4242 4242, and Ship makes sandbox labels only for TEST orders.
  Problems also tries three Stripe test cards that never take a payment
  (4000 0000 0000 0002, 4000 0000 0000 9995 and 4000 0027 6000 3184). Stop if
  a page shows live mode or offers real postage. The test itself stops unpaid if
  Stripe opens a session that isn't in test mode or shows a captcha.
- Never pay twice. If a payment went through and a later step failed, finish that
  order with `npm run finish` and `DINKUS_E2E_ORDER=<its number>`. A full run never
  starts a second checkout: when Commerce still holds one as pending, the test pays
  that checkout's own Stripe session instead.
- Read the test inbox only through the runner's mail command, which searches for
  the sign-in emails read-only. Never send mail or change mailbox settings.
- Keep sign-in links, codes, cookies, store keys and passes out of chat, files and
  logs. The proof never needs them.
- Don't change Cloudflare, Access, Stripe, Pitney Bowes, Ship or store settings to
  make a run pass. A failed step is a finding: report it with its reason.
- Manage products changes only the product, page and category it adds, each named
  "Live test" with the run's date and time. Never edit or archive the store's
  other products to make it pass.
- Full catalog changes only the catalog's own categories and products, each named
  "Catalog" and the same on every run, and it never takes them off the store.
  Never edit or archive the store's other products to make it pass.
- Mark as completed completes only TEST orders: the two it places, paying each
  once with the test card, or the Processing TEST orders
  `DINKUS_E2E_ORDERS_TO_COMPLETE` names. It leaves every other order alone.
  Problems completes only the one TEST order it places.
- The agent's key is the only credential the test makes: an admin key for the
  owner that stops working after an hour. It never leaves the test's own calls,
  and the test deletes it at the end of every run. If that last step fails,
  report the key's name and when it stops working, so the owner can revoke it
  sooner under Settings, API Tokens in the store admin.
- A failed run exits non-zero. A failure only on "Commerce's 5-minute check
  collects the label", with the steps after it passing, means the store's
  background check didn't collect the label and opening Commerce Orders did.
  Report it that way.
- A failure on "The thank-you page confirms the order and empties the cart" means
  a shopper who paid didn't see their order confirmed. The steps after it still
  run, so the proof also shows whether Commerce recorded and completed the order.
- Storefront and Cart stop at their first step when a new shopper can't open the
  store at all, such as a Cloudflare Access sign-in the test couldn't get past.
  Report that one finding; the other steps didn't run. Cart also stops when no
  product can be added to the cart, when the product shows no price, or when the
  cart lists it under another name or price than the shopper saw.
- Storefront's other steps are soft, so one run lists every finding: a developer
  notice on the homepage, a product without a name, price or photo, a product
  link that doesn't open, a category page that doesn't list its products
  properly, or a page that says checkout is unavailable on a store that takes checkouts. Report each finding with the page it came from. Store content
  the owner controls, such as a product without a photo, is still a finding.
- Cart's steps after Add to cart are soft too: a cart that shows no total or the
  wrong one, a quantity the header or a reload doesn't keep, or a Remove that
  leaves the item or doesn't stay empty after a reload. Report each finding with
  the amounts the proof gives.
- Manage products stops at its first step when Commerce on the store can't
  rename or archive a product yet. Report that the store needs a Commerce release
  with both (dinkus-commerce-beta 0.3.0-beta.2 or later) and that nothing was
  added. On a store with no products yet it finds that out on the product it
  added, before giving it a price, so report that product as left in Commerce
  Products without a price, where the store doesn't list it. It also stops when
  the product can't be added. Its other steps are soft:
  report each page that didn't follow a change, with how long the test waited.
  When the last step fails, name what it couldn't take off the store, so the
  owner can archive or trash it by hand.
- Full catalog stops when Commerce Products won't open or a category can't be
  published. Its other steps are soft: report each product a page leaves out or
  shows wrong, with the page. When it adds nothing because the store's Commerce
  is older than 0.3.0-beta.4, report that the store needs that release first.
- Mark as completed stops when the owner can't open Commerce Orders, when an
  order can't be placed, or when EmDash won't make the agent's key. Its other
  steps are soft: report a refused completion with Commerce's answer, and an
  order that shows the wrong status, carrier or tracking number with what it
  showed.
- Buy a label in the store admin buys only a sandbox label, for the one TEST
  order it places, and cancels it at the end. It stops when the Shipping page
  says why it can't use Ship (report what the page says), when the order can't
  be placed, when Commerce Orders doesn't list it as Processing, when the
  Shipping page doesn't list it with "No label", when See prices quotes no price
  for the service, when the label can't be bought, when Commerce doesn't
  complete the order, or when the cancel fails. A stop before the cancel leaves
  the sandbox label bought, which charged nothing, and Commerce still completes
  the order with it; say so. Its other steps are soft: report a wrong weight, a
  print link that doesn't answer with the label's PDF, or a Completed order whose
  label the Shipping page lost. Never record Ship's print link: it shows the
  label to anyone who has it.
- Problems stops when the owner can't open Commerce Orders, when Stripe
  Checkout won't open, when Stripe shows a captcha, or when the payment fails.
  Its other steps are soft:
  report each card Stripe didn't turn down with a clear message, with what the
  shopper saw. If Stripe took a payment from a card it should have refused, say
  so first: the test paid nothing more and completed that order instead. A
  failure on "The cart offers a way back to the same Stripe checkout" means a
  shopper who left Stripe couldn't get back to their open checkout from the cart;
  the test still paid once through the checkout's own Stripe page, so the steps
  after it ran.

## What each step proves

[runner/README.md](runner/README.md#what-it-proves) lists the steps, what each one
proves and every setting. [Status](references/status.md) records what has passed
live so far and what is still open.
