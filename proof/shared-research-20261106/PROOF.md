# Shared research companion guidance — source proof

Date: 2026-11-06. Status: **PREPARED AND PACKAGING-TESTED; NOT INSTALLED OR LIVE-OBSERVED**.
Branch: `ridge/shared-research-20261106`.
Base: `820a8397b559a8ae865bf2531fb6b420812562f1`.
Implementation source: `2bbd109b8cdbac191b16089a83a468d67d40f4f0`.
Proof root: `proof/shared-research-20261106/`.

The approved assignment adds usage/discovery guidance only. Runtime and client
transport belong to a separate plugin. This change adds no MCP server,
OAuth implementation, credential handling or installed configuration.
Implementation owner `shared_research_impl` stopped; `delivery_record` curates
this proof; the assigning coordinator owns final delivery and review.

The skill teaches discovery, readiness, bounded X queries with optional handle
and date filters, YouTube clips of at most 300 seconds, citation inspection,
explicit no-results/errors and cancellation limits. It distinguishes prepared,
installed and observed states. It does not infer successful retrieval from an
answered tool status or substitute another gateway or paid API route.

Codex/Claude root skill discovery and Cursor's explicit skill list are covered
by `tests.test_packaging.PackagingTests.test_shared_research_guidance_discovery`:
**1/1 passed**. Plugin correction tests: **1/1 passed**. Full packaging run:
34 tests, with one existing timing-recipe test failing in two subcases because
`/usr/bin/time` is absent (exit 127). The same two failures were reproduced
from the exact base test source against the unchanged recipe, so they are not
introduced by this guidance. The full repository suite timed out after 120
seconds; it remains unverified. No complete CI or external-review pass is claimed.

Public source context:

- [Native X schema](https://github.com/openclaw/openclaw/blob/1b58cb9a1b4f4353e1add63c8506db4d890962e8/extensions/xai/x-search-tool-shared.ts).
- [YouTube tool proposal](https://github.com/openclaw/gemini-oauth/blob/2ed6d91833a056b8e8a6af0b244a5af9924f9619/src/youtube.ts),
  [PR45](https://github.com/openclaw/gemini-oauth/pull/45), rechecked open and not merged.
- [Pinned invocation error handling](https://github.com/openclaw/openclaw/blob/1b58cb9a1b4f4353e1add63c8506db4d890962e8/src/gateway/tools-invoke-shared.ts):
  generic errors can hide provider status, so rate-limit classification is not universal.

Actual harness discovery and authenticated provider behavior remain unproven.
No runtime installation, provider call, credentials access, external send,
spend, merge or deployment is claimed. PR and exact-head review evidence
remain pending coordinator delivery. Further proof commits do not change the
recorded implementation source. [STATE.md](STATE.md) records the current
handoff; [events.jsonl](events.jsonl) retains earlier checkpoints append-only.
