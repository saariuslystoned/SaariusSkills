# EmDash Astro Integration & Token Binding

This reference explains how `emdash-motion-studio` animations mount inside EmDash Astro websites without touching EmDash CMS core or requiring Google Stitch round-trips.

## 1. One-Way Design Intake (`design.md` + `src/styles/tokens.css`)

When adding an animation to an EmDash site (whether built from scratch or styled via `emdash-stitch-design`):

1. **Read `design.md` and `.stitch/DESIGN.md` (if present):**
   - Match the site's locked surface posture (e.g., warm archival paper vs. dark technical vault, hairline borders vs. stamp shadows, monospace telemetry labels vs. editorial display headers).
   - Respect non-goals and `FEATURE_MAP.md` selectors (never cover or replace required e-commerce form controls such as `[data-add-to-cart]` or `[data-guest-cart-root]`).
2. **Read `src/styles/tokens.css`:**
   - Upstream EmDash themes define tokens inside `@layer base` using CSS `light-dark(<light>, <dark>)`.
   - `core.js`, `multiplane.js`, and `choreo.js` automatically inspect `getComputedStyle(targetEl)` on mount and map EmDash tokens into the motion stage:

| EmDash Token (`src/styles/tokens.css`) | Motion Engine Variable / Role | Standalone Fallback |
| --- | --- | --- |
| `--color-canvas` / `--color-surface` | `--paper` (stage background & pill fill) | `#f2efe7` |
| `--color-ink` / `--color-text` | `--ink` & `INK` (stroke ink, leader lines, typography) | `#231e16` |
| `--color-muted` | `--muted` (secondary labels, passed stops, captions) | `#857d6e` |
| `--color-border` / `--color-rule` | `--rule` (hairline dividers, track lines) | `#ddd6c8` |
| `--color-accent` / `--color-primary` | `--accent` & `PALS.site` (active part callouts, progress bar, primary vehicle/body) | `#f4b829` |
| `--color-shadow` | `SHADOW` (cast shadow fill) | `#41538f` |

### Automatic Dark Mode & Preset Switching
Because the generated `.astro` wrapper bridges `--paper: var(--color-canvas, #f2efe7)` and `--ink: var(--color-ink, #231e16)` directly in CSS and observes `data-theme` / `data-preset` attribute mutations on `document.documentElement`, switching between Light/Dark mode or playground presets in the EmDash footer updates the animation palette automatically.

---

## 2. Generating an EmDash Astro Component (`--astro`)

Always author and verify your animation as a standalone `.html` file first so `scripts/verify_motion.py` can test every angle and timeline scrub in headless Chrome. Then compile it to an `.astro` component:

```bash
python3 "<skill-dir>/scripts/build.py" espresso.html src/components/motion/EspressoCutaway.astro --astro --chrome storefront
```

### Generated `.astro` Component Contract

The generated component accepts standard typed props and scopes all DOM and CSS inside `.emdash-motion-stage`:

```astro
---
import EspressoCutaway from "../components/motion/EspressoCutaway.astro";
---

<!-- Storefront mode: interactive 3D stage + action buttons + See-through/Labels pills -->
<EspressoCutaway chrome="storefront" palette="site" class="my-8" />

<!-- Stage-only mode: pure interactive figure for compact cards or columns -->
<EspressoCutaway chrome="stage-only" height="420px" />
```

Supported props on generated `.astro` components:
- `chrome?: 'storefront' | 'stage-only' | 'full'` (defaults to `'storefront'` when built with `--astro`)
- `palette?: 'site' | 'mustard' | 'tomato' | 'mint' | 'cobalt' | 'blush'`
- `height?: string` (optional max-height constraint on the SVG stage)
- `class?: string` (additional wrapper classes)

---

## 3. Wiring into EmDash Composition Primitives

### A. Route Pages (`src/pages/index.astro`, `src/pages/products/[id].astro`)
Mount the `.astro` motion component inside the route template alongside server-rendered CMS content. Keep interactive e-commerce controls (`Add to Cart`, variant pickers) in native HTML outside the SVG canvas.

### B. Portable Text Page Blocks (`defineBlockComponents`)
To let editors place a motion figure inside `pages.layout` blocks (e.g., `home_opener` or a custom `interactive_figure` block) without storing raw scripts in the CMS database:
1. Keep the animation code in `src/components/motion/*.astro` in the repository (the repository owns structure/code; the CMS owns content).
2. Render the motion component inside the block handler registered with `defineBlockComponents`, passing CMS-authored title or initial state props if desired.

### C. Media Library Ownership vs. `public/models/` 3D Code Assets
- **CMS-Editable 2D Posters & Screenshots (`/_emdash/admin` Media Library):** Any 2D fallback poster, hero graphic, or device screenshot that editors should inspect or replace in `/_emdash/admin` must be declared as `"type": "image"` on the collection/block schema, seeded via `{ "$media": { "url": "...", "alt": "..." } }` in `seed/seed.json` (or registered idempotently via `POST /_emdash/api/media` with `deduplicate=true` in the site's import script when anonymous `/_emdash/api/media/file/*` is intentionally gated), and rendered with `<Image />` from `"emdash/ui"` (or static `/brand/*.webp` paired with the registered Media Library entry). Static files dropped only into `public/` without Media Library registration never appear in `/_emdash/admin`.
- **Runtime 3D `.glb` & Vendor Scripts (`public/models/` and `public/vendor/`):** Keep binary glTF 2.0 `.glb` meshes in `public/models/...` and Three.js vendor scripts in `public/vendor/...`. Keep the WebGL stage `[hidden]` until `GLTFLoader.load` finishes mounting the `.glb` (`onModelLoaded`), and clean up the renderer on `onModelError`, so the 2D `.webp` poster (`[data-plugin-cube-fallback]`) serves SSR, `prefers-reduced-motion: reduce`, and progressive loading without flashing an empty box.

---

## 4. Accessibility & Performance Guardrails

- **Reduced Motion (`prefers-reduced-motion: reduce`):**
  - `core.js`, `multiplane.js`, and `choreo.js` automatically pause continuous autoplay loops (turntables, transit loops, orbital rotations) when `matchMedia('(prefers-reduced-motion: reduce)').matches` is true, while keeping explicit user interactions (drag-to-turn, button clicks, stop selection, `See-through` / `Labels` toggles) working.
- **Touch & Mobile (`<= 560px`):**
  - Heavy SVG `feTurbulence` displacement filters automatically step down on coarse pointers (`(pointer: coarse)`) to maintain 60fps touch dragging.
  - Mode A `xrCallouts` automatically collapse into numbered badges (`1`, `2`, `3`…) on `< 560px` viewports with a tappable two-column legend below the stage.
