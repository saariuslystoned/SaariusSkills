# Antigravity ACP practical coding qualification

Source head: `1055199`
Installed plugin: `saarius-skills@saarius-skills` `0.3.3`
Runtime: official `antigravity-acp` `1.1.1`
Transport: `acpx` `0.17.1`
Model: exact advertised `gemini-3.7-flash-high`

## Readiness

The installed broker resolved the pinned runtime and matching helper at the
documented default path without runtime-directory overrides. Personal OAuth
was present in the dedicated profile, overage was `never`, forbidden API/Cloud
variables were absent, and the runtime advertised 11 models.

## Real coding task

The bounded edit/review/test task completed in isolated worktree
`agy-coding-qualification` through the installed 0.3.3 broker. It changed the
permission regression test and broker callback, ran the bridge suite, and
returned `17` passing tests plus clean `git diff --check`.

Canonical proof: `runs/antigravity-acp-qualification-runs/20260920-practical-coding/edit-test-retry/runs/d4cce6f3-38c9-4529-89d4-4454e6e27622/PROOF.md`

## Five-way useful-task overlap

Five concurrent jobs completed in five isolated worktrees. Each added one
focused runtime-path regression test, installed locked bridge dependencies,
ran its new test (`1/1` pass), and passed `git diff --check` without commit or
external access.

| Lane | Job | Result |
| --- | --- | --- |
| 1 | `54aad5d9-0985-48ef-aed1-ce4059012c76` | completed, 1/1 |
| 2 | `33a7bbe9-766a-42f0-9e06-a41c066f84aa` | completed, 1/1 |
| 3 | `e02f6e32-b3bc-4d7a-a500-230320566aa2` | completed, 1/1 |
| 4 | `198cc54a-81ec-4c13-9fa7-b392aaaec0a1` | completed, 1/1 |
| 5 | `3161ba02-514c-46f5-9e94-dd8dcdfe3c51` | completed, 1/1 |

Per-job `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` files are
retained under this run directory. Prompt/output bodies are not persisted.

## Native MCP reload gate

Native `antigravity_acp_readiness` succeeded with the same runtime, auth
policy, and exact model catalog. The subsequent native delegate used the
previous MCP server process and returned the earlier permission bookkeeping
`needs-input` result. The installed broker result above is the corrected
0.3.3 outcome; a fresh Codex task/reload is still required to close native
delegate acceptance against that exact installed process.
