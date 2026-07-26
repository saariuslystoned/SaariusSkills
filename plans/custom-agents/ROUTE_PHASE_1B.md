# Route packet: issue #15 Phase 1B

Status: prepared for admission; no Phase 1B model session launched

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
- source head: the exact commit containing this packet, recorded at route
  admission and in the capability fingerprint
- predecessor proof commit:
  `1cebe87c69ff11662b6bd85e8ec008fa42698336`

## Mission and stop condition

Qualify or reject the CLI workspace-plugin observer, then rerun Phase 1 C1–C8
only if its pre-model and first-positive gates pass.

Stop immediately when any of these occurs:

- filtered plugin discovery does not find `saarius-issue15-observer`;
- the first positive session emits no observer event;
- an unexpected tool, write, path, permission prompt, timeout, identity
  mismatch, or workspace delta occurs;
- every C1–C8 clause has an explicit terminal classification.

Phase 2 is not part of this route.

## Host and invocation tuple

- host: `aiworker-01` (`worker_host`, Darwin arm64)
- CLI: `/Users/aiworker/.local/bin/agy`
- CLI version: `1.1.7`
- CLI binary SHA-256:
  `48e37ce7ef2db0e8972b6fed36ce866d4b094c587d377029ba7223565f49aed8`
- model: `gemini-3.6-flash-low`
- effort: `low`
- sandbox: enabled
- permissions bypass: forbidden
- workspace: fresh disposable directory bound with absolute `--add-dir`
- sessions: fresh only; never continue or resume
- prompt transport: dedicated tmux buffer through stdin with terminal echo
  disabled

## Ownership and mutation envelope

- task type: source-blind CLI behavior proof
- allowed mode: `observe`
- product/source mutation owner during runtime: `none`
- allowed runtime writes: exact disposable fixture materialization, the exact
  result target, owned event/sentinel/raw-log files, sanitized summaries, and
  committed proof
- forbidden: PR #6 mutation, global configuration, plugin installation,
  settings or permission changes, auth inspection/change, product source
  mutation, foreign session/process actions, transcript reads, pane capture,
  merge, deploy, release, or publish

The observer plugin is workspace-local and inert in this repository. It is
never installed or copied into a user configuration directory.

## Budget

- fresh sessions remaining: `7`
- model invocations remaining: `14`
- route wall clock: `600 seconds`
- session deadline: `90 seconds`
- result mutations: `1 per session`

## Proof

- product proof root:
  `proof/custom-agents/agy-1.1.7-aiworker01-phase1b-20260726/`
- cockpit route proof root:
  `runs/saariusskills-issue15-phase1b-20260726/`
- dashboard state at admission: `proof-planned`
- review rail: source-blind hooks plus exact artifact validation
- publish behavior: normal reconciler cadence only

