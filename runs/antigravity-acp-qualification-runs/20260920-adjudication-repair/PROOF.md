# Antigravity ACP adjudication repair

This packet records the repair evidence for PR #52 after independent review.

## Regression suites

- `npm test` in `bridge/antigravity-acp`: 20 tests, 20 passed, 0 failed.
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
with the backend error, the peer remained alive after the terminal result, and
the peer exited when the owning broker shut down. This is deliberately surfaced
as uncertainty rather than claimed as observed per-session cleanup; no global
or other-task process was killed.

## F3: packaging assertion

The packaging test now expects the shipped plugin version `0.3.3`, matching the
manifest and installed plugin. The assertion remains exact; it was not removed
or weakened.

## Review boundary

The PR remains unmerged. Native MCP reload/reconnection is a separate gate: the
current Codex task must be freshly reloaded before a native delegate can be
accepted as proof against this repaired installed process. No raw prompt,
response body, token, or credential material is retained here.
