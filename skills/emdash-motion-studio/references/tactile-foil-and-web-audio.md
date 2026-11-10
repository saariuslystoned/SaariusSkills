# Mode D: Ephemera Stationery Primitives, Holographic Foil, Tear-Off Pass & Opt-In Web Audio Foley

This reference documents **Mode D** (`assets/tactile-audio.js`) in `emdash-motion-studio`:
1. **Ephemera Stationery Primitives:**
   - **Thermal Receipt (`mountReceipt` & `renderBarcodeSvg`):** `conic-gradient` serrated top/bottom teeth, deterministic 32-bit FNV-1a hash-to-SVG barcode generator (`renderBarcodeSvg(code)`), and `steps(28, end)` thermal line-feed reveal.
   - **Dry-Ink Rubber Stamp (`mountRubberStamp`):** inline SVG `<feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="4">` + `<feDisplacementMap>` dry-ink erosion filter + `cubic-bezier(0.22, 1, 0.36, 1)` stamp thud animation (ideal for `[PAID · STRIPE TEST]`, `[SHIPPED · PB SANDBOX]`, `[PAID · D1]`).
2. **Holographic Foil & Perforated Tear-Off Ticket (`mountFoilTicket`):** 3D tilt-reactive foil sheen, punched perforation seam, deterministic `tearProgress` (`0..1`) stub separation & drop, and `See-through / X-Ray` security thread view (`?xr=1`).
3. **Strictly Opt-In Procedural Web Audio Micro-Foley (`createMicroFoley`):** Zero-file `AudioContext` synthesis (`click`, `stampThud`, `thermalFeed`, `paperTear`) — never forced by default, gated behind an explicit user-toggled `Sound: Off/On` control.

---

## 1. Ephemera Thermal Receipt (`mountReceipt` & `renderBarcodeSvg`)

Use `mountReceipt(target, cfg)` for order confirmations, Pitney Bowes 4×6 label dispatch stubs, and D1 ledger receipts.

### CSS Serrated Teeth Recipe (`conic-gradient`)
Both top and bottom edges use repeating `conic-gradient` teeth bound to `--eph-paper` (`var(--color-surface, var(--color-canvas, #f7f4ec))`):

```css
.ephemera-receipt::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 7px;
  background-size: 12px 7px;
  background-repeat: repeat-x;
  background-image: conic-gradient(
    from 135deg at 50% 100%,
    var(--eph-paper) 0deg 90deg,
    transparent 90deg 360deg
  );
}

.ephemera-receipt::after {
  content: "";
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 7px;
  background-size: 12px 7px;
  background-repeat: repeat-x;
  background-image: conic-gradient(
    from -45deg at 50% 0%,
    var(--eph-paper) 0deg 90deg,
    transparent 90deg 360deg
  );
}
```

### Stepped Thermal Line-Feed Reveal (`steps(28, end)`)
The thermal printer feed steps in discrete stepper-motor increments (`steps(28, end)`) and disables automatically under `prefers-reduced-motion: reduce`:

```css
.ephemera-receipt.is-feeding {
  animation: ephemeraLineFeed 920ms steps(28, end) both;
}

@keyframes ephemeraLineFeed {
  0%   { clip-path: inset(0 0 96% 0); transform: translateY(-14px); }
  100% { clip-path: inset(0 0 0% 0);  transform: translateY(0); }
}
```

### Deterministic FNV-1a Hash-to-SVG Barcode (`renderBarcodeSvg(code)`)
Every order ID or tracking number hashes deterministically via 32-bit FNV-1a (`0x811c9dc5`, prime `0x01000193`) into variable-width SVG `<rect>` bars between start/stop guard bars:

```javascript
const svgMarkup = renderBarcodeSvg('DK-2026-0841-PB', { width: 220, height: 42 });
const receipt = mountReceipt('#order-receipt', {
  title: 'DINKUSKIT STUDIO DISPATCH',
  subtitle: 'ORDER RECEIPT · CLOUDFLARE D1 LEDGER',
  code: 'DK-2026-0841-PB',
  total: '$60.00',
  stampText: '[PAID · D1]',
  stampVariant: 'paid',
});
```

---

## 2. Dry-Ink Rubber Stamp (`mountRubberStamp` & SVG Erosion Filter)

Use `mountRubberStamp(target, cfg)` to stamp status badges (`[PAID · STRIPE TEST]`, `[SHIPPED · PB SANDBOX]`, `[PAID · D1]`) with realistic dry-ink paper fiber erosion and a physical thud curve.

### SVG Filter Recipe (`<feTurbulence>` + `<feDisplacementMap>`)
```xml
<filter id="ephemera-stamp-erosion" x="-8%" y="-8%" width="116%" height="116%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="4" seed="11" result="noise"/>
  <feDisplacementMap in="SourceGraphic" in2="noise" scale="2.4" xChannelSelector="R" yChannelSelector="G" result="eroded"/>
  <feComponentTransfer in="noise" result="inkMask">
    <feFuncA type="table" tableValues="0.55 0.92 1 1"/>
  </feComponentTransfer>
  <feComposite in="eroded" in2="inkMask" operator="in"/>
</filter>
```

### Stamp Thud Keyframe (`cubic-bezier(0.22, 1, 0.36, 1)`)
```css
.ephemera-rubber-stamp.is-thudding {
  animation: ephemeraStampThud 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
```

```javascript
const stamp = mountRubberStamp('#order-stamp', {
  text: '[PAID · STRIPE TEST]',
  variant: 'paid', // 'paid' | 'shipped' | 'accent'
  angle: -7,
});
// Trigger re-stamp on status transition:
stamp.setText('[SHIPPED · PB SANDBOX]', 'shipped');
stamp.thud();
```

---

## 3. Holographic Foil & Perforated Tear-Off Pass (`mountFoilTicket`)

- **3D Tilt & Specular Foil Sheen:** Pointer position drives `--tilt-rx`, `--tilt-ry`, and `--foil-shift` across a multi-stop iridescent gradient (`linear-gradient(calc(115deg + var(--foil-shift)), ...)`).
- **Perforated Seam & Deterministic Tear (`tearProgress` in `0..1`):** `setTearProgress(p)` separates and pivots the stub deterministically from `0.0` (intact) to `1.0` (detached & redeemed).
- **See-Through Security Thread (`?xr=1`):** Reveals embedded security watermarks, copper NFC coils, and verification hashes.

---

## 4. Strictly Opt-In Procedural Web Audio Micro-Foley (`createMicroFoley`)

- **Never enable audio automatically.** Always gate `createMicroFoley()` behind a visible `Sound: Off / On` button toggled by a user gesture.
- Available synthesizers in `assets/tactile-audio.js`:
  - `foley.click(freq, dur)` — mechanical detent click
  - `foley.stampThud()` — low-end rubber stamp thud (`165Hz -> 48Hz` sine sweep)
  - `foley.thermalFeed(dur)` — stepped thermal print head hum
  - `foley.paperTear(dur, centerHz)` — bandpass-filtered white noise burst for ticket/receipt tear
