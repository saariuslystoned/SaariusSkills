# Hop (MacBook parent → CP-1 worker) Antigravity MCP receipts

Public copies of dogfood artifacts and durable links. The hello file was
written on the **worker** worktree on CP-1; this repository holds the
committed copy for verification. Live MCP job directories on CP-1 are not
in git.

## Useful hopped coding delegate (2026-09-25)

| Field | Value |
| --- | --- |
| Placement | **Hop** — MacBook parent launcher, CP-1 worker; `SAARIUS_ACP_HOP_ARGV` stdio hop |
| Artifact | [hello.mjs](./hello.mjs) (`B_READY`, exit 0) |
| Live MCP job id | `69b134e9-6f79-4b10-8f02-6bdbf41af52d` |
| Hop wrapper on `main` | [#83](https://github.com/saariuslystoned/SaariusSkills/pull/83) → merge [`e6db967`](https://github.com/saariuslystoned/SaariusSkills/commit/e6db967c1505a1addbccbcb9596759b9a082c191) |
| Delegate | Omitted `model` → `gemini-3.8-flash-high`; worker-absolute isolated worktree; no commit |
| Outcome | `completed`; `cleanupReady`; `complete` |

Verify the artifact in git: [hello.mjs](./hello.mjs).

## Public verification without the live job folder

- Hop argv contract (unit tests):
  [`bridge/acp-runtime/test/hop.test.mjs`](../../bridge/acp-runtime/test/hop.test.mjs)
- Merged hop launcher implementation: [#83](https://github.com/saariuslystoned/SaariusSkills/pull/83)

Bare `ssh` as the laptop login user is **not** the documented hop identity;
the live hop used `ssh -T cp-1@cp-1.local` (operator config, not a published
hostname). Do not treat a shortened job id alone as proof.
