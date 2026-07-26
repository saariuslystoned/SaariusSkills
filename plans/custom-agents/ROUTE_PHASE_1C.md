# Route packet: issue #15 Phase 1C

Status: prepared for admission; no Phase 1C model session launched

## Identity

- lane id: `saariusskills-custom-agent-qualification`
- operator id: `bobby`
- owner: `codex-root-current-session`
- closer: `codex-root-current-session`
- repo: `saariuslystoned/SaariusSkills`
- issue: `#15`
- branch: `codex/custom-agent-qualification-issue15-20260726`
- worktree:
  `/Users/cp-1/Developer/worktrees/saariusskills-custom-agents-issue15-20260726`
- base SHA: `23f3b0c8062c7cffaadabee3154477285ccac0f3`
- source head: exact commit containing this packet, frozen at admission
- predecessor proof commits:
  - `1cebe87c69ff11662b6bd85e8ec008fa42698336`
  - `78de7b926d494a872bb8da79dac953414196f8f0`

## Mission

Execute C1–C8 using the external identity oracle in
`BEHAVIOR_CONTRACT_PHASE1C.md`. Produce committed machine-readable proof and
stop before Phase 2.

## Runtime

- host: `aiworker-01` (`worker_host`, Darwin arm64)
- CLI: `/Users/aiworker/.local/bin/agy` version `1.1.7`
- CLI SHA-256:
  `48e37ce7ef2db0e8972b6fed36ce866d4b094c587d377029ba7223565f49aed8`
- model: `gemini-3.6-flash-low`
- effort: `low`
- execution mode: `accept-edits`
- sandbox: enabled
- permissions bypass: forbidden
- prompt: challenge-only stdin
- lifecycle: headless print process with exact exit/deadline
- observer: runtime nonce, profile quarantine, scoped filesystem postflight,
  result verifier, and digest-then-unlink raw outputs

## Mutation envelope

- task type: source-blind CLI behavior proof
- allowed mode: `observe`
- product/source mutation owner during runtime: `none`
- allowed writes: exact disposable workspaces, runtime profiles, pre-created
  result targets, exact controller raw files, sanitized summaries, and proof
- forbidden: product source, PR #6, global agents/plugins/settings,
  permissions, auth, transcripts, panes, foreign sessions/processes,
  customer/device actions, merge, deploy, release, or publish

The per-session AGY `accept-edits` mode applies only inside the exact
disposable workspace. The custom profile exposes only `write_to_file`, and
postflight fails on every path except the pre-created result target.

## Budget

- fresh sessions: `7`
- model invocations: `14`
- per-session timeout: `90 seconds`
- positive sessions: `4`
- negative sessions: at most `3`
- C6/C8: no-model

## Proof and stop

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase1c-20260726/`
- cockpit proof root:
  `runs/saariusskills-issue15-phase1c-20260726/`
- dashboard state at admission: `proof-planned`
- review rail: source-blind external filesystem oracle
- publish behavior: normal reconciler cadence only

Stop when C1–C8 are classified and proof is committed, or immediately on the
first unexpected write, pre-quarantine result, timeout, raw retention,
cleanup ambiguity, quota failure, or foreign-state contact. Do not start
Phase 2 on this route.

