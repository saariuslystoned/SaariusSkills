# Route packet: issue #15 Phase 1E guarded selection

Status: prepared for admission; no Phase 1E live command launched

## Identity

- lane id: `saariusskills-custom-agent-guard`
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
- predecessor proof commit:
  `b2e7dbab204408b7933dcc66df9e74cefedd9063`

## Mission

Prove that `guarded-run-print` refuses absent and duplicate workspace identities
before model launch, then spends the one remaining Phase 1 session proving that
an exactly-once `subagent: false` profile still passes the unchanged external
identity oracle. Commit proof and stop before Phase 2.

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
- prompt transport: exact challenge-only `--print` argument
- discovery guard: exact requested-name occurrence count must equal `1`
- discovery raw policy: digest in memory, never print or retain
- observer: Phase 1D runtime nonce, profile quarantine, exact result verifier,
  and scoped filesystem postflight

## Mutation and safety envelope

- task type: deterministic guard plus one source-blind CLI behavior proof
- allowed mode: `observe`
- runtime product mutation owner: `none`
- allowed writes: exact disposable runtime/control/proof paths only
- forbidden: product source, PR #6, global agents/plugins/settings,
  permissions, auth, transcripts, panes, foreign sessions/processes,
  customer/device actions, merge, deploy, release, or publish

## Budget

- remaining issue-level Phase 1 model sessions: `1`;
- Phase 1E model sessions and guarded model launches: at most `1`;
- discovery invocations: at most `8`;
- discovery timeout: `10 seconds`;
- model timeout: `90 seconds`;
- negative controls: no-model only.

## Proof and stop

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase1e-20260726/`
- cockpit proof root:
  `runs/saariusskills-issue15-phase1e-20260726/`
- dashboard state: `proof-planned`
- review rail: deterministic exact-count guard plus external filesystem oracle
- publish: normal reconciler cadence only

Stop after E1–E4 classification and committed proof, or immediately on a
negative guard model launch, positive identity mismatch, unexpected write,
timeout, raw retention, cleanup ambiguity, quota failure, or foreign contact.
Do not start Phase 2 on this route.
