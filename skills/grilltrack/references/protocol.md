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

### 7. Inspect

Inspect what the implementation newly reveals. Offer one recommended next grill
and at most two credible alternatives. Offer only the recommendation when no
real alternative exists. Recommend closeout when there is no meaningful next
grill.

### 8. Close

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

## Stop conditions

Stop or pause when:

- no meaningful next grill exists;
- implementation differs from the confirmed lock;
- an upstream change invalidates the evaluated baseline;
- proof is incomplete or contradictory;
- a fidelity compromise changes the decision;
- a repository or safety gate requires the user;
- the user’s preference appears to have changed.
