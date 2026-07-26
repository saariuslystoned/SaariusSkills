# Route packet: issue #15 guarded 4x4 reliability and containment

Status: prepared for admission; no Phase 3 parent or child launched

## Identity

- lane id: `saariusskills-custom-agent-4x4`
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
- 2x2 proof commit:
  `c71206a3e6a2fad71119ee8d53d06651aee1cbc5`

## Mission

Run four fresh guarded parent sessions with four normal custom children each.
Only after four-of-four success, run one join-denial control, one malformed
delta-child control, and one one-second watchdog control. Commit proof and stop
before product-value comparisons.

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
- normal child tools: `write_to_file`
- fault child tools: none
- raw policy: digest and unlink without content inspection

## Mutation and safety envelope

- task type: source-blind nested reliability and containment proof
- allowed mode: `observe`
- runtime product mutation owner: `none`
- allowed writes: exact disposable result/control/proof paths only
- forbidden: product source, PR #6, global agents/plugins/settings,
  permissions, auth, transcripts, panes, raw log content, foreign
  sessions/processes, customer/device actions, merge, deploy, release, publish

## Budget

- parent CLI processes: `7`;
- declared child branches: at most `28`;
- total agent sessions: at most `35`;
- admitted model-invocation envelope: at most `70`;
- normal per-parent timeout: `180 seconds`;
- watchdog child deadline: `1 second`;
- campaign wall cap: `1800 seconds`;
- stop success on first failure;
- containment only after four-of-four success.

## Proof and stop

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase3-4x4-20260726/`
- cockpit proof root:
  `runs/saariusskills-issue15-phase3-4x4-20260726/`
- dashboard state: `proof-planned`
- review rail: hidden four-child artifacts plus locked/released join and exact
  containment postflight
- publish: normal reconciler cadence only

Stop after R1–R8 classification and committed proof, or immediately on a
success-round guard failure, missing/mismatched child, early/invalid join,
timeout, unexpected write, raw retention, cleanup ambiguity, quota failure,
permission prompt, or foreign contact. Do not start a product comparison on
this route.
