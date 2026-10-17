---
name: dinkuskit-live-test
description: Run the saved DinkusKit live test (Stripe TEST order, Commerce order, Pitney Bowes sandbox label in Ship, Commerce marks it Completed) and hand back its proof. Use when the owner says "run the test", asks to prove a DinkusKit release or plugin update works on a live store, or wants a stuck TEST order finished.
---

# DinkusKit live test

One saved Playwright test proves the DinkusKit stack works on a live test store.
A shopper pays with Stripe's test card, the order shows up in Commerce, Ship makes a
Pitney Bowes sandbox label with a real PDF and tracking number, and Commerce marks
the order Completed with the same tracking number.

The test runs unattended. DinkusKit.com and the store admin's Cloudflare Access
login both sign in with emailed links or codes, and the test reads them from the
test inbox itself. Nobody types a password, opens a password manager or approves
anything during a run. Read-only access to that inbox is the one standing
authorization the test needs.

## Run the test

1. Work in this skill's [runner](runner/) folder. Run `npm ci` the first time. If
   the skill folder is read-only, copy `runner/` to `~/.dinkus-e2e/runner` and work
   there.
2. Check that `~/.dinkus-e2e/env` names the store, its site id and the test inbox.
   If it doesn't, set the machine up once from [setup](references/setup.md). Ask the
   owner only for values you can't find yourself.
3. Start the run and let it finish. It opens a Chrome window with its own saved
   profile.
   - `npm test` runs the full test, from a new Stripe TEST checkout to Completed.
   - `npm run finish` finishes an order that already exists. Set
     `DINKUS_E2E_ORDER=1001` to pick one, or leave it unset to pick the only TEST
     order still waiting for a label.

   A full run takes about 15 minutes, because it gives Commerce's 5-minute
   background check up to 7 minutes to collect the label on its own.
4. Read the proof. The run ends with `Verdict: PASS` or `Verdict: FAIL` and the path
   to its `PROOF.md`. Read `PROOF.md` and `report.json`, and actually look at
   `label.pdf.png` (macOS draws it from the label PDF).
5. Hand back the verdict first. Then give one line per step with its result and
   detail, the order number, the tracking number and the proof folder, and show the
   label picture. On FAIL, lead with the failing step and its reason.

## For a new plugin release

1. Make sure the test store runs the release. The proof lists the store's plugins
   and their versions under "plugins". If it shows the old version, update the
   plugin from the store admin's Plugins page, then run the test again.
2. Run the full test with `npm test`.
3. Hand back the verdict with the plugin versions it covered, so the owner knows
   which release passed.

## Rules

- TEST mode only. The checkout pays only with Stripe's test card
  4242 4242 4242 4242, and Ship makes sandbox labels only for TEST orders. Stop if
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
- A failed run exits non-zero. A failure only on "Commerce's 5-minute check
  collects the label", with the steps after it passing, means the store's
  background check didn't collect the label and opening Commerce Orders did.
  Report it that way.

## What each step proves

[runner/README.md](runner/README.md#what-it-proves) lists the steps, what each one
proves and every setting. [Status](references/status.md) records what has passed
live so far and what is still open.
