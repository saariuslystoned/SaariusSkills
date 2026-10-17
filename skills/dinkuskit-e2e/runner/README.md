# DinkusKit live e2e

One saved Playwright test against the live services: a Stripe TEST order on the
store, the order in Commerce, a Pitney Bowes sandbox label in Ship, and Commerce
marking the order Completed with the same tracking number.

It runs in a visible Chrome window with its own saved profile
(`~/.dinkus-e2e/profile`), so sign-ins carry over between runs. DinkusKit.com and
the store's Cloudflare Access both sign in by email. The test reads those emails
itself through `DINKUS_E2E_MAIL_CMD`, so nobody has to step in.

## Run

```sh
npm install
DINKUS_E2E_SITE_ID=<site id> \
DINKUS_E2E_OWNER_EMAIL=<store owner's DinkusKit.com email> \
DINKUS_E2E_MAIL_CMD='<command printing recent mail for "$DINKUS_MAIL_QUERY">' \
npm test                 # full run: checkout to Completed
npm run finish           # start from an existing order (DINKUS_E2E_ORDER=1001, or the only unfinished TEST order)
```

`DINKUS_E2E_MAIL_CMD` runs under bash with `DINKUS_MAIL_QUERY` set to a Gmail
search (for example `from:accounts@dinkuskit.com subject:"Sign in to DinkusKit" newer_than:1h`).
It must print the matching messages' bodies. The test pulls out the newest link or
code it hasn't seen before. Without it, the test waits for a person to sign in
in the window.

Each run writes `proof/<run>/`: `PROOF.md` and `report.json` (pass or fail per
step, order, tracking, PDF hash), a screenshot per step, `label.pdf` and its
picture.

Other settings live in `support/env.mjs`: store, Ship and DinkusKit.com
addresses, label service (`GA`), the shopper's address, and how long to wait for
Completed.
