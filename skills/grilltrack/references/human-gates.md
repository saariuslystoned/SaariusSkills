# Human-guided gates

Use a resumable human-guided gate when a focused decision depends on a step the
agent cannot or must not perform: entering credentials, changing an account or
permission, completing an attended third-party UI, approving an irreversible
action, or making a physical/device interaction outside the agent's authority.

## Prepare the gate

Inspect discoverable project facts and primary documentation first. Then draft
an ordered stage list that names:

- the human owner and why the step is human-only;
- the page, device, or command surface the human will use;
- the non-secret input and expected output of each stage;
- where any secret value will be stored without entering agent context;
- the sanitized receipt or artifact that proves completion;
- the next safe GrillTrack action after the gate.

Show the stages to the user before authoring or running a guided flow. Use an
available wizard capability when one is installed and the user wants an
interactive guide; otherwise produce a concise checklist. Never invent an
unverified dashboard path.

## Preserve the boundary

- Never ask the user to paste a secret into chat, a ledger, a proof packet, or
  a generated script.
- Never print, inspect, summarize, copy, or retain credential values, auth logs,
  cookies, private keys, or secret-store output.
- Require the repository's explicit gate for account, permission, security,
  production, send, spend, deploy, or irreversible actions.
- Record only non-secret state such as `waiting_for_human`, a sanitized receipt
  reference, and the next safe action.
- Treat completion of the attended step as input to the next phase, not as
  implementation, delivery, or promotion authority.

Pause the track with the gate/checklist reference when the human step cannot be
completed in the current turn. A future clear natural request to continue, or
an explicit `$grilltrack`, may resume from the durable state.
