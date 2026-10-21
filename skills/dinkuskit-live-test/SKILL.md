---
name: dinkuskit-live-test
description: Run the saved DinkusKit live test journeys (Buy and ship, Storefront, Cart, Manage products, Full catalog, Mark as completed, Problems, Buy a label in the store admin) and hand back their proof. The journeys, runner and Live journeys workflow live in dinkuskit/live-journeys. Use when the owner says "run the test", asks to prove a DinkusKit release or plugin update works on a live store, asks for one journey, or wants a stuck TEST order finished.
---

# DinkusKit live test

The DinkusKit live journeys moved to their own public repository,
[dinkuskit/live-journeys](https://github.com/dinkuskit/live-journeys), on 21 Oct 2026.
That repository has the journeys, the runner, the first-time setup and the
**Live journeys** workflow. ClawSweeper reviews its pull requests.

To run a journey, prove a beta or finish a stuck TEST order, read and follow
[its SKILL.md](https://github.com/dinkuskit/live-journeys/blob/main/SKILL.md).
For a local run, clone that repository and work in its `runner/` folder.

- **beta.sm0ky.dev belongs to the Live journeys workflow in dinkuskit/live-journeys
  alone.** Never run journeys on it from a Mac or from this repository.
- Each plugin's **Release** workflow, `action: cut-beta`, presses that workflow
  with the `DINKUS_LIVE_JOURNEYS_TOKEN` org secret.
- Older `proof_ref` links to this repository's Live journeys runs stay valid;
  new ones point at dinkuskit/live-journeys.

This folder keeps only this pointer so agents that load this plugin still find the journeys.
