# Cursor ACP failure and fallback

Cursor can report an HTTP/2 PING timeout as assistant output and then return
`end_turn`. The bridge recognizes the evidenced terminal signature
`Error: RetriableError: [unavailable] PING timed out` and returns `failed` with
`CURSOR_TRANSPORT_UNAVAILABLE` and `error.source: cursor-output-signature`.
The separately observed terminal signature
`Error: RetriableError: [resource_exhausted] Error` becomes
`CURSOR_RESOURCE_EXHAUSTED`. It has no trusted scope or reset details and remains
ineligible for configured model fallback. Structured runtime error events also
prevent a completed result from hiding a failure. The bounded partial handoff remains available for parent review.

The text signature is a compatibility heuristic, not authenticated provider
metadata. Quoted/fenced examples, thought and tool output, and an error followed
by recovery text do not match. An indistinguishable unquoted terminal example
can still match; the parent must inspect the outcome. This rule does not broadly
interpret arbitrary prose as a provider error.

`taskComplete` means the turn is terminal. `cleanupReady` proves the recorded
owned local worker cleanup. `complete` requires both. These fields do not prove
acceptance of source changes or tests, and local worker exit does not prove
backend session history was discarded. An ordinary `completed` handoff can
still describe incomplete work.

## Opt-in parent-reviewed continuation

Default behavior remains strict. When both model and effort are omitted, the
parent may configure up to two model candidates for that task:

```json
{
  "workspace": "/absolute/owned/worktree",
  "hostConversationId": "genuine-parent-conversation-id",
  "prompt": "Perform the bounded task and report proof and remaining work.",
  "timeoutMs": 1800000,
  "fallbackModels": ["grok-4.6", "grok-4.7"]
}
```

The primary remains the plugin's Luna Medium default. Every candidate resolves
once to a unique live advertised ID. Duplicate, unavailable, ambiguous or
conflicting selections fail before a prompt. An explicit model, effort, or
server model/effort override rejects a nonempty fallback chain. An empty list
disables fallback. Readiness remains a check of the exact requested primary;
it never uses a fallback to turn red readiness green.

Status/result expose `fallback` with the root job, immutable resolved chain,
current index, original deadline, next candidate, eligibility and reason.
Reading these fields never dispatches a turn. For the recognized terminal PING
failure, the parent must first inspect partial files, test artifacts and owned
process state. Cleanup of the recorded Cursor worker alone does not establish
cleanup of every test server or an interrupted external action. After that
review, submit a fresh continuation prompt:

```json
{
  "workspace": "/absolute/owned/worktree",
  "hostConversationId": "genuine-parent-conversation-id",
  "prompt": "Continue only the reviewed unfinished step; inspect its current state before repeating an action.",
  "retryOf": "returned-failed-job-uuid",
  "partialWorkReviewed": true
}
```

`partialWorkReviewed` is a parent attestation, not a bridge proof of safe replay
and not a request for a new human approval. The parent must honor existing human
gates on external actions. Do not assert it without reviewing partial work.

A continuation creates a new job with an immutable exact model and links its
predecessor and root. It consumes the remaining original wall-clock budget;
startup time is deducted again immediately before the prompt. It cannot extend
that budget or override model, effort, timeout or candidate list. The predecessor
must remain the current conversation job under the binding lock. Workspace,
binder, conversation, executable and effective permission mode must match.
Existing one-worker admission and observed-cleanup gates still apply across
broker restarts. Missing binding or catalog drift fails closed.

Only `CURSOR_TRANSPORT_UNAVAILABLE` admits this initial policy. Completed partial
work, cancellation, interactive/permission failures, final job timeout, local
coordination errors and model-selection failures stop the chain. Each candidate
is attempted once. Exhaustion reports `reason: exhausted`; expired budgets report
`deadline_exhausted`; predecessor results and proof remain independently
readable. A later independent assignment may choose a model explicitly, but is
not a hidden extension of this chain. Historical jobs are not reclassified or
rewritten by this repair and cannot acquire a fallback chain retroactively.

This changes the model served through the same Cursor executable/account route.
Candidates can use different underlying model vendors. It does not change to a
direct vendor API, rotate auth profiles, choose another executable, alter
permissions, reload plugins, or infer billing/quota behavior. Cursor's opaque
internal request retries remain Cursor-owned. No extra same-model replay loop or
credential cooldown store is added here.

## Pinned upstream comparison

Inspected upstream: [OpenClaw 72f5840c11922793dfacad33c9fc1c0bd3e8b175](https://github.com/openclaw/openclaw/tree/72f5840c11922793dfacad33c9fc1c0bd3e8b175).
The following are upstream behavior, rather than this bridge's implementation:

- [Native selection tests](https://github.com/openclaw/openclaw/blob/72f5840c11922793dfacad33c9fc1c0bd3e8b175/src/agents/model-selection.acp-runtime.test.ts)
  keep explicit session selections strict. They also distinguish an external
  ACP harness primary from the native model/default fallback chain; they do not
  establish automatic fallback of Cursor's selected external model.
- [Candidate construction](https://github.com/openclaw/openclaw/blob/72f5840c11922793dfacad33c9fc1c0bd3e8b175/src/agents/model-fallback-candidates.ts)
  orders and deduplicates configured routes. Explicit empty overrides prevent a
  hidden configured-primary retry.
- [The fallback runner](https://github.com/openclaw/openclaw/blob/72f5840c11922793dfacad33c9fc1c0bd3e8b175/src/agents/model-fallback-runner.ts)
  applies replay/committed-work guards and treats local coordination and
  non-continuable transcript failures separately from provider failover.
  Configured native routes can cover auth, billing, rate-limit, overload,
  missing-model and timeout failures; some unknown errors can advance when
  candidates remain. Abort, terminal timeout, final refusal and context
  compaction boundaries can stop fallback. Exhaustion retains attempt details.
- [Terminal-boundary tests](https://github.com/openclaw/openclaw/blob/72f5840c11922793dfacad33c9fc1c0bd3e8b175/src/agents/model-fallback.terminal-boundary.test.ts)
  verify cancellation, cleanup/ownership and recorded terminal stops are not
  rewritten as opportunities to rotate routes.
- [Recovery controller](https://github.com/openclaw/openclaw/blob/72f5840c11922793dfacad33c9fc1c0bd3e8b175/src/agents/embedded-agent-runner/run/failover-retry-controller.ts)
  bounds rate-limit recovery at ten total attempts, other transient recovery at
  eight retries and a 90-second consecutive-outage window, with jitter capped at
  30 seconds and provider retry hints as minimum waits. It continues transcripts.
- [Auth failure state](https://github.com/openclaw/openclaw/blob/72f5840c11922793dfacad33c9fc1c0bd3e8b175/src/agents/auth-profiles/usage-failure-state.ts)
  starts transient cooldown at 30 seconds, then one minute, capped at five
  minutes; rate-limit half-open failures can grow farther. Billing/permanent-auth
  disable windows start at ten minutes. Credentials and rotation are separate
  from model selection.

The [official model-failover documentation](https://docs.openclaw.ai/concepts/model-failover)
explains selection sources, turn-local winners, cooldown probes and exhaustion.
This bridge adopts the strict-pin, explicit-chain, terminal-stop and replay
boundaries. Parent-reviewed separate jobs are our narrower adaptation because
this Cursor bridge does not preserve resumable model transcripts or own the
harness's credentials/provider health.
