# Stitch Taste, `DESIGN.md`, and Prompt Rules

Adapted from `google-labs-code/stitch-skills` (`taste-design`, `design-md`, `generate-design`, `manage-design-system`) for EmDash sites.

## 1. Anti-Slop `DESIGN.md` Rules (`taste-design`)

Encode these rules in `.stitch/DESIGN.md` before generating screens:

- **Atmosphere Axes:**
  - **Density:** 1–3 (Gallery Airy) · 4–7 (Balanced Storefront) · 8–10 (Cockpit Dense; use monospace for numbers).
  - **Variance:** 1–3 (Symmetric Grid) · 4–7 (Offset Asymmetric) · 8–10 (Editorial Asymmetric).
- **Color Calibration:**
  - Maximum 1 primary accent color (saturation < 80%).
  - Ban "AI Purple/Blue Neon" gradients and outer button glows.
  - Never use pure `#000000`; use warm off-black, charcoal, or deep ink (`#141413`, `#18181B`).
  - Give every color a semantic name + hex code + functional role.
- **Typography:**
  - Pair a distinctive display face (`Instrument Serif`, `Fraunces`, `Plus Jakarta Sans`, `Space Grotesk`, `Outfit`, `Syne`) with a high-legibility body font and a clean monospace face (`JetBrains Mono`, `IBM Plex Mono`) for SKUs, versions, and provenance metadata.
  - Scale headlines with `clamp()`; keep body copy 60–70ch max width.
- **Banned AI Tells:**
  - No emojis in UI chrome.
  - No fabricated metrics (`99.98% SLA`, `10k+ customers`) or `LABEL // 2026` filler tags.
  - No invented cart/checkout/buy buttons when the slice contract forbids them.
  - No horizontal overflow on narrow mobile viewports (`< 768px`).

## 2. Prompt Enhancement Pipeline (`generate-design`)

When calling `generate_screen_from_text`:
- **Never include hex codes, font names, or roundness values in the generation prompt** if a Stitch `DesignSystem` is attached to the project — project-level design system tokens own styling, and duplicating them in the prompt causes conflicts.
- Structure generation prompts strictly by page anatomy:
  ```markdown
  [Overall purpose and user intent of the page]

  **PLATFORM:** Web, Desktop-first with clean mobile single-column collapse

  **PAGE STRUCTURE:**
  1. **Header & Collection Nav:** [Brand title, category links]
  2. **Home Opener / Hero:** [Editorial headline, subtext, primary & secondary anchor CTAs]
  3. **Merchant Shop & Catalog Grid:** [Product cards with status badges, Regular/Sale price hierarchy]
  4. **Availability & Provenance Rail:** [Compact live status summaries with collapsible native details for SKU/version/authority]
  5. **Footer:** [Minimal provenance and navigation links]
  ```
- When calling `edit_screens` for targeted polish, hex codes and explicit visual adjustments **are** allowed: name the exact section, component, and visual change.

## 3. `update_design_system` Theme Schema

When calling `update_design_system` directly via `stitch-mcp`:
- Required `theme` fields:
  - `colorMode`: `"LIGHT"` | `"DARK"`
  - `headlineFont`: e.g. `"INSTRUMENT_SERIF"`, `"FRAUNCES"`, `"PLUS_JAKARTA_SANS"`, `"SPACE_GROTESK"`, `"OUTFIT"`, `"DM_SANS"`, `"INTER"`
  - `bodyFont`: same enum options
  - `roundness`: `"ROUND_FOUR"` | `"ROUND_EIGHT"` | `"ROUND_TWELVE"` | `"ROUND_FULL"`
  - `customColor`: `#RRGGBB` seed hex
- Optional overrides: `overridePrimaryColor`, `overrideSecondaryColor`, `overrideTertiaryColor`, `overrideNeutralColor`, `designMd`.
- When calling `apply_design_system`, each item in `selectedScreenInstances` must contain **only** `{ "id": "...", "sourceScreen": "projects/.../screens/..." }` (omit `x`, `y`, `width`, `height`, and filter out `DESIGN_SYSTEM_INSTANCE` items).
