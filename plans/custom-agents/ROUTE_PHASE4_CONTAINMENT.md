# Route packet: issue #15 containment characterization

Status: prepared for admission; no Phase 4 parent or child launched

## Identity

- lane id: `saariusskills-custom-agent-containment`
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
- failed 4x4 proof commit:
  `6be2a699fa7cb96f81fe9679ae867b6273834960`

## Mission

Run one denied-join control, one malformed-delta control, and one one-second
watchdog control. Characterize containment and retry-observation limits without
retrying width-four qualification or admitting product promotion.

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
- parent guard: exact discovery occurrence count `1`
- harness: exact committed `fanout4_harness.py`
- raw policy: digest and unlink without content inspection

## Mutation and safety envelope

- task type: source-blind failure-containment characterization
- allowed mode: `observe`
- runtime product mutation owner: `none`
- allowed writes: exact disposable result/control/proof paths only
- forbidden: width-four success retry, product source, PR #6, global
  agents/plugins/settings, permissions, auth, transcripts, panes, raw log
  content, foreign sessions/processes, customer/device actions, merge, deploy,
  release, publish

## Budget

- parent CLI processes: `3`;
- declared child branches: at most `12`;
- total agent sessions: at most `15`;
- admitted model-invocation envelope: at most `30`;
- denial/malformed timeout: `180 seconds`;
- watchdog child deadline: `1 second`;
- campaign wall cap: `720 seconds`;
- stop on first unexpected control result.

## Proof and stop

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase4-containment-20260726/`
- cockpit proof root:
  `runs/saariusskills-issue15-phase4-containment-20260726/`
- dashboard state: `proof-planned`
- review rail: exact child artifacts plus permanently locked join and process
  watchdog
- publish: normal reconciler cadence only

Stop after Q1–Q8 classification and committed proof, or immediately on guard
failure, unexpected join mutation, malformed-control mismatch, watchdog
failure, raw retention, cleanup ambiguity, quota failure, permission prompt,
or foreign contact.
