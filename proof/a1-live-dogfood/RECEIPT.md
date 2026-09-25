# Always-on (CP-1) Antigravity MCP receipts

Public copies of dogfood artifacts and durable links. Live MCP job
directories under `~/.local/state/saarius-skills/antigravity-acp-delegation/runs/`
on CP-1 are not in this repository.

## Useful coding delegate (2026-09-24 / 2026-09-25Z)

| Field | Value |
| --- | --- |
| Placement | **Always-on** — same six-tool contract on the always-on box (CP-1 worker attach) |
| Artifact | [hello.mjs](./hello.mjs) (`A1_READY`, exit 0) |
| Live MCP job id | `9028cc7a-a2ff-4606-b3a9-ccd55ff65030` |
| Plugin context | Merge [`7539ae3`](https://github.com/saariuslystoned/SaariusSkills/commit/7539ae373aca4b48db8ea38dbee290c6f0256802) ([#80](https://github.com/saariuslystoned/SaariusSkills/pull/80) + [#82](https://github.com/saariuslystoned/SaariusSkills/pull/82)) |
| Permission | `SAARIUS_ACP_PERMISSION_MODE=approve-all` on the CP-1 attach (operator break-glass, not a tool arg) |
| Delegate | Omitted `model` → `gemini-3.8-flash-high`; isolated worktree only; no commit |
| Outcome | `completed`; `cleanupReady`; `complete` |

Verify the artifact in git: [hello.mjs](./hello.mjs).

## First live job — `approve-reads` fail-closed

| Field | Value |
| --- | --- |
| Live MCP job id | `43190be6-42f4-4bbe-8a09-ab525beef457` |
| Permission | unset (`approve-reads`) |
| Outcome | `failed` / `PERMISSION_PROMPT_UNAVAILABLE`; cleanup complete |

Public verification: same host-policy merge commits as Local ([#80](https://github.com/saariuslystoned/SaariusSkills/pull/80),
[#82](https://github.com/saariuslystoned/SaariusSkills/pull/82)) and
[`bridge/antigravity-acp/test/host-permission-contract.test.mjs`](../../bridge/antigravity-acp/test/host-permission-contract.test.mjs).
The useful delegate above is the positive Always-on coding proof.
