# Behavior contract: Pixel-use single-agent versus width-two probe

Version: `2026-07-26.phase5-pixel-use-ab`

## Purpose

Compare the already-qualified width-two custom-agent pattern with a
single-agent baseline on one real, read-only Pixel-use reasoning slice. This is
a product-utility probe, not another generic fan-out qualification.

The probe covers two independent responsibilities derived from committed
Pixel-use code:

1. classify six actions using `PolicyCore`;
2. aggregate and rank six friction events using
   `buildFrictionHotspotReport`.

No Pixel-use source, device, account, process, or runtime state may be mutated.

## Frozen product source

- repo worktree:
  `/Users/cp-1/Developer/worktrees/pixel-use-general-harness-20260726`
- source head: `6474159cc15eafbd2abe602e13017a2754768ce9`
- `src/core/policy.ts` SHA-256:
  `91d134b1738fa0bc7ac5064992ad48c098bfe08b057a2dd0b4d810776144571e`
- `src/core/friction.ts` SHA-256:
  `5a7de1ff56b0619536911a9e060c064f65e65482ca5a197804e68d24af193ece`
- policy packet SHA-256:
  `8bc4cfb388ebc9b73a7c7c03ad3cbfe71741ce41dcde4dcce2a2b75fbe83bb08`
- friction packet SHA-256:
  `185354a5c64ae236b9d8deaab82f3a3320ac821609bcead3b0a2b252f36ae0ba`
- canonical policy answer SHA-256:
  `4ac5522583c2e6047c21acb6618dde2d8ee81b8fd5fbc3c68fe049c2453a7551`
- canonical friction answer SHA-256:
  `c4b3eb0f4c387c97775df27807214816ef315e1343574e9723c905abcff17148`

The controller answer key is generated from the committed Pixel-use
implementation before model launch. Models receive rules and inputs, never
the answer key.

## P1 — Source and oracle integrity

Expected: the product source stays at the exact clean head above; packet and
answer hashes match; the controller verifies exact structured outputs rather
than interpreting prose.

## P2 — Equivalent, source-blind fixtures

Expected: two fresh workspaces per arm. Both arms receive the same policy and
friction packets and fresh challenge tokens. Profiles are byte-identical
within an arm across rounds.

The single agent receives both packets. In the custom arm, the parent receives
neither packet nor child marker/path; the policy child receives only the
policy packet; the friction child receives only the friction packet. No model
profile contains the canonical answer key.

## P3 — Single-agent baseline

Expected: two fresh guarded single-agent sessions each produce one exact
combined policy/friction artifact after profile quarantine. Each artifact
matches its fresh identity, marker, challenge, schema, and controller answer
key.

## P4 — Qualified width-two arm

Expected: two fresh guarded parent sessions each produce exact policy and
friction child artifacts before profile quarantine. The parent join remains
OS-locked until both branch artifacts exist, is written after release, and
preserves both returned product objects and hidden branch markers exactly.

This proves functional width-two work and joining only. It does not expose the
CLI's internal scheduler or exact tool-call count.

## P5 — Exact comparative scoring

Expected: record per round and per arm:

- policy exactness;
- friction exactness;
- complete-result exactness;
- bounded wall duration;
- observed process exit and timeout;
- declared session multiplicity (`1` for single, at most `3` for custom).

Do not derive token use or monetary cost from unread raw output.

## P6 — Interpretation boundary

Expected: classify the product result conservatively:

- custom better only if its exact-result rate exceeds the baseline;
- comparable if exact-result rates tie, with duration and session
  multiplicity reported as costs rather than silently normalized;
- worse if its exact-result rate is lower;
- inconclusive if any guard, safety, cleanup, or infrastructure check fails.

This result cannot repair Phase 3's failed width-four join or qualify arbitrary
products. A pass can support only a bounded Pixel-use/product-specific
recommendation until another product family independently reproduces it.

## P7 — Teamwork, Puppet, and transport independence

Expected: no Teamwork Preview, Puppet, Herdr, device, or browser dependency,
fixture, invocation, or artifact. PR #6 remains unchanged historical
research. Puppet/Herdr remains an optional later replay transport, never the
capability owner.

## P8 — Privacy, cleanup, and stop

Expected: discovery output is digested in memory; raw stdout, stderr, and AGY
logs are digested then unlinked without inspection; exact workspace and
quarantine postflights pass; committed reports contain no transcript content;
all exact-owned remote roots are inventoried and removed.

Stop immediately on selection-guard failure, malformed fixture, unexpected
write, permission prompt, timeout, raw retention, product-source change,
foreign contact, cleanup ambiguity, or quota breach.

## Budget and safety

- top-level CLI processes: at most `4`;
- declared nested child branches: at most `4`;
- total agent sessions: at most `8`;
- admitted model-invocation envelope: at most `16`;
- per-process timeout: `180 seconds`;
- campaign wall cap: `720 seconds`;
- execution order: single A, custom A, single B, custom B;
- no resume;
- no merge, deploy, publish, global install, auth/settings/permission change,
  customer traffic, device action, transcript/pane/log-content read, product
  mutation, or foreign process/session contact.
