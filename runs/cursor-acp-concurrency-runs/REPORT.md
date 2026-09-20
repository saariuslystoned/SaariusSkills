# Cursor ACP concurrency investigation

Date: 2026-09-20

## Result

The bridge accepted and ran two distinct Cursor ACP jobs concurrently. Both reached independent terminal success, with no response cross-wiring. This proves a pair of overlapping jobs for this route; it does not prove arbitrary fan-out or provider-side token execution capacity.

## Route and readiness

- Repo/worktree: `/Users/bobbybones/.codex/worktrees/7790/SaariusSkills`
- Git state: detached HEAD at `5fc4a9158f4c454f2c0e2deee7642f79f4a584f8`; clean before the run
- Exact route: `/Users/bobbybones/.local/bin/cursor-agent acp`
- Requested selector: `cursor-grok-4.6-high`
- Confirmed ACP model: `grok-4.6[effort=high,fast=true]`
- Setup check: `MCP_READY`; native readiness passed for the exact worktree without a model turn
- Local bridge tests: 11 passed, 0 failed

## Bounded experiment

Both delegate calls were submitted without awaiting the first. Prompts were fixed, tiny, distinct acknowledgements; each used a separate empty absolute scratch directory and a 90-second timeout.

| Job | Created / running | Prompt started | Completed | Lifecycle duration | Session identity | Result |
|---|---|---|---|---:|---|---|
| A | 15:11:52.793 / 15:11:52.802Z | 15:11:56.303Z | 15:12:01.566Z | 8.764s | `cursor-acp:5c711688-3653-4ffb-ae15-6362b24b6814`; backend `88ef666b-fe18-4c37-b1f6-075db4f651bf` | `ACK-A`, `end_turn`, 0 tools |
| B | 15:11:54.465 / 15:11:54.478Z | 15:11:58.652Z | 15:12:02.491Z | 8.013s | `cursor-acp:6fbb224d-fb72-4d92-b8ba-1b510b5c98e7`; backend `080f69f7-1b7a-4871-a9a0-184849a094bd` | `ACK-B`, `end_turn`, 0 tools |

The bridge-level running intervals overlapped for about 7.086s. The ACP prompt lifecycles overlapped from B's `prompt_started` at 15:11:58.652Z until A completed at 15:12:01.566Z, about 2.914s. That proves overlapping initialized ACP turn lifecycles; provider-side model-token execution timing is not exposed, so deeper overlap is unknown.

The two canonical results retained distinct job IDs, workspaces, session IDs, prompt hashes, and handoffs. No scratch files were created. After completion, a targeted process check found zero matching `/Users/bobbybones/.local/bin/cursor-agent acp` processes. No cancellation was needed.

## Limits by layer

| Layer | Observed / enforced | Unknown or caveat |
|---|---|---|
| MCP tool / bridge | One job per delegate call; absolute existing workspace; bounded timeout; unique UUID job and session key; terminal jobs removed from the broker's active map. | No explicit global active-job or concurrency cap in the bridge. An absent cap is not unlimited capacity. |
| Bridge server/runtime | In-memory ACP session records; bridge shutdown cancels active turns; stale jobs fail closed after restart. | No independent server-wide admission limit was visible in source. |
| Workspace | Each job is bound to its own absolute directory; proof is outside the workspace. | No cross-workspace lock or shared workspace protection beyond the caller's choice of path. |
| Cursor/acpx session | `acpx@0.16.0` queues turns by `acpxRecordId`, so turns in one session serialize. Distinct job session keys create distinct `AcpClient` owners/process-launch scopes. | Native metadata exposed session IDs but no child-process PID. A pair of separate clients is not evidence of unlimited process capacity. |
| Cursor provider/account | The live pair was accepted and completed. | No supported non-secret metadata exposed a provider concurrency ceiling, rate-limit state, or exact billing. Cursor's usage docs describe monthly pools and the Spending dashboard, not an ACP concurrency guarantee. |

Source anchors: bridge active-job map and job creation/cleanup are in `bridge/cursor-acp/broker.mjs:337,506-544,547-593,652-653`; per-session steering/serialization policy is documented at `broker.mjs:714-719`; acpx per-record queuing is in `bridge/cursor-acp/node_modules/acpx/dist/runtime.js:987-1007,1418-1470`; distinct client creation is at `runtime.js:1324-1356`.

## Budget, safety, and recommendation

Exact billed usage is unknown. The bridge exposed no supported billing or token-cost metadata, and this report does not infer zero cost from the tiny prompts. No account, plan, billing, API-key, or quota setting was changed.

Recommended practical default: cap this route at **2 concurrent live jobs** at the caller, with one bounded prompt per job and explicit per-job timeouts. Treat 2 as the experimentally proven safe pair, not as a provider guarantee. Do not increase the cap without a separate, human-approved experiment that measures rate-limit/error behavior and usage through supported account metadata.

Official references: [Cursor ACP documentation](https://prod.cursor.com/docs/cli/acp) and [Cursor usage and limits](https://prod.cursor.com/help/models-and-usage/usage-limits).
