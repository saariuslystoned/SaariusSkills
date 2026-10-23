/* ============================================================
   EmDash Motion Studio — Mode C: Choreographed Timeline / Scroll / Data Stage
   Cue-driven 3D/SVG choreography engine (DeepMind Argon style) with:
   - Normalized timeline t in [0..1] + named cues [{ id, label, range:[t0,t1] }]
   - 3D camera keyframe interpolation (lerpCam) & orthographic/perspective projection (project3D)
   - Live telemetry HUD counters + interactive cue chapter pills + timeline scrubber
   - Deterministic ?t=0..1 and ?cue= scrubbing + EmDash tokens.css binding
   ============================================================ */

addEventListener('error', e => {
  document.documentElement.dataset.errors = (document.documentElement.dataset.errors || '') + ' ' + e.message + ';';
});

const clamp01 = v => Math.max(0, Math.min(1, v));
const subRange = (t, t0, t1) => t1 <= t0 ? 0 : clamp01((t - t0) / (t1 - t0));
const easeInOutCubic = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const easeOutExpo = t => t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
const lerp = (a, b, t) => a + (b - a) * t;
const lerpVec = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);

function lerpCam(keyframes, t){
  if (!keyframes || !keyframes.length) return { yaw: 35, pitch: 28, zoom: 1, target: [0, 0, 0] };
  if (t <= keyframes[0].at) return keyframes[0];
  if (t >= keyframes[keyframes.length - 1].at) return keyframes[keyframes.length - 1];
  for (let i = 0; i < keyframes.length - 1; i++){
    const a = keyframes[i], b = keyframes[i + 1];
    if (t >= a.at && t <= b.at){
      const k = easeInOutCubic(subRange(t, a.at, b.at));
      return {
        yaw: lerp(a.yaw, b.yaw, k),
        pitch: lerp(a.pitch, b.pitch, k),
        zoom: lerp(a.zoom ?? 1, b.zoom ?? 1, k),
        target: lerpVec(a.target || [0, 0, 0], b.target || [0, 0, 0], k),
      };
    }
  }
  return keyframes[0];
}

function project3D(pt, cam, cx = 550, cy = 300, scale = 1){
  const yaw = (cam.yaw || 0) * Math.PI / 180;
  const pitch = (cam.pitch || 0) * Math.PI / 180;
  const zoom = (cam.zoom || 1) * scale;
  const tgt = cam.target || [0, 0, 0];
  const x = pt[0] - tgt[0], y = pt[1] - tgt[1], z = pt[2] - tgt[2];
  const cyaw = Math.cos(yaw), syaw = Math.sin(yaw);
  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  const rx = x * cyaw - y * syaw;
  const ry = x * syaw + y * cyaw;
  const sx = cx + rx * zoom;
  const sy = cy + (ry * sp - z * cp) * zoom;
  const depth = ry * cp + z * sp;
  return [sx, sy, depth];
}

const CHOREO_CSS = `
  :root, body.ch-standalone, .ch-root{
    --ch-bg:var(--color-canvas,var(--color-surface,#0e131a));
    --ch-panel:var(--color-surface,#151d28);
    --ch-ink:var(--color-ink,var(--color-text,#eef3f8));
    --ch-muted:var(--color-muted,#7f91a6);
    --ch-rule:var(--color-border,var(--color-rule,#263445));
    --ch-accent:var(--color-accent,var(--color-primary,#4fd1c5));
  }
  body.ch-standalone, .ch-root{
    box-sizing:border-box;background:var(--ch-bg);color:var(--ch-ink);
    font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
    display:flex;flex-direction:column;align-items:center;
  }
  body.ch-standalone *, .ch-root *{box-sizing:border-box}
  html:has(body.ch-standalone){margin:0;min-height:100%;overflow-x:hidden}
  body.ch-standalone{margin:0;min-height:100%;padding:24px 16px 36px;overflow-x:hidden}
  .ch-root{position:relative;width:100%;padding:16px}
  .ch-shell{
    position:relative;width:100%;max-width:1040px;background:var(--ch-panel);
    border:1.5px solid var(--ch-rule);border-radius:16px;overflow:hidden;
    box-shadow:0 22px 54px rgba(0,0,0,.32);
  }
  .ch-header{
    display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;
    padding:20px 26px 14px;border-bottom:1px solid var(--ch-rule);
  }
  .ch-sub{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--ch-accent);margin:0 0 4px}
  .ch-title{font:600 18px/1.2 ui-sans-serif,system-ui,sans-serif;margin:0;letter-spacing:-.01em;color:var(--ch-ink)}
  .ch-hud{display:flex;gap:22px;flex-wrap:wrap}
  .ch-stat{text-align:right;font-variant-numeric:tabular-nums}
  .ch-stat-k{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--ch-muted)}
  .ch-stat-v{font-size:19px;font-weight:700;color:var(--ch-ink);margin-top:2px}
  .ch-stat-u{font-size:10px;color:var(--ch-accent);margin-left:3px}
  .ch-stage{position:relative;width:100%}
  .ch-stage svg{width:100%;height:auto;display:block}
  .ch-caption{
    position:absolute;left:26px;bottom:16px;max-width:540px;
    background:rgba(14,19,26,.82);border:1px solid var(--ch-rule);border-radius:8px;
    padding:8px 12px;font-size:11.5px;line-height:1.45;color:var(--ch-ink);pointer-events:none;
  }
  .ch-caption strong{color:var(--ch-accent);margin-right:6px;text-transform:uppercase;letter-spacing:.08em;font-size:10.5px}
  .ch-controls{
    padding:14px 26px 20px;border-top:1px solid var(--ch-rule);
    display:flex;flex-direction:column;gap:12px;
  }
  .ch-cues{display:flex;gap:8px;flex-wrap:wrap}
  .ch-cue{
    font:600 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--ch-muted);background:transparent;border:1.5px solid var(--ch-rule);
    border-radius:999px;padding:5px 12px;cursor:pointer;transition:all .15s;
  }
  .ch-cue:hover{border-color:var(--ch-ink);color:var(--ch-ink)}
  .ch-cue[aria-pressed="true"]{background:var(--ch-accent);border-color:var(--ch-accent);color:#0b1117;font-weight:700}
  .ch-scrub-row{display:flex;align-items:center;gap:14px}
  .ch-btn{
    font:700 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;
    color:var(--ch-ink);background:transparent;border:1.5px solid var(--ch-ink);
    border-radius:999px;padding:5px 14px;cursor:pointer;
  }
  .ch-btn[aria-pressed="true"]{background:var(--ch-ink);color:var(--ch-bg)}
  .ch-slider{flex:1;accent-color:var(--ch-accent);cursor:pointer}
  .ch-time{font-size:11px;color:var(--ch-muted);min-width:92px;text-align:right;font-variant-numeric:tabular-nums}
  [data-chrome="stage-only"] .ch-header,
  [data-chrome="stage-only"] .ch-controls{display:none!important}
  [data-chrome="storefront"] .ch-scrub-row{display:none}
  @media (max-width:560px){
    .ch-header{padding:14px 16px}
    .ch-controls{padding:12px 16px}
    .ch-caption{position:static;margin:8px 16px 0;max-width:none}
  }
`;

function _readChTokens(el){
  if (typeof getComputedStyle === 'undefined') return {};
  const cs = getComputedStyle(el || document.documentElement);
  return {
    bg: cs.getPropertyValue('--ch-bg').trim() || '#0e131a',
    panel: cs.getPropertyValue('--ch-panel').trim() || '#151d28',
    ink: cs.getPropertyValue('--ch-ink').trim() || '#eef3f8',
    muted: cs.getPropertyValue('--ch-muted').trim() || '#7f91a6',
    rule: cs.getPropertyValue('--ch-rule').trim() || '#263445',
    accent: cs.getPropertyValue('--ch-accent').trim() || '#4fd1c5',
  };
}

function mountChoreo(cfg){
  const q = new URLSearchParams(location.search);
  const rawTarget = cfg.target || window.__EMDASH_MOTION_TARGET || null;
  const rootEl = typeof rawTarget === 'string' ? document.querySelector(rawTarget) : (rawTarget || document.body);
  const isStandalone = rootEl === document.body;
  const chrome = q.get('chrome') || cfg.chrome || (rootEl && rootEl.dataset && rootEl.dataset.chrome) || window.__EMDASH_MOTION_CHROME || (isStandalone ? 'full' : 'storefront');
  const mode = q.get('mode') || cfg.mode || (rootEl && rootEl.dataset && rootEl.dataset.mode) || 'autoplay';
  const [vbW, vbH] = cfg.viewBox || [1100, 560];
  const duration = cfg.duration || 12;
  const cues = cfg.cues || [
    { id: 'c1', label: '01 · Phase I',   range: [0.00, 0.33], summary: 'Initial state.' },
    { id: 'c2', label: '02 · Phase II',  range: [0.33, 0.66], summary: 'Transition state.' },
    { id: 'c3', label: '03 · Phase III', range: [0.66, 1.00], summary: 'Locked state.' },
  ];

  if (isStandalone) document.title = cfg.title || 'Choreographed Stage';
  if (q.has('vw')){
    document.documentElement.style.maxWidth = q.get('vw') + 'px';
    document.body.style.maxWidth = q.get('vw') + 'px';
    document.body.style.margin = '0';
  }
  if (!document.getElementById('ch-core-css')){
    const style = document.createElement('style');
    style.id = 'ch-core-css';
    style.textContent = CHOREO_CSS;
    document.head.appendChild(style);
  }
  if (isStandalone) document.body.classList.add('ch-standalone');
  else rootEl.classList.add('ch-root');
  rootEl.setAttribute('data-chrome', chrome);
  rootEl.setAttribute('data-mode', mode);

  const st = Object.assign({
    t: 0,
    mode,
    playing: !q.has('t') && !q.has('cue') && mode === 'autoplay' && !(typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches),
  }, cfg.state || {});

  if (q.has('cue')){
    const found = cues.find(c => c.id === q.get('cue') || c.label.toLowerCase().includes(q.get('cue').toLowerCase()));
    if (found) st.t = found.range[0];
  }
  if (q.has('t')){
    st.t = clamp01(+q.get('t') || 0);
  }

  rootEl.innerHTML = `
    <div class="ch-shell">
      <div class="ch-header">
        <div>
          <p class="ch-sub">${cfg.subtitle || 'CHOREOGRAPHED STAGE'}</p>
          <h1 class="ch-title">${cfg.title || 'Timeline Stage'}</h1>
        </div>
        <div class="ch-hud" id="stats"></div>
      </div>
      <div class="ch-stage stage">
        <svg id="fig" viewBox="0 0 ${vbW} ${vbH}" role="img" aria-label="${cfg.title || 'Choreographed Stage'}">
          <g id="art"></g>
        </svg>
        <div class="ch-caption" id="ch-caption"></div>
      </div>
      <div class="ch-controls">
        <div class="ch-cues" id="btns"></div>
        <div class="ch-scrub-row">
          <button class="ch-btn act" id="ch-play" aria-pressed="${st.playing}">${st.playing ? 'Pause' : 'Play'}</button>
          <input class="ch-slider" id="ch-slider" type="range" min="0" max="1" step="0.002" value="${st.t}">
          <div class="ch-time" id="ch-time">T = 0.00</div>
        </div>
      </div>
    </div>
  `;

  const byId = id => rootEl.querySelector('#' + id) || document.getElementById(id);
  const artEl = byId('art');
  const statsEl = byId('stats');
  const capEl = byId('ch-caption');
  const cuesEl = byId('btns');
  const playBtn = byId('ch-play');
  const sliderEl = byId('ch-slider');
  const timeEl = byId('ch-time');

  const cueBtns = cues.map(cue => {
    const b = document.createElement('button');
    b.className = 'ch-cue act';
    b.textContent = cue.label;
    b.onclick = () => {
      st.playing = false;
      playBtn.textContent = 'Play';
      playBtn.setAttribute('aria-pressed', 'false');
      animateTo(cue.range[0] + (cue.range[1] - cue.range[0]) * 0.35);
    };
    cuesEl.appendChild(b);
    return { cue, el: b };
  });

  const helpers = {
    width: vbW,
    height: vbH,
    tokens: _readChTokens(rootEl),
    clamp01,
    subRange,
    easeInOutCubic,
    easeOutExpo,
    lerp,
    lerpVec,
    lerpCam,
    project3D,
  };
  const ui = { st, rootEl, helpers };

  ui.render = () => {
    const t = clamp01(st.t);
    helpers.tokens = _readChTokens(rootEl);
    const activeCue = cues.find(c => t >= c.range[0] && t <= c.range[1]) || cues[cues.length - 1];
    artEl.innerHTML = cfg.scene(st, t, helpers);

    cueBtns.forEach(({ cue, el }) => {
      el.setAttribute('aria-pressed', String(cue === activeCue));
    });

    if (cfg.hud){
      const items = cfg.hud(st, t, activeCue) || [];
      statsEl.innerHTML = items.map(it =>
        `<div class="ch-stat"><div class="ch-stat-k">${it.label}</div><div class="ch-stat-v">${it.value}${it.unit ? `<span class="ch-stat-u">${it.unit}</span>` : ''}</div></div>`
      ).join('');
    }
    capEl.innerHTML = `<strong>${activeCue.label}</strong>${activeCue.summary || ''}`;
    sliderEl.value = String(t);
    timeEl.textContent = `T = ${t.toFixed(2)}`;
  };

  let scrubAnim = 0;
  function animateTo(targetT, ms = 550){
    const t0 = st.t, dtTotal = targetT - t0, id = ++scrubAnim;
    let el = 0, last = performance.now();
    const step = () => {
      if (id !== scrubAnim) return;
      const now = performance.now(), dt = Math.min(50, now - last); last = now; el += dt;
      const k = Math.min(1, el / ms), e = easeInOutCubic(k);
      st.t = clamp01(t0 + dtTotal * e);
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
  sliderEl.oninput = e => {
    st.playing = false;
    playBtn.textContent = 'Play';
    playBtn.setAttribute('aria-pressed', 'false');
    st.t = clamp01(+e.target.value);
    ui.render();
  };

  ui.updateScroll = () => {
    const vh = window.innerHeight || 1;
    const docSpan = document.documentElement.scrollHeight - vh;
    if (isStandalone && docSpan > 4){
      st.t = clamp01(window.scrollY / docSpan);
    } else {
      const r = rootEl.getBoundingClientRect();
      const span = Math.max(1, vh + r.height);
      st.t = clamp01((vh - r.top) / span);
    }
    ui.render();
  };
  if (mode === 'scroll' && !q.has('t') && !q.has('cue')){
    addEventListener('scroll', ui.updateScroll, { passive: true });
    addEventListener('resize', ui.updateScroll);
  }

  ui.setTime = tNorm => {
    st.playing = false;
    cancelAnimationFrame(rafId);
    st.t = clamp01(+tNorm || 0);
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

  if (mode === 'scroll' && !q.has('t') && !q.has('cue')) ui.updateScroll();
  else ui.render();

  if (typeof MutationObserver !== 'undefined'){
    new MutationObserver(() => {
      helpers.tokens = _readChTokens(rootEl);
      if (!st.playing) ui.render();
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme', 'data-preset'] });
  }
  if (st.playing){ lastFrame = performance.now(); tick(); }
  return ui;
}
