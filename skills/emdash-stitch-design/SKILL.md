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

3. **Generate Materially Distinct Candidates (`generate_variants` / `generate_screen_from_text`):**
   - For a GrillTrack visual cycle (such as `template-store`'s 5-candidate visual lock), call `generate_variants` with `variantCount: 5`, `creativeRange: "EXPLORE"`, and `aspects: ["LAYOUT", "COLOR_SCHEME", "TEXT_FONT"]` (or call `generate_screen_from_text` with structured layout prompts).
   - Keep generation prompts strictly structural (Header, Hero, Content Grid, Summary Rail, Footer). Never leak hex codes or font names into `generate_screen_from_text` when a project `DesignSystem` is active.
   - Download each candidate's HTML and full-resolution `=w2560` screenshot via `stitch_download_screen` into `.stitch/designs/` (or `runs/` when ignored by repo hygiene).

4. **Translate the Chosen Candidate into EmDash / Astro (`emdash-sites` + `building-emdash-site`):**
   - Read [references/grilltrack-visual-cycle.md](references/grilltrack-visual-cycle.md) before modifying Astro/EmDash components.
   - Extract CSS custom properties, typography scales, spacing tokens, and structural grid layout from the winning Stitch HTML into the site's Astro layout/feature styles (e.g., `src/features/store-shell/`).
   - **Never copy raw Stitch static DOM over dynamic EmDash bindings:**
     - Keep `output: "server"` and live EmDash queries (`getEmDashCollection`, `getEmDashEntry`).
     - Render CMS media with `<Image image={...} />` from `"emdash/ui"`, rich content with `<Blocks />` / `<PortableText />`, and Dinkus Blocks through their documented classes and theme tokens.
     - Preserve every `data-*` attribute, `id` anchor, keyboard-operable `<details>` disclosure, and 404/empty-state contract required by `FEATURE_MAP.md`.

5. **Prove on Desktop and Mobile:**
   - Run the repository's canonical verification gate (e.g., `bin/verify-web full` or `pnpm verify`) across desktop Chromium and mobile viewports before closeout.
