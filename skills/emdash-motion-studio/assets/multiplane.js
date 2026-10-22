/* ============================================================
   EmDash Motion Studio — Mode B: Multiplane Occlusion Stage + Pigment Drift
   Combines:
   1. 3-Layer Shadowbox (Plane 0 Background Stage, Plane 1 Animated Midground,
      Plane 2 Foreground Occlusion Masks) + 3D Exploded Multiplane Camera (?explode=1)
   2. Artwork-Led Transit/Timeline HUD (where the midground actor IS the progress bar)
   3. Soft Current Pigment Drift (SVG feTurbulence + feDisplacementMap watercolor wash)
   ============================================================ */

addEventListener('error', e => {
  document.documentElement.dataset.errors = (document.documentElement.dataset.errors || '') + ' ' + e.message + ';';
});

const MP_CSS = `
  :root, body.mp-standalone, .mp-root{
    --mp-paper:var(--color-canvas,var(--color-surface,#f4f1ea));
    --mp-card:var(--color-surface,#e9eef2);
    --mp-ink:var(--color-ink,var(--color-text,#18222c));
    --mp-muted:var(--color-muted,#63717d);
    --mp-rule:var(--color-border,var(--color-rule,#c9d2d9));
    --mp-accent:var(--color-accent,var(--color-primary,#e89b2d));
  }
  body.mp-standalone, .mp-root{
    box-sizing:border-box;background:var(--mp-paper);color:var(--mp-ink);
    font:13px/1.4 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    display:flex;flex-direction:column;align-items:center;
  }
  body.mp-standalone *, .mp-root *{box-sizing:border-box}
  html:has(body.mp-standalone){margin:0;min-height:100%;overflow-x:hidden}
  body.mp-standalone{margin:0;min-height:100%;padding:24px 16px 36px;overflow-x:hidden}
  .mp-root{position:relative;width:100%;padding:16px}
  .mp-frame{
    position:relative;width:100%;max-width:1040px;background:var(--mp-card);
    border:1.5px solid var(--mp-rule);border-radius:16px;
    box-shadow:0 20px 50px rgba(18,26,36,.14);overflow:hidden;
    display:flex;flex-direction:column;justify-content:space-between;
  }
  .mp-hud-top{
    position:relative;z-index:5;display:flex;justify-content:space-between;align-items:flex-start;
    padding:28px 36px 8px;pointer-events:none;
  }
  .mp-eyebrow{
    font:700 10.5px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    letter-spacing:.14em;text-transform:uppercase;color:var(--mp-muted);margin:0 0 6px;
  }
  .mp-title{
    font-size:clamp(22px,3.2vw,34px);font-weight:600;letter-spacing:-.02em;
    line-height:1.1;margin:0;color:var(--mp-ink);
  }
  .mp-metric{text-align:right;font-variant-numeric:tabular-nums}
  .mp-metric-val{
    font-size:clamp(34px,4.5vw,54px);font-weight:500;line-height:.95;
    letter-spacing:-.03em;color:var(--mp-ink);
  }
  .mp-metric-unit{
    font:700 10px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    letter-spacing:.14em;text-transform:uppercase;color:var(--mp-muted);margin-top:4px;
  }
  .mp-stage-wrap{
    position:relative;width:100%;perspective:1500px;padding:0;
  }
  .mp-shadowbox{
    position:relative;width:100%;aspect-ratio:1200 / 520;
    transform-style:preserve-3d;
    transition:transform .65s cubic-bezier(.22,1,.36,1);
  }
  .mp-plane{
    position:absolute;inset:0;width:100%;height:100%;display:block;overflow:visible;
    transition:transform .65s cubic-bezier(.22,1,.36,1), box-shadow .65s ease, background .65s ease, border-color .65s ease;
    border:1px solid transparent;border-radius:6px;
  }
  .mp-plane-tag{
    position:absolute;top:10px;left:14px;z-index:6;
    font:700 10px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    letter-spacing:.1em;text-transform:uppercase;
    padding:4px 8px;border-radius:4px;background:rgba(24,34,44,.86);color:#f4f1ea;
    opacity:0;pointer-events:none;transition:opacity .35s ease;
  }
  /* Exploded 3D Multiplane Camera View (?explode=1) */
  .mp-frame[data-explode="1"] .mp-stage-wrap{padding:28px 42px 34px}
  .mp-frame[data-explode="1"] .mp-shadowbox{
    transform:rotateX(11deg) rotateY(-24deg) rotateZ(1.5deg) scale(.82);
  }
  .mp-frame[data-explode="1"] .mp-plane{
    background:rgba(244,241,234,.52);
    border-color:rgba(24,34,44,.26);
    box-shadow:-18px 22px 34px rgba(18,26,36,.18);
  }
  .mp-frame[data-explode="1"] .mp-plane-bg{transform:translateZ(-110px) translateX(-36px) translateY(-14px);background:rgba(244,241,234,.92)}
  .mp-frame[data-explode="1"] .mp-plane-mid{transform:translateZ(0px)}
  .mp-frame[data-explode="1"] .mp-plane-fg{transform:translateZ(110px) translateX(36px) translateY(14px);background:rgba(244,241,234,.22)}
  .mp-frame[data-explode="1"] .mp-plane-tag{opacity:1}

  .mp-hud-bottom{
    position:relative;z-index:5;padding:18px 36px 26px;
    background:linear-gradient(to bottom, rgba(233,238,242,0), var(--mp-card) 28%);
  }
  .mp-timeline{position:relative;width:100%;margin:6px 0 14px}
  .mp-track{
    position:relative;width:100%;height:2px;background:var(--mp-rule);border-radius:2px;
  }
  .mp-track-fill{
    position:absolute;left:0;top:0;height:100%;background:var(--mp-accent);border-radius:2px;
  }
  .mp-playhead{
    position:absolute;top:50%;width:3px;height:10px;background:var(--mp-ink);
    transform:translate(-50%,-50%);border-radius:1px;
  }
  .mp-stops{
    display:grid;grid-template-columns:repeat(var(--stop-count,4),1fr);gap:8px;margin-top:10px;
  }
  .mp-stop{
    all:unset;cursor:pointer;display:flex;flex-direction:column;align-items:center;text-align:center;
    padding:6px 4px;border-radius:8px;transition:background .15s ease;
  }
  .mp-stop:hover{background:rgba(24,34,44,.05)}
  .mp-stop-tick{
    width:2px;height:7px;background:var(--mp-rule);margin-top:-15px;margin-bottom:8px;
  }
  .mp-stop[data-state="active"] .mp-stop-tick{background:var(--mp-ink);height:9px}
  .mp-stop[data-state="passed"] .mp-stop-tick{background:var(--mp-accent)}
  .mp-stop-name{
    font-size:12.5px;font-weight:500;color:var(--mp-muted);transition:color .15s;
  }
  .mp-stop[data-state="active"] .mp-stop-name{font-weight:700;color:var(--mp-ink)}
  .mp-stop-sub{
    font:700 9.5px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    letter-spacing:.1em;text-transform:uppercase;color:var(--mp-muted);margin-top:3px;
  }
  .mp-stop[data-state="active"] .mp-stop-sub{color:var(--mp-ink)}
  .mp-toolbar{
    display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;
    margin-top:10px;padding-top:12px;border-top:1px solid var(--mp-rule);
  }
  .mp-btns{display:flex;gap:8px;flex-wrap:wrap}
  .mp-btn{
    font:600 11.5px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--mp-ink);background:var(--mp-paper);border:1.5px solid var(--mp-ink);
    border-radius:999px;padding:5px 13px;cursor:pointer;letter-spacing:.03em;
  }
  .mp-btn:hover{background:color-mix(in srgb,var(--mp-paper) 88%,var(--mp-ink))}
  .mp-btn[aria-pressed="true"]{background:var(--mp-ink);color:var(--mp-paper)}
  .mp-readout{
    font:600 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    letter-spacing:.06em;text-transform:uppercase;color:var(--mp-muted);
  }
  [data-chrome="stage-only"] .mp-hud-top,
  [data-chrome="stage-only"] .mp-hud-bottom{display:none!important}
  [data-chrome="storefront"] .mp-toolbar{display:none}
  @media (max-width:560px){
    .mp-hud-top{padding:18px 18px 6px}
    .mp-hud-bottom{padding:12px 16px 18px}
    .mp-stop-name{font-size:11px}
    .mp-frame[data-explode="1"] .mp-stage-wrap{padding:14px}
    .mp-frame[data-explode="1"] .mp-shadowbox{transform:rotateX(9deg) rotateY(-16deg) scale(.88)}
  }
`;

let _mpSeq = 0;

function _mpHexMix(a, b, k){
  const p = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const [A, B] = [p(a), p(b)];
  return '#' + [0, 1, 2].map(i => Math.round(A[i] + (B[i] - A[i]) * k).toString(16).padStart(2, '0')).join('');
}

/**
 * Deterministic timelapse sky & lighting interpolation across normalized time t (0..1).
 * Cycles dawn -> midday -> golden hour / dusk -> night -> dawn.
 */
function timelapse(t = 0){
  const stops = [
    { at: 0.00, zenith: '#d8e2dc', horizon: '#fcf6e9', glow: '#f4c078', win: 0.15, night: 0.08 },
    { at: 0.30, zenith: '#c5d7e8', horizon: '#f6f3eb', glow: '#ffd584', win: 0.05, night: 0.00 },
    { at: 0.62, zenith: '#354966', horizon: '#e59866', glow: '#f08a4b', win: 0.65, night: 0.32 },
    { at: 0.85, zenith: '#182436', horizon: '#3b4d66', glow: '#6c8ebf', win: 0.92, night: 0.58 },
    { at: 1.00, zenith: '#d8e2dc', horizon: '#fcf6e9', glow: '#f4c078', win: 0.15, night: 0.08 },
  ];
  const u = ((t % 1) + 1) % 1;
  let a = stops[0], b = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++){
    if (u >= stops[i].at && u <= stops[i + 1].at){ a = stops[i]; b = stops[i + 1]; break; }
  }
  const k = b.at > a.at ? (u - a.at) / (b.at - a.at) : 0;
  const ang = u * Math.PI * 2 - Math.PI * 0.25;
  return {
    zenith: _mpHexMix(a.zenith, b.zenith, k),
    horizon: _mpHexMix(a.horizon, b.horizon, k),
    glow: _mpHexMix(a.glow, b.glow, k),
    windowOpacity: +(a.win + (b.win - a.win) * k).toFixed(3),
    nightOpacity: +(a.night + (b.night - a.night) * k).toFixed(3),
    sunX: +(600 - Math.cos(ang) * 380).toFixed(1),
    sunY: +(240 - Math.sin(ang) * 145).toFixed(1),
  };
}

function renderTimelapse(opts = {}, t = 0){
  const W = opts.width || 1200;
  const H = opts.height || 520;
  const pfx = opts.idPrefix || 'mp';
  const tl = timelapse(t);
  return `
    <defs>
      <linearGradient id="${pfx}-tl-sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${tl.zenith}"/>
        <stop offset="100%" stop-color="${tl.horizon}"/>
      </linearGradient>
      <radialGradient id="${pfx}-tl-sun" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="${tl.glow}" stop-opacity="0.72"/>
        <stop offset="100%" stop-color="${tl.glow}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="0" y="0" width="${W}" height="${H}" fill="url(#${pfx}-tl-sky)" opacity="${opts.opacity ?? 0.78}"/>
    <circle cx="${tl.sunX}" cy="${tl.sunY}" r="130" fill="url(#${pfx}-tl-sun)"/>
  `;
}

/**
 * Render a hybrid raster/vector plate (<image> with optional SVG clipPath or mask cutout)
 * for background, midground, or foreground occlusion layers.
 */
function renderPlate(plate = {}, opts = {}){
  if (!plate || (!plate.href && !plate.src)) return '';
  const W = plate.width || opts.width || 1200;
  const H = plate.height || opts.height || 520;
  const x = plate.x || 0, y = plate.y || 0;
  const href = plate.href || plate.src;
  const pfx = opts.idPrefix || 'mp';
  const pid = `${pfx}-plate-${plate.id || 'img'}`;
  let defs = '', attr = '';
  if (plate.clipPath){
    defs += `<defs><clipPath id="${pid}-clip"><path d="${plate.clipPath}"/></clipPath></defs>`;
    attr += ` clip-path="url(#${pid}-clip)"`;
  }
  if (plate.maskSvg){
    defs += `<defs><mask id="${pid}-mask">${plate.maskSvg}</mask></defs>`;
    attr += ` mask="url(#${pid}-mask)"`;
  }
  const op = plate.opacity != null ? ` opacity="${plate.opacity}"` : '';
  const par = plate.preserveAspectRatio || 'xMidYMid slice';
  return `${defs}<image href="${href}" x="${x}" y="${y}" width="${W}" height="${H}" preserveAspectRatio="${par}"${op}${attr}/>`;
}

/**
 * Reusable Pigment Drift SVG generator (David East "Soft Current" watercolor/ink-bleed recipe).
 * Pure function of normalized time t (0..1) so ?t= scrubbing is 100% deterministic.
 */
function renderPigmentDrift(opts = {}, t = 0){
  const W = opts.width || 1200;
  const H = opts.height || 520;
  const pfx = opts.idPrefix || 'mp';
  const cols = opts.colors || ['#2a1668', '#1d52b8', '#5887d8', '#d7b4c8', '#fcf6e9'];
  const phase = t * Math.PI * 2;
  const dx1 = (Math.sin(phase) * 18).toFixed(1);
  const dy1 = (Math.cos(phase) * 10).toFixed(1);
  const dx2 = (Math.cos(phase) * -22).toFixed(1);
  const dy2 = (Math.sin(phase) * 12).toFixed(1);
  const yStart = opts.position === 'bottom' ? Math.round(H * 0.32) : 0;

  return `
    <defs>
      <filter id="${pfx}-pigment-wash" x="-12%" y="-12%" width="124%" height="124%" color-interpolation-filters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency="0.011 0.018" numOctaves="4" seed="14" result="flow"/>
        <feDisplacementMap in="SourceGraphic" in2="flow" scale="46" xChannelSelector="R" yChannelSelector="G" result="bloom"/>
        <feTurbulence type="fractalNoise" baseFrequency="0.55" numOctaves="3" seed="9" result="fibers"/>
        <feColorMatrix in="fibers" type="matrix" values="0.22 0 0 0 0.82  0.22 0 0 0 0.81  0.22 0 0 0 0.78  0 0 0 0 1" result="paperGrain"/>
        <feBlend in="bloom" in2="paperGrain" mode="multiply" result="washed"/>
        <feComposite in="washed" in2="bloom" operator="in"/>
      </filter>
      <linearGradient id="${pfx}-pigment-sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${cols[4] || '#fcf6e9'}" stop-opacity="0.95"/>
        <stop offset="55%" stop-color="${cols[3] || '#d7b4c8'}" stop-opacity="0.32"/>
        <stop offset="100%" stop-color="${cols[2] || '#5887d8'}" stop-opacity="0.48"/>
      </linearGradient>
      <radialGradient id="${pfx}-plume-indigo" cx="32%" cy="76%" r="58%">
        <stop offset="0%" stop-color="${cols[0]}" stop-opacity="0.82"/>
        <stop offset="55%" stop-color="${cols[1]}" stop-opacity="0.46"/>
        <stop offset="100%" stop-color="${cols[1]}" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="${pfx}-plume-cobalt" cx="68%" cy="82%" r="54%">
        <stop offset="0%" stop-color="${cols[1]}" stop-opacity="0.76"/>
        <stop offset="52%" stop-color="${cols[2]}" stop-opacity="0.42"/>
        <stop offset="100%" stop-color="${cols[3]}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect x="0" y="0" width="${W}" height="${H}" fill="url(#${pfx}-pigment-sky)"/>
    <g filter="url(#${pfx}-pigment-wash)" opacity="${opts.opacity ?? 0.42}">
      <ellipse cx="${380 + +dx1}" cy="${yStart + (H - yStart) * 0.68 + +dy1}" rx="460" ry="${(H - yStart) * 0.56}" fill="url(#${pfx}-plume-indigo)"/>
      <ellipse cx="${820 + +dx2}" cy="${yStart + (H - yStart) * 0.72 + +dy2}" rx="440" ry="${(H - yStart) * 0.52}" fill="url(#${pfx}-plume-cobalt)"/>
      <path d="M ${620 + +dx1} ${yStart + 20} C ${860 + +dx2} ${yStart + 90}, ${510 + +dx1} ${H - 110}, ${790 + +dx2} ${H + 10}
               L ${880 + +dx2} ${H + 10} C ${610 + +dx1} ${H - 120}, ${930 + +dx2} ${yStart + 80}, ${670 + +dx1} ${yStart + 20} Z"
            fill="${cols[4] || '#fcf6e9'}" fill-opacity="0.65"/>
    </g>
  `;
}

function _readMpTokens(el){
  if (typeof getComputedStyle === 'undefined') return {};
  const cs = getComputedStyle(el || document.documentElement);
  return {
    paper: cs.getPropertyValue('--mp-paper').trim() || '#f4f1ea',
    card: cs.getPropertyValue('--mp-card').trim() || '#e9eef2',
    ink: cs.getPropertyValue('--mp-ink').trim() || '#18222c',
    muted: cs.getPropertyValue('--mp-muted').trim() || '#63717d',
    rule: cs.getPropertyValue('--mp-rule').trim() || '#c9d2d9',
    accent: cs.getPropertyValue('--mp-accent').trim() || '#e89b2d',
  };
}

function mountMultiplane(cfg){
  const q = new URLSearchParams(location.search);
  const rawTarget = cfg.target || window.__EMDASH_MOTION_TARGET || null;
  const rootEl = typeof rawTarget === 'string' ? document.querySelector(rawTarget) : (rawTarget || document.body);
  const isStandalone = rootEl === document.body;
  const instPfx = `mp${++_mpSeq}`;
  const chrome = q.get('chrome') || cfg.chrome || (rootEl && rootEl.dataset && rootEl.dataset.chrome) || window.__EMDASH_MOTION_CHROME || (isStandalone ? 'full' : 'storefront');
  const [vbW, vbH] = cfg.viewBox || [1200, 520];
  const duration = cfg.duration || 14;
  const stops = cfg.stops || [
    { id: 'harbor',       label: 'Harbor Bridge',   at: 0.10, etaMin: 5 },
    { id: 'midtown',      label: 'Midtown Towers',  at: 0.38, etaMin: 3 },
    { id: 'cantilever',   label: 'Cantilever Hall', at: 0.64, etaMin: 2, skip: true },
    { id: 'conservatory', label: 'Conservatory',    at: 0.90, etaMin: 0 },
  ];

  if (isStandalone) document.title = cfg.title || 'Multiplane Stage';
  if (q.has('vw')){
    document.documentElement.style.maxWidth = q.get('vw') + 'px';
    document.body.style.maxWidth = q.get('vw') + 'px';
    document.body.style.margin = '0';
  }
  if (!document.getElementById('mp-core-css')){
    const style = document.createElement('style');
    style.id = 'mp-core-css';
    style.textContent = MP_CSS;
    document.head.appendChild(style);
  }
  if (isStandalone) document.body.classList.add('mp-standalone');
  else rootEl.classList.add('mp-root');
  rootEl.setAttribute('data-chrome', chrome);

  const st = Object.assign({
    t: 0,
    playing: !q.has('t') && !(typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches),
    explode: q.get('explode') === '1',
    pigment: cfg.pigment ? cfg.pigment.enabled !== false : true,
  }, cfg.state || {});

  if (q.has('stop')){
    const targetStop = stops.find(s => s.id === q.get('stop') || s.label.toLowerCase().startsWith(q.get('stop').toLowerCase()));
    if (targetStop){ st.t = targetStop.at; st.playing = false; }
  }
  if (q.has('t')){
    st.t = Math.max(0, Math.min(1, +q.get('t') || 0));
    st.playing = false;
  }

  rootEl.innerHTML = `
    <div class="mp-frame" id="mp-frame" data-explode="${st.explode ? '1' : '0'}">
      <div class="mp-hud-top">
        <div>
          <p class="mp-eyebrow" id="mp-eyebrow">${cfg.eyebrow || 'NEXT STOP'}</p>
          <h1 class="mp-title" id="mp-title">${cfg.title || stops[0].label}</h1>
        </div>
        <div class="mp-metric">
          <div class="mp-metric-val" id="mp-metric-val">1</div>
          <div class="mp-metric-unit" id="mp-metric-unit">MIN</div>
        </div>
      </div>
      <div class="mp-stage-wrap">
        <div class="mp-shadowbox" id="mp-shadowbox">
          <div class="mp-plane mp-plane-bg">
            <span class="mp-plane-tag">Plane 01 · Background Stage + Pigment Drift</span>
            <svg id="fig" viewBox="0 0 ${vbW} ${vbH}" width="100%" height="100%" role="img" aria-label="${cfg.title || 'Multiplane Stage'}">
              <g id="mp-bg-layer"></g>
            </svg>
          </div>
          <div class="mp-plane mp-plane-mid">
            <span class="mp-plane-tag">Plane 02 · Animated Midground</span>
            <svg viewBox="0 0 ${vbW} ${vbH}" width="100%" height="100%" aria-hidden="true">
              <g id="mp-mid-layer"></g>
            </svg>
          </div>
          <div class="mp-plane mp-plane-fg">
            <span class="mp-plane-tag">Plane 03 · Foreground Occlusion Mask</span>
            <svg viewBox="0 0 ${vbW} ${vbH}" width="100%" height="100%" aria-hidden="true">
              <g id="mp-fg-layer"></g>
            </svg>
          </div>
        </div>
      </div>
      <div class="mp-hud-bottom">
        <div class="mp-timeline">
          <div class="mp-track">
            <div class="mp-track-fill" id="mp-track-fill"></div>
            <div class="mp-playhead" id="mp-playhead"></div>
          </div>
          <div class="mp-stops" id="mp-stops" style="--stop-count:${stops.length}"></div>
        </div>
        <div class="mp-toolbar">
          <div class="mp-btns" id="btns">
            <button class="mp-btn act" id="mp-play-btn" aria-pressed="${st.playing}">${st.playing ? 'Pause' : 'Play'}</button>
            <button class="mp-btn act" id="mp-explode-btn" aria-pressed="${st.explode}">Layers</button>
            <button class="mp-btn act" id="mp-pigment-btn" aria-pressed="${st.pigment}">Pigment Drift</button>
          </div>
          <div class="mp-readout" id="mp-readout"></div>
        </div>
      </div>
    </div>
  `;

  const byId = id => rootEl.querySelector('#' + id) || document.getElementById(id);
  const frameEl = byId('mp-frame');
  const bgLayer = byId('mp-bg-layer');
  const midLayer = byId('mp-mid-layer');
  const fgLayer = byId('mp-fg-layer');
  const titleEl = byId('mp-title');
  const metricValEl = byId('mp-metric-val');
  const metricUnitEl = byId('mp-metric-unit');
  const fillEl = byId('mp-track-fill');
  const playheadEl = byId('mp-playhead');
  const stopsEl = byId('mp-stops');
  const readoutEl = byId('mp-readout');
  const playBtn = byId('mp-play-btn');
  const explodeBtn = byId('mp-explode-btn');
  const pigmentBtn = byId('mp-pigment-btn');

  // Build stop buttons
  const stopEls = stops.map((s, idx) => {
    const b = document.createElement('button');
    b.className = 'mp-stop act';
    b.innerHTML = `<span class="mp-stop-tick"></span><span class="mp-stop-name">${s.label}</span><span class="mp-stop-sub" data-sub>${s.skip ? 'SKIP' : ''}</span>`;
    b.onclick = () => {
      st.playing = false;
      playBtn.textContent = 'Play';
      playBtn.setAttribute('aria-pressed', 'false');
      animateTo(s.at);
    };
    stopsEl.appendChild(b);
    return { stop: s, el: b, subEl: b.querySelector('[data-sub]'), idx };
  });

  const ctx = {
    width: vbW,
    height: vbH,
    idPrefix: instPfx,
    tokens: _readMpTokens(rootEl),
    timelapse,
    renderTimelapse: (opts = {}, tNorm = st.t) => renderTimelapse(Object.assign({ width: vbW, height: vbH, idPrefix: instPfx }, opts), tNorm),
    renderPlate: (plate = {}) => renderPlate(plate, { width: vbW, height: vbH, idPrefix: instPfx }),
    renderPigmentDrift: (opts = {}, tNorm = st.t) => renderPigmentDrift(Object.assign({ width: vbW, height: vbH, idPrefix: instPfx }, opts), tNorm),
  };
  const ui = { st, rootEl, ctx };

  ui.render = () => {
    const t = ((st.t % 1) + 1) % 1;
    ctx.tokens = _readMpTokens(rootEl);
    ctx.sky = timelapse(t);
    frameEl.setAttribute('data-explode', st.explode ? '1' : '0');
    const tlSvg = cfg.timelapse ? renderTimelapse(Object.assign({ width: vbW, height: vbH, idPrefix: instPfx }, typeof cfg.timelapse === 'object' ? cfg.timelapse : {}), t) : '';
    const pigSvg = st.pigment ? renderPigmentDrift(Object.assign({ width: vbW, height: vbH, idPrefix: instPfx }, cfg.pigment || {}), t) : '';
    const plates = cfg.plates || {};
    const bgPlate = plates.background ? renderPlate(plates.background, { width: vbW, height: vbH, idPrefix: instPfx }) : '';
    const midPlate = plates.midground ? renderPlate(plates.midground, { width: vbW, height: vbH, idPrefix: instPfx }) : '';
    const fgPlate = plates.foreground ? renderPlate(plates.foreground, { width: vbW, height: vbH, idPrefix: instPfx }) : '';
    const bgSvg = cfg.background ? cfg.background(st, t, ctx) : '';
    const midSvg = cfg.midground ? cfg.midground(st, t, ctx) : '';
    const fgSvg = cfg.foreground ? cfg.foreground(st, t, ctx) : '';

    bgLayer.innerHTML = tlSvg + pigSvg + bgPlate + bgSvg;
    midLayer.innerHTML = midPlate + midSvg;
    fgLayer.innerHTML = fgPlate + fgSvg;

    // Update stops & active stop HUD
    let nextStop = stops.find(s => !s.skip && s.at >= t - 0.02) || stops[stops.length - 1];
    stopEls.forEach(({ stop, el, subEl }) => {
      const dist = stop.at - t;
      let state = 'upcoming';
      let subText = '';
      if (stop.skip){
        state = dist < -0.02 ? 'passed' : 'upcoming';
        subText = 'SKIP';
      } else if (dist < -0.025){
        state = 'passed';
        subText = 'PASSED';
      } else if (stop === nextStop){
        state = 'active';
        const mins = Math.max(0, Math.round(dist * 10));
        subText = mins === 0 ? 'ARRIVING' : `${mins} MIN`;
      } else {
        const mins = Math.max(1, Math.round(dist * 10));
        subText = `${mins} MIN`;
      }
      el.setAttribute('data-state', state);
      subEl.textContent = subText;
    });

    if (cfg.stats){
      const m = cfg.stats(st, t, nextStop);
      if (m){
        titleEl.textContent = m.title || nextStop.label;
        metricValEl.textContent = m.value;
        metricUnitEl.textContent = m.unit || 'MIN';
      }
    } else {
      titleEl.textContent = nextStop.label;
      const remMins = Math.max(0, Math.round(Math.max(0, nextStop.at - t) * 10));
      metricValEl.textContent = String(remMins);
      metricUnitEl.textContent = 'MIN';
    }

    const pct = (t * 100).toFixed(2) + '%';
    fillEl.style.width = pct;
    playheadEl.style.left = pct;
    readoutEl.textContent = `T=${t.toFixed(2)} · ${st.explode ? '3D MULTIPLANE' : 'COMPOSITED'} · ${nextStop.label.toUpperCase()}`;
  };

  let scrubAnim = 0;
  function animateTo(targetT, ms = 650){
    const t0 = st.t, dtTotal = targetT - t0, id = ++scrubAnim;
    let el = 0, last = performance.now();
    const step = () => {
      if (id !== scrubAnim) return;
      const now = performance.now(), dt = Math.min(50, now - last); last = now; el += dt;
      const k = Math.min(1, el / ms), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2)/2;
      st.t = t0 + dtTotal * e;
      ui.render();
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  let rafId = 0, lastFrame = performance.now();
  function tick(){
    if (!st.playing) return;
    const now = performance.now(), dt = Math.min(0.05, Math.max(0, (now - lastFrame) / 1000));
    lastFrame = now;
    st.t = (st.t + dt / duration) % 1;
    ui.render();
    rafId = requestAnimationFrame(tick);
  }

  playBtn.onclick = () => {
    st.playing = !st.playing;
    playBtn.textContent = st.playing ? 'Pause' : 'Play';
    playBtn.setAttribute('aria-pressed', String(st.playing));
    if (st.playing){ lastFrame = performance.now(); tick(); }
    else cancelAnimationFrame(rafId);
  };
  explodeBtn.onclick = () => {
    st.explode = !st.explode;
    explodeBtn.setAttribute('aria-pressed', String(st.explode));
    ui.render();
  };
  pigmentBtn.onclick = () => {
    st.pigment = !st.pigment;
    pigmentBtn.setAttribute('aria-pressed', String(st.pigment));
    ui.render();
  };

  ui.setTime = tNorm => {
    st.playing = false;
    cancelAnimationFrame(rafId);
    st.t = Math.max(0, Math.min(1, +tNorm || 0));
    ui.render();
  };
  window.__setMotionTime = ui.setTime;
  window.__st = st;

  const noteErr = m => { document.documentElement.dataset.errors = (document.documentElement.dataset.errors || '') + ' ' + m + ';'; };
  const starts = (el, t) => el.textContent.trim().toLowerCase().startsWith(t.trim().toLowerCase());
  if (q.has('press')) q.get('press').split(',').forEach(item => {
    const [label, ms] = item.split('@');
    setTimeout(() => {
      const b = [...rootEl.querySelectorAll('.act')].find(el => starts(el, label));
      if (!b) return noteErr(`no button "${label}"`);
      b.click();
    }, +ms || 0);
  });

  ui.render();
  if (typeof MutationObserver !== 'undefined'){
    new MutationObserver(() => {
      ctx.tokens = _readMpTokens(rootEl);
      if (!st.playing) ui.render();
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme', 'data-preset'] });
  }
  if (st.playing){ lastFrame = performance.now(); tick(); }
  return ui;
}
