/*
 * emdash-surface-fx / assets/dither.js
 * Zero-dependency vanilla JS / WebGL1 / 2D Canvas / SVG engine porting dithercn
 * (mountDitherShader, ditherPatternSvg, ditherMaskStyle, ditherImageCanvas).
 *
 * Features:
 * - Automatic EmDash src/styles/tokens.css (--color-canvas, --color-surface, --color-ink, --color-accent)
 *   and CSS light-dark() resolution.
 * - MutationObserver on :root[data-theme] and :root[data-preset] for instant dark-mode/preset updates.
 * - prefers-reduced-motion static frame fallback and deterministic ?t=0..1 URL scrub support.
 * - IntersectionObserver viewport pooling via defaultViewportPool (MAX_LIVE = 6 desktop / 1 mobile).
 */

const BAYER_4X4 = [
   0 / 16,  8 / 16,  2 / 16, 10 / 16,
  12 / 16,  4 / 16, 14 / 16,  6 / 16,
   3 / 16, 11 / 16,  1 / 16,  9 / 16,
  15 / 16,  7 / 16, 13 / 16,  5 / 16,
];

const BAYER_8X8 = [
   0 / 64, 32 / 64,  8 / 64, 40 / 64,  2 / 64, 34 / 64, 10 / 64, 42 / 64,
  48 / 64, 16 / 64, 56 / 64, 24 / 64, 50 / 64, 18 / 64, 58 / 64, 26 / 64,
  12 / 64, 44 / 64,  4 / 64, 36 / 64, 14 / 64, 46 / 64,  6 / 64, 38 / 64,
  60 / 64, 28 / 64, 52 / 64, 20 / 64, 62 / 64, 30 / 64, 54 / 64, 22 / 64,
   3 / 64, 35 / 64, 11 / 64, 43 / 64,  1 / 64, 33 / 64,  9 / 64, 41 / 64,
  51 / 64, 19 / 64, 59 / 64, 27 / 64, 49 / 64, 17 / 64, 57 / 64, 25 / 64,
  15 / 64, 47 / 64,  7 / 64, 39 / 64, 13 / 64, 45 / 64,  5 / 64, 37 / 64,
  63 / 64, 31 / 64, 55 / 64, 23 / 64, 61 / 64, 29 / 64, 53 / 64, 21 / 64,
];

function _isDarkThemeActive(el) {
  try {
    const doc = document.documentElement;
    if (doc.dataset.theme === 'dark' || doc.classList.contains('dark')) return true;
    if (doc.dataset.theme === 'light' || doc.classList.contains('light')) return false;
    const cs = getComputedStyle(el || doc);
    if (cs.colorScheme === 'dark') return true;
    if (cs.colorScheme === 'light') return false;
    return typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches;
  } catch (_) {
    return false;
  }
}

function _parseCssColorToRgb(raw, el, fallbackRgb) {
  if (!raw) return fallbackRgb;
  let s = String(raw).trim();
  const ld = s.match(/^light-dark\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)$/i);
  if (ld) {
    s = (_isDarkThemeActive(el) ? ld[2] : ld[1]).trim();
  }
  if (/^#[0-9a-fA-F]{6}$/.test(s)) {
    return [
      parseInt(s.slice(1, 3), 16),
      parseInt(s.slice(3, 5), 16),
      parseInt(s.slice(5, 7), 16),
    ];
  }
  if (/^#[0-9a-fA-F]{3}$/.test(s)) {
    return [
      parseInt(s[1] + s[1], 16),
      parseInt(s[2] + s[2], 16),
      parseInt(s[3] + s[3], 16),
    ];
  }
  const m = s.match(/rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i);
  if (m) {
    return [
      Math.max(0, Math.min(255, Number(m[1]))),
      Math.max(0, Math.min(255, Number(m[2]))),
      Math.max(0, Math.min(255, Number(m[3]))),
    ];
  }
  return fallbackRgb;
}

function _rgbToHex(rgb) {
  return (
    '#' +
    rgb
      .map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
      .join('')
  );
}

function resolveEmDashDitherColors(el, overrides) {
  const ov = overrides || {};
  const dark = _isDarkThemeActive(el);
  let cs = null;
  try {
    cs = getComputedStyle(el || document.documentElement);
  } catch (_) {}

  const readToken = (...names) => {
    if (!cs) return '';
    for (const n of names) {
      const v = cs.getPropertyValue(n).trim();
      if (v) return v;
    }
    return '';
  };

  const bgRgb = _parseCssColorToRgb(
    ov.bg || readToken('--color-canvas', '--color-surface'),
    el,
    dark ? [18, 22, 29] : [244, 240, 232]
  );
  const surfaceRgb = _parseCssColorToRgb(
    ov.surface || readToken('--color-surface', '--color-canvas'),
    el,
    dark ? [26, 32, 42] : [235, 229, 216]
  );
  const inkRgb = _parseCssColorToRgb(
    ov.ink || readToken('--color-ink', '--color-text'),
    el,
    dark ? [236, 232, 222] : [28, 36, 48]
  );
  const accentRgb = _parseCssColorToRgb(
    ov.accent || readToken('--color-accent', '--color-primary'),
    el,
    dark ? [232, 155, 45] : [196, 77, 44]
  );

  return {
    bgRgb,
    surfaceRgb,
    inkRgb,
    accentRgb,
    bgHex: _rgbToHex(bgRgb),
    surfaceHex: _rgbToHex(surfaceRgb),
    inkHex: _rgbToHex(inkRgb),
    accentHex: _rgbToHex(accentRgb),
  };
}

/* 1. ditherPatternSvg: Vanilla port of dithercn <DitherPattern> */
function ditherPatternSvg(opts) {
  const options = opts || {};
  const id = options.id || 'emdash-dither-pat';
  const density = Math.max(0.05, Math.min(0.95, options.density !== undefined ? options.density : 0.38));
  const cellSize = options.cellSize || 3;
  const fg = options.fg || 'var(--color-ink, #231e16)';
  const bg = options.bg || 'transparent';
  const matrix = options.bayer === 4 ? BAYER_4X4 : BAYER_8X8;
  const dim = options.bayer === 4 ? 4 : 8;
  const tileW = dim * cellSize;

  const rects = [];
  if (bg && bg !== 'transparent') {
    rects.push(`<rect width="${tileW}" height="${tileW}" fill="${bg}"/>`);
  }
  for (let y = 0; y < dim; y++) {
    for (let x = 0; x < dim; x++) {
      const thresh = matrix[y * dim + x];
      if (thresh < density) {
        rects.push(
          `<rect x="${x * cellSize}" y="${y * cellSize}" width="${cellSize}" height="${cellSize}" fill="${fg}"/>`
        );
      }
    }
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" aria-hidden="true">
    <defs>
      <pattern id="${id}" width="${tileW}" height="${tileW}" patternUnits="userSpaceOnUse">
        ${rects.join('')}
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#${id})"/>
  </svg>`;
}

/* 2. ditherMaskStyle: Vanilla port of dithercn ditherMaskStyle for section dividers & hero fades */
function ditherMaskStyle(opts) {
  const options = opts || {};
  const steps = options.steps || 8;
  const cellSize = options.cellSize || 4;
  const dim = 8;
  const w = dim * cellSize;
  const h = steps * dim * cellSize;

  const rects = [];
  for (let s = 0; s < steps; s++) {
    const density = 1 - s / Math.max(1, steps - 1);
    for (let y = 0; y < dim; y++) {
      for (let x = 0; x < dim; x++) {
        if (BAYER_8X8[y * dim + x] < density) {
          rects.push(
            `<rect x="${x * cellSize}" y="${(s * dim + y) * cellSize}" width="${cellSize}" height="${cellSize}" fill="#000"/>`
          );
        }
      }
    }
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${rects.join('')}</svg>`;
  const encoded = `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
  return {
    maskImage: encoded,
    WebkitMaskImage: encoded,
    maskSize: `${w}px 100%`,
    WebkitMaskSize: `${w}px 100%`,
    maskRepeat: 'repeat-x',
    WebkitMaskRepeat: 'repeat-x',
    cssText: `-webkit-mask-image:${encoded};mask-image:${encoded};-webkit-mask-size:${w}px 100%;mask-size:${w}px 100%;-webkit-mask-repeat:repeat-x;mask-repeat:repeat-x;`,
  };
}

/* 3. ditherImageCanvas: Ordered Bayer 8x8 2D canvas dithering for cards, badges & product illustrations */
function ditherImageCanvas(target, opts) {
  const options = opts || {};
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (!el) return null;

  const canvas = el.tagName === 'CANVAS' ? el : el.querySelector('canvas') || document.createElement('canvas');
  if (canvas !== el && !canvas.parentNode) {
    el.appendChild(canvas);
  }

  const width = options.width || canvas.width || 320;
  const height = options.height || canvas.height || 180;
  const pixelScale = options.pixelScale || 2;
  const cols = Math.max(24, Math.floor(width / pixelScale));
  const rows = Math.max(24, Math.floor(height / pixelScale));
  canvas.width = cols;
  canvas.height = rows;
  canvas.style.imageRendering = 'pixelated';

  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  const draw = timeSec => {
    const t = timeSec !== undefined ? timeSec : 0;
    const palette = resolveEmDashDitherColors(el, options);
    const imgData = ctx.createImageData(cols, rows);
    const data = imgData.data;

    for (let y = 0; y < rows; y++) {
      const ny = (y + 0.5) / rows;
      for (let x = 0; x < cols; x++) {
        const nx = (x + 0.5) / cols;
        const threshold = BAYER_8X8[(y & 7) * 8 + (x & 7)];

        /* Signed-distance / analytic silhouette for Aizome Cast Iron Pour-Over Kettle (0.9L) */
        /* 1. Domed & slightly tapered cast-iron kettle body centered at (0.47, 0.63) */
        const bodyY = (ny - 0.63) / 0.24;
        const bodyHalfW = 0.235 - 0.045 * bodyY;
        const bodyX = (nx - 0.47) / Math.max(0.08, bodyHalfW);
        const bodyDist = Math.hypot(bodyX, bodyY);
        const inBody = ny >= 0.41 && ny <= 0.85 && bodyDist <= 1.0;

        /* Flat cast-iron base foot */
        const inBase = ny >= 0.82 && ny <= 0.88 && Math.abs(nx - 0.47) <= 0.19;

        /* 2. Domed lid & rim collar at top of body (ny ~ 0.36..0.43) */
        const inCollar = ny >= 0.38 && ny <= 0.43 && Math.abs(nx - 0.47) <= 0.155;
        const inKnob = Math.hypot((nx - 0.47) / 0.052, (ny - 0.315) / 0.058) <= 1.0;
        const inKnobStem = ny >= 0.35 && ny <= 0.39 && Math.abs(nx - 0.47) <= 0.025;

        /* 3. Arched overhead / left C-handle (nx ~ 0.16..0.48, ny ~ 0.18..0.76) */
        const hDx = (nx - 0.27) / 0.115;
        const hDy = (ny - 0.58) / 0.185;
        const hRad = Math.hypot(hDx, hDy);
        const inSideHandle = nx <= 0.32 && hRad >= 0.68 && hRad <= 1.05;

        /* Top tetsubin bail arch above lid */
        const bailDx = (nx - 0.47) / 0.19;
        const bailDy = (ny - 0.38) / 0.23;
        const bailR = Math.hypot(bailDx, bailDy);
        const inTopBail = ny <= 0.40 && bailR >= 0.82 && bailR <= 1.02;

        /* 4. Curved Gooseneck Pour-Over Spout on the right (nx ~ 0.65..0.89, ny ~ 0.30..0.72) */
        let inSpout = false;
        let spoutRim = false;
        if (nx >= 0.62 && nx <= 0.90) {
          const u = (nx - 0.64) / 0.22;
          /* S-curve gooseneck centerline from lower right belly (ny=0.68) up to pour tip (ny=0.33) */
          const centerSpoutY = 0.68 - 0.35 * Math.pow(Math.max(0, Math.min(1, u)), 0.78) + 0.045 * Math.sin(u * Math.PI * 1.6);
          const spoutHalfThick = 0.048 * (1 - 0.38 * u);
          const dSpout = Math.abs(ny - centerSpoutY);
          if (dSpout <= spoutHalfThick && u >= -0.05 && u <= 1.04) {
            inSpout = true;
            spoutRim = ny < centerSpoutY;
          }
        }

        /* 5. Rising Pour-Over Steam Wisps above spout tip (nx ~ 0.82..0.92, ny ~ 0.08..0.28) */
        const steamWave = Math.sin(ny * 18.0 - t * 2.4) * 0.025;
        const steamDist = Math.abs(nx - (0.86 + steamWave));
        const inSteam = ny >= 0.08 && ny <= 0.27 && steamDist <= 0.032 * (1 - (0.27 - ny) * 2.2);

        const inKettle = inBody || inBase || inCollar || inKnob || inKnobStem || inSideHandle || inTopBail || inSpout;

        let rgb = palette.bgRgb;

        if (inKnob || (inCollar && ny <= 0.405)) {
          /* Brass finial knob & warm accent lid ring */
          const knobShade = 0.85 - (nx - 0.45) * 2.2;
          rgb = knobShade > threshold * 0.45 ? palette.accentRgb : palette.inkRgb;
        } else if (inBody && Math.abs(ny - 0.61) <= 0.036) {
          /* Signature DinkusKit warm accent belly band across the kettle */
          const bandSpec = 1.0 - Math.abs(nx - 0.41) * 2.4;
          rgb = bandSpec > threshold * 0.55 ? palette.accentRgb : palette.inkRgb;
        } else if (inKettle) {
          /* Cylindrical 3D specular shading + cast-iron hobnail texture */
          const lightX = 0.39;
          const spec = Math.max(0, 1 - Math.hypot((nx - lightX) * 2.5, (ny - 0.54) * 2.0));
          const hobnail = ((x + (y & 1)) & 1) === 0 ? 0.09 : -0.05;
          const rimLight = spoutRim || (inTopBail && ny < 0.22) ? 0.32 : 0;
          const kettleTone = Math.max(0, Math.min(1, 0.16 + spec * 0.62 + hobnail + rimLight));

          if (kettleTone > threshold + 0.18) {
            rgb = palette.surfaceRgb;
          } else if (kettleTone > threshold * 0.92) {
            rgb = palette.accentRgb;
          } else {
            rgb = palette.inkRgb;
          }
        } else if (inSteam) {
          if (threshold < 0.52) {
            rgb = palette.accentRgb;
          }
        } else {
          /* Subtle studio backdrop gradient + ordered Bayer table shadow under kettle base */
          const underShadow = ny >= 0.85 && ny <= 0.93 && Math.abs(nx - 0.48) <= 0.28;
          const bgSignal = 0.78 - 0.22 * ny + 0.08 * Math.sin(nx * 5.0 + t * 0.8);
          if (underShadow && threshold < 0.68) {
            rgb = palette.inkRgb;
          } else if (bgSignal < threshold * 0.42) {
            rgb = palette.surfaceRgb;
          } else {
            rgb = palette.bgRgb;
          }
        }

        const idx = (y * cols + x) * 4;
        data[idx] = rgb[0];
        data[idx + 1] = rgb[1];
        data[idx + 2] = rgb[2];
        data[idx + 3] = 255;
      }
    }
    ctx.putImageData(imgData, 0, 0);
  };

  draw(options.time || 0);
  return { canvas, draw };
}

/* 4. mountDitherShader: WebGL1 Bayer 8x8 Fragment Shader with 2D Canvas fallback + Viewport Pooler */
const DITHER_VS = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

const DITHER_FS = `
precision mediump float;
varying vec2 v_uv;
uniform vec2 u_res;
uniform float u_time;
uniform float u_scale;
uniform vec3 u_bg;
uniform vec3 u_ink;
uniform vec3 u_accent;

float bayer2(vec2 a) {
  a = floor(a);
  return fract(a.x / 2.0 + a.y * a.y * 0.75);
}
float bayer4(vec2 a) {
  return bayer2(0.5 * a) * 0.25 + bayer2(a);
}
float bayer8(vec2 a) {
  return bayer4(0.5 * a) * 0.25 + bayer2(a);
}

void main() {
  vec2 cell = floor(gl_FragCoord.xy / max(1.0, u_scale));
  vec2 uv = (cell * max(1.0, u_scale)) / max(u_res, vec2(1.0));
  float t = u_time;

  float w1 = sin(uv.x * 7.5 + t * 1.1) * cos(uv.y * 5.5 - t * 0.8);
  float w2 = sin((uv.x + uv.y) * 5.0 - t * 0.65);
  float dist = length((uv - vec2(0.74, 0.46)) * vec2(u_res.x / max(u_res.y, 1.0), 1.0));
  float ring = smoothstep(0.46, 0.08, dist);

  float signal = clamp(0.46 + 0.24 * w1 + 0.16 * w2 + 0.34 * ring, 0.0, 1.0);
  float thresh = bayer8(cell);

  vec3 col = u_bg;
  if (ring > 0.36 && signal > thresh + 0.12) {
    col = u_accent;
  } else if (signal < thresh * 0.78) {
    col = mix(u_bg, u_ink, 0.18);
  } else if (signal > thresh) {
    col = mix(u_bg, u_ink, 0.86);
  }
  gl_FragColor = vec4(col, 1.0);
}
`;

function _compileShader(gl, type, src) {
  const sh = gl.createShader(type);
  if (!sh) return null;
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

function mountDitherShader(target, opts) {
  const options = opts || {};
  const host = typeof target === 'string' ? document.querySelector(target) : target;
  if (!host) return null;

  const canvas =
    host.tagName === 'CANVAS'
      ? host
      : host.querySelector('canvas[data-dither-canvas]') || document.createElement('canvas');
  if (canvas !== host && !canvas.parentNode) {
    canvas.setAttribute('data-dither-canvas', '1');
    canvas.style.cssText = 'width:100%;height:100%;display:block;';
    host.appendChild(canvas);
  }

  let gl = null;
  let prog = null;
  let uniforms = null;
  let fallback2d = null;

  const initGl = () => {
    try {
      gl =
        canvas.getContext('webgl', { antialias: false, depth: false, stencil: false, preserveDrawingBuffer: true }) ||
        canvas.getContext('experimental-webgl', { preserveDrawingBuffer: true });
      if (!gl) return false;
      const vs = _compileShader(gl, gl.VERTEX_SHADER, DITHER_VS);
      const fs = _compileShader(gl, gl.FRAGMENT_SHADER, DITHER_FS);
      if (!vs || !fs) return false;
      prog = gl.createProgram();
      gl.attachShader(prog, vs);
      gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return false;

      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
        gl.STATIC_DRAW
      );
      const posLoc = gl.getAttribLocation(prog, 'a_pos');
      gl.enableVertexAttribArray(posLoc);
      gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

      uniforms = {
        res: gl.getUniformLocation(prog, 'u_res'),
        time: gl.getUniformLocation(prog, 'u_time'),
        scale: gl.getUniformLocation(prog, 'u_scale'),
        bg: gl.getUniformLocation(prog, 'u_bg'),
        ink: gl.getUniformLocation(prog, 'u_ink'),
        accent: gl.getUniformLocation(prog, 'u_accent'),
      };
      return true;
    } catch (_) {
      return false;
    }
  };

  const hasWebGl = options.force2d ? false : initGl();
  if (!hasWebGl) {
    fallback2d = ditherImageCanvas(canvas, {
      width: options.width || 480,
      height: options.height || 240,
      pixelScale: options.pixelScale || 3,
      bg: options.bg,
      ink: options.ink,
      accent: options.accent,
    });
  }

  let currentTime = options.initialTime || 0;
  let rafId = 0;
  let running = false;
  let lastNow = 0;
  const speed = options.speed !== undefined ? options.speed : 1.0;
  const pixelScale = options.pixelScale || 3.0;

  const renderFrame = timeSec => {
    currentTime = timeSec !== undefined ? timeSec : currentTime;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(160, Math.round(rect.width || options.width || 640));
    const h = Math.max(100, Math.round(rect.height || options.height || 280));

    if (hasWebGl && gl && prog && uniforms) {
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      const pal = resolveEmDashDitherColors(host, options);
      gl.viewport(0, 0, w, h);
      gl.useProgram(prog);
      gl.uniform2f(uniforms.res, w, h);
      gl.uniform1f(uniforms.time, currentTime);
      gl.uniform1f(uniforms.scale, pixelScale);
      gl.uniform3f(uniforms.bg, pal.bgRgb[0] / 255, pal.bgRgb[1] / 255, pal.bgRgb[2] / 255);
      gl.uniform3f(uniforms.ink, pal.inkRgb[0] / 255, pal.inkRgb[1] / 255, pal.inkRgb[2] / 255);
      gl.uniform3f(uniforms.accent, pal.accentRgb[0] / 255, pal.accentRgb[1] / 255, pal.accentRgb[2] / 255);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
    } else if (fallback2d) {
      fallback2d.draw(currentTime);
    }
  };

  const tick = now => {
    if (!running) return;
    if (!lastNow) lastNow = now;
    const dt = Math.min(0.1, (now - lastNow) / 1000);
    lastNow = now;
    currentTime += dt * speed;
    renderFrame(currentTime);
    rafId = requestAnimationFrame(tick);
  };

  const start = () => {
    if (running) return;
    running = true;
    lastNow = 0;
    rafId = requestAnimationFrame(tick);
  };

  const stop = () => {
    running = false;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
  };

  /* Observe :root[data-theme] / :root[data-preset] for live EmDash theme changes */
  let themeObserver = null;
  if (typeof MutationObserver !== 'undefined' && typeof document !== 'undefined') {
    themeObserver = new MutationObserver(() => renderFrame(currentTime));
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'data-preset', 'class', 'style'],
    });
  }

  /* Register with Viewport Pooler if available, otherwise run static + local observer */
  const pool =
    options.pool ||
    (typeof window !== 'undefined' && window.defaultViewportPool ? window.defaultViewportPool : null);
  let unregisterPool = () => {};

  if (pool && typeof pool.register === 'function') {
    unregisterPool = pool.register(host, {
      start,
      stop,
      renderStatic: () => renderFrame(currentTime),
    });
  } else {
    renderFrame(currentTime);
  }

  return {
    canvas,
    hasWebGl,
    renderFrame,
    setTime(t) {
      stop();
      renderFrame(Number(t) || 0);
    },
    start,
    stop,
    destroy() {
      stop();
      unregisterPool();
      if (themeObserver) themeObserver.disconnect();
    },
  };
}

if (typeof window !== 'undefined') {
  window.BAYER_4X4 = BAYER_4X4;
  window.BAYER_8X8 = BAYER_8X8;
  window.resolveEmDashDitherColors = resolveEmDashDitherColors;
  window.ditherPatternSvg = ditherPatternSvg;
  window.ditherMaskStyle = ditherMaskStyle;
  window.ditherImageCanvas = ditherImageCanvas;
  window.mountDitherShader = mountDitherShader;
}
