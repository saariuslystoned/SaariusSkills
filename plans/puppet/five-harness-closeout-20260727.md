# Puppet v0.1 five-harness closeout

Outcome: complete for regular sessions using each provider's current default
model at implementation head
`544a347117a9423d53f1975ab0d0176116e2e80c`.

The root controller freshly qualified AGY, Codex CLI, Claude Code, Cursor
Agent, and Grok Build, then launched all five through Puppet concurrently in
separate worktrees, profiles, tmux servers, process leases, and proof roots.
Every lane reached `ACTIVE`, received a sequenced follow-up steering turn,
exposed a native read-only TUI view with no controller attachment, produced a
valid exact-head source checkpoint, received an independent controller
`source_accept` verdict, and halted only its registered process tree. All five
post-halt records are `HALTED` with no live target process.

The final ring was deliberately read-only. Mutating implementation evidence is
preserved by the earlier per-harness receipts in
[`live-proof/`](live-proof/) and the bounded commits they forced. The last live
finding was Grok's ignored `.pytest_cache` changing the worktree root link
count. Commit `544a347` removed that volatile field from Grok workspace
identity while preserving strict activation-artifact link checks; the final
Grok checkpoint and halt then passed after equivalent test-directory churn.

## Exact-head matrix

All rows used the shared adapter fingerprint
`ee275dc7947fd472638a5384c581506d33752c9cc89b365c713bf3ca8b5ef6ef`
and protocol fingerprint
`a4e220c27ecfd4b3a28245e4849bad4b9296f192155a2d8b865ca1109d3e1ce9`.
Version output was retained only as a hash; the readable versions below are
the controller's contemporaneous census result.

| Harness | Version / executable SHA-256 | Regular unrestricted mapping | Qualification receipt SHA-256 | Concurrent checkpoint | Result |
| --- | --- | --- | --- | --- | --- |
| AGY | 1.1.7 / `48e37ce7ef2db0e8972b6fed36ce866d4b094c587d377029ba7223565f49aed8` | `--dangerously-skip-permissions --sandbox=false --new-project --log-file /dev/null` | `ba07c18de634e5db696a51ad22bc4998a0db254034a836a78484c3de3743990d` | `17b79a88b362d9d0a254cf1d727ce193d33891707e2dd68c7cc03a18b2e29291` | accepted, viewed, steered, halted |
| Codex CLI | 0.145.0 / `1da3f4e0e96028b8a771814293c3033dafd1971f943f6c7e79b0897fe705f590` | `--dangerously-bypass-approvals-and-sandbox` | `a7d3945d2b01f6f628214c77604880fe793f8faecbebb1b63ce5d22faa8872bc` | `c77adea06eb24393c2e59293dcf1f16c29a64fcf8a5230f8e8e638b8930fc8d4` | accepted, viewed, steered, halted |
| Claude Code | 2.1.215 / `90608b5c5ab504e96e77365cea6203d046e291d59b2bb42cf28dcb2ccdf9dd58` | `--dangerously-skip-permissions` plus bounded startup-gate reducer | `d5fc8b1fe560a7447494f0fca5cb926b649a42002fe66ff9764e4f98f2bd9a0a` | `1f201c964bd4fc21840c1357c3d93e8b0d9cf7a7c67c50405c76f30207bc3c19` | accepted, viewed, steered, halted |
| Cursor Agent | 2026.07.17-3e2a980 / `eed61c5224668c9236334c4c68936a16aecc37374b592f59e31eb50433817831` | `--yolo --sandbox disabled` plus bounded startup-gate reducer | `c6340b525a4b55b54b97312c2cff1c5943552037888801dbd1015f3fb0cc11de` | `b2834606f78be3631f8f18346e5f870d4a944544d1f030074618a192acc1bf54` | accepted, viewed, steered, halted |
| Grok Build | 0.2.112 / `5cf05fe670b1818561daf7566b580a5de6b81149166499d61072e49640b541a4` | `--always-approve --sandbox off` | `d958915d4b9c9adda76bb020094ad00c46d58e442fc4fcd22cc85172bfe82042` | `f1c059fb2707b259d07bb5e8f728870112f00efdad2480fde935483607f324cd` | accepted, viewed, steered, halted |

The machine-readable receipt is
[`live-proof/five-harness-544a347-20260727.json`](live-proof/five-harness-544a347-20260727.json).
It carries the checkpoint artifact, controller-review, verdict, terminal-state,
and native-view receipt hashes without retaining prompt, reply, transcript,
pane, authentication, or configuration bodies.

## Controller verification

- The critical lifecycle suite passed 129 tests during the concurrent run.
- Full discovery passed 809 tests at the same implementation head.
- The Puppet skill validator passed.
- Each review worktree remained clean at the exact implementation head.
- The five review ring was AGY→Codex, Codex→Claude, Claude→Cursor,
  Cursor→Grok, and Grok→AGY; each residual risk was independently adjudicated
  as acceptable for v0.1.
- No `/goal`, `/loop`, or `/teamwork-preview` mode was used.
- No transcript or pane body was captured, and no auth/config store was read.
- No merge, deploy, release, global install, external send, spend,
  account/security change, or destructive cleanup occurred.

## Deferred work

Automatic harness/model routing, explicit model selection, resume, native
`/goal` and `/loop` semantics, AGY `/teamwork-preview` retirement, and full
native instruction-plane activation remain deferred. Regular sessions are the
only v0.1 qualified public profile. Provider-selected model identity remains
`unavailable` where the harness does not expose it without adding a selector.
