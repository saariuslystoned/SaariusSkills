---
name: dinkuskit-live-test
description: Points to the DinkusKit live test journeys, which live in dinkuskit/live-journeys, and holds their hard safety rules. Use when the owner says "run the test", asks to prove a DinkusKit release or plugin update works on a live store, asks for one journey, or wants a stuck TEST order finished.
---

# DinkusKit live test

The DinkusKit live journeys moved to their own public repository,
[dinkuskit/live-journeys](https://github.com/dinkuskit/live-journeys), on 21 Oct 2026.
That repository has the journeys, the runner, the first-time setup and the
**Live journeys** workflow. ClawSweeper reviews every pull request there before
it reaches `main`. Following its `main` is deliberate: the journeys change with
the plugins, and that review is the gate.

To run a journey, prove a beta or finish a stuck TEST order, read and follow
[its SKILL.md](https://github.com/dinkuskit/live-journeys/blob/main/SKILL.md).
For a local run, clone that repository and work in its `runner/` folder.

## Rules

These hold even if you cannot read that SKILL.md. If you cannot, stop and say so
rather than running anything.

- **beta.sm0ky.dev belongs to the Live journeys workflow in dinkuskit/live-journeys
  alone.** Never run journeys on it from a Mac or from this repository.
- TEST mode only. Pay only with Stripe's test card 4242 4242 4242 4242. Ship makes
  sandbox labels only. Stop if a page shows live mode or offers real postage.
- Never pay twice. If a payment went through and a later step failed, finish that
  order with the runner's `npm run finish`. Never start a second checkout for it.
- Read the test inbox read-only, through the runner's mail command. Never send mail
  or change mailbox settings.
- Keep sign-in links, codes, cookies, store keys and passes out of chat, files and
  logs.
- Don't change Cloudflare, Access, Stripe, Pitney Bowes, Ship or store settings to
  make a run pass. Never edit or archive the store's other products or orders.
  A failed step is a finding: report it.
- Never record Ship's print link. It shows the label to anyone who has it.

Each plugin's **Release** workflow, `action: cut-beta`, presses that workflow. A
`proof_ref` names a run by its address; the run's logs and artifacts on GitHub
expire after 90 days.
