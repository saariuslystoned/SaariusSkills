# GrillTrack protocol

## Activation

Start, continue, resume, reopen, or close a track when the user's natural
request clearly asks for that product-cycle work. Also accept `$grilltrack` as
an explicit invocation. Do not require the user to translate clear intent into
a canned command.

A casual mention or explanation request does not activate product work. When
intent is ambiguous and mutation would be material, clarify once instead of
asking the user to paste a special phrase.

Activation authorizes the bounded local cycle after shared-understanding
confirmation. It does not widen repository permissions or authorize delivery.

## Cycle

### 1. Discover

Read repository instructions and inspect available project facts before asking
questions. Separate discoverable facts from product preferences. Select one
focused decision domain whose resolution can materially improve the product.

If the unresolved destination cannot be represented honestly in one useful
session, stop and create or adopt a source-linked decision map. Resolve one
current frontier node per GrillTrack cycle instead of flattening a multi-session
effort into one grill.

### 2. Choose cadence

Use:

- `sequential` when answers are dependent, ambiguous, high-leverage, or likely
  to reshape later questions;
- `frontier-batch` for one numbered batch of questions that are independent at
  the current dependency frontier.

Do not dump future dependency levels into a frontier batch. Let the user
override cadence.

### 3. Grill

Ask only questions that affect the focused domain. Recommend a direction when
professional judgment can reduce noise, while making the user-owned choice
clear. Record rationale when the user supplies it.

### 4. Confirm

Summarize:

- the focused domain;
- accepted choices and rationale;
- constraints and prior locks;
- the bounded implementation;
- the intended verification.

Wait for explicit shared-understanding confirmation. Do not implement before
confirmation.

### 5. Implement

Apply the confirmed domain to the real project. Keep the slice meaningful but
inspectable. Stop when repository instructions or safety gates require a
separate decision.

### 6. Verify

Prove function and fit in accumulated context. Select the renderer by domain:

| Domain | Faithful evidence |
| --- | --- |
| Frontend | Real page or faithful capture, target browsers, screenshots |
| CLI | Accepted command shape and realistic transcript |
| API | Accepted request/response flow and dependent callers |
| Document | Accepted hierarchy and surrounding content |
| Device | Accepted screen flow and target dimensions |

Automated probes alone are not enough when the decision is visual. A renderer
that drops material accepted context is a disclosed gap, not proof.

### 7. Review

When the cycle changed the project, review the verified result on two separate
axes:

- **Standards:** Does the result follow applicable repository instructions,
  conventions, and quality requirements?
- **Source intent:** Does the result faithfully implement the confirmed summary,
  decision locks, dependencies, and explicit exclusions?

Bind the review to an immutable source identity: a full commit SHA for Git or a
content hash/versioned artifact identity elsewhere. A branch name, mutable URL,
or current working tree label cannot support a clean verdict.

Classify every finding as `required_fix`, `reject_false_positive`, `defer`, or
`human_gate` before acting. A `required_fix` returns the decision to
implementation and re-verification. Review is advisory evidence and never
acquires mutation, delivery, or promotion authority.

### 8. Inspect

Inspect what the implementation newly reveals. Offer one recommended next grill
and at most two credible alternatives. Offer only the recommendation when no
real alternative exists. Recommend closeout when there is no meaningful next
grill.

### 9. Close

Ask for explicit closure confirmation. Record the reason for stopping,
verified results, history, deferrals, unresolved risk, and any separately
authorized delivery reference.

## Cumulative context

Keep accepted choices applied while evaluating later choices. If the selected
renderer cannot preserve them, choose a better renderer or disclose the
limitation and stop.

When a decision changes, preserve history and mark its transitive dependents
`needs_reverification`. Unaffected work may continue. Affected work cannot
support clean closeout until verified, superseded, or explicitly deferred.

## Context boundaries

Cross a compaction, new session, new harness, new directory, or new owner with
durable source-linked artifacts. Do not treat a chat summary as the only record
of a decision or invariant.

At a phase boundary, continue when the next phase needs the current reasoning
and the context remains sharp. Otherwise update and validate the ledger, record
the exact artifact refs and next safe action, and pause before switching
contexts. Treat repeated rediscovery, dependency fan-out, unexpected duration,
or lost ability to restate the current lock as context-risk evidence rather
than relying on a universal token threshold.

When a human-only action blocks the cycle, follow
[human-gates.md](human-gates.md), record only a sanitized artifact reference,
and pause without weakening the gate.

## Stop conditions

Stop or pause when:

- no meaningful next grill exists;
- implementation differs from the confirmed lock;
- an upstream change invalidates the evaluated baseline;
- proof is incomplete or contradictory;
- an accepted review finding requires repair or re-verification;
- a fidelity compromise changes the decision;
- context pressure makes the current lock or dependencies unreliable;
- a repository or safety gate requires the user;
- the user’s preference appears to have changed.
