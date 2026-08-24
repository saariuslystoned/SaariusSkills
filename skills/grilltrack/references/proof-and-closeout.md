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
- the immutable source identity reviewed;
- the standards and source-intent review result, finding classifications, and
  review reference when the project changed;
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

Pause when the user stops, the current session ends, context pressure threatens
decision fidelity, another owner/harness must resume, or a gate blocks progress.
Record the current focus, unresolved decisions, next safe action, blocker, and
source-linked artifact refs needed to continue. A future clear natural request
to continue, or an explicit `$grilltrack`, may resume from that durable state.

## Closeout

Before closure:

1. Validate the ledger.
2. Reconcile implemented decisions with verification evidence.
3. Reconcile any required review with the exact current source identity and
   classify every finding before acting on it.
4. Resolve every `needs_reverification` decision by verifying, superseding, or
   explicitly deferring it with risk.
5. Summarize accepted and superseded choices.
6. Record unresolved or uncertain items.
7. Record delivery references only for separately authorized actions.
8. Ask the user to confirm closure.

Close only after confirmation. The durable closeout must state:

- why the track stopped;
- verified results;
- superseded choices;
- deferrals and unresolved risk;
- proof references;
- review references and exact source identities when review was required;
- delivery references, if any.

Never rewrite history or claim a run that did not occur.
