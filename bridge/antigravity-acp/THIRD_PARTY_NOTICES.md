# Third-party notices

The local Antigravity ACP bridge uses these pinned MIT-licensed packages:

- `acpx@0.19.1`: <https://github.com/openclaw/acpx/releases/tag/v0.19.1>
- `@modelcontextprotocol/sdk@1.30.0`:
  <https://github.com/modelcontextprotocol/typescript-sdk/tree/v1.30.0>
- `zod@4.6.5`: <https://github.com/colinhacks/zod/tree/v4.6.5>

The official Google Antigravity ACP runtime (`antigravity-acp` 1.1.1) is a
separate proprietary download. This bridge does not vendor or silently install
that runtime.

The bridge reuses ACPX's runtime and does not copy its implementation into
this repository.
