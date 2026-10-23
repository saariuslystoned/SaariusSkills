# Stitch Taste, `DESIGN.md`, and Prompt Rules

Adapted from `google-labs-code/stitch-skills` (`taste-design`, `design-md`, `generate-design`, `manage-design-system`) for EmDash sites.

## 1. Anti-Slop `DESIGN.md` Rules (`taste-design`)

Encode these rules in `.stitch/DESIGN.md` before generating screens, and hold the implemented source to them:

- **Atmosphere Axes:**
  - **Density:** 1–3 (Gallery Airy) · 4–7 (Balanced Storefront) · 8–10 (Cockpit Dense; use monospace for numbers).
  - **Variance:** 1–3 (Symmetric Grid) · 4–7 (Offset Asymmetric) · 8–10 (Editorial Asymmetric).
- **Color Calibration & Optional Playground Presets:**
  - Maximum 1 primary accent color per palette (saturation < 80%).
  - Ban "AI Purple/Blue Neon" gradients and outer button glows.
  - Never use pure `#000000`; use a warm off-black, charcoal, or deep ink chosen for this site's palette.
  - Give every color a semantic name + hex code + functional role, and map the locked Stitch palette into `@layer base` in `src/styles/tokens.css` using `light-dark(<light>, <dark>)`. (Circumstantially on starter templates, demo playgrounds, or staging sites built to preview multiple colorways for prospects, also retain 2–3 runner-up Stitch palettes as `:root[data-preset="..."]` blocks.)
  - Compute contrast; never estimate it. Measure every foreground/background token pair the build uses (accent on canvas, muted text on each surface, sale and strike text, disabled-but-explained text, chips, control boundaries, and the focus ring against its neighbour) in each appearance mode that ships. Hold each pair to WCAG 2.x AA: 4.5:1 for body text and control labels, 3:1 for large text, UI boundaries and focus rings. Record each ratio in `design.md`. Node runs in every EmDash repo:
    ```bash
    node -e 'const L=h=>{const c=[1,3,5].map(i=>parseInt(h.slice(i,i+2),16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]};const[a,b]=[L(process.argv[1]),L(process.argv[2])].sort((x,y)=>x-y);console.log(((b+.05)/(a+.05)).toFixed(2))' '#FGHEX' '#BGHEX'
    ```
- **Surfaces, Borders, and Shadows Come From This Site's Lock:**
  - Derive surface tones, border weights, corner radii, and shadow style from the palette and atmosphere locked for this site, and grill them with candidates like any other variable.
  - Record locked values (hex codes, sizes, offsets) only in the project's `.stitch/DESIGN.md`, `design.md`, and `src/styles/tokens.css`. This reference holds rules, never another site's locked values: carrying one build's palette or surface system into the next site makes every site look the same.
- **Typography:**
  - Lock the type pairing in its own round: a distinctive display face with a high-legibility body face, plus a monospace face only where the site's content benefits from one (for example SKUs, versions, or tabular figures with `font-variant-numeric: tabular-nums`). Choose faces for this site's atmosphere, not from a fixed shortlist.
  - Name only faces the build can serve. If builds run offline or the font provider cannot reach its source, use locally shipped font files or an explicit system stack, and record what actually renders. Stitch draws its screenshots on its own servers, which may lack the faces a system stack names, so candidates that differ only in system stacks can look identical there. Judge them from the local render ([grilltrack-visual-cycle.md](grilltrack-visual-cycle.md) §2a) or with shipped font files.
  - Scale headlines with `clamp()`; keep body copy 60–70ch max width.
- **Banned AI Tells:**
  - No emojis in UI chrome.
  - No fabricated metrics (`99.98% SLA`, `10k+ customers`) or `LABEL // 2026` filler tags.
  - No invented cart/checkout/buy buttons when the slice contract forbids them.
  - No duplicated theme/preset switchers in both header and footer. Where a switcher lives is a grill decision for this site.
  - No horizontal overflow on narrow mobile viewports (`320px–767px`), and no clipped control text: each control's placeholder and label fit its own container at desktop and narrow widths. A page-level overflow check misses both.
  - No shopper-facing copy the content owners did not supply. Facts come from their owner: EmDash for copy, menus and media; Commerce for price, availability, identifiers and checkout readiness. Generated text (CSS `content:`, prefixes, badges, counts) is copy too. Record a missing label as a gap instead of inventing one.
  - No developer, ownership or run notes on the page, such as which system owns which data. They belong in `design.md`.
  - No label that looks like a control and does nothing. Every header and footer item either works or reads as plain text, with no pill, chip, button or link styling. An unavailable action follows the same rule: it shows its reason and never looks enabled.
  - No dead-end empty states: an empty cart, collection or search result offers the shopper's next step.

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
