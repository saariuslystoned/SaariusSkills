# Antigravity route decision

Date: 2026-09-20

## Decision

Adopt explicitly staged coexistence.

1. Keep Puppet's native `agy-print` transport as the current/default
   Antigravity route and keep its live public qualification fail-closed.
2. Treat Google's official ACP runtime as a separate future target named
   `antigravity-acp` (or `agy-acp`), never as generic `acp` and never as an
   alias for native `agy`.
3. Do not cut over, install, sign in, or run a paid/overage probe in this
   task. Graduate ACP only after the thresholds below are met.

This is a long-term architecture decision, not a claim that either route is
currently public-live qualified.

## Evidence classification

### Proven or directly documented

- `acpx` v0.17.1 is a signed release at source commit
  [`50a47ad10a75431cbc276ec9b555d11fe1f69c84`](https://github.com/openclaw/acpx/tree/50a47ad10a75431cbc276ec9b555d11fe1f69c84). Its release notes call out
  Google's official Antigravity ACP shortcut and the fixed-choice-question
  breaking behavior.
- The merged [acpx #618](https://github.com/openclaw/acpx/pull/618) says the
  route launches `agy_acp_server.par`/`.exe`, requires the matching helper,
  and uses a separate runtime sign-in. It explicitly records real Linux
  authenticated runtime evidence, synthetic macOS protocol evidence, and no
  live macOS/Windows provider-auth claim.
- The pinned [ACP registry entry](https://github.com/agentclientprotocol/registry/blob/81bf71b55e15f630c4fb8a86d20d3088071d2071/antigravity-acp/agent.json)
  identifies proprietary Google runtime `antigravity-acp` version `1.1.1`
  and platform archives/commands, including Darwin arm64.
- The [acpx Antigravity guide](https://github.com/openclaw/acpx/blob/50a47ad10a75431cbc276ec9b555d11fe1f69c84/agents/Antigravity.md)
  says the ACP route does not wrap `agy --print`; it uses a `GEMINI_HOME`
  profile with `oauth-personal`, exact advertised model IDs, and runtime-owned
  authentication. It also says acpx does not install or update the binaries.
- ACP's protocol docs define `session/new`, `session/resume`,
  `session/prompt`, `session/cancel`, and session close/recovery semantics.
  See the [ACP session setup specification](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v2/session-setup.mdx).
- Antigravity `interaction_*` requests are fixed-choice user questions. acpx
  cancels them and reports that an interactive client must answer; it does not
  safely choose the first option. Puppet must preserve this fail-closed rule.
- [PR #49](https://github.com/saariuslystoned/SaariusSkills/pull/49) is still
  OPEN and unmerged at exact head
  [`1e795546c29bf1eba3ed5b6b6e276c8b7c18c8cc`](https://github.com/saariuslystoned/SaariusSkills/commit/1e795546c29bf1eba3ed5b6b6e276c8b7c18c8cc).
  Its exact source is native `--print` + stream-json with `--conversation`,
  `--model`, and `--effort`; its accepted 125-test/CI proof does not qualify
  the public live AGY route.

### Inference

- ACP is the better long-term integration seam if Google continues treating
  the official server as the stable extension surface: it has standard
  session/model/cancel capabilities and a registry-pinned packaging shape.
- Native AGY has lower migration risk for Puppet because PR #49 already models
  the required proof boundaries and exact conversation resume. The ACP route
  would need a new adapter boundary, not a transport-name swap.
- The official ACP runtime likely reaches the same broader Antigravity account
  service when personal OAuth is used, but that is not enough to infer that a
  request consumes this operator's Google AI Ultra baseline rather than an API,
  Cloud, or credit-funded path.

### Unknown and intentionally unclaimed

- No primary source found in this review explicitly states that
  `agy_acp_server` personal OAuth consumes the caller's Google AI Ultra
  baseline quota. Google documents Ultra quota for Antigravity generally and
  documents unified auth across IDE extensions/CLI/desktop, but does not name
  the separate ACP server in that entitlement statement.
- macOS ACP provider authentication, credential expiry, and unattended
  behavior were not live-tested by the upstream PR. No local probe was run.
- ACP model IDs are account-specific. The protocol supports model selection,
  but native AGY `--effort` semantics do not automatically transfer to ACP.
- ACP session cancellation is not proof that the exact owned process tree has
  died. acpx cleanup and PID/generation handling are not Puppet's exact
  birth-identity and halt proof.
- acpx persistence/replay is not automatically compatible with Puppet's
  transcript-blind metadata contract; a body-free reducer and bounded state
  model are still required.

## Comparison

| Dimension | Native `agy-print` | Official `antigravity-acp` | Decision consequence |
| --- | --- | --- | --- |
| Official support/maturity | Official CLI stream-json surface; PR49 source hardening accepted but public live qualification pending | Official Google runtime, ACP registry entry, acpx support; pinned runtime 1.1.1 | Keep both distinct; no cutover |
| Packaging/update | One installed AGY CLI and its help contract | Separate runtime archive plus matching helper; acpx does not install/update | ACP needs explicit pin/checksum/update policy |
| macOS reliability | Native AGY runtime evidence exists in PR49 packet, but public Puppet proof remains pending | Darwin arm64 package documented; provider auth not live-proven | ACP cannot be default yet |
| Models/effort | Observed `--model`/`--effort` and `init.model` path in PR49 evidence | Exact advertised model IDs and ACP config setter; effort mapping unknown | Require observed model and explicit effort policy |
| Auth/quota | Existing native subscription route in prior evidence, still scoped and fail-closed | Personal OAuth in `GEMINI_HOME`; Ultra attribution unknown | Ultra is a graduation blocker |
| Sessions/recovery | Exact conversation identity via `--conversation`; `--continue` refused | ACP session IDs, load/resume, prompt/update, cancel | Reuse concepts, not implementation |
| Cancel vs death | Puppet proof requires owned PID/birth and tree halt | ACP cancellation plus separate process cleanup | Must prove both for ACP |
| Transcript blindness | PR49 reducer retains bounded metadata only | acpx can persist/replay ACP events/conversation state | Build body-free ACP reducer |
| Checkpoint/review/acceptance | Puppet-specific contracts and accepted repair history | Not supplied by ACP | Shared Puppet gates remain mandatory |
| Questions/permissions | Native route must preserve controller policy | `interaction_*` fixed choices require human answer; acpx cancels | Fail closed; no auto-answer |
| Portability | CLI docs cover supported platforms; installed behavior is version-specific | Registry gives Linux/macOS/Windows archives, but auth proof is uneven | Platform-by-platform qualification |
| Regression/migration | Existing target and tests; still live-E2E gap | New target, auth/profile, reducer, halt, and proof surface | Staged coexistence minimizes blast radius |

## AI Ultra conclusion

Google's [plans documentation](https://antigravity.google/docs/plans) says
Google AI Ultra gets the highest Antigravity quota, refreshed every five hours,
and that baseline usage is distinct from optional purchased AI-credit overages.
The [CLI credits documentation](https://www.antigravity.google/docs/cli/credits/)
and [CLI reference](https://www.antigravity.google/docs/cli/reference/) describe
quota/credit controls and an explicit `useG1Credits` overage setting. The
[installation/auth documentation](https://www.antigravity.google/docs/cli-install)
also distinguishes signed-in account auth from Gemini API-key auth and
custom endpoints.

Those sources prove the product-level distinction, not runtime-specific ACP
attribution. The only safe conclusion is: **ACP use of Bobby's Google AI
Ultra subscription allowance is currently unproven.** Do not claim it, and do
not permit API-key, Cloud-project, alternate-account, or purchased-credit
fallbacks while qualifying it.

Smallest non-secret account-visible check, deferred until Bobby authorizes it:

1. In an isolated `GEMINI_HOME`, verify the runtime-visible signed-in personal
   account and plan/quota panel without exposing tokens or credential stores.
2. Confirm overage use is disabled/`Never` without changing settings if the
   current value cannot be read safely.
3. Run one tiny disposable request only with explicit authorization, then
   compare the account-visible baseline quota before/after and confirm no AI
   credits/API/Cloud billing path was used.

If the ACP runtime exposes no account-visible baseline bucket, the criterion
remains unresolved; do not infer it from OAuth success.

## Disqualifiers

Reject ACP for Puppet admission if any of these occur: runtime/profile cannot
prove personal OAuth; ambient API/cloud credentials are present or silently
selected; account/model identity is not observed; model/effort request is
silently substituted; an interaction question is auto-answered; session
resume crosses identity; cancellation lacks exact owned-tree death proof;
metadata reduction retains body/transcript content; macOS package/helper or
runtime version drifts; or Ultra attribution cannot be checked without paid or
overage behavior.

## Open work

- [#36](https://github.com/saariuslystoned/SaariusSkills/issues/36): native
  AGY print transport remains open for public live qualification.
- [#37](https://github.com/saariuslystoned/SaariusSkills/issues/37): generic
  ACP transport remains open; it does not authorize Antigravity ACP.
- [#38](https://github.com/saariuslystoned/SaariusSkills/issues/38): its old
  “no official ACP” premise is stale; the decision is updated by this packet.
- [#39](https://github.com/saariuslystoned/SaariusSkills/issues/39),
  [#40](https://github.com/saariuslystoned/SaariusSkills/issues/40), and
  [#44](https://github.com/saariuslystoned/SaariusSkills/issues/44) remain
  open for qualification/model-selector sequencing.
- [#21](https://github.com/saariuslystoned/SaariusSkills/issues/21) remains an
  independent Linux process-identity risk.
- [#42](https://github.com/saariuslystoned/SaariusSkills/pull/42) and
  [#49](https://github.com/saariuslystoned/SaariusSkills/pull/49) remain open;
  neither should be merged or cherry-picked as part of this decision.
