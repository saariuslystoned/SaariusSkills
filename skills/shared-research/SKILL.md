---
name: shared-research
description: Use native X research or analyze a public YouTube video through ai-shed research MCP when those tools are available. Covers discovery, bounded requests and citation inspection, not general coding delegation.
---

Discover `research_readiness`, `x_search` and `gemini_youtube` in the separate
ai-shed plugin. Harnesses may prefix MCP tool names. This skill ships guidance
only. The prepared adapter is unavailable until an approved server transport
exists; manifest presence does not prove installation or provider operation.

Check readiness before a lookup. Use `x_search` with one `query` of at most
4,000 characters; optionally pass `allowed_x_handles` or `excluded_x_handles` (up to 20, mutually exclusive) and `from_date`/`to_date` in YYYY-MM-DD form.
For YouTube, use one public HTTPS YouTube `url` and a `prompt` of at most 4,000
characters plus required `startOffset` and `endOffset` duration strings (start >= 0, end > start) (for example `1s` and `121s`). Clips may span at most 300 seconds, ending within 24 hours. Explicit offsets replace URL time parameters; zero start is translated to an omitted native start after URL time parameters are removed, preserving the pinned parser constraints. Ask for specific timestamps and source citations.

Inspect returned public post links or video timestamps and distinguish source
claims from your synthesis. `answered` is not independently verified retrieval;
validate citations before presenting them as evidence. Treat `no-results` as
absence of retrieved evidence. Report `rate-limited`, `error`, or `unavailable`
without inventing content or blindly retrying. `rate-limited` requires a visible
HTTP 429 or explicit structured rate error. Native `/tools/invoke` can erase
provider exceptions, including provider 429, to generic HTTP 500; those remain
`error`. Do not infer absence of rate limiting from that outcome or claim
universal native provider rate-limit detection. Do not substitute paid API access
or another gateway. Cancellation stops the local wait, not proven remote work.

Setup belongs to ai-shed and the approved server operator. Never request or
copy gateway bearers into prompts, manifests, proof or client settings. Missing
transport is a concrete setup dependency, not permission to create an auth
consumer. See the ai-shed repository's `research-mcp/README.md` for current
prepared/tested/installed/observed distinctions.
