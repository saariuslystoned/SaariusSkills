# Teknium 16-Family Catalog, `dithercn` Port & EmDash Astro Recipes

This reference maps the **16 surface/motion families** from `webdev.teknium.io` and `dithercn.dev` to EmDash CMS, Astro (`src/components/surface/*.astro`), Portable Text blocks (`defineBlockComponents`), and DinkusKit storefront guardrails.

---

## 1. The 16 Families Mapped to EmDash + Astro + DinkusKit

| # | Family (`webdev.teknium.io` / `dithercn`) | Primary Libraries / Bundled Engines | Tier | EmDash / DinkusKit Storefront Use Case |
| --- | --- | --- | --- | --- |
| 1 | **Ordered & Halftone Dithering** | `assets/dither.js` (`mountDitherShader`, `ditherPatternSvg`, `ditherMaskStyle`, `ditherImageCanvas`), `dithercn` | **Tier 1 / 2** | Hero shader backdrops, Bayer 8×8 section dividers, retro-editorial borders, dithered product thumbnails |
| 2 | **Tactile Paper & Ephemera Stationery** | `assets/ephemera.js` (`mountReceipt`, `renderBarcodeSvg`, `mountRubberStamp`, `mountFoilTicket`) | **Tier 1** | Order confirmation receipts, FNV-1a SVG barcodes, `[PAID · D1]` / `[SHIPPED · PB SANDBOX]` dry-ink stamps, promo tear-off stubs |
| 3 | **Obstacle & Editorial Text Layout** | `assets/surface-micro.js` (`mountObstacleText`), `@chenglou/pretext` | **Tier 1** | Zero-reflow editorial paragraphs wrapping around floating stamps, badges, or dithered product orbs |
| 4 | **Tabular Counters & Split-Flap Tickers** | `assets/surface-micro.js` (`mountNumberTicker`), `number-flow`, `split-flap-elements` | **Tier 1** | Live cart subtotals, stock scarcity counters, D1 order ledger metrics |
| 5 | **Hand-Drawn Ink & Sketch Callouts** | `assets/surface-micro.js` (`mountRoughCallout`), `rough-notation`, `roughjs`, `perfect-freehand` | **Tier 1** | Double-pass ink underlines, circled discount callouts, craftsmanship notes |
| 6 | **Viewport GPU & Canvas Pooling** | `assets/viewport-pool.js` (`createViewportPool`, `defaultViewportPool`) | **Tier 1** | Caps active WebGL/canvas loops at `MAX_LIVE = 6` (desktop) and `MAX_LIVE = 1` (mobile tap-to-run) |
| 7 | **3D Card Tilt & Specular Glare** | `assets/surface-micro.js` (`mountHoverTilt` / `mountTilt`) | **Tier 2** | 25-line CSS-variable pointer tilt (`--rx`, `--ry`, `--glare-x`, `--glare-y`) on featured product cards |
| 8 | **Fragment & Paper Shaders** | `@paper-design/shaders` (`ShaderMount`), `glslCanvas`, `curtainsjs` | **Tier 1** | Pooled background liquid/mesh/grain shaders bound to `tokens.css` colors |
| 9 | **WAAPI & Timeline Micro-Springs** | `motion` (Motion One), `animejs` v4, `@formkit/auto-animate` | **Tier 1** | Cart drawer transitions, filter grid FLIP animations, SVG stroke-dashoffset reveals |
| 10 | **Lightweight 3D Globes & Models** | `cobe`, `@google/model-viewer`, `zdog` | **Tier 1** | 5KB WebGL dispatch-origin globe, interactive `<model-viewer>` product turntables |
| 11 | **SVG Morphing & Path Choreography** | `flubber`, `svg-path-commander`, ` animejs` SVG | **Tier 1** | Icon state morphs (cart → check), vector seal animations |
| 12 | **Generative Noise & Organic Fields** | `simplex-noise`, `p5` (instance mode), SVG `<feTurbulence>` | **Tier 1** | Paper grain overlays, Pigment Drift watercolor washes, dry-ink stamp erosion |
| 13 | **Physics & 2D Rigid Bodies** | `matter-js`, `planck-js` | **Tier 2** | Contained hero/404 badge drop boxes (never over checkout buttons) |
| 14 | **Audio-Reactive & Procedural Foley** | `assets/ephemera.js` (`createMicroFoley`), `tone` | **Tier 1 (Opt-In)** | Strictly user-toggled `AudioContext` detent clicks, stamp thuds, thermal print hums |
| 15 | **Smooth Scroll & Scroll-Hijacking** | `lenis`, `locomotive-scroll` | **Tier 3 (Avoid)** | **Do not use on storefronts.** Use native CSS scroll-driven animations or `IntersectionObserver`. |
| 16 | **Custom Cursor Followers & Trails** | `mouse-follower`, `cursor-effects`, `kursor` | **Tier 3 (Avoid)** | **Do not use on checkout/catalog routes.** Breaks Playwright `dinkuskit-live-test` hit-testing. |

---

## 2. Astro Component Recipes (`src/components/surface/*.astro`)

> **DinkusKit Zero-`\bany\b` Rule:** DinkusKit's `scripts/check-features.mjs` rejects `.astro`, `.mjs`, and `.ts` files under `src/` that contain the word `any` (`/\bany\b/u`), even inside comments or strings. Every recipe below is 100% free of `\bany\b`.

### Recipe A: `DitherHeroBanner.astro` (`dithercn` Port + `tokens.css` Bridge + Viewport Pool)

```astro
---
export interface Props {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  pixelScale?: number;
}

const {
  eyebrow = 'DINKUSKIT STUDIO EDITION',
  title,
  subtitle = 'Ordered Bayer 8x8 WebGL surface bound to src/styles/tokens.css',
  pixelScale = 3,
} = Astro.props;
---

<section class="dither-hero" data-dither-hero data-pixel-scale={pixelScale}>
  <div class="dither-hero-canvas" data-dither-mount aria-hidden="true"></div>
  <div class="dither-hero-content">
    <p class="dither-eyebrow">{eyebrow}</p>
    <h1>{title}</h1>
    {subtitle && <p class="dither-sub">{subtitle}</p>}
    <slot />
  </div>
  <div class="dither-hero-divider" data-dither-mask aria-hidden="true"></div>
</section>

<style>
  .dither-hero {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--color-border, #d8d0c1);
    border-radius: 12px;
    background: var(--color-canvas, #f4f0e8);
    color: var(--color-ink, #1c2430);
    padding: 3.5rem 2rem 4rem;
  }
  .dither-hero-canvas {
    position: absolute;
    inset: 0;
    opacity: 0.28;
    pointer-events: none;
  }
  .dither-hero-content {
    position: relative;
    z-index: 1;
    max-width: 42rem;
  }
  .dither-hero-divider {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 28px;
    background: var(--color-ink, #1c2430);
    opacity: 0.14;
  }
</style>
```

### Recipe B: `OrderEphemeraReceipt.astro` (Serrated Thermal Receipt + FNV-1a Barcode + Rubber Stamp)

Use `mountReceipt`, `renderBarcodeSvg`, and `mountRubberStamp` from `skills/emdash-surface-fx/assets/ephemera.js` on order confirmation views or interactive fulfillment previews:

```astro
---
export interface Props {
  orderCode: string;
  total: string;
  stampText?: string;
  stampVariant?: 'paid' | 'shipped' | 'accent';
}

const {
  orderCode = 'DK-2026-0841-PB',
  total = '$60.00',
  stampText = '[PAID · D1]',
  stampVariant = 'paid',
} = Astro.props;
---

<div
  class="order-receipt-host"
  data-ephemera-receipt
  data-code={orderCode}
  data-total={total}
  data-stamp-text={stampText}
  data-stamp-variant={stampVariant}
></div>
```

### Recipe C: Portable Text `defineBlockComponents` Wiring

Keep executable shader/dither code inside repository-owned `.astro` components (`src/components/surface/*.astro`) and expose clean content props to EmDash CMS editors:

```ts
import { defineBlockComponents } from '@emdash-cms/astro';
import DitherHeroBanner from '../components/surface/DitherHeroBanner.astro';
import OrderEphemeraReceipt from '../components/surface/OrderEphemeraReceipt.astro';

export const surfaceBlocks = defineBlockComponents({
  dither_callout: DitherHeroBanner,
  ephemera_receipt_preview: OrderEphemeraReceipt,
});
```

---

## 3. Storefront Safety & Verification Checklist

1. **Preserve `FEATURE_MAP.md` hooks:** Never obscure `[data-add-to-cart]`, `[data-guest-cart-root]`, or checkout form controls with pointer-capturing overlays (`pointer-events: none` on decorative `<canvas>` and `<svg>` layers).
2. **Pool all GPU canvases:** Register WebGL/2D loop surfaces with `defaultViewportPool.register(el, { start, stop, renderStatic })` so offscreen canvases sleep and mobile devices run at most `MAX_LIVE = 1`.
3. **Honor `prefers-reduced-motion: reduce`:** Render one deterministic static frame (`renderStatic()`) and skip continuous `requestAnimationFrame` loops, thermal feed clips, and stamp thud keyframes when reduced motion is enabled.
4. **Verify zero `/\bany\b/u` matches:** Run `rg '\bany\b' src/` before running DinkusKit's `bin/verify-web`.

---

## 5. Pigment Drift Recipes (Card Hover Pigment Bloom + Hero Watercolor Wash)

### A. Product Card Hover Pigment Bloom (`ProductMedia.astro`)
Layer a zero-JS CSS/SVG radial pigment wash behind product silhouettes so hovering a card blooms the ink and lifts the product off the surface:

```astro
<div class="commerce-product-media" data-pigment-drift-media>
  <span class="product-media__pigment-wash" data-pigment-drift="product-media" aria-hidden="true"></span>
  <img src={resolved.src} alt={resolved.alt} width="640" height="480" loading="lazy" decoding="async" />
</div>

<style>
  .commerce-product-media {
    position: relative;
    isolation: isolate;
    overflow: hidden;
    background: var(--store-surface-subtle);
  }
  .product-media__pigment-wash {
    position: absolute;
    inset: -14%;
    z-index: 0;
    pointer-events: none;
    opacity: 0.36;
    background:
      radial-gradient(circle at 26% 28%, var(--store-accent) 0%, transparent 56%),
      radial-gradient(circle at 76% 74%, var(--store-ink) 0%, transparent 62%);
    filter: blur(18px);
    transform: scale(0.96);
    transition: transform 0.55s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.55s ease;
  }
  .commerce-product-media img {
    position: relative;
    z-index: 1;
    transition: transform 0.48s cubic-bezier(0.22, 1, 0.36, 1);
  }
  :global(.shop-card:hover) .product-media__pigment-wash,
  .commerce-product-media:hover .product-media__pigment-wash {
    opacity: 0.92;
    transform: scale(1.08) rotate(-1.5deg);
  }
  :global(.shop-card:hover) .commerce-product-media img {
    transform: translateY(-2px) scale(1.025);
  }
  @media (prefers-reduced-motion: reduce) {
    .product-media__pigment-wash,
    .commerce-product-media img {
      transition: none;
      transform: none !important;
    }
  }
</style>
```

### B. Token-Bound Hero Watercolor Wash (`HomeOpener.astro`)
```astro
<svg class="home-opener__pigment-wash" viewBox="0 0 1120 420" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs>
    <pattern id="home-opener-riso-grain" width="10" height="10" patternUnits="userSpaceOnUse">
      <circle cx="2" cy="2" r="0.85" fill="var(--store-ink)" fill-opacity="0.065" />
      <circle cx="7" cy="7" r="0.75" fill="var(--store-accent)" fill-opacity="0.065" />
    </pattern>
    <filter id="home-opener-pigment-drift" x="-12%" y="-12%" width="124%" height="124%" color-interpolation-filters="sRGB">
      <feTurbulence type="fractalNoise" baseFrequency="0.012 0.020" numOctaves="3" seed="17" result="pigmentNoise">
        <animate attributeName="baseFrequency" values="0.012 0.020;0.016 0.026;0.012 0.020" dur="10s" repeatCount="indefinite" />
      </feTurbulence>
      <feDisplacementMap in="SourceGraphic" in2="pigmentNoise" scale="16" xChannelSelector="R" yChannelSelector="G" />
    </filter>
  </defs>
  <rect width="1120" height="420" fill="var(--store-bg)" fill-opacity="0.45" />
  <rect width="1120" height="420" fill="var(--store-surface-subtle)" fill-opacity="0.52" />
  <g filter="url(#home-opener-pigment-drift)">
    <ellipse cx="860" cy="145" rx="285" ry="165" fill="var(--store-accent)" fill-opacity="0.18" />
    <ellipse cx="695" cy="240" rx="260" ry="150" fill="var(--store-ink)" fill-opacity="0.095" />
    <ellipse cx="260" cy="110" rx="240" ry="120" fill="var(--store-surface)" fill-opacity="0.72" />
  </g>
  <rect width="1120" height="420" fill="url(#home-opener-riso-grain)" />
</svg>
```

