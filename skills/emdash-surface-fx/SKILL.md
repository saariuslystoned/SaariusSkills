---
name: emdash-surface-fx
description: Add page-level JavaScript surface effects, Bayer/halftone shaders (dithercn port), SVG dither patterns/masks, viewport GPU pooling, obstacle-aware text layout (@chenglou/pretext), Ephemera receipts/rubber stamps, NumberFlow counters, RoughNotation ink callouts, and tactile UI micro-interactions to EmDash CMS, Astro, and DinkusKit storefronts. Enforces Tier 1/2/3 storefront guardrails and DinkusKit's zero-\bany\b rule.
---

# EmDash Surface FX (`emdash-surface-fx`)

Equip EmDash CMS, Astro, and DinkusKit storefronts with page-level shaders, ordered Bayer dithering, dynamic obstacle typography, tactile stationery receipts/stamps, and micro-interactions — without breaking SSR hydration, `src/styles/tokens.css` (`light-dark()`), or Playwright live checkout journeys (`dinkuskit-live-test`).

---

## 1. Skill Boundary: `emdash-surface-fx` vs `emdash-motion-studio`

| Dimension | `emdash-surface-fx` (This Skill) | `emdash-motion-studio` (Companion Skill) |
| --- | --- | --- |
| **Primary Scope** | **Page-level surface craft & UI micro-interactions:** hero shader backgrounds, SVG dither borders/patterns, CSS dither section dividers, 3D hover-tilt product cards, obstacle-wrapped editorial copy, rolling price/order counters, thermal receipts, dry-ink rubber stamps, hand-sketched SVG callouts. | **Bespoke multi-part stage animations:** Mode A 3D isometric hardware/packaging cutaways (`core.js`), Mode B 3-layer multiplane shadowbox stages + Pigment Drift (`multiplane.js`), Mode C choreographed timeline stages (`choreo.js`), and Mode D standalone foil/tear-off stages. |
| **DOM Footprint** | Enhances native Astro HTML/CSS cards, headers, dividers, and CMS Portable Text blocks (`defineBlockComponents`) in-place. | Mounts a dedicated `<div class="emdash-motion-stage">` with a full orthographic/multiplane `<svg id="fig">` viewport. |
| **Workflow** | Drop-in Astro components or bundled zero-dependency vanilla helpers (`assets/dither.js`, `assets/viewport-pool.js`, `assets/surface-micro.js`, `assets/ephemera.js`). | Progressive GrillTrack Round 0 (5 start-to-finish stage frameworks) → Rounds 1..N (piece-by-piece cumulative canvas loop). |

---

## 1B. High-Leverage Website Placement Guide (Strong Defaults + Open Experimentation)

> **Proven Starting Points, Not Rigid Limits:** The placements below map each `emdash-surface-fx` effect and companion `emdash-motion-studio` mode to concrete, high-value surfaces across **E-Commerce, SaaS, Docs, Editorial, and Portfolio** websites. Treat these as battle-tested defaults—**users and agents are free to experiment, remix, and apply them anywhere on a site**.

| Surface Effect / Companion Mode | Locked DinkusKit / EmDash & Cross-Site Placements | E-Commerce, SaaS, Docs, Editorial & Portfolio Examples |
| --- | --- | --- |
| **`dithercn` (Bayer/Blue-Noise Shaders, SVG Patterns, CSS Masks)** | **Hero/section backgrounds**, **retro-editorial image hover treatments**, **dithered section dividers** bound to `tokens.css` `light-dark()`. | **E-Commerce / Editorial:** Halftone product feature backdrops and SVG dithered rule borders.<br>**SaaS / Docs / Portfolios:** Subtle 1-bit Bayer hero wash or section transition masks. |
| **`NumberFlow` / Tabular Ticker (`mountNumberTicker`)** | **Cart drawer subtotals**, **item quantity badges**, **pricing plan toggles (monthly/annual)**, **live dashboard metrics**. | **E-Commerce:** Rolling cart total and live stock counters.<br>**SaaS:** Monthly/annual billing toggle and telemetry KPI cards.<br>**Portfolios:** Live project/commit counters. |
| **`RoughNotation` (Hand-Drawn SVG Callouts / `mountRoughCallout`)** | **Circling *"Free Shipping"***, **underlining sale prices** or **key docs takeaways** when scrolled into view. | **E-Commerce:** Hand-drawn ink circle on promo badges or bundle savings.<br>**Docs / Editorial:** Margin callouts and highlighted thesis sentences.<br>**SaaS:** Pricing tier "Most Popular" annotation. |
| **`@chenglou/pretext` (Obstacle Text Wrap / `mountObstacleText`)** | **Editorial lookbooks / magazine-style story pages** or auto-floating illustrations (**not needed on standard e-commerce product/checkout pages**, where `dithercn`, `NumberFlow`, `mountHoverTilt`, `RoughNotation`, and `Ephemera` receipts carry the real storefront value). | **Editorial Lookbooks / Magazines:** Long-form artisan story copy flowing around an auto-floating or draggable illustration/vessel.<br>**Portfolios:** Bio/manifesto text wrapping around an interactive badge. |
| **Vanilla 3D Card Tilt (`mountHoverTilt`)** | **Featured product cards**, **bento grid cells**, **badge cards**. | **E-Commerce:** Limited-edition drop cards.<br>**SaaS / Docs:** Feature bento tiles.<br>**Portfolios:** Case-study preview cards with specular glare. |
| **Mode A (3D Object / Cutaway Stage — `emdash-motion-studio`)** | **Marketing Homepage Hero** (*"How the platform works"* in 1 click, e.g., **1-Click MacBook Order-to-Box**), **Flagship Hardware/Product Breakdown**, **Interactive Feature Spotlight**. | **E-Commerce / SaaS:** 1-click homepage hero stage (`chrome: 'stage-only'`) that opens and transitions into an automatic `See-through` internal mechanism cutaway. |
| **Mode B (Multiplane Depth + Pigment Drift — `emdash-motion-studio`)** | **Live Order Tracking / Shipping Status Header** (`/orders/[id]`, `/checkout/success` with delivery van crossing behind bridge trusses under a time-of-day sky), **Brand Story / Chapter Divider**, **Weather/Location Banner**. | **E-Commerce:** Post-purchase delivery tracker header.<br>**Editorial / Portfolios:** Layered architectural/horizon section divider with watercolor pigment drift. |
| **Mode C (Scroll / Step Choreographed Data Flow — `emdash-motion-studio`)** | **Landing Page "Under the Hood" Architecture Section**, **Merchant Onboarding Journeys** (step-by-step visual pipeline as you configure `Stripe -> D1 -> Shipping`), **Interactive Documentation Diagrams**. | **SaaS / Docs / E-Commerce:** Step-by-step or scroll-linked architecture pipeline diagram. |
| **Mode D (Opt-In Tactile Paper, Foil, Tear-Off & Thermal Receipt)** | • **Perforated Foil Tear-Off Stub:** Storefront Promo Banner / Drop Card where tearing the perforation **purely reveals the coupon code + copies it to clipboard** (zero backend coupon engine required by default, optional callback hook if wired later).<br>• **Serrated Thermal Receipt + Dry-Ink Rubber Stamp:** `/checkout/success` Order Confirmation Receipt (`conic-gradient` serrated edges, FNV-1a SVG barcode, `steps()` thermal feed, `[PAID]` rubber stamp thud). | **E-Commerce:** Storefront promo drop card (clipboard copy on tear) and `/checkout/success` thermal receipt with `[PAID]` stamp.<br>**SaaS / Portfolios:** Event ticket or verification pass. |

---

## 2. Tiered Catalog & EmDash / Astro / DinkusKit Fit

Read [references/teknium-catalog-and-astro-recipes.md](references/teknium-catalog-and-astro-recipes.md) for concrete Astro component templates and `defineBlockComponents` wiring across all 16 families from `webdev.teknium.io` and `dithercn.dev`.

### Tier 1 — Drop-In EmDash / Astro / DinkusKit Fit (Zero React Wrapper Needed)

1. **`dithercn` (`DitherPattern`, `ditherMaskStyle`, Bayer 4×4 / 8×8 Shaders & 2D Canvas):**
   - Bundled zero-dependency vanilla engine in `assets/dither.js`: `mountDitherShader`, `ditherPatternSvg`, `ditherMaskStyle`, and `ditherImageCanvas`.
   - Automatically resolves EmDash `src/styles/tokens.css` (`--color-canvas`, `--color-surface`, `--color-ink`, `--color-accent`) including CSS `light-dark()` values and observes `:root[data-theme]` / `:root[data-preset]` via `MutationObserver`.
2. **`Ephemera` Tactile Stationery (`receipt`, `rubber-stamp`, `ticket`):**
   - Bundled standalone in `skills/emdash-surface-fx/assets/ephemera.js` (`assets/ephemera.js`):
     - `mountReceipt(target, cfg)` + `renderBarcodeSvg(code)`: `conic-gradient` serrated top/bottom teeth, deterministic 32-bit FNV-1a hash-to-SVG barcode, and `steps(28, end)` thermal line-feed reveal.
     - `mountRubberStamp(target, cfg)`: inline SVG `<feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="4">` + `<feDisplacementMap>` dry-ink erosion filter + `cubic-bezier(0.22, 1, 0.36, 1)` stamp thud animation (ideal for `[PAID · D1]`, `[PAID · STRIPE TEST]`, `[SHIPPED · PB SANDBOX]`).
     - `mountFoilTicket(target, cfg)`: 3D tilt-reactive holographic foil sheen + perforated tear-off stub (`tearProgress` `0..1`).
3. **`@chenglou/pretext` (Zero-DOM Obstacle Text Layout):**
   - Bundled vanilla canvas-measured line packer in `assets/surface-micro.js` (`mountObstacleText`) + upstream `@chenglou/pretext` (`prepare`, `layoutNextLine`) recipe for flowing editorial copy around floating stamps, badges, or dither orbs at 60fps with zero DOM reflow thrashing.
   - **Placement Guidance:** Best reserved for **editorial lookbooks / magazine-style story pages** (or auto-floating illustrations); **not needed on standard e-commerce product/checkout pages** where `dithercn`, `NumberFlow`, `mountHoverTilt`, `RoughNotation`, and `Ephemera` receipts carry the real storefront value.
4. **`number-flow` & `split-flap-elements` (Tabular Counters & Split-Flap Displays):**
   - Native Web Components (`<number-flow>`, `<split-flap-board>`) or the bundled zero-dependency `mountNumberTicker(target, opts)` in `assets/surface-micro.js` (`font-variant-numeric: tabular-nums`) for live cart subtotals, inventory stock badges, and order telemetry.
5. **`@paper-design/shaders` (`ShaderMount`):**
   - Vanilla `new ShaderMount(canvas, fragmentShader, uniforms)` paired with `assets/viewport-pool.js` (`createViewportPool`) so offscreen shaders pause automatically.
6. **`rough-notation` / `roughjs` / `perfect-freehand` (Hand-Drawn Ink Callouts):**
   - Bundled zero-dependency two-path SVG callout helper `mountRoughCallout(target, { type: 'underline' | 'box' | 'circle' | 'highlight' })` in `assets/surface-micro.js` (measuring real path length via `getTotalLength()` to animate Pass 1 over `780ms` and Pass 2 over `720ms` after a `560ms` delay), or upstream `rough-notation` for editorial highlights and promo callouts.
7. **`motion` (Motion One) / `animejs` v4 / `@formkit/auto-animate`:**
   - WAAPI-backed micro-springs, SVG line-drawing (`stroke-dashoffset`), and one-line cart/filter list transitions (`autoAnimate(listEl)`).
8. **`cobe` & `@google/model-viewer`:**
   - 5KB WebGL shipping-origin globe (`createGlobe(canvas, opts)`) and declarative `<model-viewer>` 3D product inspection stages.

---

### Tier 2 — Adapter Included (Ported from React-First Upstream Libraries)

1. **Vanilla `<canvas>` / WebGL1 Port of `dithercn` (`assets/dither.js`):**
   - Upstream `dithercn` targets React/Next.js + Tailwind v4 (`@use-gpu` / React hooks) and cannot parse raw CSS `light-dark()` strings inside WebGL uniform uploads.
   - `assets/dither.js` provides a zero-React vanilla WebGL1 + 2D Canvas + SVG port that resolves `getComputedStyle(el)` tokens (`--color-canvas`, `--color-surface`, `--color-ink`, `--color-accent`), evaluates `light-dark(a, b)` against `:root[data-theme]`, and updates live via `MutationObserver`.
2. **25-Line Vanilla CSS-Variable 3D Card Tilt (`mountHoverTilt` / `mountTilt` in `assets/surface-micro.js`):**
   - Replaces React `atropos` / `vanilla-tilt` overhead with a 25-line pointer listener that writes `--rx`, `--ry`, `--glare-x`, and `--glare-y` CSS custom properties directly onto `.surface-tilt-card` elements while respecting `prefers-reduced-motion: reduce`.

---

### Tier 3 — Storefront Guardrails (Do Not Use on Checkout / Catalog Routes)

1. **No Scroll Hijackers (`lenis`, `locomotive-scroll`):**
   - Never install smooth-scroll hijackers on DinkusKit or EmDash storefronts. Native CSS `scroll-behavior: smooth` and scroll-driven animations preserve browser find-in-page, keyboard navigation, and Playwright `scrollIntoViewIfNeeded()`.
2. **No Cursor Hijackers (`mouse-follower`, `cursor-effects`) on Storefront / Checkout Routes:**
   - Custom DOM cursor followers intercept pointer hit-testing and break automated Playwright checkout journeys (`dinkuskit-live-test` Stripe & cart clicks). Keep pointer effects scoped to card-local CSS variables (`--glare-x`, `--glare-y`).
3. **No Un-Pooled WebGL Canvases (`assets/viewport-pool.js`):**
   - Browsers cap active WebGL contexts (typically 8–16) and throttle mobile GPUs. Always register WebGL/canvas surfaces with `defaultViewportPool` (`createViewportPool({ maxDesktop: 6, maxMobile: 1 })` in `assets/viewport-pool.js`), which pauses offscreen canvases via `IntersectionObserver` and enforces `MAX_LIVE = 6` on desktop and `MAX_LIVE = 1` (with tap-to-run) on `(pointer: coarse)` mobile devices.
4. **Strict Compliance with DinkusKit's Zero `\bany\b` Rule (`scripts/check-features.mjs`):**
   - DinkusKit's `scripts/check-features.mjs` (invoked by `bin/verify-web`) scans every `.astro`, `.mjs`, and `.ts` file under `src/` and **fails the build if the standalone word `any` (`/\bany\b/u`) appears anywhere** — including inside JS/HTML comments or UI strings.
   - All bundled assets (`assets/dither.js`, `assets/viewport-pool.js`, `assets/surface-micro.js`, and `assets/ephemera.js`) maintain **zero matches of `/\bany\b/u`**.
5. **Map Editable 2D Images & Posters into `/_emdash/admin` Media Library (`type: "image"` + `$media`):**
   - Never leave editable hero images, product photos, or 2D fallback posters stranded only in `public/` where editors cannot see or replace them in `/_emdash/admin`. Declare editable imagery as `"type": "image"` on collections/blocks, seed them via `$media` in `seed/seed.json` (served through `/_emdash/api/media/file/<key>`), and keep `public/` reserved for runtime code assets (such as 3D `.glb` meshes in `public/models/` or shader vendor scripts).

---

## 3. Bundled Zero-Dependency Assets & Showcase Verification

| File | Exports / Role |
| --- | --- |
| `assets/dither.js` | `mountDitherShader`, `ditherPatternSvg`, `ditherMaskStyle`, `ditherImageCanvas`, `resolveEmDashDitherColors`, `BAYER_4X4`, `BAYER_8X8` |
| `assets/viewport-pool.js` | `createViewportPool`, `defaultViewportPool` (`MAX_LIVE = 6` desktop, `MAX_LIVE = 1` mobile tap-to-run) |
| `assets/surface-micro.js` | `mountHoverTilt` (`mountTilt`), `mountObstacleText`, `mountNumberTicker`, `mountRoughCallout` |
| `assets/ephemera.js` | `mountReceipt`, `renderBarcodeSvg`, `mountRubberStamp`, `mountFoilTicket`, `createMicroFoley`, `fnv1aHash` |
| `assets/examples/dinkuskit-surface-fx-showcase.html` | Interactive EmDash storefront showcase combining Bayer 8×8 WebGL dither hero, SVG dither patterns & CSS dither mask divider, thermal order receipt with FNV-1a barcode + `[PAID · D1]` rubber stamp, obstacle-wrapped editorial copy, and live cart/order ticker |

### Verify Showcase or Custom Surface FX Page in Headless Chrome
```bash
python3 skills/emdash-motion-studio/scripts/verify_motion.py \
  skills/emdash-surface-fx/assets/examples/dinkuskit-surface-fx-showcase.html \
  --out-dir .grilltrack/proof/motion
```
