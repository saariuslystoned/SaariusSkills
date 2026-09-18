# Proof

Accepted bridge 6240a13 plus pinned acpx 0.16.0 source inspection shows startTurn serializes same-session work. The bridge marked original work completed and removed active ownership while a queued steering turn was unfinished. A controlled queued-runtime reproduction returned secondStarted=true, secondUnfinished=true, reportedComplete=true, activeOwnership=false.

Regression added first: steering fails closed before starting an unowned queued turn. Before fix it failed with Missing expected rejection. After fix npm run check passes all 10 tests. Packaging unittest passes all 12 tests. These are local fixture tests, not real-runtime model proof.

Fix: retain validated tool surface but return STEERING_UNSUPPORTED before starting another turn. Update tool/skill/docs and opt-in live smoke to prove refusal and original completion. Existing historical steering claims are not active-turn qualification. A proper future steering implementation needs a runtime-native interrupt or fully owned follow-up lifecycle.

No running bridge edited. Parent-authored emergency hardening candidate; independent Cursor review pending before landing/adoption.
