# Future acpx adoption matrix

Open upstream PRs observed against `openclaw/acpx` main at
`ce8c3689fe830fd5c6199a8a683dc979d180af1d`. None of these have landed. This
matrix does not create upstream issues and does not claim they are adopted.

| PR | Title | Why it may matter later | Current candidate stance |
| --- | --- | --- | --- |
| [#670](https://github.com/openclaw/acpx/pull/670) | fix(session): retain failed turn cleanup ownership | Failed-turn cleanup ownership could change how candidate close/fence behaves after a failed `startTurn`. | Watch only. Current tests keep original errors and reuse existing owned/unknown cleanup. |
| [#674](https://github.com/openclaw/acpx/pull/674) | fix(acp): avoid CPU spikes on fragmented large responses | Large/fragmented ACP payloads could affect event consume/discard cost. | Watch only. Candidate remains result-only and body-free. |
| [#673](https://github.com/openclaw/acpx/pull/673) | fix(queue): release completed output for stalled clients | Shared-queue output retention is outside this public-runtime candidate. | Not in scope. Ordinary broker/shared-queue pin stays `acpx@0.16.0`. |
| [#676](https://github.com/openclaw/acpx/pull/676) | fix(queue): stop detached descendants when retiring Windows owners | Windows owner-retire process cleanup is a queue/owner concern. | Not in scope. No queue-owner or Windows live route in this slice. |
| [#669](https://github.com/openclaw/acpx/pull/669) | fix(flows): release completed run caches | Flows cache release is unrelated to `createAcpRuntime` candidate proof. | Not in scope. Flows are not imported. |

`#672` is already in the frozen merged source. Treat it as event-iterator
cleanup after iteration ends only. It does not prove never-started or
indefinitely slow observers.
