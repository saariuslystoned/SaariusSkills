# Behavior contract: corrected Pixel-use comparison

Version: `2026-07-26.phase5b-pixel-use-ab`

## Purpose

Repeat the bounded single-agent versus width-two Pixel-use comparison after
correcting exactly one proof-fixture defect preserved by Phase 5.

Phase 5 required the hidden controller shape
`policy: {"cases": [...]}` but told models only to return ids in order. All
four rounds returned the six correct decisions using other reasonable outer
shapes, so the attempt was correctly classified inconclusive at proof commit
`4f823d794ada77173b1e16c6a9206a46021317f6`.

This correction explicitly names the `cases` key and exact entry keys without
revealing any expected decision or friction value. Nothing else in the product
task, answer key, arm topology, model, host, or scoring changes.

## Frozen product source

- Pixel-use source head:
  `6474159cc15eafbd2abe602e13017a2754768ce9`
- `src/core/policy.ts` SHA-256:
  `91d134b1738fa0bc7ac5064992ad48c098bfe08b057a2dd0b4d810776144571e`
- `src/core/friction.ts` SHA-256:
  `5a7de1ff56b0619536911a9e060c064f65e65482ca5a197804e68d24af193ece`
- corrected policy packet SHA-256:
  `30eb87e927875b4a606a76a882b8fca070b9bfa883c84972a738004ab08cf79e`
- unchanged friction packet SHA-256:
  `185354a5c64ae236b9d8deaab82f3a3320ac821609bcead3b0a2b252f36ae0ba`
- canonical policy answer SHA-256:
  `4ac5522583c2e6047c21acb6618dde2d8ee81b8fd5fbc3c68fe049c2453a7551`
- canonical friction answer SHA-256:
  `c4b3eb0f4c387c97775df27807214816ef315e1343574e9723c905abcff17148`

## B1 — Correction isolation

Expected: the source diff from the preserved Phase 5 runtime changes only the
policy output-envelope wording, its regression assertions, this contract/
route, schema registration, and documentation. Product inputs and canonical
answers remain byte-identical.

## B2 — Source-blind equivalent fixtures

Expected: two fresh workspaces per arm, two fresh challenges, and
byte-identical profiles within each arm. Models receive rules and inputs but
never the canonical answers. The single profile receives both packets; custom
children receive one packet each; the parent receives neither packet nor
hidden marker/path.

## B3 — Single-agent baseline

Expected: two guarded single-agent sessions each produce an exact combined
policy/friction result after profile quarantine.

## B4 — Width-two custom arm

Expected: two guarded parent sessions each produce exact policy and friction
child results before profile quarantine; each OS-locked join is written only
after release and exactly preserves both returned objects and hidden child
identities.

## B5 — Exact comparison

Expected: record exact policy, friction, complete-result, join-fidelity,
duration, exit, timeout, and declared-session metrics per round and per arm.
No token or monetary cost is inferred from unread raw output.

## B6 — Disposition rule

Expected:

- custom better only if its complete exact-result rate exceeds single;
- comparable if rates tie, with duration and session multiplicity explicit;
- custom worse if its rate is lower;
- inconclusive on guard, fixture, infrastructure, safety, or cleanup failure.

A result can support only a bounded Pixel-use-specific disposition. It cannot
repair failed width-four joining or independently justify a reusable plugin.

## B7 — Independent ordinary-agent surface

Expected: ordinary workspace custom agents only. No Teamwork Preview, Puppet,
Herdr, browser, or device involvement. PR #6 remains unchanged historical
research.

## B8 — Privacy and cleanup

Expected: discovery digested in memory; stdout, stderr, and AGY log content
digested then unlinked unread; exact postflights; committed transcript-free
reports; exact-owned roots inventoried, mode-restored where required, removed,
and verified absent.

## Budget and safety

- top-level CLI processes: at most `4`;
- declared nested child branches: at most `4`;
- total agent sessions: at most `8`;
- admitted model-invocation envelope: at most `16`;
- per-process timeout: `180 seconds`;
- campaign wall cap: `720 seconds`;
- execution order: single A, custom A, single B, custom B;
- ordinary exact-answer mismatches are data and do not authorize retries;
- stop on guard, fixture, infrastructure, safety, timeout, raw-retention,
  product-source, foreign-contact, cleanup, or quota failure;
- no merge, deploy, publish, global install, auth/settings/permission change,
  customer traffic, device action, transcript/pane/log-content read, product
  mutation, or foreign process/session contact.
