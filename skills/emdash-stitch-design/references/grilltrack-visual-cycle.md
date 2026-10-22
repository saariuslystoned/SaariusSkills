# GrillTrack Visual Cycle & EmDash Translation

Use this playbook when running a visual design cycle on any EmDash Astro site. Every visual value comes from the site's own grill locks; examples here show method, not a look to reuse.

## 1. Uploading the Real Verified Page (`stitch capture` + `stitch upload`)

Rather than prompting Stitch in a vacuum, start from the real verified EmDash route so Stitch sees the exact content sections, product cards, availability summaries, and disclosures:

1. **Authenticate (macOS Keychain service `google-stitch`):**
   - If the API key is stored in the macOS Keychain (service `google-stitch`), `stitch` (`@google/stitch@0.12.0`, for example managed via `mise`) and `stitch-mcp` (`ai-shed`) resolve `STITCH_API_KEY` from it (`security find-generic-password -s google-stitch -w`) without persisting plaintext keys on disk.
   - In non-interactive subshells, prefix CLI invocations with:
     ```bash
     STITCH_API_KEY="$(security find-generic-password -s google-stitch -w)" stitch status --json
     ```
2. **Capture Self-Contained Route HTML (`stitch capture`):**
   - Discover routes with `stitch capture routes`.
   - Capture a live rendered route, waiting for a selector that appears once dynamic DOM / islands settle:
     ```bash
     stitch capture http://localhost:4321/cart --wait-for="<ready-selector>" -o .stitch/captures/cart.html --json
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
     --prompt "Explore 5 materially distinct visual directions for <the site and its audience in one line>..." \
     --json
   ```
2. **Controlled Single-Variable & Per-Surface Rounds (Deterministic HTML Upload + Asset Download):**
   - Once the core layout is chosen, use `stitch upload screen <file> --route <route> --title "<title>" --project <PROJECT_ID> --json` (or `stitch_upload_file`) and `stitch download screen <SCREEN_ID> --project <PROJECT_ID> --html --image --output <DIR>` (or `stitch_download_screen` with `width: 2560` for full-resolution FIFE PNGs) to generate 5 deterministic candidates for each subsequent variable and surface.
   - Use `stitch url project <PROJECT_ID> --json` / `stitch url screen <SCREEN_ID> --project <PROJECT_ID> --json` for canonical Stitch Canvas links, or `stitch serve -p <PROJECT_ID> --port 3000` to launch a local preview server.
   - **Canvas Layout: A Named Group per Round or Surface (Re-flow After Each Round):**
     - Stitch appends every new frame to a single horizontal row at `+1380px` steps. Once `max(x)` passes `~60,000px` (~44 screens), new `screenInstances` stop attaching. Variants of an uploaded screen with no device type also get 390 px placeholders that are later resized without moving their neighbours, so frames overlap ([stitch-sdk#383](https://github.com/google-labs-code/stitch-sdk/issues/383)). Placeholders can also stay labelled "Generating Screen..." after the screen is done.
     - Keep one row per round or surface from the start, rows top to bottom in round order, at most ~10 frames per row (wrap long rounds within their surface).
     - After each round, once **no generation is running**, re-flow with one `PATCH /v1/projects/{id}?updateMask=screenInstances`. Use an x step of `1380`, and set each row's y to the previous row's y plus its tallest frame plus `400`. The API key is enough.
     - The mask replaces the whole list: GET the project first, keep a backup of `screenInstances`, and send **every** instance back, including non-screen ones. In the same PATCH, give stuck "Generating Screen..." frames their screen title, and give 390 px frames over DESKTOP screens their desktop size (half the screen's pixel width and height).
     - Wrap each row in a named group in the same PATCH. Add one instance with `type: "GROUP_INSTANCE"`, a new 32-character hex `id`, `label` and `groupName` set to the row's name, and `x`/`y`/`width`/`height` enclosing the row's frames plus about `120px` of padding. Give each member frame the same `groupId` and `groupName`.
     - Name rows by round or surface and their variable: `R1 · Layout`, `R2 · Palette`, `R3 · Type`, `S1 · Product page`, `S3 · Cart`. When a round locks, add the winner to its name (`R2 · Palette, locked P3`).
     - Record the group IDs you create (for example in `.stitch/canvas-groups.json`). On each re-flow, update their bounds and members, and send back unchanged every group you did not create.
     - Checked 2026-10-22: the API stores these groups, and the Stitch canvas draws each group with its name.
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
   - **When the user is torn between two candidates (e.g., two whole candidates, or one candidate's layout with another's component):**
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
    - A real live store chooses **one** locked palette in `src/styles/tokens.css` (and may expose a `Light`/`Dark`/`System` appearance toggle).
    - **Circumstantial (Starter Templates / Demo Playgrounds / Prospect Staging Sites only):** When a template or staging site shows prospects several colorways, retain **2–3 curated Stitch presets** in `@layer base` (`:root, :root[data-preset="<default>"]` plus a `:root[data-preset="<name>"]` block per alternate, named for this site's palettes). Persist the visitor's theme and preset choice (for example in a cookie) and restore it inline before first paint so the page does not flash. The switcher's look and placement are grill decisions for that site; never duplicate it in both header and footer.
- **EmDash Composition Primitives (`blocks`, `sections`, `widgetAreas`):**
  1. Use the site's existing page-layout blocks, reusable sections, and widget areas. Keep their names and seeded content, including legacy sections that migrations or tests still read.
  2. Add a primitive only where owners need to edit that content in the CMS: a `pages.layout` block for an owner-arranged page, a Portable Text section (`getSection("<slug>")` + `<PortableText />`) for copy reused across pages, or a widget area (`<WidgetArea name="<area>" />`) for an owner-managed region.
  3. Render shared chrome (header, footer) on every public route, and read its links and settings through EmDash (the site's own menus, `getSiteSettingsWithCacheHint()`) rather than hard-coding them. In `_emdash_menu_items`, custom links use the `custom_url` column.
  4. EmDash search needs `"search"` in the collection's `supports`, `"searchable": true` fields, and `<LiveSearch>` from `"emdash/ui/search"`.

## 5. Repository Invariants Before Verification

Before running the repo's verification (DinkusKit storefronts: `bin/verify-web quick` / `bin/verify-web full`), read the repo's own contracts and keep what they pin:

- **Where invariants live:** the repo's `AGENTS.md`, `FEATURE_MAP.md`, and `design.md`, its lint and feature-check scripts, and its unit and browser tests.
- **What to preserve:** `data-*` hooks and selectors that tests and `FEATURE_MAP.md` rely on; values tests assert exactly (colors, text, accessible names); copy rules that checks enforce; and words or tokens that source scans ban.
- **What a redesign commonly breaks:** accessible names that unscoped test locators now match twice, and wide header elements that overflow narrow mobile viewports (`document.documentElement.scrollWidth <= document.documentElement.clientWidth`).
- When the locked design conflicts with a pinned value, keep the pinned value and record the conflict for the owner; never edit the test to make the design pass.

## 6. Archiving Locked Reference Bundles

At closeout, copy each locked surface's self-contained `.html` source and `=w2560` `.png` screenshot—along with `.stitch/DESIGN.md`, `design.md`, `src/styles/tokens.css`, and `src/styles/theme.css`—into the project's design-asset archive (DinkusKit: `dinkuskit/dinkus-pr-assets`, `<repo>-stitch-<pr>/`) with a SHA-256 manifest table in `README.md` so coding and review agents can reference both the visual renders and exact Stitch HTML/CSS code.
