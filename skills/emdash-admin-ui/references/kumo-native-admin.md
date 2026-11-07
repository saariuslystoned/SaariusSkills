# Native React Kumo Admin Surfaces & GrillTrack Admin Cycles

When building or reviewing a **trusted native React** EmDash admin surface (`@cloudflare/kumo` + `@lingui/macro`), or running a GrillTrack visual cycle on an admin screen:

## 1. Upstream EmDash Native Admin Conventions

1. **Use `@cloudflare/kumo` Primitives Directly:**
   - Import `Badge`, `Banner`, `Button`, `Checkbox`, `CodeBlock`, `Collapsible`, `Combobox`, `Dialog`, `DropdownMenu`, `Empty`, `Input`, `InputArea`, `Link`, `LinkButton`, `Meter`, `Radio`, `Select`, `SensitiveInput`, `Switch`, `Tabs` from `@cloudflare/kumo`.
   - Use Kumo semantic tokens (`text-kumo-default`, `text-kumo-subtle`, `border-kumo-line`, `bg-kumo-bg`, `bg-kumo-tint`, `focus:ring-kumo-ring`) so light and dark themes (`<html data-theme="dark">`) stay synchronized without custom hex overrides.
2. **Logical Properties & Localization:**
   - Use logical Tailwind utilities (`text-start`, `text-end`, `ps-*`, `pe-*`, `ms-*`, `me-*`) for RTL compatibility.
   - Wrap user-facing strings with Lingui in active render scope rather than module-level constants.
3. **Never Claim Registry Readiness from a Native React Screen:**
   - Any plugin intended for the EmDash Registry must render its admin UI through `@emdash-cms/blocks/server` (`validateBlockResponse`) inside the sandboxed runtime (`@emdash-cms/sandbox-workerd/sandbox` or Cloudflare Worker Loader).

## 2. Agent-First Onboarding Pattern for AI / Service Plugins

When an EmDash plugin connects to an external agent gateway (such as OpenClaw) or companion Cloudflare Worker (such as Pi Durable):

1. **Tier 1 — Agent-Assisted Pairing (`npx` + `curl` Prompt):**
   - Provide a copy-paste prompt (`code` block) with a one-time pairing code (`oc_pair_...`) so users who rely on agents can drop the prompt into Signal, Discord, Telegram, or Web chat and let their agent run `npx --yes @dinkuskit/<pkg> pair "<siteOrigin>" "<pairingCode>"` (with a direct `curl -X POST` fallback in the same prompt).
2. **Tier 2 — 1-Click Cloudflare Deploy with Explicit Defaults Table:**
   - Pair any `https://deploy.workers.cloudflare.com/?url=...` button with a 3-row `table` naming the exact Cloudflare screen steps (including keeping **Protect with Cloudflare Access OFF** for server-to-server Bearer auth, setting `"workers_dev": true` in `wrangler.jsonc`, and toggling **`Production *.workers.dev` ON** under `Worker → Domains`).
3. **Tier 3 — Collapsed Manual Fallback (`accordion`):**
   - Keep raw URL/token inputs inside a collapsed `accordion` (`default_open: Boolean(failure)`) so power users can configure manually without intimidating first-time users.
