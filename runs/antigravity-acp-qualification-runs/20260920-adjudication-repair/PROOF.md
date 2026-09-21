# Antigravity ACP adjudication repair

This packet records the repair evidence for PR #52 after independent review.

## Regression suites

- `npm test` in `bridge/antigravity-acp`: 24 tests, 24 passed, 0 failed.
- `python3 -m unittest tests.test_packaging tests.test_puppet_antigravity_acp -q`: 20 tests, OK.
- `git diff --check`: clean.

## F1: owner-safe recovery

The broker now persists a broker identity (`brokerId`, PID, and process start
time), probes the recorded process conservatively, and recovers a non-terminal
job only when the exact owner lease matches and the owner is proven dead or
the PID is proven reused. Ambiguous or incomplete identity remains unknown.

The cross-process proof used a separate broker process against the same state
root while the original owner remained alive:

```text
{"separateProcess":true,"secondBrokerStatus":"running","ownerStatus":"cancelled","cleanup":"completed","closeCalls":1}
```

The replacement broker did not take over the live owner's job; the original
owner retained cancellation authority. A synthetic dead-owner case separately
produced `failed` with `error.code=BRIDGE_RESTARTED`.

## F2: terminal cleanup

Completed, cancelled, and needs-input paths all pass through the same awaited
terminal cleanup hook. The fixture tests assert cleanup completion and one
runtime close call for completed and needs-input outcomes; the cancellation
test asserts the explicit cancelled outcome and the full suite passes.

The pinned runtime's synthetic ACP peer does not advertise `session/close`.
For that real-runtime probe, the broker recorded `cleanup.status=uncertain`
with the backend error, but the unmodified runtime still released its local
client and the peer was observed dead after the terminal result. This is
deliberately surfaced as uncertainty rather than used to claim stronger
backend-session semantics; no global or other-task process was killed.

The remaining fence defect was independently reproduced with explicit close
failure injection: a short wait exposed `taskComplete=true` but
`cleanupReady=false`, and a replacement in the same workspace was admitted
while the first peer remained alive. The repaired broker now returns
`complete=false` until cleanup is observed, persists bounded cleanup identity,
and rejects same-workspace replacement with `WORKSPACE_CLEANUP_PENDING` while
allowing independent workspaces.

The new deterministic coverage also exercises a second broker sharing the same
state root and owner-dead recovery. The separate broker remains blocked while
the owner is live; an exact dead-owner identity records `cleanup=recovered`
with the original owner PID before replacement is admitted.

## F3: packaging assertion

The packaging test now expects the shipped plugin version `0.3.3`, matching the
manifest and installed plugin. The assertion remains exact; it was not removed
or weakened.

## Native process gate

After pushing `e365520`, the plugin was reinstalled at `0.3.3`; Antigravity
setup returned `MCP_READY` with the pinned runtime and personal OAuth policy.
The current task's native readiness call also succeeded, but native delegate
job `8b7a509d-48bf-4ad3-823c-92aee18f2105` persisted no `Owner` or `Cleanup`
fields in its non-secret `STATE.md`/`PROOF.md`. It therefore came from the
pre-repair MCP process despite the reinstall. The job was cancelled before
spending a coding turn. A fresh Codex task or explicit MCP reconnect is still
required; only a subsequent job whose persisted metadata contains the repaired
owner/cleanup fields can establish native execution on this head.

## Review boundary

The PR remains unmerged. Native MCP reload/reconnection is a separate gate: the
current Codex task must be freshly reloaded before a native delegate can be
accepted as proof against this repaired installed process. No raw prompt,
response body, token, or credential material is retained here.
