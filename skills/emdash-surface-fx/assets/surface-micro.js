/*
 * emdash-surface-fx / assets/surface-micro.js
 * Lightweight, zero-dependency surface micro-interactions for EmDash Astro & DinkusKit storefronts:
 *   1. mountHoverTilt (alias mountTilt): 25-line CSS-variable 3D card tilt + specular glare
 *   2. mountObstacleText: Pretext-style canvas-measured obstacle-aware editorial line layout
 *   3. mountNumberTicker: NumberFlow-style tabular-nums rolling currency/order counter
 *   4. mountRoughCallout: RoughNotation-style SVG hand-sketched underline, box, and circle annotations
 */

/* 1. 25-line Vanilla CSS-Variable 3D Card Tilt (mountHoverTilt / mountTilt) */
function mountHoverTilt(target, opts) {
  const options = opts || {};
  const maxDeg = options.maxDeg || 8;
  const nodes =
    typeof target === 'string'
      ? Array.from(document.querySelectorAll(target))
      : target instanceof Element
      ? [target]
      : Array.from(target || []);

  nodes.forEach(card => {
    card.style.setProperty('--rx', '0deg');
    card.style.setProperty('--ry', '0deg');
    card.style.setProperty('--glare-x', '50%');
    card.style.setProperty('--glare-y', '50%');
    card.addEventListener('pointermove', e => {
      if (typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      const r = card.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      card.style.setProperty('--rx', `${((0.5 - py) * maxDeg * 2).toFixed(2)}deg`);
      card.style.setProperty('--ry', `${((px - 0.5) * maxDeg * 2).toFixed(2)}deg`);
      card.style.setProperty('--glare-x', `${(px * 100).toFixed(1)}%`);
      card.style.setProperty('--glare-y', `${(py * 100).toFixed(1)}%`);
    });
    card.addEventListener('pointerleave', () => {
      card.style.setProperty('--rx', '0deg');
      card.style.setProperty('--ry', '0deg');
    });
  });
  return nodes;
}

const mountTilt = mountHoverTilt;

/* 2. Pretext-Inspired Zero-Reflow Obstacle Text Layout (mountObstacleText) */
let _measureCtx = null;
function _measureWordWidth(word, font) {
  try {
    if (!_measureCtx && typeof document !== 'undefined') {
      const c = document.createElement('canvas');
      _measureCtx = c.getContext('2d');
    }
    if (_measureCtx) {
      _measureCtx.font = font || '400 15px system-ui, -apple-system, sans-serif';
      return _measureCtx.measureText(word).width;
    }
  } catch (_) {}
  return word.length * 8.2;
}

function mountObstacleText(target, opts) {
  const options = opts || {};
  const host = typeof target === 'string' ? document.querySelector(target) : target;
  if (!host) return null;

  const text = String(
    options.text ||
      host.getAttribute('data-obstacle-copy') ||
      host.textContent ||
      ''
  )
    .replace(/\s+/g, ' ')
    .trim();
  const words = text.split(' ').filter(Boolean);
  const lineHeight = options.lineHeight || 24;
  const font = options.font || '400 14.5px Georgia, "Iowan Old Style", serif';
  const spaceW = _measureWordWidth(' ', font);
  const wordWidths = words.map(w => _measureWordWidth(w, font));

  const obstacle = {
    x: options.obstacleX !== undefined ? options.obstacleX : 0.76,
    y: options.obstacleY !== undefined ? options.obstacleY : 66,
    r: options.obstacleRadius !== undefined ? options.obstacleRadius : 64,
    side: options.obstacleSide || 'auto',
  };

  const layout = () => {
    const wrapEl =
      orbElRef && (orbElRef.offsetParent || host.parentElement)
        ? orbElRef.offsetParent || host.parentElement
        : host.parentElement || host;
    const rect = host.getBoundingClientRect();
    const totalW = Math.max(220, Math.floor(rect.width || options.width || 520));
    let rawCx = obstacle.x <= 1.2 ? obstacle.x * totalW : obstacle.x;
    const obsR = obstacle.r;
    const minCx = Math.min(totalW * 0.5, Math.max(36, obsR * 0.75));
    const maxCx = Math.max(totalW * 0.5, totalW - Math.max(36, obsR * 0.75));
    const obsCx = Math.max(minCx, Math.min(maxCx, rawCx));
    const obsCy = Math.max(28, obstacle.y);

    const lines = [];
    let wordIdx = 0;
    let lineIndex = 0;

    while (wordIdx < words.length && lineIndex < 40) {
      const lineTop = lineIndex * lineHeight;
      const lineBottom = lineTop + lineHeight;
      /* Vertical interval [lineTop, lineBottom] intersection against [obsCy - r, obsCy + r] */
      const closestY = Math.max(lineTop, Math.min(obsCy, lineBottom));
      const dy = Math.abs(obsCy - closestY);
      let indentLeft = 0;
      let indentRight = 0;

      if (dy < obsR) {
        const chordHalf = Math.sqrt(Math.max(0, obsR * obsR - dy * dy));
        const pad = 14;
        const effectiveSide =
          obstacle.side === 'left' || obstacle.side === 'right'
            ? obstacle.side
            : obsCx < totalW * 0.5
            ? 'left'
            : 'right';

        if (effectiveSide === 'left') {
          indentLeft = Math.min(totalW * 0.62, Math.max(0, obsCx + chordHalf + pad));
        } else {
          indentRight = Math.min(totalW * 0.62, Math.max(0, totalW - (obsCx - chordHalf - pad)));
        }
      }

      const availW = Math.max(88, totalW - indentLeft - indentRight);
      const lineWords = [];
      let usedW = 0;

      while (wordIdx < words.length) {
        const wLen = wordWidths[wordIdx];
        const nextW = lineWords.length === 0 ? wLen : usedW + spaceW + wLen;
        if (nextW > availW && lineWords.length > 0) break;
        lineWords.push(words[wordIdx]);
        usedW = nextW;
        wordIdx++;
      }

      lines.push({
        text: lineWords.join(' '),
        top: lineTop,
        left: Math.round(indentLeft),
        right: Math.round(indentRight),
        availW: Math.round(availW),
      });
      lineIndex++;
    }

    const totalH = lines.length * lineHeight + 8;
    host.style.position = 'relative';
    host.style.minHeight = `${totalH}px`;
    host.innerHTML = lines
      .map(
        l =>
          `<div class="surface-obstacle-line" style="padding-left:${l.left}px;padding-right:${l.right}px;height:${lineHeight}px;line-height:${lineHeight}px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${l.text}</div>`
      )
      .join('');

    /* Keep draggable orb clamped inside wrapEl when resizing across desktop/mobile breakpoints */
    if (orbElRef && orbElRef.style.left && wrapEl) {
      const wrapRect = wrapEl.getBoundingClientRect();
      const orbW = orbElRef.offsetWidth || 112;
      const orbH = orbElRef.offsetHeight || 112;
      const halfW = orbW * 0.5;
      const halfH = orbH * 0.5;
      if (wrapRect.width > orbW + 12) {
        const curLeft = parseFloat(orbElRef.style.left) || 0;
        const clampedLeft = Math.max(6, Math.min(wrapRect.width - orbW - 6, curLeft));
        orbElRef.style.left = `${Math.round(clampedLeft)}px`;
      }
      const maxH = Math.max(wrapRect.height, totalH + 24);
      if (maxH > orbH + 12 && orbElRef.style.top) {
        const curTop = parseFloat(orbElRef.style.top) || 0;
        const clampedTop = Math.max(6, Math.min(maxH - orbH - 6, curTop));
        orbElRef.style.top = `${Math.round(clampedTop)}px`;
      }
    }

    return { lineCount: lines.length, totalW, obsCx, obsCy };
  };

  const orbEl =
    typeof options.obstacleEl === 'string'
      ? document.querySelector(options.obstacleEl)
      : options.obstacleEl instanceof Element
      ? options.obstacleEl
      : null;
  const orbElRef = orbEl;

  const initial = layout();

  const api = {
    el: host,
    layout,
    getObstacle: () => ({ ...obstacle }),
    setObstacle(nextObs) {
      if (!nextObs) return;
      if (nextObs.x !== undefined) obstacle.x = nextObs.x;
      if (nextObs.y !== undefined) obstacle.y = nextObs.y;
      if (nextObs.r !== undefined) obstacle.r = nextObs.r;
      if (nextObs.side !== undefined) obstacle.side = nextObs.side;
      return layout();
    },
    stats: initial,
  };

  /* Optional interactive pointer-drag wiring for obstacle element */
  if (orbEl) {
    const wrapEl = orbEl.offsetParent || host.parentElement || host;
    let dragging = false;
    let grabDx = 0;
    let grabDy = 0;

    orbEl.addEventListener('pointerdown', e => {
      dragging = true;
      orbEl.classList.add('is-dragging');
      if (orbEl.setPointerCapture) {
        try {
          orbEl.setPointerCapture(e.pointerId);
        } catch (_) {}
      }
      const orbRect = orbEl.getBoundingClientRect();
      grabDx = e.clientX - (orbRect.left + orbRect.width * 0.5);
      grabDy = e.clientY - (orbRect.top + orbRect.height * 0.5);
      e.preventDefault();
    });

    orbEl.addEventListener('pointermove', e => {
      if (!dragging) return;
      const wrapRect = wrapEl.getBoundingClientRect();
      const hostRect = host.getBoundingClientRect();
      const orbW = orbEl.offsetWidth || 112;
      const orbH = orbEl.offsetHeight || 112;
      const halfW = orbW * 0.5;
      const halfH = orbH * 0.5;

      const cxWrap = Math.max(
        halfW + 6,
        Math.min(wrapRect.width - halfW - 6, e.clientX - wrapRect.left - grabDx)
      );
      const cyWrap = Math.max(
        halfH + 6,
        Math.min(wrapRect.height - halfH - 6, e.clientY - wrapRect.top - grabDy)
      );

      orbEl.style.right = 'auto';
      orbEl.style.left = `${Math.round(cxWrap - halfW)}px`;
      orbEl.style.top = `${Math.round(cyWrap - halfH)}px`;

      const hostOffsetX = hostRect.left - wrapRect.left;
      const hostOffsetY = hostRect.top - wrapRect.top;
      const relX = (cxWrap - hostOffsetX) / Math.max(180, hostRect.width || wrapRect.width || 520);
      api.setObstacle({
        x: Math.max(0.08, Math.min(0.92, relX)),
        y: cyWrap - hostOffsetY,
        side: 'auto',
      });
    });

    const stopDrag = e => {
      if (!dragging) return;
      dragging = false;
      orbEl.classList.remove('is-dragging');
      if (e && orbEl.releasePointerCapture) {
        try {
          orbEl.releasePointerCapture(e.pointerId);
        } catch (_) {}
      }
    };
    orbEl.addEventListener('pointerup', stopDrag);
    orbEl.addEventListener('pointercancel', stopDrag);
  }

  return api;
}

/* 3. NumberFlow-Style Tabular Number Ticker (mountNumberTicker) */
function mountNumberTicker(target, opts) {
  const options = opts || {};
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) return null;

  const decimals = options.decimals !== undefined ? options.decimals : 2;
  const prefix = options.prefix !== undefined ? options.prefix : '$';
  const suffix = options.suffix !== undefined ? options.suffix : '';
  const duration = options.duration || 520;
  let currentVal = options.value !== undefined ? Number(options.value) : 60.0;
  let rafId = 0;

  el.style.fontVariantNumeric = 'tabular-nums';

  const formatVal = v => {
    const num = Number(v) || 0;
    const fixed = num.toFixed(decimals);
    const parts = fixed.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return `${prefix}${parts.join('.')}${suffix}`;
  };

  const renderImmediate = v => {
    currentVal = Number(v) || 0;
    el.textContent = formatVal(currentVal);
    el.setAttribute('data-ticker-value', currentVal.toFixed(decimals));
  };

  const animateTo = nextVal => {
    const targetVal = Number(nextVal) || 0;
    if (rafId) cancelAnimationFrame(rafId);

    const reduced =
      typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || duration <= 0) {
      renderImmediate(targetVal);
      return;
    }

    const startVal = currentVal;
    const startTime = performance.now();

    const step = now => {
      const p = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const val = startVal + (targetVal - startVal) * eased;
      el.textContent = formatVal(val);
      if (p < 1) {
        rafId = requestAnimationFrame(step);
      } else {
        renderImmediate(targetVal);
      }
    };
    rafId = requestAnimationFrame(step);
  };

  renderImmediate(currentVal);
  return {
    el,
    setValue: animateTo,
    setImmediate: renderImmediate,
    getValue: () => currentVal,
  };
}

/* 4. RoughNotation-Style Hand-Drawn SVG Callout (mountRoughCallout) */
function mountRoughCallout(target, opts) {
  const options = opts || {};
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) return null;

  const type = options.type || el.getAttribute('data-rough-type') || 'underline';
  const color = options.color || 'var(--color-accent, #c84b31)';
  const strokeWidth = options.strokeWidth || 2.4;
  const duration = options.duration !== undefined ? options.duration : 780;

  el.style.position = el.style.position || 'relative';
  el.style.display = el.style.display || 'inline-block';

  const existing = el.querySelector('svg[data-rough-svg]');
  if (existing) existing.remove();

  const w = Math.max(48, el.offsetWidth || options.width || 130);
  const h = Math.max(20, el.offsetHeight || options.height || 26);

  let path1D = '';
  let path2D = '';
  let fallbackLen = 220;
  let actualStrokeW = strokeWidth;
  let strokeOpacity1 = '0.96';
  let strokeOpacity2 = '0.84';

  if (type === 'box') {
    /* Pass 1 & Pass 2 separate hand-sketched marker box strokes */
    path1D = `M 1.5,3 L ${w - 1.5},1.8 L ${w - 1},${h - 1.5} L 2.5,${h - 1} Z`;
    path2D = `M 3.5,1.4 L ${w - 2.5},3.2 L ${w - 2.2},${h - 2.6} L 1.2,${h - 2.4} Z`;
    fallbackLen = Math.round((w + h) * 2.08);
  } else if (type === 'circle') {
    /* Pass 1 & Pass 2 separate hand-sketched marker ellipse strokes */
    const cy = (h / 2 + 1).toFixed(1);
    const rx1 = (w / 2 + 5).toFixed(1);
    const ry1 = (h / 2 + 4.5).toFixed(1);
    const rx2 = (w / 2 + 3.2).toFixed(1);
    const ry2 = (h / 2 + 3).toFixed(1);
    path1D = `M -2,${cy} A ${rx1},${ry1} 0 1,0 ${w + 2},${cy} A ${rx1},${ry1} 0 1,0 -2,${cy}`;
    path2D = `M 0,${cy} A ${rx2},${ry2} 0 1,1 ${w},${cy} A ${rx2},${ry2} 0 1,1 0,${cy}`;
    fallbackLen = Math.round((w + h) * 1.75);
  } else if (type === 'highlight') {
    /* Pass 1 & Pass 2 separate chisel marker highlight sweeps */
    const ym1 = (h * 0.52).toFixed(1);
    const ym2 = (h * 0.58).toFixed(1);
    path1D = `M 1,${ym1} Q ${(w * 0.5).toFixed(1)},${(h * 0.44).toFixed(1)} ${w - 1},${ym1}`;
    path2D = `M 2,${ym2} L ${w - 2},${ym2}`;
    actualStrokeW = Math.max(12, Math.round(h * 0.68));
    strokeOpacity1 = '0.24';
    strokeOpacity2 = '0.20';
    fallbackLen = Math.round(w * 1.04);
  } else {
    /* Pass 1 & Pass 2 separate hand-sketched marker underline strokes */
    const y1 = (h - 1.2).toFixed(1);
    const y2 = (h + 1.0).toFixed(1);
    const midX = (w * 0.52).toFixed(1);
    path1D = `M 1,${y1} Q ${midX},${(h - 3.8).toFixed(1)} ${w - 1},${y1}`;
    path2D = `M 2.5,${y2} Q ${midX},${(h + 2.4).toFixed(1)} ${w - 2},${(h - 0.4).toFixed(1)}`;
    fallbackLen = Math.round(w * 1.05);
  }

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('data-rough-svg', type);
  svg.setAttribute('viewBox', `0 0 ${w} ${h + 6}`);
  svg.setAttribute('aria-hidden', 'true');
  svg.style.cssText =
    'position:absolute;left:-4px;top:-2px;width:calc(100% + 8px);height:calc(100% + 7px);pointer-events:none;overflow:visible;z-index:2;';
  svg.innerHTML =
    `<path data-rough-path="1" d="${path1D}" fill="none" stroke="${color}" stroke-opacity="${strokeOpacity1}" stroke-width="${actualStrokeW}" stroke-linecap="round" stroke-linejoin="round" />` +
    `<path data-rough-path="2" d="${path2D}" fill="none" stroke="${color}" stroke-opacity="${strokeOpacity2}" stroke-width="${(actualStrokeW * 0.88).toFixed(2)}" stroke-linecap="round" stroke-linejoin="round" />`;
  el.appendChild(svg);

  const path1El = svg.querySelector('path[data-rough-path="1"]');
  const path2El = svg.querySelector('path[data-rough-path="2"]');

  const measureRealLen = (p, fb) => {
    try {
      if (p && typeof p.getTotalLength === 'function') {
        const total = Math.ceil(p.getTotalLength() || fb);
        if (total > 0 && Number.isFinite(total)) return total;
      }
    } catch (_) {}
    return fb;
  };

  const len1 = measureRealLen(path1El, fallbackLen);
  const len2 = measureRealLen(path2El, fallbackLen);

  if (path1El) {
    path1El.setAttribute('stroke-dasharray', String(len1));
    path1El.setAttribute('stroke-dashoffset', '0');
  }
  if (path2El) {
    path2El.setAttribute('stroke-dasharray', String(len2));
    path2El.setAttribute('stroke-dashoffset', '0');
  }

  let activeAnims = [];
  let pendingTimers = [];

  const clearPending = () => {
    activeAnims.forEach(a => {
      if (a && typeof a.cancel === 'function') {
        try {
          a.cancel();
        } catch (_) {}
      }
    });
    activeAnims = [];
    pendingTimers.forEach(tId => clearTimeout(tId));
    pendingTimers = [];
  };

  const draw = extraDelayMs => {
    if (!path1El || !path2El) return;
    const baseDelay = typeof extraDelayMs === 'number' && extraDelayMs > 0 ? extraDelayMs : 0;
    clearPending();

    const reduced =
      typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || duration <= 0) {
      [path1El, path2El].forEach(p => {
        p.style.transition = 'none';
        p.style.strokeDashoffset = '0';
        p.setAttribute('stroke-dashoffset', '0');
      });
      return;
    }

    const pass1Dur = 780;
    const pass2Dur = 720;
    const pass2OffsetDelay = 560;
    const easeCurve = 'cubic-bezier(0.4, 0.0, 0.2, 1)';

    path1El.style.transition = 'none';
    path2El.style.transition = 'none';
    path1El.style.strokeDashoffset = String(len1);
    path1El.setAttribute('stroke-dashoffset', String(len1));
    path2El.style.strokeDashoffset = String(len2);
    path2El.setAttribute('stroke-dashoffset', String(len2));
    void svg.getBoundingClientRect();

    if (typeof path1El.animate === 'function') {
      const a1 = path1El.animate(
        [{ strokeDashoffset: len1 }, { strokeDashoffset: 0 }],
        {
          duration: pass1Dur,
          delay: baseDelay,
          easing: easeCurve,
          fill: 'both',
        }
      );
      a1.onfinish = () => {
        path1El.style.strokeDashoffset = '0';
        path1El.setAttribute('stroke-dashoffset', '0');
      };
      const a2 = path2El.animate(
        [{ strokeDashoffset: len2 }, { strokeDashoffset: 0 }],
        {
          duration: pass2Dur,
          delay: baseDelay + pass2OffsetDelay,
          easing: easeCurve,
          fill: 'both',
        }
      );
      a2.onfinish = () => {
        path2El.style.strokeDashoffset = '0';
        path2El.setAttribute('stroke-dashoffset', '0');
      };
      activeAnims.push(a1, a2);
    } else {
      const t1 = setTimeout(() => {
        path1El.style.transition = `stroke-dashoffset ${pass1Dur}ms ${easeCurve}`;
        path1El.style.strokeDashoffset = '0';
        path1El.setAttribute('stroke-dashoffset', '0');
      }, baseDelay);
      const t2 = setTimeout(() => {
        path2El.style.transition = `stroke-dashoffset ${pass2Dur}ms ${easeCurve}`;
        path2El.style.strokeDashoffset = '0';
        path2El.setAttribute('stroke-dashoffset', '0');
      }, baseDelay + pass2OffsetDelay);
      pendingTimers.push(t1, t2);
    }
  };

  /* Automatically animate on live load (skip animation when ?t= probe is active so screenshots capture full stroke) */
  const isProbeSnap =
    typeof location !== 'undefined' && new URLSearchParams(location.search).has('t');
  if (!isProbeSnap && options.animate !== false) {
    draw(options.delay || 0);
  }

  if (options.replayOnHover !== false) {
    el.addEventListener('pointerenter', () => draw(0));
    el.addEventListener('click', () => draw(0));
  }

  return { el, svg, pathEl: path1El, path2El, len1, len2, draw, replay: draw };
}

if (typeof window !== 'undefined') {
  window.mountHoverTilt = mountHoverTilt;
  window.mountTilt = mountTilt;
  window.mountObstacleText = mountObstacleText;
  window.mountNumberTicker = mountNumberTicker;
  window.mountRoughCallout = mountRoughCallout;
}
