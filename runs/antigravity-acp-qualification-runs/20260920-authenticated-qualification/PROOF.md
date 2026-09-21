# Antigravity ACP authenticated qualification proof

Outcome: `QUALIFIED_BOUNDED_FIVE_WAY`

## Activation

- Reinstalled Codex plugin `saarius-skills 0.3.0` from PR #52 head
  `e5f4b574216b35ec43bbaf3a26ed1d7985c839db`.
- Installed locked bridge dependencies from the installed plugin copy.
- `setup.mjs --check`: `MCP_READY` with six
  `antigravity_acp_*` tools.
- Installed-copy bridge test suite: 15 passed, 0 failed.
- Installed official Google runtime/helper `antigravity-acp 1.1.1` for
  `darwin-aarch64`; archive SHA-256:
  `fdfa915652cdb7ba8085cc8fffed072cbe009251aa2c951aabdda07a8c28a189`.
- Readiness returned `ready=true`, exact runtime/helper pin, 11 advertised
  model IDs, `oauth-personal`, `overageState=never`, no API-key/cloud fallback,
  and `ultraAttribution=unclaimed`.

## Live stages

### Stage 1

Proof: `stage-1-retry/state/runs/b7300917-ccb6-4d5e-8014-268f9d56b2ed/PROOF.md`

- One canonical `completed` result.
- Exact model `gemini-3.7-flash-high`.
- Handoff `AGY-ACP-QUAL-01`.
- Zero tool calls.

### Stage 2 pair

Proofs:

- `stage-2-pair/state/runs/de8a5626-e907-4fe9-8831-3957f426f4d2/PROOF.md`
- `stage-2-pair/state/runs/072d236c-bf96-41fe-b7c2-d36560100e56/PROOF.md`

Both jobs completed with exact model `gemini-3.7-flash-high`, handoffs
`AGY-ACP-PAIR-01` and `AGY-ACP-PAIR-02`, and zero tool calls. Prompt starts
overlapped for approximately 1.96 seconds.

### Stage 5 fan-out

All five jobs completed with exact model `gemini-3.7-flash-high`, handoffs
`AGY-ACP-FIVE-01` through `AGY-ACP-FIVE-05`, and zero tool calls. Submission
timestamps were within 1 ms. Each job used a distinct scratch workspace.
Prompt intervals overlapped from approximately `23:13:34.465Z` through
`23:13:36.337Z`, approximately 1.87 seconds of measured five-way overlap.

Proof roots:

- `stage-5/state/runs/e35f9e29-e100-4945-a753-3d6c488a26a0/PROOF.md`
- `stage-5/state/runs/2ca12078-aa7f-42da-abd3-a50268103fe3/PROOF.md`
- `stage-5/state/runs/86f6a11c-86bc-433f-9364-bb7a19bf85bc/PROOF.md`
- `stage-5/state/runs/80dce54c-e484-4ada-a92d-176004c6eb0e/PROOF.md`
- `stage-5/state/runs/17e18856-0374-4145-8494-7c80d6f0840e/PROOF.md`

## Comparison and limits

The retained Cursor ACP baseline proved ten completed jobs, peak five jobs in
`running`, and peak three overlapping ACP prompt intervals. This Antigravity
run proves five completed jobs with measured five-way prompt overlap, so it
meets the requested bounded five-session concurrency target and exceeds the
retained Cursor prompt-overlap observation at that scale.

This is not a claim of Google AI Ultra quota attribution, a provider maximum,
ten-way concurrency, Puppet qualification, or active-turn steering. The route
remains experimental and caller-capped at five until a broader authorized
qualification is requested.

Raw ACP bodies, credentials, auth logs, and tokens were not persisted.
