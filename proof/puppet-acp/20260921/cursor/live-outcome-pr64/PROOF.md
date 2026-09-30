# Cursor PR64 candidate qualification proof

The fresh PR64 checkout passed the reviewed v3 focused tests (10/10) and all pinned ACPx archive/runtime/chunk integrity checks. The one released Cursor candidate session used the official `cursor-agent acp` route and completed one useful first task: only `normalize-lines.mjs` changed, the protected test digest stayed unchanged, and the protected test passed 3/3.

The attempt is not accepted as qualification because owner-mediated cleanup failed with `ValidationError: Agent does not support session/close for cursor-proof-v3-live-pr64-20260921`. The driver retained the workspace/state and wrote a replacement-blocking cleanup fence. Backend termination is not verified; helper exit is not treated as proof. Selected/current model metadata was not durably retained before the cleanup failure, so no model PASS is claimed.

The allocation is consumed: one session, one completed prompt, no retry or replacement. The sanitized receipt is `receipts/live-outcome.json`.
