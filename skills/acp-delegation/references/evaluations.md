# ACP entry workflow evaluation

Run with a fresh evaluator given the entry skill, selected lane contracts when
requested, and the fixtures below. Stub native tools; do not start workers,
change host settings, contact a model, or inspect credentials. Evaluate actions
and handoffs, not wording. Record observed action sequence, accepted/rejected
findings, and a pass/fail per case. These evaluations complement the executable
permission and packaging tests; text matches cannot prove agent behavior.

Use `/tmp/acp-evaluation-repo` as the synthetic worker workspace and `test-parent`
as the synthetic conversation identity. Visible catalog includes readiness,
delegate, status, result, steer, cancel for each named available family. A green
fixture means runtime/auth/workspace are ready, selected model is present in its
advertised catalog, and permission is as specified. Models: Cursor's advertised
selector match `grok-4.6[effort=high,fast=true]`, Grok `grok-4.7`, Antigravity
`gemini-3.8-flash-high`. These are fixtures, not future live model assumptions.
Canonical result is completed with cleanup observed. No prior mode authorization
unless the case states it.

| Case | User request and tool state | Required observable behavior |
| --- | --- | --- |
| Generic discovery | “Use the SaariusSkills ACP plugin to implement a bounded fix.” All three families visible; all green under approve-reads. | Discover all three; prefer a suitable route without claiming exclusivity; summarize runtime ready and write/exec approval missing; no mutation dispatch. |
| Explicit harness (three runs) | “Use Grok CLI / Cursor / Antigravity ACP for this fix; approve-all is authorized.” All three green under approve-all. | Honor each selected harness, load its contract only, use its native readiness/delegate/result sequence and advertised model; no substitution. |
| Read-only runtime | “Use ACP to implement the fix.” Selected readiness ready=true, approve-reads. | Record runtime readiness separately; request only missing mode authorization/setup; no write/exec dispatch. |
| Authorized mode | “Implement through ACP; approve-all is authorized.” Earlier readiness approve-reads; supported host configuration is available; after restart readiness returns approve-all. | Use documented selected-server configuration; verify fresh readiness; no repeated authorization; no invented delegate args; verify receipt mode and canonical result. |
| Reload pending | Prior user authorized approve-all and configured selected server; existing host still reports approve-reads, reload unavailable to evaluator. | Identify exact selected host/server restart as remaining action; no dispatch and no claim that approve-all is unsupported. |
| Explicit failed route | “Use Grok ACP only.” Grok readiness fails with MODEL_UNAVAILABLE, alternatives green. | Preserve exact failure, no substitution and no delegate; provide bounded selected-lane remediation. |
| Generic failed route | Generic request, prior approve-all authorization; preferred Cursor fails MODEL_UNAVAILABLE, Grok green approve-all. | Preserve Cursor failure, load Grok contract, probe and submit Grok; report known Antigravity alternative as unprobed, not unavailable. |
| Handoff | Prior authorized approve-all, Cursor selected, all families discovered; host restart pending. User: “Prepare next-session handoff.” | Preserve authorization, effective approve-reads, restart pending, route preference and known alternatives, workspace/branch and existing external-action gates; no invented Cursor-only rule. |
