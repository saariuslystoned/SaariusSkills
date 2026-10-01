# ACPx 0.19.4 proof

Fresh main: e6aaaded1b05f871bbbde65008b17abcf61fe111. Isolated branch codex/acpx-0194-upgrade; PR111. No tracked AGENTS.md/REPO_HYGIENE.md; supplied task constraints apply.

## Artifact identity

`parent-artifact-verification.json` independently verifies the published tarball SHA512 integrity, SHA256 tarball/runtime/registry, package exports and declared dependencies. Tag v0.19.4 independently resolved to 8e396609238086dee6a407fdb3b3ac46dbdedd70. npm gitHead absent (null in contract). All three locks pin 0.19.4. Historical candidate 0.18.0 and prior proof identities remain historical.

## Implementation and verification

Native Cursor Luna Medium, approve-all, job 89b90bdf-c548-406f-8a74-bed0cef687fe failed at its 300000ms budget. Canonical receipt confirms taskComplete/cleanupReady/complete and exact owned exits; no retry. `implementation-receipt.json` records launch identities and external bounded proof path. Parent completed synthetic coverage only after cleanupReady.

The added worker catalog fallback was rejected: the pinned public API already normalizes availableModelIds, so the change was unnecessary. Its wrong missing-model expectation failed initial testing. Removed this new behavior/test; no existing acceptance test relaxed.

New shared regressions resolve each bridge's own acpx public runtime exports: accepted alias versus resolved current ID and reconnect, omitted/non-list acknowledgement catalogs, reused provider IDs with independent history and replacement ownership, timeout before prompt and adapter retirement/reconnect. Temporary startup catalog tests exercise published CLI exec (upstream #794 runOnce path), with zero provider calls. Timed local notification delivery is smoke evidence, not general wire-order linearization. Every test records peer launches/exits or trace PIDs and asserts absence after retirement.

Initial new regressions passed 21/21. Legacy setter alias variation separately passed 3/3. Python passed 101 tests. Initial Antigravity passed 66 (12 historical candidates skipped); Grok passed 85. Final Cursor/shared suites pending at this checkpoint. Raw logs are generated local run artifacts, not model transcripts. Final summaries will retain hashes and exact command outcomes.

## Live gate and routes

`native-readiness-summary.json`: installed 0.19.3 Cursor and AGY pass; approve-all; exact selected/current IDs. Grok native tool callable but MODEL_UNAVAILABLE: required grok-4.7, advertised grok-4.6/grok-4.5. No model substitution.

`proof/acpx-0194/candidate-live.mjs` prepares three separate retained fixtures and all three supported runtimes under this task root with SAARIUS_ACP_RUNTIME_ROOT. It does not modify shared installed pins or launch any prompt during prepare. Live run requires independent source/driver review and explicit authorization for a task-local candidate MCP client, because installed native tools remain 0.19.3. Each route has an exclusive one-shot launch fence, max300000ms prompt budget, protected-test hash/mode checks, canonical outcome and cleanup acceptance, no automatic retry/fallback. Candidate runs are not installed-native execution proof.

## Review gates

Spark-2 effective SSH route passed (alias spark-2, smoky@192.168.1.41, hostname spark-2). Independent source/driver review, official comprehensive Spark autoreview, exact-head CI, and human merge gate remain pending. No ClawSweeper per assigned repo contract. No merge/install/restart/account/billing changes.
