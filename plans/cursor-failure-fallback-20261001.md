# Cursor failure classification and bounded fallback decision

Accepted scope: repair the observed Cursor ACP error-as-text completion gap and add opt-in parent-reviewed fallback continuation. Source baseline e6aaaded1b05f871bbbde65008b17abcf61fe111; upstream OpenClaw 72f5840c11922793dfacad33c9fc1c0bd3e8b175.

## Decisions before implementation

- Recognize only the evidenced terminal Cursor PING-error signature and structured runtime errors. Preserve partial bounded handoffs; terminal lifecycle and cleanup remain separate from acceptance.
- An omitted default model may opt into at most two advertised model fallbacks using `fallbackModels`. An explicit model, effort, or server model setting stays strict.
- No automatic prompt replay: Cursor sessions are ephemeral and cannot supply trustworthy continuation/replay evidence. The parent must inspect partial files/processes/proof and submit a new bounded continuation with `retryOf` and `partialWorkReviewed: true`.
- Resolve the configured chain once against the advertised catalog. Each continuation creates a separate immutable job, uses only the next candidate, and consumes the original wall-clock deadline. The original exact executable, workspace, conversation, binder, and permission policy stay required. No auth-profile rotation or executable substitution.
- The source must have the recognized transport failure, terminal state and observed cleanup, and remain the current binding under the conversation lock. Completed/incomplete handoffs, cancellation, input/permission problems, selection drift, local coordination failures, exhausted candidates, and exhausted deadlines cannot enter fallback.
- No bridge-level transient retry loop or credential cooldown store: Cursor owns opaque request retries and credentials. Each configured candidate runs once. Exhaustion remains visible with separate job/proof links.
- The run heartbeat is event-driven; owner lease heartbeat is periodic. Neither is the HTTP/2 PING. Investigate without altering live leases; do not add a watchdog that kills a quiet worker.

## Acceptance and review

Hermetic regressions must prove the observed error is failed with partial handoff and independent cleanup; quoted/errors in thought or tools do not count; explicit pins stay strict; parent review, current binding, ownership, workspace, policy and deadline gates hold; candidate IDs are resolved once and rechecked; no original prompt body is retained or auto-replayed. Run existing Cursor/shared runtime and packaging suites. Open a focused draft PR, preserve independent review findings and official review receipts; no merge or global install.

This is a focused adaptation of OpenClaw selection/replay boundaries, not a claim that OpenClaw automatically changes an external ACP harness model. Upstream ACP native-default tests explicitly separate native model fallbacks from the external harness primary.

## Evidence-driven repair 1

A bounded independent native Luna review on the candidate terminated with `Error: RetriableError: [resource_exhausted] Error` while canonical status again said completed. No review verdict was produced. Recognize this second exact native suffix as `CURSOR_RESOURCE_EXHAUSTED`, preserve the partial handoff, and keep model fallback ineligible because model/account/backend scope and reset details are unavailable. No reviewer retry, permission change or model substitution is inferred. Initial exact-head CI remains historical after this source repair; rerun the changed suites and obtain review for the repaired head.

Final pin audit: retain whether the host supplied its model explicitly, including the same alias as the plugin default. String equality with the default must not erase a host pin. The explicit-pin regression includes that case.
