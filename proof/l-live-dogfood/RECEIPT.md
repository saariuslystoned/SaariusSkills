# Local (MacBook) Antigravity MCP receipts

Public copies of dogfood artifacts and durable links. Live MCP job
directories under `~/.local/state/saarius-skills/antigravity-acp-delegation/runs/`
stay on the operator host and are not in this repository.

## Useful coding delegate (2026-09-24)

| Field | Value |
| --- | --- |
| Placement | **Local** — parent and worker on the same MacBook desktop Agent chat |
| Artifact | [hello.mjs](./hello.mjs) (`L_READY`, exit 0) |
| Live MCP job id | `38a1c9e7-2c5b-4baf-95d9-b940f8c3090d` |
| Plugin context | [#77](https://github.com/saariuslystoned/SaariusSkills/pull/77) default `gemini-3.8-flash-high`; [#78](https://github.com/saariuslystoned/SaariusSkills/pull/78) `acpx@0.19.1` pins |
| Delegate | Omitted `model` → `gemini-3.8-flash-high`; isolated worktree only; no commit |
| Outcome | `completed`; `cleanupReady`; `complete` |

Verify the artifact in git: [hello.mjs](./hello.mjs). The full job UUID is
recorded here because MCP job folders are not published.

## Host policy fail-closed ([#80](https://github.com/saariuslystoned/SaariusSkills/pull/80))

| Field | Value |
| --- | --- |
| Merged policy | Merge commit [`51fa3a6`](https://github.com/saariuslystoned/SaariusSkills/commit/51fa3a61910e0fe30f59f54e583fb3267012daa2) |
| Live MCP job id | `a8c3cbbf-7433-4334-86d7-f59a3fe2b57d` |
| Permission | `SAARIUS_ACP_PERMISSION_MODE` unset (`approve-reads`, not break-glass) |
| Outcome | `failed` / `PERMISSION_PROMPT_UNAVAILABLE`; cleanup complete |

Public verification without the operator job folder: host-policy behavior and
tests on `main`, including
[`bridge/antigravity-acp/test/host-permission-contract.test.mjs`](../../bridge/antigravity-acp/test/host-permission-contract.test.mjs).
Do not treat a shortened job id alone as proof.
