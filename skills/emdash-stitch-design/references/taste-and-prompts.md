# Stitch Taste, `DESIGN.md`, and Prompt Rules

Adapted from `google-labs-code/stitch-skills` (`taste-design`, `design-md`, `generate-design`, `manage-design-system`) for EmDash sites.

## 1. Anti-Slop `DESIGN.md` Rules (`taste-design`)

Encode these rules in `.stitch/DESIGN.md` before generating screens:

- **Atmosphere Axes:**
  - **Density:** 1–3 (Gallery Airy) · 4–7 (Balanced Storefront) · 8–10 (Cockpit Dense; use monospace for numbers).
  - **Variance:** 1–3 (Symmetric Grid) · 4–7 (Offset Asymmetric) · 8–10 (Editorial Asymmetric).
- **Color Calibration & Optional Playground Presets:**
  - Maximum 1 primary accent color per palette (saturation < 80%).
  - Ban "AI Purple/Blue Neon" gradients and outer button glows.
  - Never use pure `#000000`; use a warm off-black, charcoal, or deep ink chosen for this site's palette.
  - Give every color a semantic name + hex code + functional role, and map the locked Stitch palette into `@layer base` in `src/styles/tokens.css` using `light-dark(<light>, <dark>)`. (Circumstantially on starter templates, demo playgrounds, or staging sites built to preview multiple colorways for prospects, also retain 2–3 runner-up Stitch palettes as `:root[data-preset="..."]` blocks.)
- **Surfaces, Borders, and Shadows Come From This Site's Lock:**
  - Derive surface tones, border weights, corner radii, and shadow style from the palette and atmosphere locked for this site, and grill them with candidates like any other variable.
  - Record locked values (hex codes, sizes, offsets) only in the project's `.stitch/DESIGN.md`, `design.md`, and `src/styles/tokens.css`. This reference holds rules, never another site's locked values: carrying one build's palette or surface system into the next site makes every site look the same.
- **Typography:**
  - Lock the type pairing in its own round: a distinctive display face with a high-legibility body face, plus a monospace face only where the site's content benefits from one (for example SKUs, versions, or tabular figures with `font-variant-numeric: tabular-nums`). Choose faces for this site's atmosphere, not from a fixed shortlist.
  - Name only faces the build can serve. If builds run offline or the font provider cannot reach its source, use locally shipped font files or an explicit system stack, and record what actually renders.
  - Scale headlines with `clamp()`; keep body copy 60–70ch max width.
- **Banned AI Tells:**
  - No emojis in UI chrome.
  - No fabricated metrics (`99.98% SLA`, `10k+ customers`) or `LABEL // 2026` filler tags.
  - No invented cart/checkout/buy buttons when the slice contract forbids them.
  - No duplicated theme/preset switchers in both header and footer. Where a switcher lives is a grill decision for this site.
  - No horizontal overflow on narrow mobile viewports (`320px–767px`).

## 2. Prompt Enhancement Pipeline (`generate-design`)

When calling `generate_screen_from_text`:
- **Never include hex codes, font names, or roundness values in the generation prompt** if a Stitch `DesignSystem` is attached to the project — project-level design system tokens own styling, and duplicating them in the prompt causes conflicts.
- Structure generation prompts strictly by page anatomy:
  ```markdown
  [Overall purpose and user intent of the page]

  **PLATFORM:** Web, [desktop-first or mobile-first], [how the layout collapses on narrow screens]

  **PAGE STRUCTURE:**
  1. **[First section of the captured page]:** [What it holds on the real page]
  2. **[Next section]:** [Its real content and purpose]
  3. **[...]:** [...]
  N. **[Closing section, e.g. the footer]:** [Its real content]
  ```
- Build the section list from the captured route's own sections, in page order. Do not add sections, controls, or chrome the page does not have.
- When calling `edit_screens` or uploading deterministic HTML via `stitch_upload_file` (`screens:batchCreate`) for single-variable or tiebreaker rounds, explicit hex codes, CSS custom properties, and layout adjustments **are** used so locked variables stay 100% constant.

## 3. `update_design_system` Theme Schema

When calling `update_design_system` directly via `stitch-mcp`:
- Required `theme` fields:
  - `colorMode`: `"LIGHT"` | `"DARK"`
  - `headlineFont`: e.g. `"FRAUNCES"`, `"INSTRUMENT_SERIF"`, `"PLUS_JAKARTA_SANS"`, `"SPACE_GROTESK"`, `"OUTFIT"`, `"DM_SANS"`, `"INTER"`
  - `bodyFont`: same enum options
  - `roundness`: `"ROUND_FOUR"` | `"ROUND_EIGHT"` | `"ROUND_TWELVE"` | `"ROUND_FULL"`
  - `customColor`: `#RRGGBB` seed hex
- Optional overrides: `overridePrimaryColor`, `overrideSecondaryColor`, `overrideTertiaryColor`, `overrideNeutralColor`, `designMd`.
- When calling `apply_design_system`, each item in `selectedScreenInstances` must contain **only** `{ "id": "...", "sourceScreen": "projects/.../screens/..." }` (omit `x`, `y`, `width`, `height`, and filter out `DESIGN_SYSTEM_INSTANCE` items).
