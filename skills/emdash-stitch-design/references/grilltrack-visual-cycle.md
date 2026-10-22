# GrillTrack Visual Cycle & EmDash Translation

Use this playbook when running a visual design cycle on `template-store` or any EmDash Astro site.

## 1. Uploading the Real Verified Page (`stitch capture` + `stitch upload`)

Rather than prompting Stitch in a vacuum, start from the real verified EmDash route so Stitch sees the exact content sections, product cards, availability summaries, and disclosures:

1. **Authenticate via macOS Keychain (`google-stitch`):**
   - On Bobby's machines, `stitch` (`@google/stitch@0.12.0` managed via `mise`) and `stitch-mcp` (`ai-shed`) resolve `STITCH_API_KEY` from macOS Keychain (`security find-generic-password -s google-stitch -w`) without persisting plaintext keys on disk.
   - In non-interactive subshells, prefix CLI invocations with:
     ```bash
     STITCH_API_KEY="$(security find-generic-password -s google-stitch -w)" stitch status --json
     ```
2. **Capture Self-Contained Route HTML (`stitch capture`):**
   - Discover routes with `stitch capture routes`.
   - Capture a live rendered route (waiting for dynamic DOM / islands to settle):
     ```bash
     stitch capture http://localhost:4321/cart --wait-for="[data-guest-cart-root]" -o .stitch/captures/cart.html --json
     ```
   - Or capture an open `chrome-devtools` tab after driving interactive UI state (without reloading the page):
     ```bash
     stitch capture --tab -o .stitch/captures/checkout-stage.html --json
     ```
3. **Upload `DESIGN.md` & Route Screen (`stitch upload` or `stitch_upload_file`):**
   - Upload and apply `.stitch/DESIGN.md` as a Stitch Design System:
     ```bash
     stitch upload design .stitch/DESIGN.md --project <PROJECT_ID> --apply --json
     ```
   - Upload the captured route screen and bind it to its route in the manifest:
     ```bash
     stitch upload screen .stitch/captures/cart.html --route /cart --title "Guest Cart (/cart)" --project <PROJECT_ID> --json
     ```
   - (Or call `stitch_upload_file` via `stitch-mcp` in `ai-shed`.)

## 2. Generating 5 GrillTrack Candidates & Tiebreaker Hybrids

1. **Initial Exploration (`stitch generate variant` or MCP `generate_variants`):**
   ```bash
   stitch generate variant \
     --project <PROJECT_ID> \
     --screen <BASELINE_SCREEN_ID> \
     --count 5 \
     --creative-range EXPLORE \
     --aspects LAYOUT,COLOR_SCHEME,TEXT_FONT \
     --prompt "Explore 5 materially distinct editorial and storefront visual directions for this neutral DinkusKit store starter..." \
     --json
   ```
2. **Controlled Single-Variable & Per-Surface Rounds (Deterministic HTML Upload + Asset Download):**
   - Once the core layout is chosen, use `stitch upload screen <file> --route <route> --title "<title>" --project <PROJECT_ID> --json` (or `stitch_upload_file`) and `stitch download screen <SCREEN_ID> --project <PROJECT_ID> --html --image --output <DIR>` (or `stitch_download_screen` with `width: 2560` for full-resolution FIFE PNGs) to generate 5 deterministic candidates for each subsequent variable and surface.
   - Use `stitch url project <PROJECT_ID> --json` / `stitch url screen <SCREEN_ID> --project <PROJECT_ID> --json` for canonical Stitch Canvas links, or `stitch serve -p <PROJECT_ID> --port 3000` to launch a local preview server.
   - **Canvas Layout: One Row per Surface (Re-flow After Each Round):**
     - Stitch appends every new frame to a single horizontal row at `+1380px` steps. Once `max(x)` passes `~60,000px` (~44 screens), new `screenInstances` stop attaching. Variants of an uploaded screen with no device type also get 390 px placeholders that are later resized without moving their neighbours, so frames overlap ([stitch-sdk#383](https://github.com/google-labs-code/stitch-sdk/issues/383)). Placeholders can also stay labelled "Generating Screen..." after the screen is done.
     - Keep one row per round or surface from the start, rows top to bottom in round order, at most ~10 frames per row (wrap long rounds within their surface).
     - After each round, once **no generation is running**, re-flow with one `PATCH /v1/projects/{id}?updateMask=screenInstances`. Use an x step of `1380`, and set each row's y to the previous row's y plus its tallest frame plus `400`. The API key is enough.
     - The mask replaces the whole list: GET the project first, keep a backup of `screenInstances`, and send **every** instance back, including non-screen ones. In the same PATCH, give stuck "Generating Screen..." frames their screen title, and give 390 px frames over DESKTOP screens their desktop size (half the screen's pixel width and height).
     - Then ask the user to refresh the canvas tab; an open tab keeps its stale layout until reloaded.
     - `uploadFileToStitch` in `ai-shed` still performs only atomic `screens:batchCreate`. Layout PATCHes are a separate, explicit step between rounds.

## 2a. Desktop + Mobile Pairs and the Mobile Pass

1. **Pairs at every decision:** Show each candidate's desktop render (full-width `=w2560` or `=w1440` PNG) beside the same screen at a 390 px viewport:
   - Download its HTML with `stitch download screen <SCREEN_ID> --project <PROJECT_ID> --html --output <DIR>`.
   - Render that file locally at `390×844` with headless Chrome or Playwright.
   - This costs no Stitch credits. Check the nav collapse, hero type scale, grid density, cart and checkout controls, tap targets of at least 44 px, and no horizontal overflow (`scrollWidth <= clientWidth`).
   - Optional, for the user's eye: a 390 px-wide copy of the candidate's canvas frame (an extra `screenInstances` entry for the same `sourceScreen`). Confirm the canvas accepts the added instance before relying on it.
2. **Mobile pass after the desktop lock (optional):** When a surface's desktop direction locks, offer one mobile-specific round for what reflow can't fix: the nav pattern, a sticky add-to-cart, tap targets, and dense tables or ledgers.
   - Use `stitch generate variant --device MOBILE` (or `edit_screen` with `device: MOBILE`) on the locked desktop screen, or targeted CSS for the breakpoint.
   - Show it as a desktop + mobile pair, lock mobile separately, and record both locks in the GrillTrack ledger.
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
