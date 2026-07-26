# Route packet: issue #15 Phase 0/1

Status: prepared for admission; no live agent launched by this packet

## Identity

- route id: `saariusskills-issue15-phase0-1-20260726`
- lane id: `saariusskills-custom-agent-qualification`
- operator id: `bobby`
- owner: `codex-root-current-session`
- closer: `codex-root-current-session`
- repo: `saariuslystoned/SaariusSkills`
- issue: `#15`
- historical input only: PR #6 at
  `baea84b2bb0d21ff749ce65d077a76cc76f2e1de`
- branch: `codex/custom-agent-qualification-issue15-20260726`
- worktree:
  `/Users/cp-1/Developer/worktrees/saariusskills-custom-agents-issue15-20260726`
- base: `origin/main`
- observed base SHA: `23f3b0c8062c7cffaadabee3154477285ccac0f3`

## Mission and terminal artifact

Prove or reject workspace-local custom-agent discovery and exact identity
selection on one exact Antigravity CLI tuple. Produce committed Phase 0/1
behavior proof and a draft PR or `NO_PR_REASON.md`, then stop before 2x2
fan-out.

Expected terminal artifacts:

- `proof/custom-agents/agy-1.1.7-aiworker01-phase1-20260726/PROOF.md`
- `proof/custom-agents/agy-1.1.7-aiworker01-phase1-20260726/capability-fingerprint.json`
- `proof/custom-agents/agy-1.1.7-aiworker01-phase1-20260726/events.jsonl`
- `proof/custom-agents/agy-1.1.7-aiworker01-phase1-20260726/behavior-report.json`
- PR-visible link to those committed artifacts

Stop condition: every Phase 1 clause has a `pass`, `fail`, `blocked`, or
`out_of_scope` result, proof is committed and visible, and no Phase 2 campaign
has started.

## Surface and host

- requested surface: Antigravity CLI TUI
- host taxonomy: `worker_host`
- host: `aiworker-01`
- target: `aiworker@aiworker-01.swarm`
- installed CLI: `/Users/aiworker/.local/bin/agy`
- observed CLI version: `1.1.7`
- candidate model: `gemini-3.6-flash-low`
- reasoning effort: `low`
- sandbox: explicitly enabled at launch
- permissions bypass: forbidden; never pass
  `--dangerously-skip-permissions`
- session mode: fresh only; never `--continue` and never a foreign
  conversation id

CP-1 has the same CLI version but its public model-list surface reports that no
CLI account is signed in. This route does not initiate, inspect, or change
authentication. `aiworker-01` exposes the model catalog through its existing
operator account without revealing credentials.

Unrelated AGY processes were present on `aiworker-01` at preflight. Concurrent
operator sessions are treated as resource telemetry, not as authority to
inspect, resume, signal, or clean them. Every campaign uses a fresh disposable
workspace, fresh conversation, exact owned tmux socket/session, and exact owned
cleanup.

## Launcher and visibility

- launcher: dedicated remote tmux TUI over the existing SSH worker doorway
- socket label: `saarius-issue15-agy`
- session: `saarius-issue15-phase1`
- read-only attach:
  `ssh -t aiworker@aiworker-01.swarm 'tmux -L saarius-issue15-agy attach-session -r -t saarius-issue15-phase1'`
- prompt transport: controller loads a tmux buffer from stdin and pastes it;
  prompt bodies never enter process argv
- pane capture: forbidden
- raw transcript access: forbidden
- reduced-visibility decision: accepted because controller-owned hooks and
  bounded result artifacts are the authoritative observer; no pane or
  transcript output is promotion evidence

## Allowed task and mutation envelope

- task type: source-blind CLI behavior proof
- allowed mode: `observe`
- product/source mutation owner: `none`
- allowed writes: exact disposable workspace fixtures, one bounded identity
  result per fresh session, external sanitized event/log summaries, and the
  committed proof packet
- forbidden writes: product source, PR #6, global custom-agent configuration,
  account settings, permission settings, unrelated workspaces, or live product
  state

The hook denies every tool except the first `write_to_file` call whose
`TargetFile` resolves to the exact disposable identity result. It compares the
target in memory without retaining the value. Postflight rejects any unexpected
workspace change.

## Observer and evidence

The controller-owned observer records only:

- run-scoped salted actor ids;
- event kind;
- allowlisted tool name and top-level argument-key names;
- invocation/step/execution ordinals;
- boolean error and fully-idle state;
- bounded termination reason and permission decision;
- hashes and pass/fail enums.

It never reads or retains prompts, model messages, transcript paths, transcript
contents, source contents, raw tool arguments, auth data, cookies, or unrelated
logs. A CLI log may be consumed once by the allowlist sanitizer to locate an
exact expected agent-profile field; the raw log is never printed or committed
and is removed by exact-owned cleanup after its sanitized result is written.

## Budget

- maximum fresh model sessions: 8
- maximum model invocations: 16
- maximum wall clock: 12 minutes
- per-session deadline: 90 seconds
- maximum result writes: 1 per session
- model class: lowest-cost available qualified candidate
- account overage or plan changes: forbidden
- stop immediately on authoritative quota failure or when any bound is reached

## Dashboard and review

- initial dashboard state: `proof-planned`
- running dashboard state: `proof-running`
- terminal dashboard state: `proof-complete`, `proof-failed`, or
  `proof-blocked`
- dashboard projection: worker execution/proof lane
- publish path: normal CP-1 event/reconciler cadence; no foreground production
  publish
- behavior review: source-blind contract report
- code/artifact review: exact-head independent review before review-ready state
- finding classes: `required_fix`, `reject_false_positive`, `defer`, or
  `human_gate`

## Gates

- no merge, release, deploy, or publish;
- no auth, account, permission, or security changes;
- no global custom-agent installation;
- no customer sends or device mutation;
- no unbounded spend;
- no prompt, transcript, credential, or unrelated-session retention;
- no broad process inspection, signaling, or cleanup;
- no Phase 2 admission until Phase 1 exit criteria pass on one unchanged
  capability fingerprint.
