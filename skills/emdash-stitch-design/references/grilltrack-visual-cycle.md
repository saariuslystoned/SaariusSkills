# GrillTrack Visual Cycle & EmDash Translation

Use this playbook when running a visual design cycle on `template-store` or any EmDash Astro site.

## 1. Uploading the Real Verified Page (`code-to-design`)

Rather than prompting Stitch in a vacuum, start from the real verified EmDash route so Stitch sees the exact content sections, product cards, availability summaries, and disclosures:

1. Start the local Astro server or run a single-route HTML snapshot of the rendered page.
2. Inline critical stylesheet rules into a temporary standalone HTML snapshot (e.g., `.stitch/snapshots/home.html`) so Stitch renders the current baseline accurately.
3. Call `stitch_upload_file` (or `uploadFileToStitch` in `ai-shed/stitch-mcp/client.mjs`):
   ```json
   {
     "projectId": "<PROJECT_ID>",
     "filePath": "/abs/path/to/.stitch/snapshots/home.html",
     "title": "/"
   }
   ```
4. Upload `.stitch/DESIGN.md` with `stitch_upload_file`, inspect `get_project` to find the uploaded screen instance (`id` + `sourceScreen`), and call `create_design_system_from_design_md`.

## 2. Generating 5 GrillTrack Candidates & Tiebreaker Hybrids

1. **Initial Exploration (`generate_variants`):**
   ```json
   {
     "projectId": "<PROJECT_ID>",
     "selectedScreenIds": ["<BASELINE_SCREEN_ID>"],
     "prompt": "Explore 5 materially distinct editorial and storefront visual directions for this neutral DinkusKit store starter...",
     "variantOptions": {
       "variantCount": 5,
       "creativeRange": "EXPLORE",
       "aspects": ["LAYOUT", "COLOR_SCHEME", "TEXT_FONT"]
     }
   }
   ```
2. **Controlled Single-Variable & Per-Surface Rounds (Deterministic HTML Upload):**
   - Once the core layout is chosen, use `stitch_upload_file` (`screens:batchCreate`) + `stitch_download_screen` (`width: 2560`) to generate 5 deterministic candidates for each subsequent variable and surface (Color Palette, Typography, PDP, Category, Cart, Checkout, Order Confirmation, Account, Policies, Footer, Search).
   - **When the user is torn between two candidates (e.g., Candidate 1 vs. Candidate 4, or Candidate 3's layout with Candidate 2's search bar):**
     - Do not force a blind choice. Immediately generate a **2–3 screen Tiebreaker / Hybrid round** combining the exact preferred elements and showing them in realistic page context (for example, rendering a footer candidate directly beneath the bottom of a storefront page canvas so surface contrast is obvious).

## 3. Handling Unbuilt Code or Plugin Features Discovered During Design

When a visual review uncovers a missing capability in the EmDash storefront or a companion plugin (for example, missing PDP quantity selectors, multi-variant batch selection, or structured policy highlight fields):

1. **File an issue on the owning repository (`gh issue create --label smoky-agent`)** with the exact component path, current limitation, and requested behavior.
2. **Mock the control or state directly in the Stitch screen** so the locked visual design and spacing accommodate the target UX.
3. **Stay focused on the frontend/UI grill**—never pause the visual design cycle to build plugin or backend features, and never start long verification builds until the user's visual grill rounds are complete.

## 4. Upstream EmDash Theming & Composition Architecture

When translating locked Stitch designs into an EmDash starter or storefront:

- **Token Layering (`src/styles/tokens.css` + `src/styles/theme.css`):**
  - Place all design tokens inside `@layer base` in `src/styles/tokens.css` using CSS `light-dark(<light>, <dark>)` with `color-scheme: light dark` controlled by `:root[data-theme="light"|"dark"|"system"]`.
  - Ship a blank unlayered `src/styles/theme.css` (`:root {}`) imported immediately after `tokens.css` so DevToolbar live previews and adopter overrides win without `!important`.
  - **Production Storefront vs. Starter / Playground Showcase:**
    - A real live store chooses **one** locked palette in `src/styles/tokens.css` (and may expose a `Light`/`Dark`/`System` appearance toggle in the footer colophon).
    - **Circumstantial (Starter Templates / Demo Playgrounds / Prospect Staging Sites only):** When showcasing a template or staging site across multiple color formats to prospects (such as `template-store`), retain **2–3 curated Stitch presets** in `@layer base` (e.g. `:root, :root[data-preset="aizome"]`, `:root[data-preset="forest"]`, `:root[data-preset="cobalt"]`) and mount cookie-persisted (`dinkus_theme`, `dinkus_preset`) **color-coded preset pills** (each styled with its own palette swatch, fill, border, and offset shadow) **strictly in the footer colophon** (never duplicated in the header), restored inline in `StoreHeader.astro` before first paint.
- **Exercise All 3 EmDash Composition Primitives:**
  1. `blocks`: `pages.layout` (`home_opener`, `rich_text`, `query_card`) on `/`.
  2. `sections`: Reusable Portable Text section (`getSection("<slug>")` + `<PortableText />`) on `/shipping` and `/returns`, keeping legacy sections (`home-opener`) in `seed/seed.json` for migration test compatibility.
  3. `widgetAreas`: Shared `StoreFooter.astro` mounted across all public routes (`/`, `/categories/[slug]`, `/products/[id]`, `/cart`, `/checkout/success`, `/account`, `/shipping`, `/returns`, `/search`) using `getSiteSettingsWithCacheHint()`, `footer_shop` / `footer_policies` menus, and `<WidgetArea name="footer" />` containing all 3 widget types (`content`, `menu`, `component: core:search`).

## 5. EmDash / DinkusKit Verification Guardrails

Before running `bin/verify-web quick` or `bin/verify-web full`, verify these repository-specific invariants:

- **Zero `\bany\b` tokens in `src/`:** `scripts/check-features.mjs` scans `src/**/*.{astro,mjs,ts}` with `/\bany\b/u`. Never use the word `any` in TypeScript types, comments, or UI prose inside `src/`.
- **Preserve `FEATURE_MAP.md` & E2E Selectors:**
  - Keep all `data-*` attributes intact (`data-store-header`, `data-store-main-nav`, `data-guest-cart-nav`, `data-store-footer`, `data-footer-shop-nav`, `data-footer-policies-nav`, `data-widget-area="footer"`, `data-policy-support-section`, `data-search-result={hit.slug ?? hit.id}`).
  - In `_emdash_menu_items`, custom links use the `custom_url` column.
  - Preserve exact light-mode RGB values on primary action tokens if asserted by existing E2E tests (e.g. `--dinkus-action-color: #fffefb`, `--dinkus-action-background: #172033` for `.home-opener__primary`).
  - Avoid `$N`, two-letter uppercase words (`\b[A-Z]{2}\b`), or `\d+ days` in unconfigured `/shipping` fallback/section prose (`structured-data-policy-feed.spec.ts`).
  - Avoid duplicate accessible link names in footer menus that collide with unscoped Playwright locators (e.g. label the footer `/cart` link `"Shopping bag"` so `getByRole("link", { name: /Cart/ })` resolves uniquely to the header cart link).
  - Hide wide desktop header search pills below `48rem` so `320px` mobile viewports pass horizontal-overflow checks (`document.documentElement.scrollWidth <= document.documentElement.clientWidth`).

## 6. Archiving Locked Reference Bundles to `dinkus-pr-assets`

At closeout, copy each locked surface's self-contained `.html` source and `=w2560` `.png` screenshot—along with `.stitch/DESIGN.md`, `design.md`, `src/styles/tokens.css`, and `src/styles/theme.css`—into `dinkuskit/dinkus-pr-assets` (`<repo>-stitch-<pr>/`) with a SHA-256 manifest table in `README.md` so coding and review agents can reference both the visual renders and exact Stitch HTML/CSS code.
