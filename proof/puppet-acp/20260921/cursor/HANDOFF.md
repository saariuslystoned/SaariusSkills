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
- Historical PR62 live failure had no provider turn; the later PR64 qualification attempt reached one real Cursor task turn and is recorded separately below.

## Artifact hashes

- Driver: `2292f0f39220b214fa561ff413d162e812b668a8ccdc86013ed1b645c0cb682f`
- Tests: `4e3440bd04e7b3fc9b957faba8656614889d5b785a0c0db9da88d8f953724b56`
- Offline receipt: `fb082d7857faf13a29b8c00d22db12b714261119cc75b77284eb7eb10048e10e`
- Staged invocation: `ee8f40ba6a791900e4573ac9749b6ad9985ea9cdd8c9d6f2ace876aac27118be`
- Fixture implementation: `7b0e90143afb9f04537e1992861bbc8b7cef87b5e4e626e3fd22de702ae1365b`
- Fixture tests: `bf063a0bdbf43dbe3fcda4e4d297af1aebcc2d7d1766efb6582f38e84710742e`

## Qualification status

Independent v3 review, the bounded release decision, and the PR64 source acceptance are complete. The fresh PR64 qualification session reached one useful task turn but failed closed during owner cleanup; qualification is not accepted. That allocation is consumed, with no retry or replacement authorization. A future live proof requires the cleanup repair and a fresh concrete parent allocation.

## Bounded release decision

- Parent acceptance: `APPROVE10/10`; v3 review and proof were read before release.
- Release record: `dual-v3-live-release.json`, recorded `2026-09-21T15:55:26Z`.
- Parent release token: `parent-pr62-v3-20260921`.
- Released budget: one session, at most two prompts of 300000 ms each, actual runtime timeout 30000 ms, no retry or replacement session.
- The released execution used a fresh d5 checkout and the exact reviewed driver hash above. This archival branch remains a checkpoint only; it is not the live execution checkout.

## Released live attempt outcome

- Execution worktree: `/Users/bobbybones/Developer/worktrees/puppet-cursor-controller-live-20260921`; branch `codex/puppet-cursor-controller-live-20260921`; exact d5/tree938ef948 verified.
- Session: `cursor-proof-v3-live-20260921-oneshot`; the one released session was consumed exactly once. No retry, replacement session, or second prompt.
- Result: blocked before the first task turn during `_cursor_acp_structured_launch.require_observation` / `ensureSession`.
- Exact sanitized error: `ValidationError: Failed to spawn agent command: candidate. The agent process could not start because a required executable, interpreter, working directory, or other launch path was not found.`
- No candidate backend incarnation, provider turn, useful agent output, or live PASS was established. Fixture `changed_paths=[]`; implementation/protected-test hashes stayed at the frozen baseline. Workspace/state were retained; no cleanup fence was required.
- Budget used: 1 session, 0 completed prompts; allocation was 1 session, max 2 prompts of 300000 ms each, actual runtime timeout 30000 ms, no retry.
- Sanitized outcome receipt: `live-outcome/live-failure.json`, SHA-256 `93270b1f5b1369510a25786c51cf03340e9a0d8bb779ddb4e551f9e32e24e9fc`.
- Parent adjudication identifies the blocker as a local product-wiring defect: `CursorAcpNodeRuntime` registers the official executable under `cursor`, while `CandidateAcpRuntimeRunner._ensure_owned_handle` hardcodes `agent: candidate`; the synthetic registry hid this mismatch. This is not an established upstream or authentication failure.
- Repair owner: task `01a0c01d-4a3b-7123-80eb-44a9ae9228f8`. Repair packet: `/Users/bobbybones/Developer/worktrees/acpx-upstream-plan-20260920/runs/puppet-overnight-runs/20260921/CURSOR_ROUTE_IDENTITY_REPAIR.md`.

## PR64 qualification outcome

- Execution worktree: `/Users/bobbybones/Developer/worktrees/puppet-cursor-qualification-pr64-20260921`; branch `codex/puppet-cursor-qualification-pr64-20260921`; exact PR64 head/tree `84a6dad7110ed97722b35ff1d7c102671312ec80` / `c923dfc6fc698d14d2e5c3fcdfdce3f156226b39`.
- Session `cursor-proof-v3-live-pr64-20260921` completed one useful first task. Only `normalize-lines.mjs` changed; the protected test stayed unchanged and passed 3/3.
- Owner cleanup then failed with `ValidationError: Agent does not support session/close for cursor-proof-v3-live-pr64-20260921.` The cleanup fence is retained and replacement is blocked; backend termination is not verified.
- Requested/expected model were `cursor-grok-4.6-high` / `grok-4.6[effort=high,fast=true]`, but selected/current model metadata was not durably retained before cleanup failure. No model qualification claim is made.
- Sanitized receipt: `live-outcome-pr64/live-outcome.json`, SHA-256 `a940d5425bd21c04e6542bb754e7cd01ad0d0e473bd933e79f4bb2f68e42fe33`.
- Budget used: one session, one completed prompt, no retry. This is useful behavior evidence with cleanup uncertainty, not a qualification PASS or ordinary production admission.
- Read-only diagnosis: `qualification-diagnosis-pr64.md`, SHA-256 `34b7656595f9d4773fe93440423904a28bad7b7c258b08d4afe12e748b4309f5`. The exact blocker is unsupported backend `session/close` plus missing matched Cursor worker lifecycle proof; helper exit is not treated as backend termination. The next gate is an offline synthetic unsupported-close regression and durable model/lifecycle metadata before any new live allocation.
- Offline repair gate: `offline-repair-gate-pr64.md`, SHA-256 `7c8c328a03f0ee82ab89fe1e656e04648224af67fb8bcc5cfacc0d4c66798979`. It defines the source-facing lifecycle/cleanup contract, the bounded proof-driver diff, and exact positive/negative/model-before-cleanup assertions. Dependency is a parent-accepted source repair head followed by offline proof-driver verification; the consumed PR64 allocation is not reused.

## Attribution

Implementation was delegated through Cursor ACP; orchestration, review, evidence normalization, and release gating were performed by Codex.

## Review recovery

- Prerequisite controller work is tracked in [PR #61](https://github.com/saariuslystoned/SaariusSkills/pull/61).
- v2 received independent review; the v3 delta review and bounded release review are complete.
- The owner's 10/10 result was separately confirmed by independent review before release.
- v3 repairs the accepted gaps: no live fixture deletion/retry, no byte-equality false negative or known-answer helper in live mode, and post-task/post-finish backend-incarnation observation with fail-closed uncertainty.
- Sister Antigravity checkpoint: [PR #63](https://github.com/saariuslystoned/SaariusSkills/pull/63).
- Both proof allocations are consumed; do not infer retry authority from unused prompt count.
