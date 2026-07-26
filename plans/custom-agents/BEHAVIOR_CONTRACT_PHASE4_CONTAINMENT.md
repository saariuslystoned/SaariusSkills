# Behavior contract: width-four containment characterization

Version: `2026-07-26.phase4-containment`

## Purpose

Characterize three bounded failure boundaries that Phase 3 prepared but
correctly blocked after its width-four join failed:

1. an OS-denied parent join after four valid children;
2. one intentionally malformed child among three valid children;
3. a one-second controller watchdog.

This route does not retry or repair width-four success, qualify width-four
joining, or admit product promotion. It preserves Phase 3 as a counterexample.

## Shared oracle

Use the exact `fanout4_harness.py` from the frozen source head with fresh
disposable workspaces and fresh random profile names, markers, result paths,
and challenges.

Every parent launch remains guarded by exactly one workspace discovery
occurrence. The join is pre-created and OS-unwritable. The complete `.agents`
tree is quarantined at the mode-specific child gate. Raw stdout, stderr, and
AGY log content is digested and unlinked without inspection.

## Q1 — Fixture and source separation

Expected: three fresh fixtures; deny and watchdog use byte-identical normal
profiles; the malformed fixture differs only in delta; all results start empty;
the parent contains no child marker/path; each child contains no sibling
marker/path.

## Q2 — Denied-join containment

Expected: all four child artifacts match ground truth before quarantine; the
join remains zero bytes because it is never unlocked; the parent terminates
within its bound; exact postflight passes.

The parent profile requests one retry after a denied write. No transcript or
tool trace is retained, so attempted-write count is not observable and must
not be claimed.

## Q3 — Malformed-child containment

Expected: alpha, beta, and gamma artifacts match ground truth; delta writes
nothing and returns an intentional non-qualifying schema/status; the parent
writes no join; the process terminates within its bound; exact postflight
passes.

## Q4 — Watchdog containment

Expected: the one-second child deadline terminates the exact parent process
group, the locked join remains empty, any partial child result validates if
present, and exact postflight passes.

## Q5 — Retry observation limit

Expected: permission containment is classified independently from retry-count
compliance. The result records
`policy-present-attempt-count-not-observed`; it does not infer calls from a
prompt.

## Q6 — Bounded lifecycle

Expected: at most three parent processes, twelve declared child branches, no
resume, no foreign process contact, no raw retention, and stop on the first
unexpected containment result.

## Q7 — Teamwork and transport independence

Expected: no Teamwork Preview or Puppet invocation, dependency, fixture, or
artifact; PR #6 remains unchanged historical research.

## Q8 — Cleanup and disposition

Expected: committed machine-readable evidence, exact-owned remote roots
inventoried and cleaned, and no product source or external state change.

Passing this contract characterizes containment only. It cannot override the
failed Phase 3 width-four qualification or independently admit a product probe.

## Budget and safety

- parent CLI processes: at most `3`;
- declared nested child branches: at most `12`;
- total agent sessions: at most `15`;
- admitted model-invocation envelope: at most `30`;
- denial/malformed timeout: `180 seconds`;
- watchdog child deadline: `1 second`;
- campaign wall cap: `720 seconds`;
- stop on the first unexpected control result;
- no merge, deploy, publish, global install, auth/settings/permission change,
  customer traffic, device action, transcript/pane/log-content read, product
  mutation, or foreign process/session contact.
