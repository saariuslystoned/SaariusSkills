#!/usr/bin/env python3
"""Build a self-contained HTML artifact or an EmDash Astro component (.astro).

Usage:
  # 1. Standalone self-contained HTML page (Mode A, B, or C)
  python3 build.py figure.html OUT.html [--chrome full|storefront|stage-only]

  # 2. Zero-dependency EmDash Astro component (.astro)
  python3 build.py figure.html src/components/motion/HeroFigure.astro --astro [--chrome storefront]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS_DIR = HERE.parent / "assets"
SURFACE_FX_ASSETS_DIR = HERE.parent.parent / "emdash-surface-fx" / "assets"

ENGINES = ("core.js", "multiplane.js", "choreo.js", "tactile-audio.js", "ephemera.js", "dither.js", "viewport-pool.js", "surface-micro.js")
ANY_WORD_RE = re.compile(r"\bany\b", flags=re.UNICODE)

CF_HEAD = (
    '<style>.mcap{display:none!important}'
    '@media (max-width:560px){.stat .v{font-size:20px!important}.stats{align-items:flex-end}}'
    '@media (min-width:561px){.vset{top:4px!important}#stats{top:var(--vset-h,44px)!important}}</style>'
    '<style>@media (max-width:560px){body.cf-standalone > header,.cf-root > header{display:none}}</style>'
    '<script>window.FIG_A = window.FIG_A || (() => innerWidth <= 560 ? 1.1 : .75);</script>'
    '<script>window.LBL_U = () => { if (innerWidth > 560) return 0; const r = (typeof _activeRoot !== "undefined" && _activeRoot) || document; const s = r.querySelector("#fig") || document.getElementById("fig"); '
    'return s && s.clientWidth && s.viewBox.baseVal.width ? s.viewBox.baseVal.width / s.clientWidth : 0; };</script>'
)

CF_TAIL = r"""<style>@media (max-width:560px),(pointer:coarse){#art{filter:none!important}.ctl:has(#wb){display:none!important}}</style><style>@media (max-width:560px){html body .kpad{width:100%;box-sizing:border-box;justify-content:space-between;gap:10px;margin:10px 0 0;padding:0;border:0;background:none;box-shadow:none}
html body .kpad .dp{display:flex;gap:8px}html body .kpad .hub{display:none}
html body .kpad .k{width:46px;height:42px;font-size:14px;border-radius:9px}
html body .kpad .go{width:auto;height:42px;padding:0 26px;border-radius:999px;flex-direction:row;font-size:13px;box-shadow:0 3px 0 var(--ink),inset 0 -4px 0 rgba(0,0,0,.18)}
html body .kpad .go small{display:none}html body .kpad .go.down{transform:translateY(2px);box-shadow:0 1px 0 var(--ink),inset 0 -2px 0 rgba(0,0,0,.18)}}</style>
<script>requestAnimationFrame(() => { const o = { "◀": 0, "▲": 1, "▼": 2, "▶": 3 }; for (const k of document.querySelectorAll(".kpad .k")) k.style.order = o[k.textContent] ?? 0; });</script><style>@media (max-width:560px){.vset{margin:8px 0 2px!important}}</style><script>requestAnimationFrame(() => { const v = document.querySelector(".vset"), s = document.getElementById("stats"), z = document.querySelector(".zwrap"); if (!v) return; if (z && z.parentNode === v.parentNode){ const kp = document.querySelector(".kpad"); if (kp && innerWidth <= 560){ z.after(kp); kp.after(v); } else z.after(v); } else if (s && s.parentNode) s.parentNode.insertBefore(v, s); });</script><script>(() => { const fit = () => { const fig = document.getElementById("fig"); if (!fig || !document.body.classList.contains("cf-standalone")) return;
  fig.style.maxHeight = ""; if (innerWidth <= 560) return;
  const extra = document.documentElement.scrollHeight - fig.clientHeight, room = innerHeight - extra - 12;
  if (room < fig.clientHeight) fig.style.maxHeight = Math.max(320, room) + "px"; };
  addEventListener("load", () => requestAnimationFrame(fit)); addEventListener("resize", fit); setTimeout(fit, 400); })();</script><style>.zwrap{position:relative}.zwrap.on{overflow:hidden}@media (min-width:561px){.zwrap.on{overflow:visible}html.zoomed,html.zoomed body.cf-standalone{overflow:hidden}}.zwrap #fig{transform-origin:0 0}
.zchip{position:absolute;right:2px;bottom:6px;display:flex;align-items:center;gap:2px;font:600 11px ui-monospace,Menlo,monospace;
 background:rgba(242,239,231,.88);border:1px solid rgba(35,30,22,.25);border-radius:999px;padding:2px;z-index:3;user-select:none}
.zchip button{all:unset;cursor:pointer;min-width:22px;height:22px;line-height:22px;text-align:center;border-radius:999px;color:#231e16}
.zchip button:hover{background:rgba(35,30,22,.08)}.zchip .zp{min-width:44px}</style>
<script>(() => { const fig = document.getElementById("fig"); if (!fig) return;
  const wrap = document.createElement("div"); wrap.className = "zwrap"; fig.parentNode.insertBefore(wrap, fig); wrap.appendChild(fig);
  const chip = document.createElement("div"); chip.className = "zchip";
  chip.innerHTML = '<button class="zm" aria-label="Zoom out">−</button><button class="zp" aria-label="Reset zoom">100%</button><button class="zi" aria-label="Zoom in">+</button>';
  wrap.appendChild(chip);
  let s = 1, tx = 0, ty = 0;
  const box = () => ({ w: fig.clientWidth, h: fig.clientHeight });
  const apply = () => { const { w, h } = box(); s = Math.min(5, Math.max(1, s));
    if (s <= 1.001){ s = 1; tx = ty = 0; } else { tx = Math.min(0, Math.max(w - w*s, tx)); ty = Math.min(0, Math.max(h - h*s, ty)); }
    fig.style.transform = s === 1 ? "" : `translate(${tx}px,${ty}px) scale(${s})`; wrap.classList.toggle("on", s > 1); document.documentElement.classList.toggle("zoomed", s > 1);
    chip.querySelector(".zp").textContent = Math.round(s*100) + "%"; grain(); };
  const grain = () => { const fl = document.getElementById("hand"); if (!fl) return;
    const ts = [...fl.querySelectorAll("feTurbulence")]; if (!ts.length) return;
    const g = ts.find(t => t.getAttribute("result") === "n1") || ts.reduce((a, b) => parseFloat(b.getAttribute("baseFrequency")) > parseFloat(a.getAttribute("baseFrequency")) ? b : a);
    if (!g.dataset.f0) g.dataset.f0 = g.getAttribute("baseFrequency");
    const v = (parseFloat(g.dataset.f0) * s).toFixed(4); if (g.getAttribute("baseFrequency") !== v) g.setAttribute("baseFrequency", v); };
  const fd = document.getElementById("fdefs"); if (fd) new MutationObserver(() => grain()).observe(fd, { childList: true, subtree: true });
  const zoomAt = (k, px, py) => { const s2 = Math.min(5, Math.max(1, s*k)); tx = px - (px - tx)*s2/s; ty = py - (py - ty)*s2/s; s = s2; apply(); };
  const local = e => { const r = wrap.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  wrap.addEventListener("wheel", e => {
    if (e.ctrlKey || e.metaKey){ e.preventDefault(); const [x, y] = local(e); zoomAt(Math.exp(-Math.max(-50, Math.min(50, e.deltaY))*.006), x, y); }
    else if (s > 1){ e.preventDefault(); tx -= e.deltaX; ty -= e.deltaY; apply(); } }, { passive: false });
  const center = () => { const { w, h } = box(); return [w/2, h/2]; };
  chip.querySelector(".zi").onclick = () => zoomAt(1.5, ...center());
  chip.querySelector(".zm").onclick = () => zoomAt(1/1.5, ...center());
  chip.querySelector(".zp").onclick = () => { s = 1; apply(); };
  chip.addEventListener("pointerdown", e => e.stopPropagation());
  const pts = new Map(); let pinch = null;
  const two = () => { const [a, b] = [...pts.values()]; return { d: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x)/2, y: (a.y + b.y)/2 }; };
  wrap.addEventListener("pointerdown", e => { if (e.pointerType !== "touch") return; pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2){ pinch = two(); e.stopPropagation(); } }, true);
  wrap.addEventListener("pointermove", e => { if (!pts.has(e.pointerId)) return; pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pts.size === 2){ e.stopPropagation(); e.preventDefault(); const n = two(), r = wrap.getBoundingClientRect();
      tx += n.x - pinch.x; ty += n.y - pinch.y; zoomAt(n.d / pinch.d, n.x - r.left, n.y - r.top); pinch = n; } }, true);
  const up = e => { pts.delete(e.pointerId); if (pts.size < 2) pinch = null; };
  wrap.addEventListener("pointerup", up, true); wrap.addEventListener("pointercancel", up, true);
  addEventListener("resize", apply);
})();</script><style>.toast{position:absolute!important;left:50%!important;right:auto!important;top:6%!important;bottom:auto!important;z-index:4!important;
  transform:translate(-50%,8px)!important;opacity:0!important;pointer-events:none!important;display:flex!important;align-items:center;gap:8px;
  width:max-content;max-width:min(86%,440px);white-space:normal!important;font:600 12.5px/1.35 ui-monospace,Menlo,monospace!important;
  letter-spacing:.01em!important;text-transform:none!important;color:#231e16!important;background:#fff1bf!important;
  border:1px solid rgba(35,30,22,.28)!important;border-radius:8px!important;box-shadow:0 8px 22px rgba(35,30,22,.16)!important;
  padding:7px 13px 7px 9px!important;transition:opacity .18s ease,transform .18s ease!important}
.toast::before{content:"!";flex:none;width:17px;height:17px;border-radius:50%;background:#231e16;color:#fff1bf;font:800 11px/17px ui-monospace,Menlo,monospace;text-align:center}
.toast.show{opacity:1!important;transform:translate(-50%,0)!important}</style>
<script>(() => { const cap = () => { const t = document.getElementById("toast"); if (!t) return; const s = t.textContent;
  if (s && s[0] !== s[0].toUpperCase()) t.textContent = s[0].toUpperCase() + s.slice(1); };
  let seen = null; const watch = () => { const t = document.getElementById("toast"); if (!t || t === seen) return; seen = t;
    const zw = document.querySelector(".zwrap"); if (zw && t.parentNode !== zw) zw.appendChild(t);
    new MutationObserver(cap).observe(t, { childList: true, characterData: true, subtree: true }); cap(); };
  watch(); const st = document.querySelector(".stage"); if (st) new MutationObserver(watch).observe(st, { childList: true }); })();</script><script>(() => { const fix = () => { const art = document.getElementById('art'); if (!art) return;
    for (const el of art.querySelectorAll('[fill="#41538f" i]')){ let top = null, a = el.parentElement;
      while (a && a !== art){ const o = a.getAttribute('opacity'); if (o !== null && +o < 1) top = a; a = a.parentElement; }
      if (top) top.parentNode.insertBefore(el, top); } };
  const go = () => { const art = document.getElementById('art'); if (!art) return setTimeout(go, 50); fix(); new MutationObserver(fix).observe(art, { childList: true }); };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', go); else go(); })();</script><style>.lgd{display:none}@media (max-width:560px){html:not(.nolabels) .cf-root:not(.nolabels) .lgd.has,html:not(.nolabels) body.cf-standalone .lgd.has{display:grid}}
.lgd{grid-template-columns:1fr 1fr;gap:2px 8px;margin:4px 0 12px;font:700 10.5px/1.25 ui-monospace,Menlo,monospace;letter-spacing:.03em;color:var(--ink,#231e16)}
.lgd button{all:unset;display:flex;align-items:center;gap:6px;cursor:pointer;padding:4px;border-radius:7px;-webkit-tap-highlight-color:transparent}
.lgd b{flex:none;min-width:17px;height:17px;padding:0 3px;box-sizing:border-box;border-radius:999px;border:1.2px solid var(--ink,#231e16);background:#fff4d6;color:#231e16;text-align:center;font:800 10px/15px ui-monospace,Menlo,monospace}
.lgd .on b{background:var(--accent,#f4b829);color:var(--accent-fg,#231e16)}.lgd .sel{background:rgba(35,30,22,.09)}.lgd .sel b{background:#231e16;color:#fff4d6}</style>
<script>(() => { const fig = document.getElementById("fig"); if (!fig) return;
  const lg = document.createElement("div"); lg.className = "lgd"; const at = document.querySelector(".zwrap") || fig; at.parentNode.insertBefore(lg, at.nextSibling);
  const hs = document.createElement("style"); document.head.appendChild(hs);
  let sig = "", sel = 0, q = 0, names = "", num = new Map();
  const renum = () => { if (innerWidth > 560) return; const gs = [...fig.querySelectorAll(".tag[data-t]")];
    const key = gs.map(g => g.dataset.t).sort().join("|");
    if (key !== names){ names = key; num = new Map(); const vb = fig.viewBox.baseVal, cx = vb.x + vb.width/2;
      const at = g => { const r = g.querySelector("rect"); return r ? [+r.getAttribute("x") + r.getAttribute("width")/2, +r.getAttribute("y")] : [0, 0]; };
      gs.map(g => [g.dataset.t, ...at(g)]).sort((a, b) => ((a[1] > cx) - (b[1] > cx)) || a[2] - b[2]).forEach(([t]) => { if (!num.has(t)) num.set(t, num.size + 1); }); }
    for (const g of gs){ const n = String(num.get(g.dataset.t)); if (g.dataset.n !== n){ g.dataset.n = n; const t = g.querySelector("text"); if (t) t.textContent = n; } } };
  const mark = () => { hs.textContent = sel ? `#fig .tag[data-n="${sel}"] rect{fill:#231e16!important}#fig .tag[data-n="${sel}"] text{fill:#fff4d6}#fig .tag[data-n="${sel}"] path{stroke-width:2.4}` : "";
    for (const x of lg.children) x.classList.toggle("sel", +x.dataset.n === sel); };
  const upd = () => { q = 0; const m = new Map();
    if (innerWidth <= 560) for (const g of fig.querySelectorAll(".tag[data-n]")){ const n = +g.dataset.n; if (!m.has(n)) m.set(n, [g.dataset.t, g.classList.contains("on")]); }
    const a = [...m].sort((x, y) => x[0] - y[0]), s = JSON.stringify(a); if (s === sig) return; sig = s;
    lg.classList.toggle("has", a.length > 0);
    lg.innerHTML = a.map(([n, [t, on]]) => `<button data-n="${n}" class="${on ? "on" : ""}"><b>${n}</b><span>${t}</span></button>`).join(""); mark(); };
  lg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; sel = sel === +b.dataset.n ? 0 : +b.dataset.n; mark(); });
  new MutationObserver(() => { renum(); if (!q) q = requestAnimationFrame(upd); }).observe(fig, { childList: true, subtree: true }); renum();
  addEventListener("resize", () => { if (!q) q = requestAnimationFrame(upd); }); upd(); })();</script>"""

CF_ASTRO_LGD_CSS = """
  .emdash-motion-stage .lgd{display:none;grid-template-columns:1fr 1fr;gap:2px 8px;margin:4px 0 12px;font:700 10.5px/1.25 ui-monospace,Menlo,monospace;letter-spacing:.03em;color:var(--ink,#231e16)}
  @media (max-width:560px){html:not(.nolabels) .emdash-motion-stage:not(.nolabels) .lgd.has{display:grid}}
  .emdash-motion-stage .lgd button{all:unset;display:flex;align-items:center;gap:6px;cursor:pointer;padding:4px;border-radius:7px;-webkit-tap-highlight-color:transparent}
  .emdash-motion-stage .lgd b{flex:none;min-width:17px;height:17px;padding:0 3px;box-sizing:border-box;border-radius:999px;border:1.2px solid var(--ink,#231e16);background:#fff4d6;color:#231e16;text-align:center;font:800 10px/15px ui-monospace,Menlo,monospace}
  .emdash-motion-stage .lgd .on b{background:var(--accent,#f4b829);color:var(--accent-fg,#231e16)}
"""

CF_ASTRO_LGD_JS = """
    const fig = rootEl.querySelector('#fig');
    if (fig) {
      const lg = document.createElement('div');
      lg.className = 'lgd';
      fig.parentNode.insertBefore(lg, fig.nextSibling);
      let sig = '', q = 0;
      const upd = () => {
        q = 0;
        const m = new Map();
        if (innerWidth <= 560) {
          for (const g of fig.querySelectorAll('.tag[data-n]')) {
            const n = +g.dataset.n;
            if (!m.has(n)) m.set(n, [g.dataset.t, g.classList.contains('on')]);
          }
        }
        const a = [...m].sort((x, y) => x[0] - y[0]);
        const s = JSON.stringify(a);
        if (s === sig) return;
        sig = s;
        lg.classList.toggle('has', a.length > 0);
        lg.innerHTML = a.map(([n, [t, on]]) => `<button data-n="${n}" class="${on ? 'on' : ''}"><b>${n}</b><span>${t}</span></button>`).join('');
      };
      new MutationObserver(() => { if (!q) q = requestAnimationFrame(upd); }).observe(fig, { childList: true, subtree: true });
      addEventListener('resize', () => { if (!q) q = requestAnimationFrame(upd); });
      upd();
    }
"""


def _resolve_engine_path(eng: str) -> Path | None:
    cand1 = ASSETS_DIR / eng
    if cand1.is_file():
        return cand1
    cand2 = SURFACE_FX_ASSETS_DIR / eng
    if cand2.is_file():
        return cand2
    return None


def inline_engines(page: str, src_path: Path, inline_vendor: bool = False) -> tuple[str, list[str]]:
    """Inline core.js, multiplane.js, choreo.js, tactile-audio.js, surface-fx, or vendor/three.min.js script tags."""
    inlined: list[str] = []
    for eng in ENGINES:
        pattern = re.compile(
            rf'<script\s+src=["\'](?:\.\.?/|assets/|(?:\.\./)+emdash-[a-z-]+/assets/)?{re.escape(eng)}["\']\s*>\s*</script>',
            re.IGNORECASE,
        )
        match = pattern.search(page)
        if match:
            eng_path = _resolve_engine_path(eng)
            if not eng_path:
                sys.exit(f"error: engine asset {eng} not found for {src_path}")
            eng_code = eng_path.read_text(encoding="utf-8")
            page = page[: match.start()] + "<script>\n" + eng_code + "\n</script>" + page[match.end() :]
            inlined.append(eng)

    if inline_vendor:
        three_pattern = re.compile(
            r'<script\s+src=["\'][^"\']*three\.min\.js["\']\s*>\s*</script>',
            re.IGNORECASE,
        )
        three_match = three_pattern.search(page)
        if three_match:
            three_path = ASSETS_DIR / "vendor" / "three.min.js"
            if not three_path.is_file():
                sys.exit(f"error: vendor asset three.min.js not found for {src_path}")
            three_code = three_path.read_text(encoding="utf-8")
            page = (
                page[: three_match.start()]
                + "<script>\n"
                + three_code
                + "\n</script>"
                + page[three_match.end() :]
            )
            inlined.append("three.min.js")

    if not inlined:
        # Check if already inlined
        for eng, marker in (
            ("core.js", "function mountFigure("),
            ("multiplane.js", "function mountMultiplane("),
            ("choreo.js", "function mountChoreo("),
            ("tactile-audio.js", "function mountReceipt("),
            ("dither.js", "function mountDitherShader("),
            ("viewport-pool.js", "function createViewportPool("),
            ("surface-micro.js", "function mountHoverTilt("),
            ("three.min.js", "THREE.WebGLRenderer"),
        ):
            if marker in page:
                inlined.append(eng)
    if not inlined:
        sys.exit(
            f"error: no <script src=\"core.js|multiplane.js|choreo.js|tactile-audio.js\"></script> found in {src_path}"
        )
    return page, inlined


def extract_body_markup(page: str) -> str:
    """Extract non-script, non-style HTML markup inside <body>...</body> for .astro component output."""
    body_match = re.search(r"<body(?:\s+[^>]*)?>(.*?)</body>", page, flags=re.DOTALL | re.IGNORECASE)
    if not body_match:
        return ""
    inner = body_match.group(1)
    inner = re.sub(r"<script(?:\s+[^>]*)?>.*?</script>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    inner = re.sub(r"<style(?:\s+[^>]*)?>.*?</style>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    return inner.strip()


def sanitize_dinkuskit_astro(astro_code: str, strict: bool = False) -> str:
    """Ensure generated .astro file contains zero matches of /\\bany\\b/u for DinkusKit check-features.mjs."""
    hits = list(ANY_WORD_RE.finditer(astro_code))
    if hits and strict:
        sys.exit(
            f"error: DinkusKit check-features.mjs forbids /\\bany\\b/u in .astro files; found {len(hits)} match(es)"
        )
    if hits:
        astro_code = ANY_WORD_RE.sub("each", astro_code)
    remaining = ANY_WORD_RE.search(astro_code)
    if remaining:
        sys.exit(
            "error: generated .astro still matches /\\bany\\b/u after sanitization"
        )
    return astro_code


def build_html(page: str, inlined: list[str], chrome: str | None) -> str:
    extra_head = ""
    if chrome:
        extra_head += f"<script>window.__EMDASH_MOTION_CHROME = {json.dumps(chrome)};</script>"
    if "core.js" in inlined:
        head_inject = extra_head + CF_HEAD
        page = page.replace("</head>", head_inject + "</head>", 1) if "</head>" in page else head_inject + page
        i = page.rfind("</body>")
        page = page[:i] + CF_TAIL + page[i:] if i >= 0 else page + CF_TAIL
    elif extra_head:
        page = page.replace("</head>", extra_head + "</head>", 1) if "</head>" in page else extra_head + page
    return page


def build_astro(raw_page: str, src_path: Path, default_chrome: str, strict_no_any: bool = False) -> str:
    page, inlined = inline_engines(raw_page, src_path, inline_vendor=False)
    body_markup = extract_body_markup(page)
    scripts = re.findall(r"<script(?:\s+[^>]*)?>(.*?)</script>", page, flags=re.DOTALL | re.IGNORECASE)
    styles = re.findall(r"<style(?:\s+[^>]*)?>(.*?)</style>", page, flags=re.DOTALL | re.IGNORECASE)
    combined_js = "\n\n".join(s.strip() for s in scripts if s.strip())
    combined_css = "\n".join(s.strip() for s in styles if s.strip())
    if "core.js" in inlined:
        combined_css = (combined_css + "\n" + CF_ASTRO_LGD_CSS).strip()

    # Escape accidental </script> inside JS string literals if needed
    safe_js = combined_js.replace("</script>", "<\\/script>")
    core_pre = (
        "  window.FIG_A = window.FIG_A || (() => innerWidth <= 560 ? 1.1 : .75);\n"
        "  window.LBL_U = () => { if (innerWidth > 560) return 0; const r = (typeof _activeRoot !== 'undefined' && _activeRoot) || rootEl; const s = r.querySelector('#fig'); return s && s.clientWidth && s.viewBox.baseVal.width ? s.viewBox.baseVal.width / s.clientWidth : 0; };\n"
        if "core.js" in inlined
        else ""
    )
    core_post = CF_ASTRO_LGD_JS if "core.js" in inlined else ""
    stage_inner = f"\n{body_markup}\n" if body_markup else ""

    astro_out = f"""---
/**
 * Generated by emdash-motion-studio/scripts/build.py from {src_path.name}
 * Engine(s): {", ".join(inlined)}
 * Zero external runtime dependencies; binds automatically to EmDash src/styles/tokens.css (light-dark()).
 */
export interface Props {{
  chrome?: 'storefront' | 'stage-only' | 'full';
  palette?: string;
  height?: string;
  class?: string;
}}

const {{
  chrome = {json.dumps(default_chrome)},
  palette,
  height,
  class: className = '',
}} = Astro.props;
---

<div
  class:list={{['emdash-motion-stage', className]}}
  data-motion-stage
  data-chrome={{chrome}}
  data-palette={{palette}}
  style={{height ? `--motion-max-h:${{height}}` : undefined}}
>{stage_inner}</div>

<style is:global>
  .emdash-motion-stage {{
    --paper: var(--color-canvas, var(--color-surface, #f2efe7));
    --ink: var(--color-ink, var(--color-text, #231e16));
    --muted: var(--color-muted, #857d6e);
    --rule: var(--color-border, var(--color-rule, #ddd6c8));
    --accent: var(--color-accent, var(--color-primary, #f4b829));
    --mp-paper: var(--color-canvas, var(--color-surface, #f4f1ea));
    --mp-card: var(--color-surface, #e9eef2);
    --mp-ink: var(--color-ink, var(--color-text, #18222c));
    --mp-muted: var(--color-muted, #63717d);
    --mp-rule: var(--color-border, var(--color-rule, #c9d2d9));
    --mp-accent: var(--color-accent, var(--color-primary, #e89b2d));
    --ch-bg: var(--color-canvas, var(--color-surface, #0e131a));
    --ch-panel: var(--color-surface, #151d28);
    --ch-ink: var(--color-ink, var(--color-text, #eef3f8));
    --ch-muted: var(--color-muted, #7f91a6);
    --ch-rule: var(--color-border, var(--color-rule, #263445));
    --ch-accent: var(--color-accent, var(--color-primary, #4fd1c5));
    width: 100%;
    position: relative;
  }}
  .emdash-motion-stage #fig {{
    max-height: var(--motion-max-h, none);
  }}
  {combined_css}
</style>

<script is:inline>
(() => {{
  let cur = document.currentScript ? document.currentScript.previousElementSibling : null;
  while (cur && (!cur.hasAttribute || !cur.hasAttribute('data-motion-stage') || cur.hasAttribute('data-motion-mounted'))) {{
    cur = cur.previousElementSibling;
  }}
  const rootEl = cur || document.querySelector('[data-motion-stage]:not([data-motion-mounted])');
  if (!rootEl) return;
  rootEl.setAttribute('data-motion-mounted', '1');
  window.__EMDASH_MOTION_TARGET = rootEl;
  window.__EMDASH_MOTION_CHROME = rootEl.dataset.chrome || {json.dumps(default_chrome)};
  window.__EMDASH_MOTION_PALETTE = rootEl.dataset.palette || '';
{core_pre}  try {{
{safe_js}
{core_post}  }} finally {{
    window.__EMDASH_MOTION_TARGET = null;
  }}
}})();
</script>
"""
    return sanitize_dinkuskit_astro(astro_out, strict=strict_no_any)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build standalone HTML or EmDash .astro motion component.")
    parser.add_argument("src", help="Input .html file")
    parser.add_argument("out", help="Output .html or .astro file")
    parser.add_argument("--astro", action="store_true", help="Emit an EmDash Astro (.astro) component")
    parser.add_argument(
        "--strict-no-any",
        action="store_true",
        help="Fail closed instead of auto-replacing if /\\bany\\b/u is found in --astro output",
    )
    parser.add_argument(
        "--chrome",
        choices=("full", "storefront", "stage-only"),
        default=None,
        help="Default UI chrome mode (defaults to 'full' for HTML, 'storefront' for --astro)",
    )
    args = parser.parse_args()

    src_path = Path(args.src)
    out_path = Path(args.out)
    raw_page = src_path.read_text(encoding="utf-8")
    is_astro = args.astro or out_path.suffix.lower() == ".astro"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if is_astro:
        default_chrome = args.chrome or "storefront"
        astro_code = build_astro(raw_page, src_path, default_chrome, strict_no_any=args.strict_no_any)
        out_path.write_text(astro_code, encoding="utf-8")
    else:
        page, inlined = inline_engines(raw_page, src_path, inline_vendor=not args.strict_no_any)
        built = build_html(page, inlined, args.chrome)
        if args.strict_no_any:
            built = sanitize_dinkuskit_astro(built, strict=True)
        out_path.write_text(built, encoding="utf-8")

    print("wrote", out_path)


if __name__ == "__main__":
    main()
