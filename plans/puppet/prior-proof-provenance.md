# Puppet prior-proof provenance and delta map

Status: curated public implementation input, not proof that Puppet exists

Evidence cutoff: 2026-07-21

Scope: prior orchestration, lifecycle, proof, review, and packaging evidence
relevant to the minimum Puppet N kernel

## Public evidence boundary

The GrillTrack inspected a private operator repository, local installed skills,
open implementation branches, current CLI help/version surfaces, and this
public SaariusSkills repository. The private evidence remains a local campaign
overlay. This public map preserves every material invariant, limitation,
classification, and revalidation delta without publishing private checkout
paths, commit identities, pull-request identifiers, machine topology, or raw
event history.

Private evidence cannot be copied into the MIT-licensed Puppet distribution
merely because the operator can access it. Its contracts may be cleanly
reimplemented; source extraction requires an explicit license and attribution
decision. SaariusSkills and GrillTrack are MIT-licensed. One studied upstream
PTY implementation is Apache-2.0 and would require its license, notice, and
change-marking obligations if it were ever vendored.

## Locked admission rules

- Puppet learns from exact commits, bounded structured checkpoints, controller
  tests, and sanitized evidence. It never learns from target panes, transcripts,
  prompts, tool arguments, conversation stores, or auth-bearing logs.
- Every live target is launched only through a current-version, fail-closed
  unrestricted/always-approve mapping with the harness sandbox disabled where
  exposed. That does not widen the task's external-action authority.
- An adapter remains doctor-only until its exact executable, adapter, and probe
  protocol pass the shared real-harness control-loop probe.
- Direct tests and controlled fault injection qualify pure Puppet kernel
  behavior. A fake target never qualifies an adapter or end-to-end claim.
- Prior proof reduces only the exact known delta. Every reimplemented component
  reruns deterministic tests, and every changed mechanism or new composition
  receives fresh live proof.

## Zero-agent CLI census

This is a dated static census, not behavioral proof. Puppet must resolve and
fingerprint the installed commands again before use.

| Harness | Observed version | Declared surface worth probing | Status |
|---|---:|---|---|
| AGY / Google Antigravity | `1.1.5` | interactive/print modes, persistent conversation, model/effort, permission bypass, sandbox control | installed; behavioral delta required |
| Codex | `codex-cli 0.145.0` | stdin execution, JSONL/schema output, resume, model/cwd, approval+sandbox bypass | installed; behavioral delta required |
| Claude Code | `2.1.215` | stream JSON/schema, session identity/resume, model/effort, permission bypass, hooks | installed; behavioral delta required |
| Cursor agent | `2026.07.17-3e2a980` | JSON/stream JSON, resume, model, workspace/worktree, YOLO, sandbox disable | installed; no admitted prior lane |
| Cursor application CLI | `3.9.16` (`arm64`) | alternate `cursor agent` entrypoint | installed companion surface; equivalence unproved |
| Grok | `0.2.106` | prompt file, JSON/stream JSON, session identity/resume/fork, model/effort, permission bypass, sandbox, headless/server modes | installed; newer than historical lane evidence |

AGY is the harness; Gemini is the separately recorded model family. The same
harness/model separation applies to every adapter. Codex changed versions
during the design session, demonstrating why cached capability claims must be
invalidated on executable, version/help, adapter, or protocol drift.

A dated, untrusted operator fixture records this expected AGY interpretation:
the display `Gemini 3.6 Flash · high · AI: Out of credits` refers to AI overage
credits rather than subscription exhaustion or task failure. It must not by
itself stop or trigger diagnosis. Puppet may normalize it as the non-terminal
advisory `agy_ai_overage_credits_exhausted`, but must freshly validate the
interpretation for the current executable/provider surface, never scrape a pane
to detect it, and require separate controller-observed failure evidence.

## Provenance-and-delta matrix

| Evidence family | Classification | Supported Puppet invariant | Honest limitation | Smallest fresh Puppet delta |
|---|---|---|---|---|
| AGY orchestration lanes | reusable transport contract | Preflight before launch; one named tmux lane; process/store-lock refusal; durable `STATE.md`, events, heartbeat, and proof; unrestricted launch | Historical transport exposed prompts in argv and monitored pane/log content; both are rejected. It does not qualify Teamwork Preview or make custom-agent semantics a Puppet dependency. | Rebuild a current doctor adapter; prove ordinary non-argv prompt transport, checkpoint handoff, one follow-up, exact identity, and exact halt against real AGY. |
| Sanitized AGY hook prototype | reusable implementation pattern | A narrow event can retain timestamp, event kind, conversation identity, step/tool name, idle/termination, and error boolean while omitting payloads. | Local prototype only; disappearance can be silent and does not prove routing, acknowledgement, or halt. | Recreate a bounded schema; fault-inject dropped/malformed/oversized events; keep checkpoints authoritative when the hook is absent. |
| Codex goal lanes | admitted narrow proof | Real Codex can run in an isolated worktree with explicit model/effort, approval bypass, full-access posture, durable lifecycle files, and a separate terminal artifact. Launch is not completion. | Host/repo-specific; historical monitoring scraped panes/logs and some prompts used argv. Current exact version remains unproved. | Reimplement only portable launch-versus-terminal and worktree contracts; run the shared real probe against current Codex without transcript inspection. |
| Claude goal lanes | reusable contract | Persistent sessions, permission bypass, bounded prompt hashes, durable outbox packets, and explicit launch-versus-terminal distinction. | Prior wrapper proof was largely dry-run and historical status gating read pane content. | Reimplement packet/receipt semantics and prove current prompt/follow-up transport, checkpoint acknowledgement, process identity, and halt against real Claude. |
| Cursor census | discovery only | Doctor may discover and fingerprint both `cursor-agent` and `cursor agent`. | Installation/help output does not prove persistence, YOLO behavior, checkpoints, resume, or halt; no admitted prior Cursor lane exists. | Generate a disabled manifest and keep every live capability unsupported until the shared real probe passes. |
| Grok lane base | historical branch-only | Regular and long-running goal lanes, full-access launch, file/tmux-buffer prompt transfer, lifecycle receipt, and clean-exit-versus-completion distinction. | Open/conflicting historical work targeted an older Grok surface and is not merged product truth. | Cleanly reimplement the contracts, rerun lifecycle tests, and prove current Grok with the shared prompt. |
| Grok lifecycle hardening | historical branch-only | Unique lifecycle identity, per-run input buffers, proof-last publication, confirmed commit signal, legacy/ambiguous proof refusal, and interrupted-sync ambiguity. | Stacked open work lacks a final exact-head review/promotion verdict and includes platform-specific durability assumptions. | Reimplement or clear rights, add cross-platform interruption tests, obtain fresh exact-head independent review, and run the current Grok probe. |
| PTY control research | reusable implementation pattern | Structural liveness, lost-wakeup-free waits, explicit terminal state, hermetic child environment, and separation of PTY control from registry. | Static study only; screen/scrollback features conflict with transcript blindness and no third-party orchestration behavior was run. | Defer until after the tmux kernel; if adopted, comply with Apache-2.0 and prove structural status/halt with every screen-reading surface disabled. |
| Session-control proof | admitted narrow proof | One current runner; replacement fences the old runner; input reaches only current identity; disconnect is not completion; completion is explicit; unknown completion creates no phantom session. | In-memory/worker-shaped proof did not exercise a real terminal, tmux, agent harness, or auth boundary. | Port the state invariants into kernel tests, fault-inject replacement/disconnect/completion, then prove them around real harness sessions. |
| Lane receipts | reusable contract | Launch proof, expected terminal proof, and actual terminal proof are distinct; `launch_only` never means done; receipts bind run, owner, head, verdict, blocker, and proof pointer. | Historical shell receipts could be non-atomic and free-form Markdown extraction is weak. | Define a versioned bounded JSON receipt, validate transitions, use atomic writes, and require controller verdict plus exact identity. |
| Identifier validation | admitted narrow proof | Allowlist run/session identifiers before subprocess or filesystem use; reject traversal, metacharacters, unsafe targets, and out-of-root paths; sanitize rejected values. | Historical tests stubbed network calls and accepted grammars were product-specific. | Specify Puppet's own grammar and containment roots; rerun hostile fixtures against argv, tmux, state, and attach surfaces. |
| Generational lifecycle | reusable contract | Stable supervisor promotes a unique generation only after preflight; one live owned generation; global lifecycle lock; atomic current pointer; replacement fence; exact ownership before stop; ambiguous stop stays fenced; prior generation remains recoverable. | Historical suite used a fake product executable and did not prove a live Puppet harness. Product-specific UI/registry topology is out of scope. | Reimplement the minimum one-target generation state machine, fault-inject crash windows, then prove one real harness at a time. |
| Checkout provenance | admitted narrow proof | Bind mutation authority to exact checkout, remote digest, branch/default, full head, instruction digest, and genuinely clean worktree; fail closed on hidden index flags, untracked state, ambiguous remotes, and module hijacking. | Does not prove executable authenticity or process ownership and the original implementation is larger than Puppet N. | Build a smaller manifest binding base/head, instructions, controller, adapter, and cleanliness; rerun tampering fixtures before mutation. |
| Tamper-evident journal | admitted narrow proof | Canonical append-only rows with sequence/previous hash, exclusive lock, durable append, atomic head, idempotency, owner transitions, and fail-closed truncation recovery. | Original service-account/socket deployment boundary was not live-proved and is far beyond a local v0.1. | Reimplement a single-user local journal; fault-inject every append/head crash window; do not auto-repair ambiguity. |
| Exact-head review | reusable contract | Bind review to immutable base, exact submitted head, reviewer/request/result identity, and terminal artifact; changed head invalidates verdict; transport receipt is not review; stop after two repair cycles. | Prior routing is product-specific, a model's clean statement is insufficient, and Puppet reviewer independence remains to be proved. | Add stale-head/mutable-base tests; before first mutation qualify a materially different read-only review rail and bind that qualification to every promoted head. |
| GrillTrack | reusable implementation pattern | Explicit activation, durable projection plus append-only events, non-destructive proposed/locked/implemented/verified/superseded/deferred history, ignored work, curated proof, and explicit closeout confirmation. | A product-decision ledger is not a process/session authority boundary or autonomous promotion engine. | Reuse/factor utilities only where semantics match; give Puppet its own schemas and migration tests. |
| Cross-harness packaging branch | historical branch-only | A minimal alternate-controller manifest may expose the same `skills/` tree alongside Codex plugin metadata. | Open packaging work proves shape only, not discovery, invocation, or shared behavioral control. | Revalidate current manifest schemas and real discovery; keep packaging adapters separate from runtime authority. |

## What can be scaffolded immediately

The admitted evidence supports a stronger start than five ad-hoc wrappers:

1. A versioned kernel state machine for `doctor`, `launch`, `send`, `status`,
   `wait`, `checkpoint`, `review`, `accept`, `attach-command`, and `halt`.
2. A single-active-target registry with stable run ID, exact executable and
   birth identity, tmux ownership, lifecycle lock, replacement fence, and
   atomic current pointer.
3. A hash-chained idempotent journal with durable append/head handling and no
   automatic ambiguity repair.
4. Typed receipts separating launch, target checkpoint, independent review,
   controller acceptance, promotion, rollback, and exact halt.
5. Checkout/candidate provenance binding immutable base/head, instruction
   digest, controller, adapter/protocol fingerprints, and cleanliness.
6. One adapter interface plus doctor-only manifests for AGY, Cursor, Claude,
   Codex, and Grok.
7. Direct hostile-ID, state-transition, stale-head, collision, interruption,
   diagnostics, and tampering tests derived from the prior failure classes.
8. Codex packaging plus a separately validated alternate-controller manifest.

Operator-specific paths, standing authorization, accounts, model preferences,
host/device topology, private repository identifiers, and external-action gates
belong in a local overlay, never public defaults.

## Fresh proof that cannot be inherited

Before any adapter graduates beyond doctor-only, the exact current executable
must prove:

- its YOLO/unrestricted mapping and prominent user warning;
- prompt and follow-up transport without prompt text in argv;
- one exact owned process/session and collision/identity-drift refusal;
- nonce-bound ready checkpoint and exactly one follow-up acknowledgement;
- controller learning from bounded checkpoint/commit evidence only;
- zero target transcript, pane, prompt, tool-argument, or auth material in
  controller state and proof;
- no protected-source drift during the read-only probe;
- exact graceful halt affecting only the registered target while preserving
  permitted tmux evidence; and
- current harness/model/version/effort plus controller verdict in the receipt.

The shared prompt runs serially: AGY first, then the other real harnesses. The
first AGY rung ends after the read-only control loop and exact halt. Mutation
and promotion begin only in later sessions after an independent review rail is
qualified.
