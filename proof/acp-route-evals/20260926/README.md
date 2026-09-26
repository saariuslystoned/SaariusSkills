# ACP route benchmark baseline — 2026-09-26

Dated baseline for [`evals/acp-routes`](../../../evals/acp-routes/README.md)
on the maintainer's MacBook (darwin-arm64, node v24.19.0). Five fixed tasks ×
three routes × three repeats = 45 attempts, run one at a time, graded by
hidden tests only. [`SUMMARY.md`](SUMMARY.md) has the table.

## Result in one paragraph

Every route produced correct work on these tasks; the difference is speed and
cost. Cursor · grok-4.6 high solved 15/15 at a median of 20–81 s per task with
the fewest tool calls. Antigravity · gemini-3.8-flash-high solved 15/15 at
76 s–2 m 46 s with about 1.5× Cursor's tool calls. Grok · grok-4.7, with
reasoning effort pinned to `high` (#89), solved 13/15 (mean score 0.94) at
86 s–10 m 35 s and hit the job timeout 3 times (one review, two ui-slice).
No attempt left a syntax-broken file or edited a protected file.

## How to read it

- This is a benchmark only for these five tasks, on this machine and these
  subscriptions, on this date. Re-run it after model or CLI upgrades.
- Correctness is at the ceiling for Cursor and Antigravity: these tasks
  separate routes on speed, tool calls and timeouts, not on quality. Harder
  tasks are the next step for telling routes apart on correctness.
- Tool calls and ACP events are cost proxies. ACP does not report tokens or
  subscription usage.
- Timeouts are the task budgets (600 s; 900 s for refactor). A timed-out job can
  still have written a correct workspace; it is graded as found.

## Grader corrections during the run

Both were defects in the benchmark, not in the workers. Worker attempts were
not re-run; every preserved workspace was re-graded offline with the fixed
graders (`run.mjs --regrade`). Original grades are kept in
[`results.original.jsonl`](results.original.jsonl).

1. **Protected paths** (commit `6904d2b`). The bounded-impl brief invites extra
   tests under `test/`, but the grader treated any change to `test/` as
   tampering, so correct work scored 0. Protection now means the seed's files
   are unchanged and not deleted; new files are allowed. Regression test added.
2. **Refactor success-rate scale** (commit `2875ad0`). The brief asks for "the
   same numbers the current code computes" (a percentage), but the hidden test
   demanded a 0–1 fraction. All three routes followed the brief and lost two
   tests. The tests now accept either scale when `aggregate()` and
   `formatMarkdown()` agree.

The runner commit at start was `70c28b9`; the regrade used `ae19e8c`. The
grader validity suite (`evals/acp-routes/test/graders.test.mjs`) passed
before and after each fix.

## Case study

[`case-study/`](case-study/CASE_STUDY.md) holds the three-harness cockpit case
study (chained UI rounds 4–10 with identical briefs). It is evidence for how
to drive each route, not a ranking. Its Grok rounds ran before the
reasoning-effort fix.
