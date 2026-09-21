# Antigravity v3 live proof result

Result: `FAILED_NO_USEFUL_EDIT`. This is the sanitized outcome of the one
parent-released official v3 manual attempt. It is not a qualification PASS.

## Exact invocation

```text
/opt/homebrew/opt/python@3.14/bin/python3.14 \
  /Users/bobbybones/Developer/worktrees/puppet-antigravity-controller-proof-20260921/runs/puppet-controller-proof-runs/20260921/v3/driver/agy_live_capable_proof_driver.py \
  --live \
  --launch-input /Users/bobbybones/Developer/worktrees/puppet-antigravity-controller-proof-20260921/runs/puppet-controller-proof-runs/20260921/v3/staged/launch-input.contract.json \
  --mode lifecycle
```

Preflight matched the frozen source head/tree, v3 driver SHA
`1bf2c9b22be3561f0e3461edc8b191e61de8e1067aa20cbbeb48c6e7d0a89ba8`, v3
launch-input SHA `b78a5b1d3d1d30811e92eba331712fa52e3135474436f819f8b7be5d399d484c`,
exact `gemini-3.8-flash-high`, effort unset, and no prior v3 live state.

## Outcome

- Official route invocation: one session consumed; no retry, replacement, or
  second provider job.
- Process result: exit `2`; body-free blocker `fixture after tests did not pass independently`.
- The fresh owned fixture remained unchanged: baseline behavior was 1 pass / 1
  missing-command failure, `bin/normalize-lines.mjs` was absent, protected
  digests were unchanged, and the changed-path set was empty.
- The generated ownership record identifies the official `antigravity-acpx`
  controller session as non-qualifying. A qualified model/session continuation
  receipt was not emitted by this failure path, so exact model observation,
  useful edit, and live PASS are all unproven.
- No residual controller/helper/backend/localharness process was observed. The
  workspace and state ownership records are retained as failure evidence. No
  cleanup-uncertainty fence was emitted; no replacement was attempted.
- Prompt ceiling remained at the parent gate of at most two prompts; the
  failure receipt does not expose a reliable prompt count. No retry occurred.

No raw provider transcript, prompt body, credential, auth/profile data, argv,
environment, or runtime payload is included here.
