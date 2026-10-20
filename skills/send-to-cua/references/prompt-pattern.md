# How a cua prompt is written

Learned from the 21 computer-use prompts written for Bobby between 10 and 20
Oct 2026 and the 8 reports his cua sent back. The cua is the Codex app's
Computer Use on his MacBook: it drives his signed-in browser (Cloudflare,
Stripe, GitHub, Google Cloud, the store admins) and his Terminal, and it stops
at anything the prompt does not cover.

## Shape

1. **One opening paragraph.** What to do, on which one target, and the scope
   fence: "Work on beta.sm0ky.dev only; don't touch e2e-v2." If it runs start
   to finish, say so: "Work start to finish. Stop only where a step says STOP,
   and report what you saw."
2. **Ground rules**, short, before any step:
   - Never write a secret value anywhere: no API tokens, keys, cookies, sign-in
     links or PIN codes in chat, files, logs or screenshots. A secret goes only
     into the one field it belongs in, by clipboard or file, and the clipboard
     is cleared after (`pbcopy < /dev/null`). Keys worth keeping go into
     1Password under a named item.
   - STOP on: creating or widening a token, a new permission, signing in to a
     different account, a password, 2FA code or passkey, a payment, live mode
     or a live key, a real ID or real personal details.
   - Name what must not be touched: the other stores, Workers, Access apps,
     shared login methods, other secrets.
   - "If a command fails, stop, show the error and hand back. Do not improvise
     a different command." Normal pushes only, never `--force`.
3. **Facts** the cua cannot guess: the Cloudflare account ID and which account
   holds which Worker, Worker and branch names, URLs, plugin ids, store site
   ids, the exact text a screen should show.
4. **Numbered steps**, each with where to click or the exact command, what it
   should show, and the STOP condition when it does not. Read-only checks
   first. Record the rollback target (current version id) before changing
   anything. Verify with commands that print one line each, for example
   `curl -s -o /dev/null -w '%{http_code}\n' <url>` with the expected code.
5. **Bobby-only steps** are labelled as his: passkeys, "Authorize publishing",
   EmDash's first setup screen, anything his device asks him to allow.
6. **Report back**: a table of what each step ended on, new and old version
   ids, the rollback command, screenshots by name, every STOP hit with its
   exact text, and what Bobby still has to do. Never a key, code or link.

## Things that went wrong, so prompts say them up front

- **Wrong Cloudflare account.** The cua signed in to an account without
  `dinkus-ship`. Name the account (ID) for every Worker.
- **"Retry build" in Workers Builds** re-runs the old job with its old branch
  and commit, so the source guard refuses it. Set `DINKUS_EXPECTED_COMMIT` to
  the exact commit, then push a new commit.
- **Encryption keys** must come from `npx --yes emdash@1.2.0 secrets generate`
  (first line only, no quotes or line breaks); any other shape breaks every
  plugin's settings on that store.
- **A Worker secret cannot be read back.** When a value replaces a list (for
  example `EMDASH_OPERATOR_ALLOWLIST`), the prompt gives every entry that must
  stay.
- **Registry install consent** stops the cua unless the prompt lists the exact
  permissions, hosts and routes it may accept; anything extra means Cancel and
  STOP.
- **Stripe TEST onboarding** only accepts Stripe's test values (DOB
  01/01/1901, SSN 000000000, address `address_full_match`, phone 000 000 0000,
  code 000000, website https://accessible.stripe.com, the test bank). Name the
  Stripe environment too: the platform's Sandbox and Test mode are different,
  and a webhook in the wrong one receives nothing.
- **Cloudflare Access:** exact paths only, never a wildcard, and never touch
  the shared One-time PIN login or a policy other apps share.
- **Node on Bobby's Mac** lives under mise:
  `export PATH=$HOME/.local/share/mise/installs/node/22.23.2/bin:$PATH`, then
  check `node --version`. Check `gh auth status` before `gh secret set`.
- **Sign-in codes** for agent@smokyproduct.co come from the inbox through
  `gogcli`, read only.
- **One target at a time.** Don't act on a test store while a Live journeys
  run or the Mac runner's Chrome window is using it.
- **Long prompts** are fine (the longest was about 8 KB); the cua follows
  numbered steps and STOP rules well and reports in a table.

## Where proof goes

The cua keeps its own proof under
`~/Developer/side-quests/x-api/runs/<area>/<date>/PROOF.md` with screenshots
next to it. `send-to-cua.sh` also tells it to write the report to
`~/.cua/reports/<stamp>-<name>.md` and copy it to the clipboard.
