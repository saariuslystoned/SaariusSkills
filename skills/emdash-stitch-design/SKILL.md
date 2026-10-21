---
name: emdash-stitch-design
description: Design and upgrade EmDash Astro sites with Google Stitch MCP (`stitch-mcp`) and GrillTrack. Use for `code-to-design` snapshots, `taste-design` `DESIGN.md` systems, 5-candidate GrillTrack visual variants, tiebreaker hybrids, upstream EmDash `tokens.css`/`theme.css` theming (plus optional playground preset switchers), and Astro/EmDash translation preserving `FEATURE_MAP.md` hooks.
---

# EmDash Stitch Design

Pair GrillTrack's product/visual decision loop with Google Stitch's native MCP (`https://stitch.googleapis.com/mcp` via `ai-shed`'s `stitch-mcp` server) to design and upgrade EmDash Astro websites without losing server-rendered CMS contracts or `FEATURE_MAP.md` verification hooks.

## Core Loop: GrillTrack ↔ Stitch ↔ EmDash

1. **Grill & Lock Visual Intent (`grilltrack` + `design.md`):**
   - Before generating screens, read the target repo's `design.md`, `FEATURE_MAP.md`, and `.grilltrack/ledger.json`.
   - Use GrillTrack to lock the atmosphere, density, variance, typography posture, and non-goals (e.g., no invented checkout/cart controls on catalog-only slices).
   - Synthesize a semantic `.stitch/DESIGN.md` following [references/taste-and-prompts.md](references/taste-and-prompts.md).

2. **Snapshot the Verified Real Page into Stitch (`code-to-design`):**
   - Start or build the real EmDash Astro project and capture self-contained rendered HTML for the target route (e.g., `/`, `/categories/[slug]`, `/products/[id]`, `/cart`).
   - Check `stitch_status` on the `stitch-mcp` server.
   - Create or select the Stitch project (`list_projects` / `create_project`).
   - Upload `.stitch/DESIGN.md` and the rendered route HTML using `stitch_upload_file` (which posts directly to `screens:batchCreate` in-process so base64 never hits LLM output token limits), then sync the project design system via `create_design_system_from_design_md` or `update_design_system`.

3. **Walk the Complete Storefront Surface Checklist (One Variable / Surface at a Time):**
   - Never compound multiple visual variables in one round, and **never jump into codebase implementation or long test runs until every storefront surface on the checklist is visually locked** (unless the user explicitly requests a checkpoint PR):
     1. **Global Foundations (`design.md` + `tokens.css`):** Homepage Layout Architecture (`/`) → Color Palette (holding chosen layout constant) → Typography Role System (holding chosen layout + palette constant).
     2. **Core Storefront Pages:** Product Detail Page (`/products/[id]`) → Category Collection Page (`/categories/[slug]`) → Guest Cart (`/cart`) → Checkout (`/checkout` or cart checkout stage) → Order Confirmation (`/checkout/success`) → Shopper Account (`/account`, showing both Signed-In and Signed-Out states) → Store Policies (`/shipping` & `/returns`, standardized against Shopify/WooCommerce/BigCommerce/Google Merchant Center).
     3. **Global Chrome & Discovery:** Shared Global Footer (`StoreFooter.astro` with `<WidgetArea name="footer" />` + footer-only Theme toggle and, if a starter/playground showcase, Preset switcher) → Header Search Bar & Live Search Page (`/search` with `<LiveSearch />`).
   - When holding locked variables constant, upload deterministic HTML variants via `stitch_upload_file` (`screens:batchCreate`) so Stitch renders pixel-accurate `=w2560` screenshots in ~2s without mutating locked DOM structure.
   - **Tiebreaker & Hybrid Rounds:** When the user is torn between two candidates (e.g., likes Layout A's frame with Candidate B's cards or search pill bar), immediately generate a 2–3 screen **Tiebreaker / Hybrid** round in real page context so the user can compare the exact combination before locking.

4. **Handle Unbuilt Code / Plugin Gaps Without Losing UI Momentum:**
   - If the user requests a UI control, interaction, or workflow during the design grill that is not yet supported by the underlying EmDash site code or companion plugin (for example, per-variant quantity steppers, multi-variant batch add on a PDP, or structured policy highlight fields):
     1. **File an issue immediately** (`gh issue create --label smoky-agent`) on the relevant repository documenting the gap and desired contract (creating the `smoky-agent` label first if missing).
     2. **Mock the feature cleanly in the Stitch design** so the visual system and layout hierarchy account for the real UX.
     3. **Keep moving on the frontend/UI design grill**—never get sidetracked implementing backend or plugin feature additions mid-design.

5. **Align with Upstream EmDash Theming & All 3 Composition Primitives:**
   - Read [references/grilltrack-visual-cycle.md](references/grilltrack-visual-cycle.md) before modifying Astro/EmDash components.
   - **Upstream EmDash Theming (`src/styles/tokens.css` + `src/styles/theme.css`):**
     - Define all design tokens inside `@layer base` in `src/styles/tokens.css` using CSS `light-dark(<light>, <dark>)`, and ship a blank unlayered `src/styles/theme.css` (`:root {}` with adopter comments) imported after `tokens.css`.
     - **Real Live Store vs. Starter / Playground Showcase:** A live production storefront locks **one** chosen brand palette in `src/styles/tokens.css` (with optional `Light` / `Dark` / `System` appearance toggle in the footer colophon). Only include multi-palette `:root[data-preset="..."]` blocks and **color-coded preset pills** (styled with each preset's palette fill, border, stamp shadow, and dual-tone swatch dot) **circumstantially on starter templates, demo playgrounds, or staging sites** meant to showcase multiple color formats to prospects—and keep any switcher strictly in the footer colophon (never duplicated in the header).
   - **All 3 EmDash Composition Primitives (`blocks`, `sections`, `widgetAreas`):**
     - `blocks`: Keep `pages.layout` blocks (`home_opener`, `rich_text`, `query_card`) on `/`.
     - `sections`: Seed a reusable Portable Text section (e.g., `policy-support-note`) rendered via `getSection()` + `<PortableText />` on `/shipping` and `/returns` while preserving any legacy migration section (`home-opener`).
     - `widgetAreas`: Mount a shared `StoreFooter.astro` (`getSiteSettingsWithCacheHint()`, `footer_shop`, `footer_policies`) across all public routes rendering `<WidgetArea name="footer" />` with all 3 EmDash widget types (`content`, `menu`, `component: core:search`), paired with `"search"` in collection `supports` + `"searchable": true` fields and `/search` using `<LiveSearch>` from `"emdash/ui/search"`.

6. **Prove on Desktop and Mobile & Archive to `dinkus-pr-assets`:**
   - Run `bin/verify-web quick` and `bin/verify-web full` (`pnpm verify`) across desktop Chromium and mobile viewports before closeout.
   - Archive the locked Stitch `.html` source files, `=w2560` `.png` screenshots, `.stitch/DESIGN.md`, `design.md`, and `tokens.css`/`theme.css` into `dinkuskit/dinkus-pr-assets` (`<repo>-stitch-<pr>/`) so future implementation and review agents have both visual and HTML/CSS reference truth.
