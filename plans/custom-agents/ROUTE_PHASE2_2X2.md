# Route packet: issue #15 guarded 2x2 fan-out

Status: prepared for admission; no Phase 2 parent or child launched

## Identity

- lane id: `saariusskills-custom-agent-2x2`
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
- guarded-selection proof commit:
  `d01fb5c5ce4a01e9acbb19ceb40ac48ccc32a1d2`

## Mission

Run two fresh guarded parent sessions. Each parent must invoke the same two
custom `subagent: true` children and produce one externally gated join carrying
both hidden child markers. Commit proof and stop before 4x4.

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
- workspace inheritance: `inherit`
- parent guard: exact discovery occurrence count `1`
- parent tools: `invoke_subagent`, `write_to_file`
- child tools: `write_to_file`
- observer: hidden child markers, hidden child-only result paths, OS-locked
  parent join, profile quarantine after both child writes, strict validators
- raw policy: digest and unlink without content inspection

## Mutation and safety envelope

- task type: source-blind nested behavior proof
- allowed mode: `observe`
- runtime product mutation owner: `none`
- allowed writes: exact disposable result/control/proof paths only
- forbidden: product source, PR #6, global agents/plugins/settings,
  permissions, auth, transcripts, panes, raw log content, foreign
  sessions/processes, customer/device actions, merge, deploy, release, publish

## Budget

- parent CLI processes: `2`;
- declared child branches: `4`;
- total agent sessions: at most `6`;
- model invocations: at most `12`;
- per-round timeout: `180 seconds`;
- campaign wall cap: `720 seconds`;
- stop on first failed round.

## Proof and stop

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase2-2x2-20260726/`
- cockpit proof root:
  `runs/saariusskills-issue15-phase2-2x2-20260726/`
- dashboard state: `proof-planned`
- review rail: hidden child artifacts plus OS-gated parent join
- publish: normal reconciler cadence only

Stop after F1–F8 classification and committed proof, or immediately on guard
failure, missing/mismatched child, early/invalid join, timeout, unexpected
write, raw retention, cleanup ambiguity, quota failure, permission prompt, or
foreign contact. Do not start 4x4 on this route.
