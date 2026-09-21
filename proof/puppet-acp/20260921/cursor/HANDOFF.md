# Cursor ACP v3 archival checkpoint

This is a reviewable proof snapshot, not product integration and not live qualification.

## Provenance

- Owner task: `01a0c01d-9ac8-7552-a0f7-aea711f1cb3d`
- Coordination task: `01a0b564-7919-7851-a28d-34afa78683c8`
- Publication branch: `codex/puppet-cursor-proof-checkpoint-20260921`
- Publication base: `49a46404854db7c9c7e7935b351e47fb771beaca` (`origin/main` at checkout)
- Original execution checkout: `/Users/bobbybones/Developer/worktrees/puppet-cursor-controller-proof-20260921`
- Original execution branch: `codex/puppet-cursor-controller-proof-20260921`
- Original execution HEAD at checkpoint: `6840e3c7da84954320289239540aa5358ac2fbd2`
- Product source identity used by the driver: d5e33f67f6b42384f6feec1d15be3b69b4525eb8 / tree `938ef948a6a1218ad055a17d5d297c633b936167`
- Important: the original execution checkout now has proof artifacts on top of d5, so its full checkout HEAD/tree no longer equals the driver's exact d5 guard. This publication snapshot does not bypass that guard. A fresh d5 execution checkout must be prepared and verified before any live launch.
- Canonical native Cursor ACP implementation job: `91a1240f-de3d-4546-a809-3a68c54d13d0` (completed)
- A worker-reported secondary ID `4e0415d3-f1e1-4e7c-951b-cd093b06f13d` was not a native ACP job and is not authoritative.

## Route and runtime

- Official executable: `/Users/bobbybones/.local/bin/cursor-agent`
- Route: `cursor-agent acp`
- Selector/current model: `cursor-grok-4.6-high` / `grok-4.6[effort=high,fast=true]`
- Frozen upstream acpx: `2e05de525dd1ab62e9e74bf02d91e3638920fcf3`; existing artifact/runtime materialization was reused, not rebuilt.
- Machine-local execution requires the above executable, the frozen fixture/runtime, and the original proof-run layout; this archive is not a portable product command.

## Verified offline evidence

- Independent focused run: `python3 -m unittest discover -s .../tests -p 'test_*.py' -q` → 10 tests, 21.031s, OK, exit 0.
- Publication-worktree smoke: 10 tests, OK, with 6 skipped because the archival checkout intentionally does not satisfy the driver's exact d5 HEAD guard; this is expected and is not live proof.
- Offline synthetic driver: `ok=true`, `live=false`; ordinary availability remains false.
- Live release/session gates reject before process start; existing live workspace/state/fence rejects without deletion or retry.
- Live path does not call the known-answer helper; attribution uses independent before/after digests and protected-test checks.
- First turn is `_cursor_acp_structured_launch.require_observation`; helper exit is not backend proof; post-finish backend uncertainty fails closed.
- No live Cursor provider turn was executed.

## Artifact hashes

- Driver: `2292f0f39220b214fa561ff413d162e812b668a8ccdc86013ed1b645c0cb682f`
- Tests: `4e3440bd04e7b3fc9b957faba8656614889d5b785a0c0db9da88d8f953724b56`
- Offline receipt: `fb082d7857faf13a29b8c00d22db12b714261119cc75b77284eb7eb10048e10e`
- Staged invocation: `ee8f40ba6a791900e4573ac9749b6ad9985ea9cdd8c9d6f2ace876aac27118be`
- Fixture implementation: `7b0e90143afb9f04537e1992861bbc8b7cef87b5e4e626e3fd22de702ae1365b`
- Fixture tests: `bf063a0bdbf43dbe3fcda4e4d297af1aebcc2d7d1766efb6582f38e84710742e`

## Remaining blocker

Parent review, then a fresh verified d5 execution checkout and one parent-issued live session. Budget is one session, at most two prompts of 300000 ms each, no retry. The staged live command is archived under `staged/live-invocation.json` and has not been executed.

## Bounded release decision

- Parent acceptance: `APPROVE10/10`; v3 review and proof were read before release.
- Release record: `dual-v3-live-release.json`, recorded `2026-09-21T15:55:26Z`.
- Parent release token: `parent-pr62-v3-20260921`.
- Released budget: one session, at most two prompts of 300000 ms each, actual runtime timeout 30000 ms, no retry or replacement session.
- Released execution must use a fresh d5 checkout and the exact reviewed driver hash above. This archival branch remains a checkpoint only; it is not the live execution checkout.

## Review recovery

- Prerequisite controller work is tracked in [PR #61](https://github.com/saariuslystoned/SaariusSkills/pull/61).
- v2 received independent review; the v3 delta review is pending.
- The owner's 10/10 result is separate from independent final acceptance.
- v3 repairs the accepted gaps: no live fixture deletion/retry, no byte-equality false negative or known-answer helper in live mode, and post-task/post-finish backend-incarnation observation with fail-closed uncertainty.
- Sister Antigravity checkpoint: [PR #63](https://github.com/saariuslystoned/SaariusSkills/pull/63).
