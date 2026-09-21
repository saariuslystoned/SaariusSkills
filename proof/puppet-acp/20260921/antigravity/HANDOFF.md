# Antigravity ACP proof checkpoint

This draft PR is an archival/review checkpoint, not live qualification. It
contains the task-only v3 lifecycle repair produced in the execution checkout
`/Users/bobbybones/Developer/worktrees/puppet-antigravity-controller-proof-20260921`.
Product source, ordinary Antigravity availability, plugin pins, and the
candidate-only `live_antigravity_acp_claimed:false` behavior are unchanged.

## Frozen provenance

```text
execution HEAD d5e33f67f6b42384f6feec1d15be3b69b4525eb8
execution TREE 938ef948a6a1218ad055a17d5d297c633b936167
upstream       2e05de525dd1ab62e9e74bf02d91e3638920fcf3
upstream tree  c612e764ead5d8eaa409956fb1b11c008a7579ed
acpx artifact  5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614
runtime.js     ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683
```

Implementation jobs: v1 `d3834068-43d5-4a4e-8092-6882bbe3cc93`, v2
`a7158f99-fdc2-47f6-8fc9-9d1cf4940dc2`, and final v3
`ce47ac58-45f3-4958-9427-fc72792d10e2`; each used native Cursor ACP exact
Grok 4.6 High. No AGY provider job was launched.

## v3 delta

The v3 driver/test snapshot adds real owned-backend incarnation observation
(PID, PPID, executable, start/birth identity only), re-observes that same
incarnation after `owner.finish`, and passes the result into unsupported-close
acceptance. Helper exit alone is insufficient. Offline tests prove both:

- an unsupported close plus an owned `localharness_external` peer exit is
  accepted; and
- unknown/surviving backend state retains the primary failure, durable fence,
  fixture/state identity, and replacement block.

The first turn is the structured-launch `require_observation`; `next_turn` is
not mislabeled as the first task. The existing 30000ms product runtime cap is
recorded, not changed. No broad process kill, auth/profile/env read, or live
provider call occurred.

## Evidence

The v3 driver ran 14 focused tests and the public-runtime synthetic lifecycle
test successfully. Fixture baseline/after checks passed with exact changed set
`{bin/normalize-lines.mjs}`; live refusals exit 2 before process start. Useful
edit ability remains unproven because the provider turn was not authorized.

## Live-command safety boundary

The copied `v3/staged/live-invocation.json` is preserved as source evidence,
but its command intentionally points to the parent-specified v2 driver and
v2 launch-input. This checkpoint does not silently promote that old command or
claim that v3 is integrated into the product live path. Do not execute it from
this PR. Parent must explicitly select/integrate the reviewed v3 delta before
releasing the one-session/two-prompt live allocation.

The remaining allocation is one owned session, at most two prompts, each
`<=300000ms`, no retry. Current runtime cap is stricter at 30 seconds. Sister
review checkpoint: https://github.com/saariuslystoned/SaariusSkills/pull/62.

## Original execution evidence

The complete v1/v2/v3 run history remains in the original task-owned run root;
this PR contains only the explicit immutable v3 snapshot, minimal v2 fixture
inputs, and this sanitized handoff. No raw ACP transcript, token, credential,
account/auth/config/env file, runtime tarball, cache, or nested git workspace
is included.
