# Third-party notices

The local Muse ACP bridge and its in-bridge muse-agent-acp adapter use
these pinned packages:

- `@agentclientprotocol/sdk@1.5.1` (Apache-2.0):
  <https://github.com/agentclientprotocol/typescript-sdk>
- `acpx@0.19.4` (MIT): <https://github.com/openclaw/acpx/releases/tag/v0.19.4> (source tag `8e396609238086dee6a407fdb3b3ac46dbdedd70`)
- `@modelcontextprotocol/sdk@1.30.0` (MIT):
  <https://github.com/modelcontextprotocol/typescript-sdk/tree/v1.30.0>
- `zod@4.6.5` (MIT): <https://github.com/colinhacks/zod/tree/v4.6.5>

The bridge reuses ACPX's runtime and does not copy its implementation into
this repository.
