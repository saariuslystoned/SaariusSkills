# Proof packet

Status: candidate contract implemented and verified; runtime remains non-qualifying.

## Worktree proof

- Worktree: `/Users/bobbybones/.codex/worktrees/d90a/SaariusSkills`
- Branch: `codex/acpx-antigravity-decision`
- Remote default fetched and verified: `origin/main`
- Base/head before packet: `72934effc7db38be0c95a773cd841dbd7b52283e`
- Final source change: standalone candidate contract, focused tests, adapter
  contract pointer, and this run packet
- No secret, credential store, `.env`, token, private key, or auth log read.

## Evidence ledger

| Claim | Result | Evidence |
| --- | --- | --- |
| Official ACP runtime exists | PASS | acpx v0.17.1 release, merged #618, ACP registry v1.1.1 |
| ACP is separate from native AGY stream-json | PASS | acpx Antigravity guide explicitly says it does not wrap `agy --print` |
| ACP Linux runtime behavior | PASS upstream evidence | #618 contributor Linux authenticated proof; not repeated here |
| ACP macOS provider auth | UNKNOWN | #618 explicitly says macOS/Windows provider authentication not live-tested |
| Native PR49 exact state | PASS | `gh pr view 49`: OPEN, unmerged, head `1e7955…`; Ubuntu/macOS checks SUCCESS |
| PR49 source comparison | PASS | exact `refs/remotes/origin/pr-49-head` inspected; native `--print`/stream-json/`--conversation`/`--model`/`--effort` |
| Cursor ACP route | BLOCKED | readiness found exact executable/selector route but `Authentication required`; setup `--check` returned `MCP_READY`; no worker turn sent |
| AI Ultra quota attribution for ACP | UNKNOWN | Google plan/CLI docs cover product quota and credits; no runtime-specific ACP entitlement statement found |
| Native live public qualification | NOT CLAIMED | PR49 review/proof explicitly says it remains pending |
| Candidate contract remains off the default route | PASS | `transport_capability_table()` has no `antigravity-acp`; native transport tests pass |
| Body-free metadata | PASS | new validator rejects prompt/output/content/text/transcript/title/options keys recursively |
| Auth fallback policy | PASS | tests reject API key, Cloud, alternate account, interactive login, and unknown overage state |
| Model policy | PASS | tests reject unavailable/substituted models and unproved effort selection |
| Question policy | PASS | tests require cancelled + human-required interaction state and reject options/answer state |
| Black-box native preflight | PASS | AGY 1.2.7 help/version surface verified without a prompt |
| Black-box ACP session/runtime | PASS | pinned `acpx` v0.17.1 plus official `agy_acp_server_1.1.1` session created in an isolated temporary root; 11 models advertised |
| Black-box ACP smoke request | PASS (bounded) | one request completed with exit code 0 after selecting `gemini-3.8-flash-high`; response body discarded |
| ACP qualification | BLOCKED / NOT CLAIMED | one smoke request does not prove quota entitlement, question handling, cancellation, or Puppet transport ownership |

## Commands and checks

- `git fetch origin --prune`, `git remote set-head origin --auto`, verified
  `origin/main` at `72934effc7db38be0c95a773cd841dbd7b52283e`.
- `gh pr view 49 ...` verified PR state/head/checks.
- Fetched exact `refs/pull/49/head` as `origin/pr-49-head`; inspected exact
  adapter contract and AGY source.
- `gh issue view` verified #21/#31/#35/#36/#37/#38/#39/#40/#44 states.
- Cursor readiness tool returned `ready:false` with
  `Authentication required`; setup check returned `{"ok":true,"code":"MCP_READY"}`.
- `git diff --check` passed after the documentation change.
- `python3 -m unittest tests.test_puppet_antigravity_acp tests.test_puppet_transport tests.test_puppet_adapters -q` → 52 passed.
- `python3 -m py_compile skills/puppet/scripts/puppet_lib/antigravity_acp.py` passed.
- Source-blind preflight report: `behavior-report.json`; no runtime output,
  auth URL, credential, prompt, or model response retained. The bounded ACP
  smoke result records only exit code and selected model metadata.

## Source set

- [acpx v0.17.1](https://github.com/openclaw/acpx/releases/tag/v0.17.1)
- [acpx #618](https://github.com/openclaw/acpx/pull/618)
- [acpx Antigravity guide at `50a47ad`](https://github.com/openclaw/acpx/blob/50a47ad10a75431cbc276ec9b555d11fe1f69c84/agents/Antigravity.md)
- [ACP registry at `81bf71b`](https://github.com/agentclientprotocol/registry/blob/81bf71b55e15f630c4fb8a86d20d3088071d2071/antigravity-acp/agent.json)
- [ACP session setup](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v2/session-setup.mdx)
- [Google Antigravity plans](https://antigravity.google/docs/plans)
- [Google CLI credits](https://www.antigravity.google/docs/cli/credits/)
- [Google CLI auth](https://www.antigravity.google/docs/cli-install)
- [Puppet PR49](https://github.com/saariuslystoned/SaariusSkills/pull/49)

## Limitations

The runtime was installed only under a temporary isolated root and launched as
a separate candidate session. No account or billing state was changed. One
small smoke request completed, but no paid/overage entitlement was claimed;
the isolated profile's `useG1Credits=false` setting is configuration evidence,
not proof of server-side quota behavior. This packet intentionally does not
claim ACP macOS qualification.
