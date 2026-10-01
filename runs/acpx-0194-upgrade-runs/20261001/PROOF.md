# ACPx 0.19.4 proof

Fresh main: e6aaaded1b05f871bbbde65008b17abcf61fe111. Isolated branch codex/acpx-0194-upgrade; PR111. No tracked AGENTS.md/REPO_HYGIENE.md; supplied task constraints apply.

## Artifact identity

`parent-artifact-verification.json` independently verifies the published tarball SHA512 integrity, SHA256 tarball/runtime/registry, package exports and declared dependencies. Tag v0.19.4 independently resolved to 8e396609238086dee6a407fdb3b3ac46dbdedd70. npm gitHead absent (null in contract). All three locks pin 0.19.4. Historical candidate 0.18.0 and prior proof identities remain historical.

## Implementation and verification

Native Cursor Luna Medium, approve-all, job 89b90bdf-c548-406f-8a74-bed0cef687fe failed at its 300000ms budget. Canonical receipt confirms taskComplete/cleanupReady/complete and exact owned exits; no retry. `implementation-receipt.json` records launch identities and external bounded proof path. Parent completed synthetic coverage only after cleanupReady.

The added worker catalog fallback was rejected: the pinned public API already normalizes availableModelIds, so the change was unnecessary. Its wrong missing-model expectation failed initial testing. Removed this new behavior/test; no existing acceptance test relaxed.

New shared regressions resolve each bridge's own acpx public runtime exports: accepted alias versus resolved current ID and reconnect, omitted/non-list acknowledgement catalogs, reused provider IDs with independent history and replacement ownership, timeout before prompt and adapter retirement/reconnect. Temporary startup catalog tests exercise published CLI exec (upstream #794 runOnce path), with zero provider calls. Timer delivery is smoke evidence, not owned-creation ordering proof; the unresolved qualification blocker is detailed below. Every test records peer launches/exits or trace PIDs and asserts absence after retirement.

Initial new regressions passed 21/21. Legacy setter alias variation separately passed 3/3. Final provider-free counts are in test-summary.json; these passes do not resolve the later startup ordering finding. Raw logs are generated local run artifacts, not model transcripts. Final summaries will retain hashes and exact command outcomes.

## Live gate and routes

`native-readiness-summary.json`: installed 0.19.3 Cursor and AGY pass; approve-all; exact selected/current IDs. Grok native tool callable but MODEL_UNAVAILABLE: required grok-4.7, advertised grok-4.6/grok-4.5. No model substitution.

`proof/acpx-0194/candidate-live.mjs` prepares three separate retained fixtures and all three supported runtimes under this task root with SAARIUS_ACP_RUNTIME_ROOT. It does not modify shared installed pins or launch any prompt during prepare. Live run requires independent source/driver review and explicit authorization for a task-local candidate MCP client, because installed native tools remain 0.19.3. Each route has an exclusive one-shot launch fence, max300000ms prompt budget, protected-test hash/mode checks, canonical outcome and cleanup acceptance, no automatic retry/fallback. Candidate runs are not installed-native execution proof.

## Review gates

Spark-2 effective SSH route passed (alias spark-2, smoky@192.168.1.41, hostname spark-2). Independent source/driver review cleared before live. Official comprehensive Spark review cleared head4ff23ac with exact-tuple qualification and P3 native/applied threshold. CI at that head failed macOS shared startup case; other3 checks passed. Human merge gate remains closed. No ClawSweeper per assigned repo contract. No merge/install/restart/account/billing changes.

## Offline closeout

`test-summary.json`: Cursor128 passed/11 skipped; AGY66 passed/12 skipped; Grok85 passed; shared135 passed serially; Python101 passed. Shared initial parallel run had one existing five-second executable-preflight timeout; serial rerun passed without changing thresholds. CI b7b88b7 passed all four Linux/macOS checks. Later4ff23ac CI passed3/4 but failed macOS startup timer case.

Independent review `independent-review.json` clean at ee016454349ffc4b6bbe1fe497f2a4bba50b78eb. Accepted R1 local route/hop and AGY executable binding, and R2 exact-worker termination/failure retention; all resolved. Rejected added broker catalog fallback as unnecessary; public API already normalizes it. Driver SHA2561bef7e6f5ec124e9a2bff04afb1d4af9dbef9971f6784c4d2c78e57486c9f80a unchanged. Physical absence of every complete recorded worker identity is required; missing per-worker native exit receipt remains explicit (AGY only exposes one). No process kills.

## Authorized candidate live results

Human answer: “Authorize the two candidate tasks.” Both used the reviewed unchanged driver SHA2561bef7e6f5ec124e9a2bff04afb1d4af9dbef9971f6784c4d2c78e57486c9f80a. `live-summary.json` binds exact0.19.4 runtime identities, one prompt each, 300000ms caps, requested/selected/current model, host conversation, protected hash and physical absence of every recorded complete worker identity. Cursor Luna Medium job1eb49a04-41ae-457e-ab5c-2e7b401bfb4c completed~23s; Antigravity gemini-3.8-flash-high jobe58ae6d1-4d26-4809-b378-77e78f6306f6 completed~32s. Each passed4 independently rerun protected cases. Their candidate-live/<lane>/result.json, verification.json, owned-worker-termination.json and retained fixtures are the bounded raw evidence. Backend session discard unsupported remains explicit. No retries or native installed execution claim. Grok MODEL_UNAVAILABLE requiredgrok-4.7, advertised4.6/4.5, zero prompts or fallback.

## Startup qualification blocker

`startup-qualification-blocker.json` records failed macOS CI36867016925 on4ff23ac, raw log path/hash and rejected timing attempts. Sending the notification before response is pre-ownership and ignored; putting response then notification in one write still arrives before ownership. Neither is accepted as a fix. Raw failed logs remain retained.

Independent review acceptedR3: timer smoke does not establish notification processing after loadedSessionId assignment and before createSession return. This remains unresolved. Published public CLI offers no deterministic acknowledgement/hook for that boundary; upstream#794 uses a private descendant-capture test seam. No private monkeypatch/runtime replacement/synthetic process table was used. A passing timer rerun does not closeR3.

AcceptedR4: original removal case was vacuous because stale snapshot never advertised requested model. Corrected initial catalog to advertise it and strengthened assertion to require zero setters as well as zero prompts. Corrected six smoke cases passed locally (startup-removal-strengthened.log). R4resolved; R3blocked. No acceptance criterion relaxed or skipped. Narrow follow-up: supported upstream creation lifecycle/test barrier or public conformance fixture, then qualify exact published artifact.

## Review receipts and gate

`spark-review-4ff23ac.json/.txt` identify official requestreq-20261001T131603Z-158257323880 onSpark-2: comprehensive, native/appliedP3, exact_tuple_qualifiedtrue, zero findings, basee6aaaded and head4ff23ac. This receipt applies only to that head. `ci-4ff23ac.json` retains the failed exact-head CI outcome. Source/fixture changes and final proof require fresh final-head review/CI; PR body records their resulting status without recursively changing reviewed commits.

No ClawSweeper under assigned repo contract. Asset shelf saari-co/swarm-pr-assets explicitly resolved; no changed media, placement pass. Installed plugin/shared runtimes remain0.19.3 unchanged. Draft PR remains blocked for startup qualification and Grok model availability. No merge/install/restart/account/billing changes.
