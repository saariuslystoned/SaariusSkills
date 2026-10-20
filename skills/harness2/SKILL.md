---
name: harness2
description: Qualify and route one bounded Harness² Propose–Probe–Compose refinement experiment when a reproducible workflow weakness has measurable acceptance criteria. Use for lost handoff facts, repeated avoidable questions, or recurring workflow repairs; skip ordinary product bugs, unresolved preferences, provider outages, and authority gates.
---

# Harness²

Use this skill to improve the execution harness around a real task, not to
replace product delivery. Harness² is an external dependency, not source
copied into this plugin. The inspected upstream pin is
`1cfe254e8d25b15f37048c3730134686abe60335` at
<https://github.com/google-research/harness2>.

## Decide whether to route

Route one bounded refinement experiment by default when all of these are true:

- the weakness is concrete and reproducible;
- acceptance is measurable before the run;
- the proposed change is to the harness around execution (for example,
  prompt, guardrail, memory, tool guidance, subagent, skill, script, or
  plugin), not an ordinary product defect;
- current authorization, task capacity, run budget, and one-writer ownership
  permit it; and
- no active experiment already owns the same task, source, and failure,
  regardless of hypothesis wording; completed matches satisfy the reopening
  rule below.

Recognize lost handoff facts, repeated avoidable questions, and repeat
workflow repairs. Skip ordinary product bugs, unresolved user preferences,
provider outages, and real authority gates. Inline a fix only when the defect
blocks the current task; otherwise continue product delivery while the
experiment is independently bounded.

Check existing active and completed records before dispatch. Alternative
hypotheses are candidates within the same bounded experiment, not automatic
new experiments. Do not restart a completed failure without material new
evidence or source and an explicitly admitted remaining budget. Do not create
a scheduler, new queue, or always-on watcher. Do not dispatch if the runtime
capability is absent, unqualified, unauthorized, at capacity, or lacks an
owner; report `blocked` or `pending` with the reason and owner instead.

## Freeze the experiment

Before any runtime handoff, freeze a compact task packet using
[references/experiment-contract.md](references/experiment-contract.md). It
must bind the exact source revision and allowed editable instruction surfaces,
time/run budget, candidate isolation, hard checks, product criteria, tests,
proof/review gates, permissions, and a stop condition. Preserve repository
contracts and authority. The candidate must not access held-out judge answers,
rubrics, or other evaluation leakage.

The default is one full sequential `k=1` trial. Upstream's actual
Propose–Probe–Compose flow starts with the reference execution and performs
three improvement stages; this bounded trial therefore has four solver
executions total, followed by reflection. The sole composed candidate is
automatically adopted by upstream. Adoption is not evidence that it improved
the task. The across-task library retains adopted harnesses and
evidence-supported lessons for later tasks in the same compatible library.
Keep the exact benchmark/executor/mode/budget/seed identity when comparing
results.

Distinguish full recursion from evaluation-only fixed A/B: the former proposes,
probes, composes, adopts, and reflects; the latter evaluates an unchanged
original and candidate under a fixed protocol and does not run recursive
improvement.

An optional AI Shed `harness2-replay` integration and its documentation may
expose this capability. Discover and qualify it at dispatch time; the currently
described capability is one response-only frozen-task trial through explicit
Codex CLI, not arbitrary product writes, other harnesses, or an installed
runtime. Qualify permissions, exact source binding, cost and data limits, and
candidate isolation. Do not invent a command, ready flag, or claim readiness.
If the capability is unavailable or unqualified, use the truthful blocked or
pending route and do not emulate the run in chat. Runtime unavailability blocks
the experiment only; it does not block independent product delivery. Runtime
source awaiting review or merge is not a readiness signal.

Editable guardrails, scripts, skills, prompts, and plugins are experiment
surfaces, not a place to replace immutable repository policy. Preserve
immutable sections and do not modify or override them. Keep mandatory
repository policies, safety or authority rules, acceptance criteria, and
installed-file boundaries in the frozen packet and the repository's
authoritative sources.

An inline Harness² experiment still requires a qualified runtime and the full
bounded loop; an inline patch under a heading such as "inline harness fix" is
not by itself a Harness² run. An ordinary authorized task repair may proceed
separately when needed and must not be represented as Harness² evidence.
Optional refinement work does not make that ordinary repair wait.

## Evaluate and record

After hard checks pass, use the existing Jev underlying `decision_evaluate`
capability separately when authorized and available. Give Jev compact,
sanitized, anonymized A/B evidence with provenance; do not provide optimizer
preference, the original/candidate mapping, or raw transcripts. Ask only for
`A-better`, `B-better`, `equivalent`, or `insufficient-evidence`, using
criteria that compare the supplied evidence and do not reveal which label is
the original. Keep the A/B mapping outside the judge input and translate the
returned decision to `original-better` or `candidate-better` only in the
record. Preserve unavailable provenance and label an independent manual
fallback as manual. Jev is not a new delivery gate: when it is unavailable,
the same fixed criteria may be applied by an explicitly labeled independent
manual evaluation. Without comparative evidence, the result remains
`inconclusive`.
Jev cannot clear a hard failure or grant action authority. Honor service
authorization, cost, and data bounds. JevSweeper is only for published review
leftovers and is not this evaluator.

Record the experiment as `keep`, `reject`, `inconclusive`, or `blocked`.
Separate the first attempt from any recovery attempt. A successful transfer
of a lesson to another real task remains unproved until that task supplies
its own evidence. Never auto-edit installed checkouts, merge, roll out, or
claim product improvement from adoption alone.

When handing off, include status, exact repository/branch/SHA, artifacts and
checks, unresolved issues, ownership/cleanup, and one next action. The next
action may be runtime qualification, a bounded run, evaluation, recovery, or
manual review; it is not implicit permission to execute it.
