# Herdr-Puppet Qualification Proof (five-row)

Observed: 2026-07-30

## Goal

Validate experimental, transcript-blind Herdr transport for five bounded
subscriptions under implementation head
`8ee87d8ed9882043762ca1877e54cb844072d685`.

## Result

Two rows passed, two stopped at the first wrapped-message consumption
checkpoint, and one stopped at a login/enrollment gate. This is a bounded
experimental set, not a universal acceptance claim or a merge-ready result.

| Run | Harness | Result | Row notes |
| --- | --- | --- | --- |
| `hp58-agy-20260730-r1` | AGY | PASS | Transport + status + detach/reattach + cleanup closed |
| `hp58-cursor-20260730-r1` | Cursor | BLOCKED_LOGIN_ENROLLMENT | Log-in screen required but not crossed |
| `hp58-grok-20260730-r1` | Grok | PASS | Transport + status + detach/reattach + cleanup closed |
| `hp58-claude-20260730-r1` | Claude Code | FAIL | Required STATUS beacon not matched in two 480s watcher attempts |
| `hp58-codex-20260730-r1` | Codex CLI | FAIL | Required STATUS beacon not matched in two 480s watcher attempts |

## Redacted row evidence

All rows used workspace `wC`, the same implementation head, the exact-head
132-test suite, Python compile checks, and Skill Creator validation. SSH process
IDs remain in the machine-local leases/events and are intentionally omitted
from this public matrix.

- **AGY 1.1.8 — PASS.** Exact identity
  `wC:t6B` / `wC:p6B` / `term_657dabd772aba13c`; enrolled dedicated profile;
  regular unrestricted launch with no model selector; default model/effort
  recorded as `unavailable`; ready without an account/security gate; wrapped
  send sequence 4 produced `HERDR_PUPPET_STATUS AYCO-8EE87D8`; separate
  steering sequence 5 produced `HERDR_PUPPET_DONE AYDN-8EE87D8`; native
  detach/reattach preserved every leased identity; DONE auto-preserved the
  lease; exact maintenance and cleanup passed.
- **Grok Build 0.2.117 — PASS.** Exact identity
  `wC:t6D` / `wC:p6D` / `term_657dad95afb6e13e`; enrolled dedicated profile;
  regular unrestricted launch with no model selector; default model/effort
  recorded as `unavailable`; ready with no startup gate; wrapped send sequence
  4 produced `HERDR_PUPPET_STATUS GKCO-8EE87D8`; separate steering sequence 5
  produced `HERDR_PUPPET_DONE GKDN-8EE87D8`; native detach/reattach preserved
  every leased identity; DONE auto-preserved the lease; exact maintenance and
  cleanup passed.
- **Cursor Agent 2026.07.16-899851b — BLOCKED_LOGIN_ENROLLMENT.** Exact identity
  `wC:t6C` / `wC:p6C` / `term_657dad012c1ff13d`; the census recorded
  `interactive_pending`; the regular unrestricted launch reached the login
  handoff, which this campaign was not authorized to cross. Harness readiness,
  wrapped/steering sends, checkpoint, and detach/reattach were therefore not
  claimed. The lease was preserved as a human gate and exact maintenance and
  cleanup passed.
- **Claude Code 2.1.206 — FAIL.** Exact identity
  `wC:t69` / `wC:p69` / `term_657da9ff7c37913a`; enrolled dedicated profile;
  three startup-gate checks were `not_present`; regular unrestricted launch
  reached independently attested ready input. Wrapped send sequence 7 was
  socket-acknowledged once with the Claude two-Enter vector, but neither
  permitted 480-second watcher matched
  `HERDR_PUPPET_STATUS CLCO-8EE87D8`. No steering, DONE, or detach/reattach was
  claimed. The lease was preserved as `checkpoint_failed`; exact maintenance
  and cleanup passed.
- **Codex CLI 0.146.0 — FAIL.** Exact identity
  `wC:t6A` / `wC:p6A` / `term_657dab1e88dbe13b`; enrolled dedicated profile;
  three startup-gate checks were `not_present`; regular unrestricted launch
  reached independently attested ready input. Wrapped send sequence 7 was
  socket-acknowledged once with the one-Enter vector, but neither permitted
  480-second watcher matched `HERDR_PUPPET_STATUS CXCO-8EE87D8`. Re-census
  after the operator's update still reported 0.146.0 and no executable drift.
  No steering, DONE, or detach/reattach was claimed. The lease was preserved as
  `checkpoint_failed`; exact maintenance and cleanup passed.

## Next diagnostic

Do not resend either completed failed row. Use fresh Claude and Codex tabs,
sequences, and nonces. After the one wrapped send:

1. retain only one bounded operator classification:
   `composer_retained`, `composer_cleared_busy`, or
   `assistant_output_visible`; never copy pane text;
2. if the strict beacon misses, run the existing token probe once for the fully
   assembled expected checkpoint, which the submitted wrapper itself could not
   contain; and
3. patch only the failure class that result proves:
   qualify paste-settle/submit choreography if the composer retained the
   wrapper, normalize only an exact proven TUI presentation if the token
   appeared noncanonically, or tighten immediate standalone checkpoint wording
   if the composer cleared and the token remained absent.

This diagnostic preserves the strict checkpoint contract and does not turn a
socket acknowledgement into a consumption claim.

## Evidence root

- [`herdr-puppet-five-row-evidence.json`](herdr-puppet-five-row-evidence.json)
- `~/Developer/_machine-runs/herdr-puppet-five-8ee87d8-20260730/rows`
- Row `events.jsonl`, `STATE.md`, `PROOF.md`, and `lease.json`

## Non-claims

- No ordinary terminal transcript, account identifiers, auth stores, or private data are in these packets.
- No delivery, deployment, account, security, or secret authority is implied.
- These results remain bound to the implementation head above when a later
  docs-only commit records them.

## Discovery proof — 2026-07-23

The earlier discovery asked whether a controller could steer AGY processes on a
remote worker while the same native AGY TUIs remained human-visible in uniquely
labeled Herdr tabs, without tmux.

It passed for the transport primitive and three-pane concurrent dispatch. It
was not Puppet qualification: it used a pre-existing operator Herdr session,
ordinary Herdr pane delivery, and bounded pane reads for exact-token validation.

### Observed topology

```text
operator Herdr session
└── remote-worker workspace
    ├── tab/pane: agy-proof-1
    ├── tab/pane: agy-proof-2
    └── tab/pane: agy-proof-3
```

Each pane's foreground controller-side process was an independent SSH client
targeting the same remote worker. The worker reported exactly three distinct
AGY processes. The remote tmux inventory reported no tmux server.

### Concurrent dispatch

Three Herdr pane sends were issued concurrently before waiting for responses:

| Tab | Expected token | Observed token |
| --- | --- | --- |
| `agy-proof-1` | `AGY_CONCURRENCY_ONE_20260723` | exact match |
| `agy-proof-2` | `AGY_CONCURRENCY_TWO_20260723` | exact match |
| `agy-proof-3` | `AGY_CONCURRENCY_THREE_20260723` | exact match |

After all responses, the same three remote AGY process identities remained and
no tmux server appeared.

### Earlier 1×1 anti-cheat probe

The original pane returned two different exact tokens to two different prompts:

- `HERDR_PUPPET_PROOF_20260723`
- `HERDR_PUPPET_VARIATION_20260723`

This ruled out a single static or cached response.

### Passed clauses

- Herdr displayed a live AGY TUI reached over SSH.
- The controller delivered input to the exact Herdr pane.
- Matching AGY output appeared in the same pane.
- Three uniquely labeled tabs hosted three distinct AGY processes.
- Three prompts were dispatched concurrently and returned matching outputs.
- The remote AGY process count remained exactly three.
- No tmux server participated.
- The Herdr server remained running throughout the proof.

### Blocked or unproved clauses

- Herdr client detach and reattach was not exercised.
- Herdr server crash recovery was not exercised.
- The parent operator-session lifecycle was not independently qualified for
  reuse by a controller.
- No Puppet lease, controller ledger, structured checkpoint, or acceptance
  receipt governed this discovery proof.
- Bounded pane reads were valid for that explicit behavior probe but
  incompatible with Puppet's ordinary transcript-blind runtime contract.

### Public boundary

Account identifiers, machine paths, network addresses, process IDs, and
unrelated terminal content were omitted. No credentials, auth stores,
environment files, browser sessions, tokens, or private keys were inspected.

## Pixel Use dogfood findings — 2026-07-25

A later bounded Pixel Use build exercised repeated fresh AGY tabs through the
qualification controller without ordinary transcript reads. It retained four
repeatable lessons for this PR:

- task-owned prompt files plus exact send-sequence acknowledgements remained a
  reliable transport bridge;
- `qualification-create-tab` could previously create the live tab and lease
  before discovering that the controller journal was absent, leaving an exact
  run-owned orphan after the command reported failure;
- strict checkpoint beacons were not reliably observable from the AGY TUI even
  while independent commits, gates, MCP subprocess identity, and proof
  artifacts advanced; `not_matched` therefore cannot mean "worker offline" or
  "human gate"; and
- Herdr transport did not imply AGY auto-approval. The bounded launch required
  the caller to authorize and pass the harness flag explicitly. Exact tab
  closure remained a separate, operator-authorized maintenance action.

The journal precondition is now checked before live tab creation, with negative
tests for an absent and cross-run journal. The other findings are contract
clarifications; this PR still does not add generic tab cleanup, process reaping,
remote harness adoption, or a transcript-reading fallback.

## Follow-up dogfood findings — 2026-07-26

A later completion run exposed three additional repeatable failures:

- a successful Herdr `pane.send_input` acknowledgement arrived before the
  interactive harness was ready, so the real task was not submitted even
  though transport had acknowledged the keystrokes;
- process and receipt polling distracted the controller from the exact visible
  nonce checkpoint that the operator later reported; and
- milestone maintenance remained prose-only, leaving preserved and stale lease
  records without one deterministic inventory command.

The source skill and installed dogfood copy also differed by one commit. Future
qualification must name the source revision being exercised and must not treat
an older installed copy as proof of the current PR head.

This repair narrows every send receipt to `herdr_pane_input_only`, requires
independent harness-readiness evidence before a real task, adds a controller
hard cap around native output waits, automatically preserves terminal
checkpoints, and adds transcript-blind `maintenance-checkpoint` classification.
The operator clarified that maintenance must also remove completed owned tabs,
not only inventory them. The separately gated `cleanup-preserved-tab` adapter
therefore requires a preserved exact lease, repeated tab-ID confirmation, and
post-close tab, pane, and foreground-SSH-PID absence. Unit tests cover controller
timeout, terminal preservation, live exact-resource inventory, stale-lease
routing, exact-only cleanup, and already-absent reconciliation. Live cleanup
dogfood then closed and verified four exact preserved leases (`wC:t13`,
`wC:t15`, `wC:t16`, and `wG:t4`) and reconciled two exact already-absent
leases (`wC:t12` and `wC:t14`). Each close verified exact tab and pane absence
plus leased foreground SSH PID absence without reading transcript text or
directly signaling a process.

Four older `puppet-*` tabs remained visible without any discoverable lease or
journal (`wC:tX`, `wC:tY`, `wC:tZ`, and `wC:t0`). The controller left them
untouched: a familiar label is not cleanup authority. They require a separate
operator decision naming the exact IDs or recovery of their original lease
records.
