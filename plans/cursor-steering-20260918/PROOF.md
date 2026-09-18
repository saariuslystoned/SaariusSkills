# Proof

Accepted bridge 6240a13 plus pinned acpx 0.16.0 source inspection shows startTurn serializes same-session work. The bridge marked original work completed and removed active ownership while a queued steering turn was unfinished. A controlled queued-runtime reproduction returned secondStarted=true, secondUnfinished=true, reportedComplete=true, activeOwnership=false.

Regression added first: steering fails closed before starting an unowned queued turn. Before fix it failed with Missing expected rejection. After fix npm run check passes all 10 tests. Packaging unittest passes all 12 tests. These are local fixture tests, not real-runtime model proof.

Fix: retain validated tool surface but return STEERING_UNSUPPORTED before starting another turn. Update tool/skill/docs and opt-in live smoke to prove refusal and original completion. Existing historical steering claims are not active-turn qualification. A proper future steering implementation needs a runtime-native interrupt or fully owned follow-up lifecycle.

No running bridge edited. Parent-authored emergency hardening candidate; independent Cursor review pending before landing/adoption.

## Independent review and live proof

Cursor ACP review at exact code head `88c500a20190194e795587285fc0d976cd716d98` found no blockers and independently passed all 10 bridge tests. Accepted: refusal precedes all runtime calls and no second turn is enqueued; delegation/result/cancel unchanged. Rejected: historical steering smoke proves active-turn steering.

Parent live probe used that immutable code head, explicit local cursor-agent ACP, requested `cursor-grok-4.6-high`, selected/current `grok-4.6[effort=high,fast=true]` from 38 advertised models. Job `d14a88fb-fa6d-4d36-becf-17b05861c1f8` returned `STEERING_UNSUPPORTED` during its active turn, wrote the exact expected marker in the supplied disposable workspace, and completed normally. Broker shutdown completed. No raw protocol/thought/auth output was inspected or retained in this proof.

Linux and macOS CI passed at 88c500a. This follow-up changes proof records only; final-head CI remains the merge gate. Raw local proof is retained by the parent campaign, not published as a transcript.
