---
name: smoky-performance
description: Investigate and improve application, service, test-suite or CI performance using reproducible workloads, work counts and comparable measurements. Use for latency, CPU, memory, I/O, render costs, caching or slow tests and workflows.
---

# Measure and remove unnecessary work

Use this skill for a bounded application, service, test or CI workload. Read the request,
applicable repository instructions and any supplied performance profile. Use
the repository's existing commands, instrumentation and workload scripts.
Diagnosing a slowdown can end with evidence and a recommendation. Change code
only within the assigned implementation scope and writer's worktree.

For test runtime, builds, coverage or CI efficiency, also read
[test and CI guidance](references/test-and-ci.md). The measurement helper and
existing test/CI protocols are part of this same skill.

## Define the comparison before tuning

Name the user action, representative workload, primary metric and acceptance
rule before the candidate measurement. Include other metrics that could reveal
a shifted cost or regression, such as tail latency, CPU, memory, payload size,
cold start or total work. Use the task's actual budget and requirements.

When load affects the question, record request rate, concurrency and workload
mix alongside error/timeout rates and relevant saturation signals. For
streaming, UI, agent or terminal flows, measure time to first useful output and
completion time when both matter. Check how buffering changes that tradeoff.

Bind measurements to the source revision, build, runtime, relevant config,
dependency inputs and environment. Separate cold and warm runs and record
cache state. Account for the cost of creating or warming a cache as well as
its hits. Keep setup, queue time, action latency and background work distinct
when those differences affect the conclusion.

Choose a repeatable workload that exercises the affected boundary. State what
fixtures or simulated services exclude from the claim. A real external-service
claim needs evidence at that service boundary within existing permissions.
Reuse or extend an owned workload script when repeated execution is needed.
Keep credentials and private payloads out of traces and reports.

For a single non-interactive command on macOS or Linux with Python 3, read
[the capture contract](references/capture-contract.md) and use
`scripts/capture.py`. It preserves argv, streams and exit status in one
measurement. Copy reported fields from its receipt and keep unknowns unknown.
The caller owns context and any external deadline. The helper retains its
existing `smoky-ci-performance.capture.v1` receipt schema for compatibility.

Repeat baseline and candidate enough to expose noise that could change the
decision. Prefer interleaved runs on the same environment and report sample
count, spread, typical latency and relevant tail behavior. If conditions or
inputs differ materially, label the comparison inconclusive. Do not infer
tail improvements from a few favorable observations.

## Count work and find its cause

Measure operations per action before choosing a mechanism. Useful counts
include queries, RPCs, file reads, catalog builds, process launches, copies,
allocations, rendered updates and bytes transferred. Trace dominant work to
the code that issues it. Use a CPU profile, allocation profile or browser trace
when counts alone cannot explain the cost.

Ask whether the action needs each operation. Look for eager optional work,
per-item recomputation, rechecking an already admitted fact, rebuilding a
catalog, rescanning a full result for each delta or rereading a completed write.
Retain operations that protect correctness, freshness, authorization or a
supported lifecycle. Profiling overhead and instrumentation changes also need
to be comparable between runs.

## Try the smallest justified improvement

Prefer removing unnecessary work, doing it once at its existing owner, carrying
the prepared result through the flow, and then batching independent work.
Preserve ordering, cancellation, error, freshness and resource limits.
Batching can improve throughput while worsening interactive or tail latency.

Consider a cache only after establishing why those simpler changes cannot
satisfy the requirement. Define key identity, scope, invalidation owner,
freshness, capacity and miss behavior. Check stale or partial entries and the
cost of population and eviction. Preserve correctness when caching provides no
benefit. Adding a worker or deferring work also requires measuring total cost
and the later wait, not just the original thread's timing.

Keep experiments small enough to attribute effects. A read-only assignment
ends with the supported diagnosis and candidate change. New product tradeoffs
or reduced guarantees need the owner's decision.

## Verify the result and stop

Rerun the same workload under the written acceptance rule. Verify the affected
behavior and consumers with the repository's applicable checks. Retain raw
measurements or durable references, failed and rejected experiments, and the
reason a result is comparable. Report any metric that regressed or remains
unmeasured. A benefit in one metric cannot silently accept harm in another.

If the target is met with the required correctness proof, hand the change to
the repository's review and delivery process. If the evidence shows no
meaningful gain, withdraw the candidate or report no change. If measurement
cannot support a decision, report the specific gap and stop that experiment.
This skill defines no recurring schedule or deployment authority.

Report the workload and command, source/environment identity, acceptance rule,
before/after work counts and timing distributions, sample counts, correctness
checks, rejected candidates and remaining limits. A faster local measurement
does not establish production performance or monetary savings.

## Provenance

Adapted from OpenClaw's `openclaw-performance` skill. This version uses the
consumer's workloads, budgets and review process. See the
[source and license notice](THIRD_PARTY_NOTICES.md).
