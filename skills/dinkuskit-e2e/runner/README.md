# DinkusKit live e2e

One saved Playwright test against the live services: a Stripe TEST order on the
store, the order in Commerce, a Pitney Bowes sandbox label in Ship, and Commerce
marking the order Completed with the same tracking number.

It runs in a visible Chrome window with its own saved profile
(`~/.dinkus-e2e/profile`), so sign-ins carry over between runs. DinkusKit.com
signs in with an emailed link, and the store admin's Cloudflare Access app signs
in with an emailed one-time PIN. The test reads both emails itself through
`DINKUS_E2E_MAIL_CMD`, so nobody has to step in. If the Access app offers only
Google, set `DINKUS_E2E_ADMIN_SIGNIN=wait` and sign in once in the window.

## Run

```sh
npm ci
DINKUS_E2E_SITE_ID=<site id> \
DINKUS_E2E_OWNER_EMAIL=<store owner's DinkusKit.com email> \
DINKUS_E2E_MAIL_CMD="$PWD/scripts/gog-mail.sh" \
npm test                 # full run: checkout to Completed
npm run finish           # start from an existing order (DINKUS_E2E_ORDER=1001, or the only unfinished TEST order)
```

`DINKUS_E2E_MAIL_CMD` runs under bash with `DINKUS_MAIL_QUERY` set to a Gmail
search (for example `from:accounts@dinkuskit.com subject:"Sign in to DinkusKit" newer_than:1h`).
It must print the matching messages' bodies. The test pulls out the newest link or
code it hasn't seen before. `scripts/gog-mail.sh` does this read-only with gogcli
for agent@smokyproduct.co. Without a mail command, the test waits for a person to
sign in in the window.

## What it proves

After the label, the test waits up to `DINKUS_E2E_COMPLETE_WAIT_SECONDS` (420)
for Commerce's 5-minute background check to collect it, without opening the store
admin. That check passes or fails on its own row. If it hasn't collected the
label, the test opens Commerce Orders the way an owner would, since that collects
labels too, and checks Completed and the tracking number from there. The verdict
is PASS only when every step passed, and `npx playwright test` exits non-zero
otherwise.

Each run writes `proof/<run>/`: `PROOF.md` and `report.json` (pass or fail per
step, order, tracking, PDF hash), a screenshot per step, `label.pdf` and its
picture.

Other settings live in `support/env.mjs`: store, Ship and DinkusKit.com
addresses, label service (`GA`), the shopper's address, and the Gmail search for
the Access code email (`DINKUS_E2E_ACCESS_MAIL_QUERY`).
