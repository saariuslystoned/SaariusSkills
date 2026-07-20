# Proof and closeout

## Proof

Keep proof with the project that produced it. Store curated evidence under
`.grilltrack/proof/` and reference it from the ledger. Keep large or rejected
working artifacts under ignored `.grilltrack/work/`.

For each implemented decision, record:

- the accepted lock and relevant dependencies;
- the implementation reference;
- commands or interactions used to verify it;
- the renderer and its fidelity limits;
- the verification reference;
- whether earlier locks remained represented;
- failures, deferrals, and remaining risk.

Use screenshots plus direct inspection for visual decisions. Do not treat
string presence, computed style values, or numeric probes as sufficient visual
proof.

Never publish private project details, secrets, credentials, auth logs, or
prohibited customer data as proof.

## Delivery boundary

Implementation and verification are part of the confirmed local cycle. Delivery
is separate.

Do not commit, push, open or merge a pull request, deploy, spend, send, or
change an account unless the user explicitly requests that action and the
project permits it. Record generic references:

- `implementation_ref`
- `verification_ref`
- `review_ref`
- `delivery_ref`

These may contain Git references, artifact paths, or external URLs, but no one
platform is required.

## Pause

Pause when the user stops, the current session ends, or a gate blocks progress.
Record the current focus, unresolved decisions, next safe action, and blocker.
A future session must receive a new explicit `$grilltrack` invocation before
resuming.

## Closeout

Before closure:

1. Validate the ledger.
2. Reconcile implemented decisions with verification evidence.
3. Resolve every `needs_reverification` decision by verifying, superseding, or
   explicitly deferring it with risk.
4. Summarize accepted and superseded choices.
5. Record unresolved or uncertain items.
6. Record delivery references only for separately authorized actions.
7. Ask the user to confirm closure.

Close only after confirmation. The durable closeout must state:

- why the track stopped;
- verified results;
- superseded choices;
- deferrals and unresolved risk;
- proof references;
- delivery references, if any.

Never rewrite history or claim a run that did not occur.
