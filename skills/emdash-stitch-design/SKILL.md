---
name: emdash-stitch-design
description: Design and upgrade EmDash Astro sites with Google Stitch MCP (`stitch-mcp`) and GrillTrack. Use for `code-to-design` snapshots, `taste-design` `DESIGN.md` systems, 5-candidate GrillTrack visual variants, and Astro/EmDash translation preserving `FEATURE_MAP.md` hooks.
---

# EmDash Stitch Design

Pair GrillTrack's product/visual decision loop with Google Stitch's native MCP (`https://stitch.googleapis.com/mcp` via `ai-shed`'s `stitch-mcp` server) to design and upgrade EmDash Astro websites without losing server-rendered CMS contracts or `FEATURE_MAP.md` verification hooks.

## Core Loop: GrillTrack ↔ Stitch ↔ EmDash

1. **Grill & Lock Visual Intent (`grilltrack` + `design.md`):**
   - Before generating screens, read the target repo's `design.md`, `FEATURE_MAP.md`, and `.grilltrack/ledger.json`.
   - Use GrillTrack to lock the atmosphere, density, variance, typography posture, and non-goals (e.g., no invented checkout/cart controls on catalog-only slices).
   - Synthesize a semantic `.stitch/DESIGN.md` following [references/taste-and-prompts.md](references/taste-and-prompts.md).

2. **Snapshot the Verified Real Page into Stitch (`code-to-design`):**
   - Start or build the real EmDash Astro project and capture self-contained rendered HTML for the target route (e.g., `/`, `/collections/[slug]`, `/products/[slug]`, `/shop/[id]`).
   - Check `stitch_status` on the `stitch-mcp` server.
   - Create or select the Stitch project (`list_projects` / `create_project`).
   - Upload `.stitch/DESIGN.md` and the rendered route HTML using `stitch_upload_file` (which posts directly to `screens:batchCreate` in-process so base64 never hits LLM output token limits), then sync the project design system via `create_design_system_from_design_md` or `update_design_system`.

3. **Generate Materially Distinct Candidates (`generate_variants` / `generate_screen_from_text` / Deterministic HTML Upload):**
   - Grill one visual variable or one core page at a time so the user never has to evaluate compounded changes:
     1. **Global `design.md` Foundations:** Layout Architecture → Color Scheme (holding chosen layout constant) → Typography Role System (holding chosen layout + palette constant).
     2. **Core Page Templates:** Homepage (`/`) → Single Product Page (`/products/[id]`) → Single Category Page (`/categories/[slug]`) → Cart & Checkout Flow (`/cart`, `/checkout/success`).
   - When holding locked variables constant (e.g., applying 5 color palettes to a locked layout, or 5 font pairings to a locked layout + palette), upload deterministic HTML variants via `stitch_upload_file` (`screens:batchCreate`) so Stitch renders pixel-accurate `=w2560` screenshots in ~2s without mutating locked DOM structure.
   - Download each candidate's HTML and full-resolution `=w2560` screenshot via `stitch_download_screen` into `.stitch/designs/` (or `runs/` when ignored by repo hygiene).

4. **Handle Unbuilt Code / Plugin Gaps Without Losing UI Momentum:**
   - If the user requests a UI control, interaction, or workflow during the design grill that is not yet supported by the underlying EmDash site code or companion plugin (for example, per-variant quantity steppers or multi-variant batch add on a Product Detail Page):
     1. **File an issue immediately** (`gh issue create --label smoky-agent`) on the relevant repository documenting the gap and desired contract (creating the `smoky-agent` label first if missing).
     2. **Mock the feature cleanly in the Stitch design** so the visual system and layout hierarchy account for the real UX.
     3. **Keep moving on the frontend/UI design grill**—never get sidetracked implementing backend or plugin feature additions mid-design.

5. **Translate the Chosen Candidate into EmDash / Astro (`emdash-sites` + `building-emdash-site`):**
   - Read [references/grilltrack-visual-cycle.md](references/grilltrack-visual-cycle.md) before modifying Astro/EmDash components.
   - Extract CSS custom properties, typography scales, spacing tokens, and structural grid layout from the winning Stitch HTML into the site's Astro layout/feature styles (e.g., `src/features/store-shell/`).
   - **Never copy raw Stitch static DOM over dynamic EmDash bindings:**
     - Keep `output: "server"` and live EmDash queries (`getEmDashCollection`, `getEmDashEntry`).
     - Render CMS media with `<Image image={...} />` from `"emdash/ui"`, rich content with `<Blocks />` / `<PortableText />`, and Dinkus Blocks through their documented classes and theme tokens.
     - Preserve every `data-*` attribute, `id` anchor, keyboard-operable `<details>` disclosure, and 404/empty-state contract required by `FEATURE_MAP.md`.

6. **Prove on Desktop and Mobile:**
   - Run the repository's canonical verification gate (e.g., `bin/verify-web full` or `pnpm verify`) across desktop Chromium and mobile viewports before closeout.
