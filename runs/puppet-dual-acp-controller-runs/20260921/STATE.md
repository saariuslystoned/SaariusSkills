# Dual ACP controller state

- status: repair cycle 2 worker completed; independent checks pass for injected/public-runtime seams, but normal default-factory reachability is blocked by missing executable wiring
- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-dual-acp-controller-20260921`
- branch: `codex/puppet-dual-acp-controller-20260921`
- base: `d0f0644f4ef4c84286d5307966514cf52cededc8`
- frozen upstream acpx: `f8883645c261e07b2df7f9c3b4ad243b62d8168a`
- artifact SHA-256: `642d4c299bd58b275ca1a360196f3077fc4f84997e2654542f492b1e0001c162`
- worker_job_id: `59754615-f2c0-41b9-a2e8-d41d999ba4cb`
- antigravity_worker_job_id: `7214ec87-9b2b-4c6b-a5b1-69cab059854f`
- repair_worker_job_id: `35e20824-58e5-46b9-bb14-402098b36b69`
- repair2_worker_job_id: `f3b870e8-94af-42da-a9e9-fe9819ce335c`
- ordinary/plugin/shared pins: unchanged
- live qualification: not launched; parent admission required after source acceptance
- AGY cleanup: canonical `cleanupReady=true`; no owned worker remains running
- independent validation: 58 focused Python tests, 30 Cursor bridge tests, and 33 Antigravity bridge tests passed; clean-checkout portable run passed with Cursor 23 passed/7 skipped and AGY 1 skipped
- decisive blocker: default `_cursor_acp_structured_launch` and `_antigravity_acp_structured_launch` invoke the candidate factory without the trusted manifest executable; exact reproductions return `ValidationError: ... candidate executable is missing`
- source review: blocked pending parent adjudication of the missing executable consumer seam; live qualification and pin refresh remain closed
- next: parent rescope/repair decision; no owner-local source finish or extra worker dispatched
