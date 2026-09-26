---
name: acp-route-lessons
description: Evidence-backed field notes for choosing and driving an ACP delegation route (cursor-acp, antigravity-acp, grok-acp) by task type. Use before delegating through any *-acp-delegation skill, when choosing which harness + model gets a task, when a delegated result disappoints, or when recording what a route did well or badly.
---

# ACP route lessons

The delegation skills say *how* to call a route. This skill says *which*
route to use for which kind of work, and *how to drive it*, based on
recorded evidence rather than impressions.

## Choose a route

1. Classify the task: Quick fix, Bounded implementation, Long refactor,
   UI / design, Verification / review, or Multi-round UI build.
2. Read `references/lessons.jsonl` and filter by that category. Prefer, in
   this order:
   - `source: "benchmark"`: fixed tasks with hidden graders
     (`evals/acp-routes`). Only benchmark lessons may rank one route above
     another.
   - `source: "case-study"`: the same orchestrated work given to several
     routes. Use it to learn how to drive a route, not to rank it.
   - `source: "field"`: observations from ordinary use. Use it to spot
     patterns such as "failures are all timeouts", never to rank.
3. Check the lesson's `model` against the model the route advertises today
   (readiness reports it). A lesson about another model version is a hint
   only.
4. Weigh `n`. With `n < 3`, say the evidence is thin.
5. State the choice in one line: "use <route>/<model> for <category>
   because <lesson note> (<source>, n=<n>)".

When no benchmark lesson covers the category, say so, and suggest running
`node evals/acp-routes/run.mjs --permission approve-all --tasks <task> --repeats 3`.

## Current evidence (baseline 2026-09-26)

From [`proof/acp-route-evals/20260926`](../../proof/acp-route-evals/20260926/README.md),
45 sequential attempts:

| Route · model | Solved | Median time per task | Notes |
| --- | --- | --- | --- |
| cursor · grok-4.6 high | 15/15 | 20–81 s | fastest on every task |
| antigravity · gemini-3.8-flash-high | 15/15 | 76 s–2 m 46 s | correct, about 1.5–4× Cursor's time |
| grok · grok-4.7 (effort high) | 13/15 | 86 s–10 m 35 s | 3 timeouts (review, UI) |

All three are correct on these five tasks, so the benchmark separates them on
speed and cost, not quality. Re-run it after model or CLI upgrades.

## Drive the route

Apply every `tactic` and `weakness` lesson for the chosen route. The
standing rules, from the evidence so far:

- Verify the artifact, never the worker's summary. Run the syntax check, the
  tests, and the live page yourself.
- Keep briefs to one bounded pass with a numbered checklist, and send
  failed checks back verbatim.
- Budget timeouts from the route's recorded p90, not its median.

## Record a lesson

Append one JSON object per line to `references/lessons.jsonl`:

```json
{"at":"2026-09-26T00:00:00Z","lane":"antigravity","model":"gemini-3.8-flash-high","category":"UI / design","kind":"strength","source":"benchmark","n":3,"note":"One sentence a future orchestrator can act on.","evidence":"Numbers and where they came from.","jobIds":["…"]}
```

- `kind` is one of `strength`, `weakness`, `tactic` or `observation`.
- `source` is one of `benchmark`, `case-study` or `field`, and `n` is the
  number of attempts behind the lesson.
- `evidence` must cite numbers or artifacts. A lesson without evidence is an
  opinion; do not record it.
- `scripts/distill.mjs --benchmark <results.jsonl> --case-study <case-study.jsonl>`
  prints candidate lessons from evidence files. Review and edit them before
  appending; they are summaries, not verdicts.
- When a route's model changes, keep the old lessons and add new ones. Do not
  edit history.
