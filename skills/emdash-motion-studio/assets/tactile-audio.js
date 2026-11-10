/*
 * emdash-motion-studio / assets/tactile-audio.js
 * Opt-In Mode D: Ephemera Stationery Primitives (Thermal Receipt, Dry-Ink Rubber Stamp,
 * Holographic Foil & Perforated Tear-Off Ticket) + Strictly Opt-In Procedural Web Audio Micro-Foley.
 *
 * Zero external runtime dependencies. Binds automatically to EmDash src/styles/tokens.css
 * (--color-canvas, --color-surface, --color-ink, --color-muted, --color-border, --color-accent).
 */

const EPHEMERA_STYLE_ID = 'emdash-ephemera-styles';
const EPHEMERA_FILTER_ID = 'ephemera-stamp-erosion';

const EPHEMERA_CSS = `
.ephemera-stage {
  --eph-paper: var(--color-surface, var(--color-canvas, #f7f4ec));
  --eph-canvas: var(--color-canvas, #f2efe7);
  --eph-ink: var(--color-ink, var(--color-text, #231e16));
  --eph-muted: var(--color-muted, #766e60);
  --eph-rule: var(--color-border, var(--color-rule, #d8d0c1));
  --eph-accent: var(--color-accent, var(--color-primary, #c84b31));
  --eph-paid: #1f6f4a;
  --eph-shipped: #1d4e89;
  color: var(--eph-ink);
  font-family: ui-monospace, 'SFMono-Regular', Menlo, Monaco, Consolas, monospace;
}

/* 1. Thermal Receipt with conic-gradient serrated top/bottom teeth & steps(28, end) feed */
.ephemera-receipt-Slot {
  position: relative;
  display: inline-block;
  width: 100%;
  max-width: 340px;
  filter: drop-shadow(0 10px 24px rgba(24, 20, 14, 0.14));
}

.ephemera-receipt {
  position: relative;
  background: var(--eph-paper);
  color: var(--eph-ink);
  padding: 20px 20px 18px;
  font: 500 12px/1.45 ui-monospace, 'SFMono-Regular', Menlo, Monaco, Consolas, monospace;
  letter-spacing: 0.02em;
  border-left: 1px solid var(--eph-rule);
  border-right: 1px solid var(--eph-rule);
  overflow: hidden;
  transform-origin: top center;
}

.ephemera-receipt.is-feeding {
  animation: ephemeraLineFeed 920ms steps(28, end) both;
}

@keyframes ephemeraLineFeed {
  0% {
    clip-path: inset(0 0 96% 0);
    transform: translateY(-14px);
  }
  100% {
    clip-path: inset(0 0 0% 0);
    transform: translateY(0);
  }
}

.ephemera-receipt::before,
.ephemera-receipt::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  height: 7px;
  background-size: 12px 7px;
  background-repeat: repeat-x;
  pointer-events: none;
}

.ephemera-receipt::before {
  top: 0;
  background-image: conic-gradient(
    from 135deg at 50% 100%,
    var(--eph-paper) 0deg 90deg,
    transparent 90deg 360deg
  );
}

.ephemera-receipt::after {
  bottom: 0;
  background-image: conic-gradient(
    from -45deg at 50% 0%,
    var(--eph-paper) 0deg 90deg,
    transparent 90deg 360deg
  );
}

.ephemera-receipt-hdr {
  text-align: center;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px dashed var(--eph-rule);
}

.ephemera-receipt-title {
  font-weight: 800;
  font-size: 13px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.ephemera-receipt-sub {
  font-size: 10.5px;
  color: var(--eph-muted);
  margin-top: 2px;
}

.ephemera-receipt-rows {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px dashed var(--eph-rule);
  font-variant-numeric: tabular-nums;
}

.ephemera-receipt-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}

.ephemera-receipt-row.is-total {
  font-weight: 800;
  font-size: 13px;
  padding-top: 6px;
  margin-top: 4px;
  border-top: 1.5px solid var(--eph-ink);
}

.ephemera-receipt-barcode {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin-top: 10px;
  padding-top: 6px;
}

.ephemera-receipt-barcode svg {
  width: 100%;
  max-width: 240px;
  height: 44px;
  display: block;
}

.ephemera-receipt-code {
  font-size: 10px;
  letter-spacing: 0.16em;
  color: var(--eph-muted);
  text-transform: uppercase;
}

/* 2. Dry-Ink Rubber Stamp with SVG feTurbulence + feDisplacementMap erosion & thud */
.ephemera-rubber-stamp {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 5px 12px;
  border: 2.5px solid var(--stamp-color, var(--eph-accent));
  outline: 1px solid var(--stamp-color, var(--eph-accent));
  outline-offset: -5px;
  border-radius: 4px;
  color: var(--stamp-color, var(--eph-accent));
  font: 800 12px/1.1 ui-monospace, 'SFMono-Regular', Menlo, Monaco, Consolas, monospace;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  white-space: nowrap;
  user-select: none;
  transform: rotate(var(--stamp-angle, -7deg));
  filter: url(#ephemera-stamp-erosion);
  opacity: 0.92;
  mix-blend-mode: multiply;
}

:root[data-theme="dark"] .ephemera-rubber-stamp,
.dark .ephemera-rubber-stamp {
  mix-blend-mode: normal;
}

.ephemera-rubber-stamp[data-variant="paid"] {
  --stamp-color: var(--eph-paid, #1f6f4a);
}

.ephemera-rubber-stamp[data-variant="shipped"] {
  --stamp-color: var(--eph-shipped, #1d4e89);
}

.ephemera-rubber-stamp[data-variant="accent"] {
  --stamp-color: var(--eph-accent, #c84b31);
}

.ephemera-rubber-stamp.is-thudding {
  animation: ephemeraStampThud 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes ephemeraStampThud {
  0% {
    opacity: 0;
    transform: rotate(calc(var(--stamp-angle, -7deg) - 6deg)) scale(1.85);
  }
  55% {
    opacity: 0.96;
    transform: rotate(var(--stamp-angle, -7deg)) scale(0.95);
  }
  100% {
    opacity: 0.92;
    transform: rotate(var(--stamp-angle, -7deg)) scale(1);
  }
}

/* 3. Mode D Holographic Foil & Perforated Tear-Off Ticket */
.ephemera-ticket {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto;
  background: var(--eph-paper);
  color: var(--eph-ink);
  border: 1.5px solid var(--eph-ink);
  border-radius: 10px;
  overflow: hidden;
  transform-style: preserve-3d;
  transform: perspective(800px) rotateX(var(--tilt-rx, 0deg)) rotateY(var(--tilt-ry, 0deg));
  transition: transform 140ms ease-out;
}

.ephemera-ticket-foil {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(
    calc(115deg + var(--foil-shift, 0deg)),
    transparent 20%,
    rgba(255, 225, 130, 0.28) 38%,
    rgba(120, 220, 255, 0.26) 48%,
    rgba(255, 150, 210, 0.24) 56%,
    transparent 74%
  );
  mix-blend-mode: overlay;
}

.ephemera-ticket-body {
  padding: 14px 16px;
}

.ephemera-ticket-stub {
  position: relative;
  padding: 14px 16px;
  border-left: 2px dashed var(--eph-rule);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  transform-origin: bottom left;
}

@media (prefers-reduced-motion: reduce) {
  .ephemera-receipt.is-feeding,
  .ephemera-rubber-stamp.is-thudding {
    animation: none !important;
    clip-path: none !important;
  }
}
`;

function injectEphemeraStyles(doc) {
  const d = doc || (typeof document !== 'undefined' ? document : null);
  if (!d || d.getElementById(EPHEMERA_STYLE_ID)) return;
  const style = d.createElement('style');
  style.id = EPHEMERA_STYLE_ID;
  style.textContent = EPHEMERA_CSS;
  (d.head || d.documentElement).appendChild(style);
}

function ensureStampFilterSvg(rootEl) {
  const d = (rootEl && rootEl.ownerDocument) || (typeof document !== 'undefined' ? document : null);
  if (!d) return;
  injectEphemeraStyles(d);
  if (d.getElementById(EPHEMERA_FILTER_ID)) return;
  const holder = d.createElement('div');
  holder.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;pointer-events:none';
  holder.setAttribute('aria-hidden', 'true');
  holder.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" aria-hidden="true">
    <defs>
      <filter id="${EPHEMERA_FILTER_ID}" x="-8%" y="-8%" width="116%" height="116%" color-interpolation-filters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="4" seed="11" result="noise"/>
        <feDisplacementMap in="SourceGraphic" in2="noise" scale="2.4" xChannelSelector="R" yChannelSelector="G" result="eroded"/>
        <feComponentTransfer in="noise" result="inkMask">
          <feFuncA type="table" tableValues="0.55 0.92 1 1"/>
        </feComponentTransfer>
        <feComposite in="eroded" in2="inkMask" operator="in"/>
      </filter>
    </defs>
  </svg>`;
  (d.body || d.documentElement).appendChild(holder);
}

/* Deterministic 32-bit FNV-1a hash */
function fnv1aHash(input) {
  const str = String(input || 'DINKUS-0001');
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/* Deterministic FNV-1a hash-to-SVG barcode generator */
function renderBarcodeSvg(code, opts) {
  const options = opts || {};
  const width = options.width || 220;
  const height = options.height || 42;
  const ink = options.ink || 'currentColor';
  const cleanCode = String(code || 'DK-ORD-8841');

  const bars = [];
  let cursor = 6;
  /* Start guard pattern */
  bars.push({ x: cursor, w: 2, h: height }); cursor += 4;
  bars.push({ x: cursor, w: 1, h: height }); cursor += 3;

  let seed = fnv1aHash(cleanCode);
  const barCount = options.bars || 34;
  for (let i = 0; i < barCount; i++) {
    seed = fnv1aHash(`${cleanCode}:${i}:${seed}`);
    const barW = 1 + (seed % 3);
    const gapW = 1 + ((seed >>> 4) % 3);
    if (cursor + barW + gapW > width - 14) break;
    bars.push({ x: cursor, w: barW, h: height - 2 });
    cursor += barW + gapW;
  }

  /* Stop guard pattern */
  bars.push({ x: cursor, w: 1, h: height }); cursor += 3;
  bars.push({ x: cursor, w: 2, h: height }); cursor += 2;

  const totalW = Math.max(cursor + 6, 120);
  const rects = bars
    .map(b => `<rect x="${b.x}" y="1" width="${b.w}" height="${b.h}" fill="${ink}" />`)
    .join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${totalW} ${height + 2}" role="img" aria-label="Barcode ${cleanCode}">${rects}</svg>`;
}

/* Mount or trigger an eroded dry-ink rubber stamp */
function mountRubberStamp(target, cfg) {
  const config = cfg || {};
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) return null;
  ensureStampFilterSvg(el);

  const label = config.text || el.getAttribute('data-stamp-text') || '[PAID · STRIPE TEST]';
  const variant = config.variant || el.getAttribute('data-variant') || 'paid';
  const angle = config.angle !== undefined ? config.angle : -7;

  el.classList.add('ephemera-rubber-stamp');
  el.setAttribute('data-variant', variant);
  el.style.setProperty('--stamp-angle', `${angle}deg`);
  el.textContent = label;

  const thud = () => {
    el.classList.remove('is-thudding');
    void el.offsetWidth;
    el.classList.add('is-thudding');
    if (config.foley && typeof config.foley.stampThud === 'function') {
      config.foley.stampThud();
    }
  };

  if (config.animate !== false) {
    thud();
  }

  return {
    el,
    thud,
    setText(nextText, nextVariant) {
      el.textContent = String(nextText || '');
      if (nextVariant) el.setAttribute('data-variant', nextVariant);
    },
  };
}

/* Mount a serrated thermal receipt with FNV-1a barcode and steps(28, end) line-feed reveal */
function mountReceipt(target, cfg) {
  const config = cfg || {};
  const host = typeof target === 'string' ? document.querySelector(target) : target;
  if (!host) return null;
  ensureStampFilterSvg(host);

  host.classList.add('ephemera-stage');
  const title = config.title || 'DINKUSKIT STUDIO DISPATCH';
  const subtitle = config.subtitle || 'ORDER RECEIPT · CLOUDFLARE D1 LEDGER';
  const code = config.code || 'DK-2026-0841-PB';
  const items = Array.isArray(config.items) && config.items.length
    ? config.items
    : [
        { label: '1x Aizome Cast Kettle', price: '$68.00' },
        { label: 'Promo (SAVE20 · -20%)', price: '-$13.60' },
        { label: 'PB Ground Label (4x6)', price: '$5.60' },
      ];
  const total = config.total || '$60.00';
  const stampText = config.stampText || '[PAID · D1]';
  const stampVariant = config.stampVariant || 'paid';

  const rowsHtml = items
    .map(
      item =>
        `<div class="ephemera-receipt-row"><span>${item.label}</span><span>${item.price}</span></div>`
    )
    .join('');

  host.innerHTML = `
    <div class="ephemera-receipt-Slot">
      <div class="ephemera-receipt is-feeding" data-receipt-root>
        <div class="ephemera-receipt-hdr">
          <div class="ephemera-receipt-title">${title}</div>
          <div class="ephemera-receipt-sub">${subtitle}</div>
        </div>
        <div class="ephemera-receipt-rows">
          ${rowsHtml}
          <div class="ephemera-receipt-row is-total">
            <span>TOTAL SETTLED</span>
            <span data-receipt-total>${total}</span>
          </div>
        </div>
        <div style="display:flex;justify-content:center;margin:8px 0 4px;">
          <span data-receipt-stamp></span>
        </div>
        <div class="ephemera-receipt-barcode">
          ${renderBarcodeSvg(code)}
          <span class="ephemera-receipt-code">${code}</span>
        </div>
      </div>
    </div>
  `;

  const receiptEl = host.querySelector('[data-receipt-root]');
  const stampEl = host.querySelector('[data-receipt-stamp]');
  const stampCtrl = mountRubberStamp(stampEl, {
    text: stampText,
    variant: stampVariant,
    angle: config.stampAngle !== undefined ? config.stampAngle : -6,
    foley: config.foley,
  });

  const replayPrint = () => {
    if (!receiptEl) return;
    receiptEl.classList.remove('is-feeding');
    void receiptEl.offsetWidth;
    receiptEl.classList.add('is-feeding');
    if (config.foley && typeof config.foley.thermalFeed === 'function') {
      config.foley.thermalFeed();
    }
    if (stampCtrl) stampCtrl.thud();
  };

  const setProgress = t => {
    if (!receiptEl) return;
    const clamped = Math.max(0, Math.min(1, Number(t) || 0));
    receiptEl.classList.remove('is-feeding');
    if (clamped >= 0.99) {
      receiptEl.style.clipPath = 'none';
      return;
    }
    const step = Math.round(clamped * 28) / 28;
    const insetBottom = Math.round((1 - step) * 96);
    receiptEl.style.clipPath = `inset(0 0 ${insetBottom}% 0)`;
  };

  return {
    el: receiptEl,
    stampCtrl,
    replayPrint,
    setProgress,
    stamp(text, variant) {
      if (stampCtrl) {
        stampCtrl.setText(text, variant);
        stampCtrl.thud();
      }
    },
  };
}

/* Mode D Holographic Foil & Perforated Tear-Off Ticket helper */
function mountFoilTicket(target, cfg) {
  const config = cfg || {};
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) return null;
  ensureStampFilterSvg(el);
  el.classList.add('ephemera-stage');

  const setTearProgress = p => {
    const k = Math.max(0, Math.min(1, Number(p) || 0));
    const stub = el.querySelector('.ephemera-ticket-stub') || el.querySelector('[data-ticket-stub]');
    if (!stub) return;
    const rotZ = (k * 16).toFixed(2);
    const dropY = (k * k * 28).toFixed(2);
    const sepX = (k * 14).toFixed(2);
    stub.style.transform = `translate(${sepX}px, ${dropY}px) rotate(${rotZ}deg)`;
    stub.style.opacity = String((1 - k * 0.35).toFixed(2));
  };

  el.addEventListener('pointermove', e => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const nx = (e.clientX - r.left) / r.width - 0.5;
    const ny = (e.clientY - r.top) / r.height - 0.5;
    el.style.setProperty('--tilt-rx', `${(-ny * 10).toFixed(2)}deg`);
    el.style.setProperty('--tilt-ry', `${(nx * 12).toFixed(2)}deg`);
    el.style.setProperty('--foil-shift', `${(nx * 45).toFixed(1)}deg`);
  });

  el.addEventListener('pointerleave', () => {
    el.style.setProperty('--tilt-rx', '0deg');
    el.style.setProperty('--tilt-ry', '0deg');
    el.style.setProperty('--foil-shift', '0deg');
  });

  if (config.tearProgress !== undefined) {
    setTearProgress(config.tearProgress);
  }

  return { el, setTearProgress };
}

/* Strictly Opt-In Procedural Web Audio Micro-Foley (muted until explicit user toggle) */
function createMicroFoley() {
  let ctx = null;
  let enabled = false;
  const ensure = () => {
    if (!enabled) return null;
    if (!ctx && typeof AudioContext !== 'undefined') ctx = new AudioContext();
    if (ctx && ctx.state === 'suspended') ctx.resume();
    return ctx;
  };
  return {
    setEnabled(v) {
      enabled = Boolean(v);
      if (enabled) ensure();
    },
    isEnabled() {
      return enabled;
    },
    click(freq = 920, dur = 0.028) {
      const ac = ensure();
      if (!ac) return;
      const osc = ac.createOscillator();
      const g = ac.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, ac.currentTime);
      osc.frequency.exponentialRampToValueAtTime(140, ac.currentTime + dur);
      g.gain.setValueAtTime(0.18, ac.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + dur);
      osc.connect(g);
      g.connect(ac.destination);
      osc.start();
      osc.stop(ac.currentTime + dur);
    },
    stampThud() {
      const ac = ensure();
      if (!ac) return;
      const osc = ac.createOscillator();
      const g = ac.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(165, ac.currentTime);
      osc.frequency.exponentialRampToValueAtTime(48, ac.currentTime + 0.085);
      g.gain.setValueAtTime(0.26, ac.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.09);
      osc.connect(g);
      g.connect(ac.destination);
      osc.start();
      osc.stop(ac.currentTime + 0.09);
    },
    thermalFeed(dur = 0.22) {
      const ac = ensure();
      if (!ac) return;
      const osc = ac.createOscillator();
      const g = ac.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(280, ac.currentTime);
      osc.frequency.linearRampToValueAtTime(340, ac.currentTime + dur);
      g.gain.setValueAtTime(0.06, ac.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + dur);
      osc.connect(g);
      g.connect(ac.destination);
      osc.start();
      osc.stop(ac.currentTime + dur);
    },
    paperTear(dur = 0.16, centerHz = 1800) {
      const ac = ensure();
      if (!ac) return;
      const len = Math.floor(ac.sampleRate * dur);
      const buf = ac.createBuffer(1, len, ac.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < len; i++) {
        const env = Math.sin((i / len) * Math.PI);
        data[i] = (Math.random() * 2 - 1) * env * (0.6 + 0.4 * Math.sin(i * 0.08));
      }
      const src = ac.createBufferSource();
      src.buffer = buf;
      const bp = ac.createBiquadFilter();
      bp.type = 'bandpass';
      bp.frequency.value = centerHz;
      bp.Q.value = 1.4;
      const g = ac.createGain();
      g.gain.value = 0.22;
      src.connect(bp);
      bp.connect(g);
      g.connect(ac.destination);
      src.start();
    },
  };
}

if (typeof window !== 'undefined') {
  window.fnv1aHash = fnv1aHash;
  window.renderBarcodeSvg = renderBarcodeSvg;
  window.mountRubberStamp = mountRubberStamp;
  window.mountReceipt = mountReceipt;
  window.mountFoilTicket = mountFoilTicket;
  window.createMicroFoley = createMicroFoley;
}
