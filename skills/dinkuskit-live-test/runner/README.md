# DinkusKit live test runner

One saved Playwright test against the live services: a Stripe TEST order on the
store, the order in Commerce, a Pitney Bowes sandbox label in Ship, and Commerce
marking the order Completed with the same tracking number.

It runs in a visible Chrome window with its own saved profile
(`~/.dinkus-e2e/profile`), so sign-ins carry over between runs. DinkusKit.com
signs in with an emailed link, and the store admin's Cloudflare Access app signs
in with an emailed one-time PIN. The test reads both emails itself through the
mail command, so nobody has to step in. If the Access app offers only Google, set
`DINKUS_E2E_ADMIN_SIGNIN=wait` and sign in once in the window.

## Run

```sh
npm ci
npm test            # full run: checkout to Completed
npm run finish      # start from an existing order (DINKUS_E2E_ORDER=1001, or the only unfinished TEST order)
npm run unit        # the runner's own offline checks
```

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

| Step | What it proves |
| --- | --- |
| Place a Stripe TEST order on the store | A shopper can add a physical product to the cart and pay on Stripe's hosted Checkout with the test card |
| Commerce Orders shows the paid TEST order | Commerce recorded the order as TEST, provider-paid and Processing |
| Ship has the order | Commerce sent the order to Ship |
| Make the Pitney Bowes sandbox label | Ship quotes sandbox prices and buys a sandbox label |
| Label is a TEST SANDBOX label with a tracking number | The label is a sandbox label, not a practice one, and carries a tracking number |
| Label PDF downloads and is a real PDF | Ship serves the provider's PDF |
| Commerce's 5-minute check collects the label | Commerce's background check collects the label without anyone opening the store admin |
| Opening Commerce Orders collects the label | Runs only when the check above didn't: an owner opening Commerce Orders collects it |
| Commerce marks the order Completed with the same tracking | Ship shows Commerce completed the order with the label's tracking number |
| Commerce Orders shows Completed in the store admin | The store admin agrees, with carrier and tracking |

The verdict is PASS only when every step passed or was skipped for a stated
reason, and `npx playwright test` exits non-zero otherwise.

Each run writes `~/.dinkus-e2e/proof/<run>/`: `PROOF.md` and `report.json` (the
result and detail of every step, the order, tracking number and PDF hash, and the
plugins and versions the store ran, read from its admin), a screenshot per step,
`label.pdf` and, on macOS, its picture `label.pdf.png`.
