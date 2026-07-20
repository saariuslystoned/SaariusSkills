---
name: grilltrack
description: Explicit-only progressive product development through focused decision, implementation, verification, and inspection cycles with durable state. Use only when the user invokes $grilltrack to start, resume, or reopen a track. A natural-language mention without $grilltrack receives invocation guidance and must not create or mutate state.
license: MIT
---

# GrillTrack

Build the next knowable slice of a complicated product. Do not pretend every
important decision is visible at the beginning.

## Enforce explicit activation

Require `$grilltrack` in the current user request before starting, resuming, or
reopening a track.

If the user only names GrillTrack in natural language:

1. Explain briefly that GrillTrack is explicit-only.
2. Suggest an invocation such as
   `$grilltrack Help me decide and build the next product slice.`
3. Do not inspect, create, or mutate `.grilltrack/`.

Explicit activation does not override repository instructions, approval gates,
or limits on external actions.

## Load only the needed guidance

Read:

- [references/protocol.md](references/protocol.md) for every activated cycle.
- [references/ledger.md](references/ledger.md) before creating or changing
  durable track state.
- [references/proof-and-closeout.md](references/proof-and-closeout.md) before
  verification, pause, delivery handoff, or closeout.
- [references/grill-frontend/README.md](references/grill-frontend/README.md)
  only when the focused grill is visual or frontend-specific.

Load only the frontend module named by its router. Do not load the frontend pack
for CLI, API, document, device, or other non-frontend cycles.

## Run one complete cycle

1. Inspect discoverable project facts and applicable repository instructions.
   Own fact-finding; leave product and preference decisions to the user.
2. Inspect the durable ledger when `.grilltrack/ledger.json` exists. Never treat
   chat history as the canonical state.
3. Select one high-leverage focused grill. Do not invent a grill merely to keep
   the track alive.
4. Choose sequential questioning for dependent or ambiguous decisions, or one
   numbered frontier batch for currently independent questions. Explain a
   non-obvious cadence choice briefly and let the user override it.
5. Record answers and scoped locks. Preserve dependencies and cumulative
   context.
6. Summarize the focused grill and wait for explicit shared-understanding
   confirmation before implementation.
7. Implement only the confirmed, bounded domain in the real project.
8. Verify behavior and fit beside earlier accepted decisions. Disclose a
   fidelity gap and improve the renderer or stop; do not present a misleading
   mock as proof.
9. Inspect the new state. Recommend one next grill and up to two real
   alternatives, or recommend closeout when no meaningful grill remains.
10. Ask the user to confirm closure before closing the ledger.

Treat the complete cycle—not an answer—as the atomic unit of progress.

## Preserve cumulative context

Judge every new decision beside previously accepted decisions whenever the
domain can represent them faithfully. Keep unaffected locks intact.

When reopening a decision:

1. Preserve its prior value and history.
2. Mark dependent decisions `needs_reverification`.
3. Replace or supersede the decision without deletion.
4. Reimplement and verify the replacement in cumulative context.
5. Do not cleanly close while affected decisions remain unresolved.

## Use the ledger tools

Run the standard-library ledger CLI from this skill directory:

```bash
python3 scripts/grilltrack_ledger.py --project <project-root> init \
  --activation '$grilltrack' --title "<track title>"
python3 scripts/grilltrack_ledger.py --project <project-root> show
python3 scripts/grilltrack_ledger.py --project <project-root> validate
```

Use the narrow subcommand that matches the real transition. Let the tool reject
invalid lifecycle changes; do not hand-edit around validation. The ledger is the
single current projection and `events.jsonl` is its append-only history.

Working candidates belong under `.grilltrack/work/`, which the initializer
ignores locally. Keep curated proof under `.grilltrack/proof/`. Never
auto-delete working artifacts.

## Apply the frontend contract conditionally

For a visual decision, present exactly five materially distinct candidates in
one active unresolved slot. Present them neutrally and preserve prior locks on
the same faithful canvas.

Never propose a hybrid. When the user explicitly requests a precise hybrid,
preview it for confirmation as a replacement for the active five—not as a
sixth option. A vague hybrid may start a new round of exactly five.

Validate a picker manifest before treating it as usable:

```bash
python3 scripts/validate_picker.py <path-to-picker-manifest.json>
```

The live variant picker is development tooling and must not ship in production.

## Keep decisions separate from delivery

A lock or shared-understanding confirmation authorizes only the bounded local
implementation contained in the activated cycle. It never authorizes a commit,
push, pull request, merge, deployment, purchase, send, account change, or
security-affecting action.

Perform delivery only when the user separately requests it and the active
repository permits it. Record generic `implementation_ref`, `verification_ref`,
`review_ref`, and `delivery_ref` values without making GitHub a core dependency.

## Stop honestly

Pause or block when implementation drifts from the lock, proof is incomplete,
the baseline changed materially, fidelity is misleading, or a repository or
safety gate requires user action.

At closeout, record verified results, superseded choices, deferrals, unresolved
risk, proof references, delivery references if any, and the reason the track
stopped. Never claim a proof run that did not happen.
