# Swarm Cockpit case study: three harnesses, chained rounds

**Type:** case study (orchestrated, chained). Not a benchmark: each round builds on that lane's own previous output, and the lanes ran concurrently, so wall times are rough. Rankings belong to `evals/acp-routes`.

**Setup:** identical briefs, written before each round started (rounds 5–10 frozen together); shared base commit `9767bba` (end of the Antigravity-only rounds 1–3); one worktree per lane; 900 s job timeout; `approve-all` scoped to the driver. Feedback to a lane is only its failed automated checks, same wording for every lane, at most one repair per round.

**Checks per round:** `node --check app.js`, protected files unchanged (server, tests, lessons), server tests, plus a fixed live-page script for that round's features, run in the lane's own served page.

## Per round

| Round | Antigravity · gemini-3.8-flash-high | Cursor · grok-4.6 high | Grok · grok-4.7 |
| --- | --- | --- | --- |
| 4 | ✅ 350s · 73 tools | ✅ 93s · 48 tools | ✅ 497s · 99 tools |
| 5 | ✅ 338s · 118 tools | ✅ 63s · 36 tools | ⏱️ 901s · 183 tools |
| 6 | ✅ 393s · 202 tools | ✅ 65s · 60 tools | ✅ 756s · 150 tools |
| 7 | ✅ 406s · 155 tools | ✅ 87s · 48 tools | ⏱️ 901s · 135 tools |
| 8 | ✅ 301s · 89 tools | ✅ 102s · 84 tools | ⏱️ 901s · 141 tools |
| 9 | ✅ 375s · 166 tools | ✅ 74s · 63 tools | ✅ 460s · 102 tools |
| 10 | ✅ 414s · 120 tools | ✅ 104s · 156 tools | ⏱️ 901s · 258 tools |

✅ passed every check · ⏱️ job timed out · ❌ failed a check

## Totals

| Lane | Rounds | Passed first time | Timeouts | Median wall | Median tool calls | Median events | Logged defects |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Antigravity · gemini-3.8-flash-high | 7 | 7 | 0 | 375s | 120 | 258 | — |
| Cursor · grok-4.6 high | 7 | 7 | 0 | 87s | 60 | 575 | — |
| Grok · grok-4.7 | 7 | 3 | 4 | 901s | 141 | 1369 | r5: job TIMEOUT at 900s; left 9 stray files (screenshots, scratch scripts); r7: job TIMEOUT at 900s; left scratch file .tmp-r7-check.mjs; r8: job TIMEOUT at 900s; r10: job TIMEOUT at 900s |

## Findings

1. **All three harnesses produced working output in every round.** All 21
   lane-rounds passed every functional check; no repair was ever needed. The
   difference was time and cost, not correctness, on this chained UI build.
2. **Cursor · grok-4.6 high was the fastest by a wide margin**: median 87 s and
   60 tool calls per round, 7/7 first time. It is the default pick when the
   work is well specified and speed matters.
3. **Antigravity · gemini-3.8-flash-high was steady and 7/7 first time**, at a
   median 375 s and 120 tool calls, about 4× Cursor's wall time. It grew the
   code fastest (about +1,000 lines in round 6 alone). Earlier, in the
   Antigravity-only rounds, it once corrupted `app.js` with literal `\n` escapes
   while reporting success; asking for `node --check` in every brief prevented a
   repeat across 7 rounds.
4. **Grok · grok-4.7 timed out in 4 of 7 rounds, each time with output that
   passed every check.** Root cause, found from Grok's own session log: the
   `grok-acp` bridge did not pin reasoning effort, so jobs inherited
   `default_reasoning_effort = "xhigh"` from `~/.grok/config.toml`. One 885 s run
   had 3 s of tool execution; the rest was reasoning. Fix: branch
   `claude/grok-acp-reasoning-effort-20260926` pins the ACP `reasoning_effort`
   option to `high`. Rounds 9–10 deliberately kept the old configuration so the
   case study stays internally consistent; the benchmark measures the fix.
5. **No worker reported a broken environment.** In round 9 the brief asked for a
   file the protected server could not serve; every lane's page broke with a
   404 and every lane still reported success. Workers verify what they are
   told to verify, so the orchestrator's live checks are the real gate.
6. **Heuristics written from field data are fragile.** Given the same data and
   the same written scoring rule in round 6, the three lanes produced three
   different rankings. Ranking must come from the benchmark.

## Context before the three-lane rounds

Rounds 1–3 were Antigravity only (81 s, 125 s, 289 s) and built the shared base
commit `9767bba`. Round 4's first Antigravity attempt (`5f56f791`) corrupted
`app.js`; it was discarded and the three-lane rounds started from `9767bba`.

## Orchestrator notes (logged, never sent to lanes)

- r5 grok: timed out at 900 s after spending the run on self-verification (screenshots at 375/1100 px in light and dark, plus scratch check scripts). Output passed every check anyway.
- r6 all lanes: identical data and identical written heuristic produced three different rankings (UI / design #1: agy lane → antigravity, cursor lane → antigravity, grok lane → cursor; Quick fix #1: agy → cursor, cursor → antigravity, grok → cursor). The brief's weights were under-specified, so each worker chose its own. Evidence that field-data heuristics are fragile, and a reason the final advisor ranks on benchmark evidence only.
- r6 agy: app.js + styles.css grew by about 1,000 lines in one round (largest growth of any lane).
- r7 all lanes: faked one-job change re-rendered only the jobs section (2.4–2.8 ms) in every lane; grok again timed out while its output passed every check.
- r8 orchestrator errors, corrected before scoring: (1) my fetch interceptor called an unbound fetch ("Illegal invocation"), which made agy look like it never recovered; re-run with fetch bound to window, agy passed. (2) the grok tab was backgrounded mid-check, so its polling correctly paused; re-run with the tab in front, grok passed. Lesson for graders: validate the harness before blaming the worker.
- r8: grok's third consecutive timeout (r5, r7, r8), each time with output that passed every check. Pattern: grok-4.7 spends its budget on self-verification.
- r9 orchestrator brief defect: the brief required format.js, but the protected server's static whitelist did not serve it, so every lane's page broke (404, CockpitFormat undefined). Fixed with one identical orchestrator commit per lane ("orchestrator: serve format.js"); all lanes then passed. No lane reported the 404; all three claimed success.
- Grok debugging (during r9): the r5/r7/r8 timeouts were not a bridge fault. Grok's own session log for r8 shows 885 s of wall time with 3 s of tool execution and 0 s of permission wait; the rest was model reasoning (723 streaming_reasoning phases, gaps of 87–210 s between tool steps). Root cause: ~/.grok/config.toml sets default_reasoning_effort = "xhigh" and the grok-acp bridge launched `grok agent stdio` without pinning effort, so delegated jobs inherited the interactive xhigh setting. Fix on branch claude/grok-acp-reasoning-effort-20260926 pins --reasoning-effort high (override via SAARIUS_GROK_ACP_REASONING_EFFORT). Rounds 9–10 stay on the original configuration for case-study consistency.
- Also seen in Grok's session log: each worker tries to start antigravity-acp, cursor-acp and grok-acp MCP servers with relative paths inherited from local MCP config; all three fail to handshake, but a working config would let a worker delegate recursively.
- r10: cursor and grok close their <dialog> natively on a real Escape key press; a synthetic keydown does not trigger that, so the check was repeated with a real key press. agy handles Escape in its own keydown handler.
