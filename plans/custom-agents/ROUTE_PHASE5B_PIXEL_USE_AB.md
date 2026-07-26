# Route packet: corrected issue #15 Pixel-use comparison

Status: prepared for admission; no Phase 5B model session launched

## Identity

- lane id: `saariusskills-custom-agent-pixel-use-ab-corrected`
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
- inconclusive predecessor proof:
  `4f823d794ada77173b1e16c6a9206a46021317f6`
- Pixel-use read-only source head:
  `6474159cc15eafbd2abe602e13017a2754768ce9`

## Mission

Repeat two rounds per arm after explicitly disclosing the policy envelope
required by the unchanged controller answer key. Compare exact product
behavior without touching Pixel-use runtime state.

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
- selection guard: exact discovery occurrence count `1`
- harness: exact committed corrected `product_probe_harness.py`
- raw policy: digest and unlink without content inspection

## Mutation and safety envelope

- task type: corrected source-blind read-only product comparison
- allowed mode: `observe`
- runtime product mutation owner: `none`
- allowed writes: exact disposable result/control/proof paths only
- forbidden: post-hoc answer normalization, product source/device mutation,
  PR #6, global agents/plugins/settings, permissions, auth, transcripts, panes,
  raw-log content, foreign sessions/processes, customer/device actions, merge,
  deploy, release, publish

## Budget

- top-level CLI processes: `4`;
- declared child branches: at most `4`;
- total agent sessions: at most `8`;
- admitted model-invocation envelope: at most `16`;
- per-process timeout: `180 seconds`;
- campaign wall cap: `720 seconds`;
- no resume or answer-driven retry.

## Proof and stop

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase5b-pixel-use-ab-20260726/`
- cockpit proof root:
  `runs/saariusskills-issue15-phase5b-pixel-use-ab-20260726/`
- dashboard state: `proof-planned`
- review rail: unchanged exact answer key, explicit format contract, per-arm
  artifacts, OS-gated joins, comparison summary, scoped postflight
- publish: normal reconciler cadence only

Complete all four admitted rounds unless a non-answer stop condition fires.
Stop after B1–B8 classification and committed proof.
