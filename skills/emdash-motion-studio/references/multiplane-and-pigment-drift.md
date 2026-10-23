# Mode B & Mode C: Multiplane Occlusion, Pigment Drift, and Choreographed Stages

This reference details the engineering patterns behind **Mode B** (`assets/multiplane.js` — David East's Multiplane Occlusion, Artwork-Led UI, and Soft Current Pigment Drift) and **Mode C** (`assets/choreo.js` — DeepMind Argon Choreographed Timeline Stages).

---

## 1. Mode B: 3-Layer Multiplane Occlusion (`assets/multiplane.js`)

Traditional web animations float flat icons on top of a background image. **Multiplane Occlusion** creates genuine depth by splitting the scene into three registered planes inside a shadowbox stage:

```text
[ Plane 0: Background Stage ]  <-- Distant skyline, sky/water wash, Pigment Drift filter, rear viaducts
[ Plane 1: Midground Actors ]  <-- Moving trains, ferries, delivery vehicles, signal pulses (driven by t = 0..1)
[ Plane 2: Foreground Masks ]  <-- Bridge towers, truss cages, highway overpasses, glass conservatory arches
[ Plane 3: Artwork-Led HUD  ]  <-- Minimal top-left stop title, top-right countdown, bottom route timeline bar
```

### Why Three Planes Work
When a midground train or ferry moves across `x(t)`, it passes *in front of* the distant skyline on Plane 0 and *behind* the suspension bridge cables, truss spans, and glass conservatory arches on Plane 2. Because Plane 2 is drawn over Plane 1 in the same SVG coordinate system (`viewBox="0 0 1200 680"`), occlusion is mathematically exact at every resolution with zero mask seams.

### Calling `mountMultiplane(cfg)`

```javascript
const ui = mountMultiplane({
  title: 'Harbor Line Transit Stage',
  eyebrow: 'NEXT STOP',
  viewBox: [1200, 680],
  duration: 14,          // seconds for a full 0..1 loop
  chrome: 'full',        // 'full' | 'storefront' | 'stage-only'
  timelapse: false,      // optional true or { opacity: 0.78 } for dawn->midday->dusk->night sky lighting
  pigment: {             // optional Pigment Drift background wash
    enabled: true,
    position: 'bottom',  // 'bottom' | 'full' | 'sky'
    colors: ['#3b1d7a', '#1e4db7', '#6a8fd8', '#e8c5b0']
  },
  plates: {              // optional hybrid raster/vector plates per plane (<image> + clipPath/maskSvg)
    // background: { href: '/assets/skyline-bg.webp', opacity: 0.9 },
    // midground:  { href: '/assets/ferry-mid.png' },
    // foreground: { href: '/assets/bridge-fg.png', clipPath: 'M0,0 ... Z' }
  },
  stops: [
    { id: 'harbor',       label: 'Harbor Bridge',   at: 0.08, etaMin: 6 },
    { id: 'midtown',      label: 'Midtown Towers',  at: 0.36, etaMin: 4 },
    { id: 'cantilever',   label: 'Cantilever Hall', at: 0.64, etaMin: 2, skip: true },
    { id: 'conservatory', label: 'Conservatory',    at: 0.90, etaMin: 0 },
  ],
  background(st, t, ctx) {
    // Return SVG string for Plane 0 (skyline, distant bridges, water lines; ctx.sky has timelapse(t) colors)
  },
  midground(st, t, ctx) {
    // Return SVG string for Plane 1 (moving vehicles positioned by t in 0..1)
  },
  foreground(st, t, ctx) {
    // Return SVG string for Plane 2 (foreground bridge towers, truss spans, arches that occlude Plane 1)
  }
});
```

### Artwork-Led UI Principles
1. **The moving artwork IS the progress indicator:** Sync the horizontal position `x(t)` of the primary midground vehicle directly with the bottom timeline stop markers (`stop.at`).
2. **Restrained editorial HUD:**
   - Top-left: small uppercase eyebrow (`NEXT STOP`) + crisp title of the upcoming stop (`Midtown Towers`).
   - Top-right: large tabular numeral (`1` / `MIN`) counting down as `t` approaches the next stop.
   - Bottom: single horizontal hairline track with stop ticks (`PASSED`, `1 MIN`, `SKIP`, `5 MIN`) and an accent progress bar that tracks `t`. Clicking any stop smoothly scrubs the vehicle to that stop's `at` coordinate.
3. **3D Exploded Shadowbox Toggle (`?explode=1` / `Layers` button):**
   - Toggling `Layers` (or passing `?explode=1` in the URL) rotates the stage in 3D CSS perspective (`rotateX(10deg) rotateY(-22deg)`) and separates Plane 0 (`translateZ(-90px)`), Plane 1 (`translateZ(0px)`), and Plane 2 (`translateZ(90px)`) on translucent archival cards so viewers and reviewers can verify that each layer is a true independent plane.

---

## 2. Pigment Drift Technique (`renderPigmentDrift`)

Inspired by David East's *Soft Current* watercolor/ink-bleed study: warm archival paper (`#fcf6e9` / `--color-canvas`) meets a living, granulated watercolor pigment wash that slowly drifts along paper fibers without distracting from editorial typography.

### How Pigment Drift Works in SVG
1. **Dual-Octave Paper & Flow Turbulence (`<filter id="mp-pigment">`):**
   - Coarse `feTurbulence` (`baseFrequency="0.012 0.018"`, `numOctaves="3"`) displaces layered organic ellipses/paths (`feDisplacementMap scale="48"`) to create feathered watercolor blooms.
   - Fine `feTurbulence` (`baseFrequency="0.65"`, `numOctaves="3"`) multiplies subtle pigment granulation into the wash so it reads as real ink on cotton rag paper rather than a CSS blur.
2. **Sinuous Negative-Space River / Channel:**
   - A bright paper-toned S-curve ribbon cuts through the pigment plumes, giving the eye a calm focal path across the wash.
3. **Slow Phase Drift:**
   - The plumes shift gently as a pure periodic function of `Math.sin(t * Math.PI * 2)` (`±14px`), ensuring seamless loop closure at `t = 0` and `t = 1` and deterministic rendering at any `?t=` scrub point.

---

## 3. Mode C: Choreographed Timeline / Scroll Stage (`assets/choreo.js`)

Use `mountChoreo(cfg)` when an animation follows a multi-chapter technical narrative (e.g., orbital mechanics, packet routing, multi-stage manufacturing, or kinetic data telemetry):

```javascript
const ui = mountChoreo({
  title: 'Argon Orbital Telemetry Stage',
  subtitle: 'PHASE-LOCKED SATELLITE CONSTELLATION',
  viewBox: [1100, 640],
  duration: 12,
  mode: 'autoplay', // 'autoplay' | 'scroll' | 'scrub'
  cues: [
    { id: 'inject',   label: '01 · Transfer Injection', range: [0.00, 0.25] },
    { id: 'phasing',  label: '02 · Plane Phasing',      range: [0.25, 0.55] },
    { id: 'crosslink',label: '03 · Optical Crosslink',  range: [0.55, 0.80] },
    { id: 'zenith',   label: '04 · Zenith Lock',        range: [0.80, 1.00] },
  ],
  hud(st, t, cue) {
    return [
      { label: 'INCLINATION', value: (53.0 + 4.2 * Math.sin(t * Math.PI)).toFixed(1), unit: 'DEG' },
      { label: 'CROSSLINK',   value: t >= 0.55 ? 'LOCKED' : 'ACQUIRING', unit: 'LASER' },
      { label: 'ALTITUDE',    value: Math.round(340 + 210 * easeInOutCubic(t)), unit: 'KM' },
    ];
  },
  scene(st, t, helpers) {
    // Pure function of (st, t): use helpers.project3D(x,y,z,cam), helpers.subRange(t, a, b), etc.
  }
});
```

### Deterministic Verification Contract for Modes B & C
Both `multiplane.js` and `choreo.js` expose:
- `?t=0..1` URL parameter: pauses autoplay and locks the scene at exact normalized time `t`.
- `window.__setMotionTime(t)`: programmatic scrubber used by `scripts/verify_motion.py`.
- `window.__st`: live state object inspected by DOM tests.
- `<html data-errors="...">`: automatic runtime error trap checked by `scripts/verify_motion.py`.
