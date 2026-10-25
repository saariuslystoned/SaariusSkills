---
name: pstack-playbooks
description: "Standardized engineering task runbooks for bug-fixes, features, refactors, hillclimbing, and trace forensics."
---

# Engineering Task Playbooks

Select and execute the appropriate runbook for the engineering task:

## 1. Bug Fix Playbook
1. **Repro First**: Write a standalone reproduction test or script that demonstrates the defect.
2. **Observe Failure**: Run the test and capture the exact failure trace.
3. **Root Cause**: Locate the exact bug in the source code; avoid patching symptoms.
4. **Surgical Fix**: Apply the minimal diff to correct the logic.
5. **Verify**: Prove the repro test now passes, and run the full test suite to ensure zero regressions.

## 2. Feature Playbook
1. **Contract Design**: Define types, interfaces, and API contracts before coding.
2. **Feature Flag / Isolation**: Build behind a flag or isolated module if high-impact.
3. **Incremental Implementation**: Build bottom-up (data types -> core logic -> integration -> UI/API).
4. **End-to-End Proof**: Run integration tests and capture verifiable receipts.

## 3. Refactoring Playbook
1. **Preserve Behavior**: Refactoring strictly reorganizes structure; never add features or fix bugs in the same commit.
2. **Baseline Green**: Verify all existing tests pass before touching code.
3. **Surgical Restructuring**: Rename, extract, deduplicate, or simplify in small atomic commits.
4. **Verify Parity**: Run tests after every discrete change to ensure zero behavioral drift.

## 4. Hillclimb (Performance) Playbook
1. **Measure Baseline**: Record exact benchmark metrics, latencies, or byte sizes.
2. **Identify Bottleneck**: Profile CPU/memory/IO to find the hot path.
3. **Targeted Optimization**: Make one focused improvement.
4. **Benchmark Proof**: Re-measure under identical conditions and output a before/after comparison table.

## 5. Trace Forensics Playbook
1. **Gather Telemetry**: Collect logs, traces, error stacks, and environmental state.
2. **Form Hypothesis**: Propose a falsifiable hypothesis for the intermittent failure.
3. **Instrument & Isolate**: Add targeted logging or reproduction scaffolding.
4. **Handoff**: Once root cause is proven, transition to the Bug Fix Playbook.\n