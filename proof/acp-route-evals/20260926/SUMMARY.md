# ACP route benchmark — 2026-09-26

Plugin commit `70c28b9`, host darwin-arm64, node v24.19.0. Sequential, 3 repeat(s) per route × task.
Permission: `approve-all` scoped to the runner's bridge processes. Scores are hidden-test pass fractions (0 when a gate fails).
Regraded offline 2026-09-26 with grader `ae19e8c`; original grades are in results.original.jsonl.

| Task | Route | Model | Solved | Mean score | Median job time | Median tool calls | Syntax fails | Protected edits | Non-completed |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| bounded-impl | antigravity | gemini-3.8-flash-high | 3/3 | 1.00 | 84s | 32 | 0 | 0 | — |
| bounded-impl | cursor | grok-4.6[effort=high,fast=true] | 3/3 | 1.00 | 37s | 21 | 0 | 0 | — |
| bounded-impl | grok | grok-4.7 | 3/3 | 1.00 | 3m 31s | 27 | 0 | 0 | — |
| quick-fix | antigravity | gemini-3.8-flash-high | 3/3 | 1.00 | 76s | 34 | 0 | 0 | — |
| quick-fix | cursor | grok-4.6[effort=high,fast=true] | 3/3 | 1.00 | 20s | 15 | 0 | 0 | — |
| quick-fix | grok | grok-4.7 | 3/3 | 1.00 | 86s | 30 | 0 | 0 | — |
| refactor | antigravity | gemini-3.8-flash-high | 3/3 | 1.00 | 2m 09s | 49 | 0 | 0 | — |
| refactor | cursor | grok-4.6[effort=high,fast=true] | 3/3 | 1.00 | 37s | 30 | 0 | 0 | — |
| refactor | grok | grok-4.7 | 3/3 | 1.00 | 10m 35s | 72 | 0 | 0 | — |
| review | antigravity | gemini-3.8-flash-high | 3/3 | 1.00 | 1m 51s | 40 | 0 | 0 | — |
| review | cursor | grok-4.6[effort=high,fast=true] | 3/3 | 1.00 | 81s | 33 | 0 | 0 | — |
| review | grok | grok-4.7 | 2/3 | 0.73 | 9m 20s | 42 | 0 | 0 | TIMEOUT |
| ui-slice | antigravity | gemini-3.8-flash-high | 3/3 | 1.00 | 2m 46s | 57 | 0 | 0 | — |
| ui-slice | cursor | grok-4.6[effort=high,fast=true] | 3/3 | 1.00 | 75s | 36 | 0 | 0 | — |
| ui-slice | grok | grok-4.7 | 2/3 | 0.97 | 10m 01s | 108 | 0 | 0 | TIMEOUT, TIMEOUT |
