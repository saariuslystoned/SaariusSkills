# Route packet: issue #15 Phase 1D

Status: prepared for admission; no Phase 1D model session launched

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
- latest predecessor proof commit:
  `e3505f7c6ea33a125e924f75163b6110e8224b90`

## Mission

Execute Phase 1 C1–C8 using the external oracle from Phase 1C with only the
documented print-argument transport correction in
`BEHAVIOR_CONTRACT_PHASE1D.md`. Commit proof and stop before Phase 2.

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
- lifecycle: fresh headless process, ninety-second timeout
- observer: runtime nonce, 350 ms profile quarantine, scoped filesystem
  postflight, exact result verifier, digest-then-unlink raw outputs

## Mutation and safety envelope

- task type: source-blind CLI behavior proof
- allowed mode: `observe`
- runtime product mutation owner: `none`
- allowed writes: exact disposable runtime/control/proof paths only
- forbidden: product source, PR #6, global agents/plugins/settings,
  permissions, auth, transcripts, panes, foreign sessions/processes,
  customer/device actions, merge, deploy, release, or publish

Per-session `accept-edits` is bounded to the disposable workspace. The custom
profile exposes only `write_to_file`; every unexpected path fails the route.

## Budget

- fresh sessions: `7`
- model invocations: `14`
- positive sessions: `4`
- negative sessions: at most `3`
- per-session timeout: `90 seconds`
- C6/C8: no-model

## Proof and stop

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase1d-20260726/`
- cockpit proof root:
  `runs/saariusskills-issue15-phase1d-20260726/`
- dashboard state: `proof-planned`
- review rail: source-blind external filesystem oracle
- publish: normal reconciler cadence only

Stop after C1–C8 classification and committed proof, or immediately on an
unexpected write, pre-quarantine mutation, timeout, raw retention, cleanup
ambiguity, quota failure, or foreign contact. Do not start Phase 2.

