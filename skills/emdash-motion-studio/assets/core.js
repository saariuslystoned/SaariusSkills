/* ============================================================
   Colorfigures + EmDash Motion Studio core (Mode A):
   projection, shapes, shading, ink, labels, scoped container mount,
   EmDash tokens.css (light-dark()) binding, storefront chrome, and ?t= scrubbing.
   A figure page includes this file (scripts/build.py inlines it), then calls mountFigure({...}).
   See SKILL.md for the drawing contract and conventions.
   ============================================================ */

/* ---------- palettes ---------- */
const PALS = {
  mustard: { l:'#f4b829', m:'#d49c1f', d:'#4e4a18' },
  tomato:  { l:'#ef6a4c', m:'#cf5038', d:'#4a2219' },
  mint:    { l:'#93d3b0', m:'#71b693', d:'#1f4034' },
  cobalt:  { l:'#76a0e2', m:'#5a82c6', d:'#1c2948' },
  blush:   { l:'#f3a6bb', m:'#d8869c', d:'#4b2430' },
  aizome:  { l:'#2b5b9e', m:'#1e4278', d:'#112647' },
  site:    { l:'#f4b829', m:'#d49c1f', d:'#4e4a18' },
};
const METAL   = { l:'#eef0f0', m:'#c6ccce', d:'#8f989b' };
const CLEAR   = { l:'#e4f2f4', m:'#c4dfe4', d:'#97b9c0' };
const CERAMIC = { l:'#fbfaf3', m:'#e3e0d2', d:'#bdb8a6' };
const DARK    = { l:'#55504a', m:'#3d3935', d:'#272421' };
let INK = '#231e16';
let SHADOW = '#41538f';

/* ---------- projection (x = depth toward viewer-right, y = toward viewer-left, z = up) ---------- */
const C = Math.cos(Math.PI/6), S = Math.sin(Math.PI/6);
let OX = 0, OY = 0;
let VIEW = 0, RC = [0, 0], RCZ = 0;
const VIEW_NAMES = ['front', 'left side', 'back', 'right side'];
const TURNS = [0, 2];
const YAW0 = 45, PITCH0 = Math.atan(1/Math.SQRT2) * 180/Math.PI, CAM_K = Math.sqrt(1.5);
let YAW = YAW0, PITCH = PITCH0, CAM_R, CAM_U, CAM_V, CAM_D;
const camBasis = (yaw, pitch) => { const t = yaw*Math.PI/180, p = pitch*Math.PI/180, ct = Math.cos(t), st = Math.sin(t), cp = Math.cos(p), sp2 = Math.sin(p);
  return { R:[st,-ct,0], U:[-sp2*ct,-sp2*st,cp], V:[cp*ct,cp*st,sp2] }; };
const CAM_B0 = camBasis(YAW0, PITCH0);
let CAM_LIM = null;
function setCam(yaw, pitch){ YAW = CAM_LIM == null ? yaw : Math.max(YAW0 - CAM_LIM, Math.min(YAW0 + CAM_LIM, yaw));
  PITCH = CAM_LIM == null ? Math.max(6, Math.min(78, pitch)) : Math.max(15, Math.min(62, pitch)); const b = camBasis(YAW, PITCH); CAM_R = b.R; CAM_U = b.U; CAM_V = b.V; CAM_D = CAM_U.map(v => -v); }
setCam(YAW0, PITCH0);
const camDot = (a,b) => a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const rotV = n => { const r = camDot(n,CAM_R), u = camDot(n,CAM_U), v = camDot(n,CAM_V); return [0,1,2].map(i => CAM_B0.R[i]*r + CAM_B0.U[i]*u + CAM_B0.V[i]*v); };
const yawTurn = ([x,y]) => { const t = (YAW - YAW0)*Math.PI/180, c = Math.cos(t), s = Math.sin(t); return [x*c - y*s, x*s + y*c]; };
const rotXY = (x,y) => [x, y];
const P0 = (x,y,z) => [(x-y)*C + OX, (x+y)*S - z + OY];
const P  = (x,y,z) => { const q = [x-RC[0], y-RC[1], z-RCZ];
  return [CAM_K*camDot(q,CAM_R) + (RC[0]-RC[1])*C + OX, CAM_K*camDot(q,CAM_D) + (RC[0]+RC[1])*S - RCZ + OY]; };
const Dv = (x,y,z) => [CAM_K*camDot([x,y,z],CAM_R), CAM_K*camDot([x,y,z],CAM_D)];
const depthOf = p => camDot(p, CAM_V);
const boxMid = b => [0,1,2].map(k => (b[0][k] + b[1][k]) / 2);
const sepOrder = (p, q) => { if (!p.box || !q.box) return 0;
  for (let k = 0; k < 3; k++){ if (p.box[1][k] <= q.box[0][k] + 1e-6) return CAM_V[k] >= 0 ? -1 : 1; if (q.box[1][k] <= p.box[0][k] + 1e-6) return CAM_V[k] >= 0 ? 1 : -1; }
  return 0; };
const byDepth = parts => parts.filter(Boolean).sort((p,q) => sepOrder(p,q) || (depthOf(p.at || boxMid(p.box)) - depthOf(q.at || boxMid(q.box)))).map(p => p.svg).join('');
const nearHalf = () => [YAW - 90, YAW + 90], farHalf = () => [YAW + 90, YAW + 270];
const openShell = (A, B, colour, contents = '') => loft(A, B, colour, true) + contents + loft(A, B, colour);
const f  = v => v.toFixed(1);
const pd = (pts, close=true) => 'M' + pts.map(p => { const q = P(p[0],p[1],p[2]); return f(q[0])+' '+f(q[1]); }).join('L') + (close ? 'Z' : '');
const sp = pts => 'M' + pts.map(q => f(q[0])+' '+f(q[1])).join('L') + 'Z';

/* ---------- 2D shapes in a plane's (u,v) coords (v up), mapped to 3D by a plane ---------- */
const arcUV  = (cu,cv,r,a0,a1,n=7) => { const o=[]; for (let i=0;i<=n;i++){ const a=(a0+(a1-a0)*i/n)*Math.PI/180; o.push([cu+r*Math.cos(a), cv+r*Math.sin(a)]); } return o; };
const rrUV   = (u0,v0,u1,v1,r,n=7) => r <= 0 ? rectUV(u0,v0,u1,v1) : [...arcUV(u1-r,v0+r,r,-90,0,n), ...arcUV(u1-r,v1-r,r,0,90,n), ...arcUV(u0+r,v1-r,r,90,180,n), ...arcUV(u0+r,v0+r,r,180,270,n)];
const rectUV = (u0,v0,u1,v1) => [[u0,v0],[u1,v0],[u1,v1],[u0,v1]];
const ellUV  = (cu,cv,ru,rv,n=24) => Array.from({length:n}, (_,i) => { const a=i/n*2*Math.PI; return [cu+ru*Math.cos(a), cv+rv*Math.sin(a)]; });
const PX = x => ([u,v]) => [x,u,v];
const PY = y => ([u,v]) => [u,y,v];
const PZ = z => ([u,v]) => [u,v,z];
const on = (plane, uv) => uv.map(plane);

/* ---------- vectors + shading ---------- */
const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]], dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const norm=a=>{ const l=Math.hypot(...a)||1; return a.map(v=>v/l); };
const avg=ps=>ps.reduce((s,p)=>[s[0]+p[0]/ps.length,s[1]+p[1]/ps.length,s[2]+p[2]/ps.length],[0,0,0]);
const vis = n => { const r = rotV(n); return r[0]+r[1]+r[2] > 1e-6; };
const facing = vis;
const SHADOW_K = 0.85, AZ_MIN = 20, AZ_MAX = 160;
const SHADOW_LEN = 0.45;
let L = [0,0,1], SH = [0,0];
function setLight(deg){ const a=deg*Math.PI/180; SH=[SHADOW_K*Math.cos(a), SHADOW_K*Math.sin(a)]; L=norm([-SH[0],-SH[1],1]); }
const LIN = norm([.6,.2,1]);
const SOFT = .18;
const step3 = (d, hi, lo, m) => { const ss = (a, b, x) => { const k = Math.min(1, Math.max(0, (x - a)/(b - a))); return k*k*(3 - 2*k); };
  const a = ss(hi - SOFT, hi + SOFT, d), b = ss(lo - SOFT, lo + SOFT, d);
  return a >= 1 ? m.l : b <= 0 ? m.d : a > 0 ? mix(m.m, m.l, a) : b < 1 ? mix(m.d, m.m, b) : m.m; };
const tone  = (n,m) => step3(dot(rotV(n),L),   -.15, -.45, m);
const toneI = (n,m) => step3(dot(rotV(n),LIN),  .6,   .05, m);
const mix = (a,b,t) => '#' + [1,3,5].map(i => Math.round(parseInt(a.substr(i,2),16)*(1-t) + parseInt(b.substr(i,2),16)*t).toString(16).padStart(2,'0')).join('');
const matOf = hex => ({ l:hex, m:mix(hex,'#000000',.16), d:mix(hex,'#000000',.42) });
const ease = t => t<.5 ? 2*t*t : 1-Math.pow(-2*t+2,2)/2;

/* ---------- drawing primitives (all return SVG strings) ---------- */
const ink   = (d,w=1.0) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"/>`;
const fill  = (d,c,extra='') => `<path d="${d}" fill="${c}" ${extra}/>`;
const face  = (d,c) => `<path d="${d}" fill="${c}" stroke="${c}" stroke-width=".7" stroke-linejoin="round"/>`;
const shape = (pts,c,w=.9) => fill(pd(pts),c) + (w ? ink(pd(pts),w) : '');
const line  = (pts,w=.9) => ink(pd(pts,false),w);
function loft(A, B, colour, flip=false){
  const n=A.length, cen=avg(A.concat(B)); let s='';
  for (let i=0;i<n;i++){
    const a0=A[i], a1=A[(i+1)%n], b1=B[(i+1)%n], b0=B[i];
    let nr = norm(cross(sub(a1,a0), sub(b0,a0)));
    if (!isFinite(nr[0])) continue;
    if (dot(nr, sub(avg([a0,a1,b1,b0]), cen)) < 0) nr = nr.map(v=>-v);
    if (flip) nr = nr.map(v=>-v);
    if (vis(nr)) s += face(pd([a0,a1,b1,b0]), colour(nr));
  }
  return s;
}
function hull(pts){
  pts = pts.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const cr=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]); const lo=[], up=[];
  for (const p of pts){ while(lo.length>=2 && cr(lo[lo.length-2],lo[lo.length-1],p)<=0) lo.pop(); lo.push(p); }
  for (const p of pts.reverse()){ while(up.length>=2 && cr(up[up.length-2],up[up.length-1],p)<=0) up.pop(); up.push(p); }
  lo.pop(); up.pop(); return lo.concat(up);
}
const hullInk = (pts3, w=1.4) => { const h = hull(pts3.map(p=>P(...p))); let a = 0, per = 0;
  for (let i = 0; i < h.length; i++){ const p = h[i], q = h[(i+1) % h.length]; a += p[0]*q[1] - q[0]*p[1]; per += Math.hypot(q[0]-p[0], q[1]-p[1]); }
  const thick = per ? Math.abs(a) / per / (INK_K * INK_REF_VB) : 0;
  return ink(sp(h), Math.min(w, .9 + 20*thick)); };
function box(x0,y0,z0,x1,y1,z1,m,shade=toneI,w=.9){
  const F = [
    [[0,1,0],  [[x0,y1,z0],[x1,y1,z0],[x1,y1,z1],[x0,y1,z1]]],
    [[1,0,0],  [[x1,y0,z0],[x1,y1,z0],[x1,y1,z1],[x1,y0,z1]]],
    [[0,-1,0], [[x0,y0,z0],[x1,y0,z0],[x1,y0,z1],[x0,y0,z1]]],
    [[-1,0,0], [[x0,y0,z0],[x0,y1,z0],[x0,y1,z1],[x0,y0,z1]]],
    [[0,0,1],  [[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]]] ];
  return F.filter(([n]) => vis(n)).map(([n,q]) => shape(q, shade(n,m), w)).join('');
}
function extrude(profileUV, x0, x1, m, shade=tone){ return loft(on(PX(x0),profileUV), on(PX(x1),profileUV), n=>shade(n,m)); }
function cyl(x,y,z0,z1,r,m,shade=toneI,w=1.2,n=24){
  const A=on(PZ(z0),ellUV(x,y,r,r,n)), B=on(PZ(z1),ellUV(x,y,r,r,n));
  return loft(A,B,nr=>shade(nr,m)) + fill(pd(B),shade([0,0,1],m)) + hullInk([...A,...B],w) + ink(pd(B),w*.8);
}
function cylX(x0,x1,y,z,r,m,shade=toneI,w=1.1,n=20){
  const A=on(PX(x0),ellUV(y,z,r,r,n)), B=on(PX(x1),ellUV(y,z,r,r,n));
  const capB = vis([1,0,0]), cap = capB ? B : A, cn = capB ? [1,0,0] : [-1,0,0];
  return loft(A,B,nr=>shade(nr,m)) + (vis(cn) ? fill(pd(cap),shade(cn,m)) : '') + hullInk([...A,...B],w) + (vis(cn) ? ink(pd(cap),w*.8) : '');
}
function rod(a, b, r, m, shade=toneI, w=1, r1=r, n=16){
  const d = norm(sub(b, a)), u = norm(cross(d, Math.abs(d[2]) < .9 ? [0,0,1] : [1,0,0])), v = cross(d, u);
  const ring = (p, rr) => Array.from({length:n}, (_,i) => { const t = i/n*2*Math.PI, c = Math.cos(t)*rr, s2 = Math.sin(t)*rr;
    return [p[0] + u[0]*c + v[0]*s2, p[1] + u[1]*c + v[1]*s2, p[2] + u[2]*c + v[2]*s2]; });
  const A = ring(a, r), B = ring(b, r1), capB = vis(d), cap = capB ? B : A, cn = capB ? d : d.map(x => -x);
  return loft(A, B, nr => shade(nr, m)) + (Math.max(r, r1) > 0 ? fill(pd(cap), shade(cn, m)) + ink(pd(cap), w*.8) : '') + hullInk([...A, ...B], w);
}
const txM = (o, U, V) => (U[0]*V[1] - U[1]*V[0]) <= .02 * Math.hypot(...U) * Math.hypot(...V) ? `matrix(0 0 0 0 ${f(o[0])} ${f(o[1])})` : `matrix(${U[0].toFixed(4)} ${U[1].toFixed(4)} ${V[0].toFixed(4)} ${V[1].toFixed(4)} ${f(o[0])} ${f(o[1])})`;
const tx = (x,y,z,str,size,col=INK,weight=700) => { const o=P(x,y,z);
  return `<text transform="${txM(o, Dv(0,-1,0), Dv(0,0,-1))}" font-size="${size}" fill="${col}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-weight="${weight}" letter-spacing=".04em">${str}</text>`; };
const txY = (x,y,z,str,size,col=INK,weight=700) => { const o=P(x,y,z);
  return `<text transform="${txM(o, Dv(1,0,0), Dv(0,0,-1))}" font-size="${size}" fill="${col}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-weight="${weight}" letter-spacing=".04em">${str}</text>`; };
const castShadow = (pts3, z0=0, clip=null) => { const k = SHADOW_LEN / SHADOW_K, [sx, sy] = yawTurn(SH);
  const s = fill(sp(hull(pts3.map(([x,y,z]) => P(x+(z-z0)*sx*k, y+(z-z0)*sy*k, z0)))), SHADOW);
  return clip ? clipTo(clip, s) : s; };
const BOARD = { l:'#e6e1d4', m:'#cfc8b8', d:'#aaa293' }, WOOD = { l:'#d9a86c', m:'#bf8a4f', d:'#8e6236' };
const boardTop = (x0,y0,x1,y1,h=3,r=5) => on(PZ(h), rrUV(x0,y0,x1,y1,r));
function board(x0,y0,x1,y1,h=3,r=5,m=BOARD){
  const A = on(PZ(0), rrUV(x0,y0,x1,y1,r)), B = boardTop(x0,y0,x1,y1,h,r);
  return loft(A, B, n => toneI(n, m)) + fill(pd(B), m.l) + ink(pd(B), 1) + hullInk([...A, ...B], 1.8);
}
const act  = (name, inner, data='') => `<g data-act="${name}" ${data}>${inner}</g>`;
let _clipN = 0;
const _lum = hex => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || '');
  return m ? (0.299 * parseInt(m[1], 16) + 0.587 * parseInt(m[2], 16) + 0.114 * parseInt(m[3], 16)) / 255 : 1;
};
function tag(p3, dx, dy, text, on=false){
  const u = window.LBL_U ? LBL_U() : 0, n = ((window.__ln || (window.__ln = {}))[text] || (__ln[text] = Object.keys(__ln).length + 1));
  const k = INK_K, [X,Y] = P(...p3), fs = u ? 10*u : 8.6*k, h = u ? 17*u : fs*1.8, w = u ? h*(n > 9 ? 1.3 : 1) : text.length*fs*.62 + fs*1.5, cx = X + dx*k, cy = Y + dy*k;
  return `<g class="tag${on ? ' on' : ''}" data-n="${n}" data-t="${text}"><path d="M${f(X)} ${f(Y)}L${f(cx)} ${f(cy)}" fill="none" stroke="${INK}" stroke-width="1"/>`
    + `<circle cx="${f(X)}" cy="${f(Y)}" r="${f(1.3*k)}" fill="${INK}"/>`
    + `<rect x="${f(cx-w/2)}" y="${f(cy-h/2)}" width="${f(w)}" height="${f(h)}" rx="${f(h/2)}" fill="${on ? 'var(--accent,#f4b829)' : '#fff4d6'}" stroke="${INK}" stroke-width="1.2"/>`
    + `<text x="${f(cx)}" y="${f(cy+fs*.36)}" font-size="${f(fs)}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-weight="800" letter-spacing=".04em" fill="${on ? 'var(--accent-fg,#1b222c)' : '#1b222c'}">${u ? n : text}</text></g>`;
}
const clipTo = (pts3, inner) => { const id = 'k' + (++_clipN); return `<clipPath id="${id}"><path d="${pd(pts3)}"/></clipPath><g clip-path="url(#${id})">${inner}</g>`; };

/* ---------- constant on-screen line weight ---------- */
const INK_REF_VB = 585;
let INK_K = 1;
const inkScale = svg => INK_K === 1 ? svg : svg.replace(/stroke-width="([\d.]+)"/g, (_, w) => `stroke-width="${(+w * INK_K).toFixed(2)}"`);

/* ---------- page & container shell ---------- */
const CORE_CSS = `
  :root, body.cf-standalone, .cf-root{--paper:var(--color-canvas,var(--color-surface,#f2efe7));--ink:var(--color-ink,var(--color-text,#231e16));--muted:var(--color-muted,#857d6e);--rule:var(--color-border,var(--color-rule,#ddd6c8))}
  body.cf-standalone, .cf-root{box-sizing:border-box;background-color:var(--paper);
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='320' height='320'><filter id='p'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .42  0 0 0 0 .39  0 0 0 0 .33  .16 0 0 0 0'/></filter><rect width='100%' height='100%' filter='url(%23p)'/></svg>");
    color:var(--ink);font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;display:flex;flex-direction:column;align-items:center}
  body.cf-standalone *, .cf-root *{box-sizing:border-box}
  html:has(body.cf-standalone){margin:0;min-height:100%;overflow-x:hidden;box-sizing:border-box}
  body.cf-standalone{margin:0;min-height:100%;overflow-x:hidden;padding:24px 16px 32px}
  .cf-root{position:relative;width:100%;padding:20px 16px 24px;border-radius:var(--radius-lg,14px);overflow:hidden}
  .cf-root header, body.cf-standalone > header{width:100%;max-width:760px;display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
  .cf-root header h1, body.cf-standalone > header h1{font-size:13px;font-weight:600;margin:0;letter-spacing:.02em}
  .cf-root header span, body.cf-standalone > header span{color:var(--muted)}
  #fig{width:100%;max-width:760px;height:auto;display:block;margin:4px 0 8px;user-select:none;overflow:visible;cursor:grab;touch-action:pan-y}
  #fig.drag{cursor:grabbing} #fig [data-act]{cursor:pointer}
  #readout, .idea{display:none}
  .idea{width:100%;max-width:760px;margin:-6px 0 16px;font-size:12.5px;line-height:1.5;text-align:center;color:var(--ink)}
  .idea strong{letter-spacing:.12em;text-transform:uppercase;font-size:11px;margin-right:8px}
  #readout{position:relative;min-height:1.4em;letter-spacing:.08em;text-transform:uppercase;margin-bottom:14px;text-align:center;text-shadow:0 0 3px var(--paper),0 0 6px var(--paper),0 0 10px var(--paper)}
  .stage{position:relative;width:100%;max-width:760px}
  .actions{position:absolute;top:4px;left:0;display:flex;flex-direction:column;align-items:flex-start;gap:8px;z-index:2;max-width:220px}
  .actions .cap{color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase;margin:0 0 2px}
  html.nolabels body.cf-standalone #fig .tag, .cf-root.nolabels #fig .tag{display:none}
  .ctl[hidden]{display:none}
  .toast{position:absolute;left:0;z-index:3;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;background:var(--paper);
    border:1.5px solid var(--ink);border-radius:8px;padding:4px 9px;box-shadow:2px 2px 0 var(--ink);opacity:0;transition:opacity .2s;pointer-events:none;max-width:240px}
  .toast.show{opacity:1}
  .made-with{width:100%;max-width:760px;margin-top:18px;text-align:right;font-size:11px;letter-spacing:.1em;text-transform:uppercase}
  .made-with a{color:var(--muted);text-decoration:none} .made-with a:hover{color:var(--ink)}
  .stats{position:absolute;top:4px;right:0;display:flex;flex-direction:column;align-items:flex-end;gap:10px;z-index:2;text-align:right}
  .stat .k{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
  .stat .v{font-size:34px;font-weight:800;line-height:1.05;letter-spacing:-.01em;font-variant-numeric:tabular-nums;color:var(--ink)}
  .stat.small .v{font-size:20px}
  .stat .v.bump{animation:bump .35s ease-out}
  @keyframes bump{0%{transform:scale(1.18)}100%{transform:none}}
  .stepwrap{position:relative;display:flex;align-items:center;gap:8px}
  .act{font:inherit;color:var(--ink);background:var(--paper);border:1.5px solid var(--ink);border-radius:999px;padding:5px 14px;cursor:pointer;white-space:nowrap}
  .act:hover{background:color-mix(in srgb,var(--paper) 92%,var(--ink))}
  .act .car{margin-left:6px;font-size:10px}
  .act:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
  .chips{display:none;flex-wrap:wrap;gap:6px;background:var(--paper);border:2px solid var(--ink);border-radius:12px;box-shadow:3px 3px 0 var(--ink);
    padding:8px;width:max-content;max-width:min(300px,62vw);position:absolute;left:calc(100% + 10px);top:-4px;z-index:3}
  .stepwrap.open .chips{display:flex}
  .chip{white-space:nowrap;font:inherit;font-size:11.5px;font-weight:700;color:var(--ink);background:var(--paper);border:1.5px solid var(--ink);border-radius:8px;padding:4px 8px;cursor:pointer;box-shadow:2px 2px 0 var(--ink)}
  .chip:hover{background:var(--accent,#f4b829);transform:translate(-1px,-1px)}
  .chip.current{background:var(--ink);color:var(--paper)} .chip.current:hover{background:var(--ink);transform:none}
  .chip.off{opacity:.45} .chip.off:hover{transform:none;background:var(--paper)}
  @media (max-width:560px),(pointer:coarse){#art{filter:none!important}.ctl:has(#wb){display:none!important}}
  @media (max-width:560px){body.cf-standalone{padding:14px 12px 24px}.cf-root{padding:12px 10px 18px}header span,.actions .cap{display:none}.actions{flex-direction:row;flex-wrap:wrap;gap:6px}.act{font-size:12px;padding:4px 11px}.stats{position:static;flex-direction:row;justify-content:flex-end;gap:18px;margin-bottom:4px}.actions{position:static;max-width:none;margin:6px 0 4px}.chips{left:0;top:calc(100% + 8px)}}
  .controls{width:100%;max-width:760px;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px 28px;border-top:1px solid var(--rule);padding-top:16px}
  .ctl{display:flex;flex-direction:column;gap:6px}
  .ctl label{color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase}
  input[type=range]{width:100%;accent-color:var(--ink)}
  .row{display:flex;gap:8px;flex-wrap:wrap}
  .controls button, .vset button{font:inherit;color:var(--ink);background:transparent;border:1.5px solid var(--ink);border-radius:999px;padding:5px 14px;cursor:pointer}
  .controls button:hover, .vset button:hover{background:#0000000d}
  .controls button[aria-pressed=true]:not(.sw), .vset button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
  .sw{width:26px;height:26px;padding:0;border-radius:50%} .sw[aria-pressed=true]{outline:2px solid var(--ink);outline-offset:2px}
  /* Storefront & stage-only chrome modes for EmDash sites */
  [data-chrome="storefront"] > header, [data-chrome="storefront"] .made-with,
  [data-chrome="storefront"] .ctl:has(#wb), [data-chrome="storefront"] .ctl:has(#pals){display:none!important}
  [data-chrome="storefront"] .controls{display:flex;justify-content:flex-end;border-top:0;padding-top:6px}
  [data-chrome="storefront"] .controls .ctl label{display:none}
  [data-chrome="stage-only"] > header, [data-chrome="stage-only"] .controls,
  [data-chrome="stage-only"] .made-with, [data-chrome="stage-only"] .actions{display:none!important}`;

const filterFor = k => `<filter id="hand" x="-3%" y="-3%" width="106%" height="106%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="${(0.045/k).toFixed(4)}" numOctaves="2" seed="4" result="warp"/>
  <feDisplacementMap id="wob" in="SourceGraphic" in2="warp" scale="${(2.4*k).toFixed(2)}" xChannelSelector="R" yChannelSelector="G" result="wob"/>
  <feTurbulence type="fractalNoise" baseFrequency="${(0.9/k).toFixed(4)}" numOctaves="3" seed="11" result="n1"/>
  <feColorMatrix in="n1" type="matrix" values=".3 0 0 0 .84  .3 0 0 0 .84  .3 0 0 0 .84  0 0 0 0 1" result="grain"/>
  <feTurbulence type="fractalNoise" baseFrequency="${(0.012/k).toFixed(4)}" numOctaves="2" seed="7" result="n2"/>
  <feColorMatrix in="n2" type="matrix" values=".3 0 0 0 .85  .3 0 0 0 .85  .3 0 0 0 .85  0 0 0 0 1" result="blot"/>
  <feBlend in="wob" in2="grain" mode="multiply" result="g1"/><feBlend in="g1" in2="blot" mode="multiply" result="g2"/>
  <feComposite in="g2" in2="wob" operator="in"/></filter>`;

addEventListener('error', e => { document.documentElement.dataset.errors = (document.documentElement.dataset.errors || '') + ' ' + e.message + ';'; });

function bakeNoise(svg){
  const fl = svg.querySelector('#hand') || document.getElementById('hand'); if (!fl || typeof Image === 'undefined') return;
  const NS = 'http://www.w3.org/2000/svg', vb = svg.viewBox.baseVal;
  const x0 = vb.x - vb.width*.35, y0 = vb.y - vb.height*.35, w0 = vb.width*1.7, h0 = vb.height*1.7;
  for (const t of [...fl.querySelectorAll('feTurbulence')]){
    const fq = parseFloat(t.getAttribute('baseFrequency')), oct = +(t.getAttribute('numOctaves') || 1);
    if (!(fq > 0)) continue;
    const fine = fq * Math.max(w0, h0) > 80;
    if (fine) continue;
    const rx = fine ? 0 : x0, ry = fine ? 0 : y0, rw = fine ? 48 / fq : w0, rh = fine ? 48 / fq : h0;
    const ppu = fq * (fine ? 7 : 5) * Math.pow(2, Math.max(0, oct - 1) * .5), PW = Math.ceil(rw * ppu), PH = Math.ceil(rh * ppu);
    if (PW * PH > 1200 * 1200) continue;
    const tb = t.cloneNode(); tb.removeAttribute('result'); if (fine) tb.setAttribute('stitchTiles', 'stitch');
    const src = `<svg xmlns="${NS}" width="${PW}" height="${PH}" viewBox="${rx} ${ry} ${rw} ${rh}"><filter id="n" filterUnits="userSpaceOnUse" x="${rx}" y="${ry}" width="${rw}" height="${rh}" color-interpolation-filters="sRGB">${tb.outerHTML}</filter><rect x="${rx}" y="${ry}" width="${rw}" height="${rh}" filter="url(#n)"/></svg>`;
    const img = new Image();
    img.onload = () => { try {
      const c = document.createElement('canvas'); c.width = PW; c.height = PH; const g = c.getContext('2d'); g.drawImage(img, 0, 0);
      const px = g.getImageData(0, 0, PW, PH); for (let i = 3; i < px.data.length; i += 4) px.data[i] = 255; g.putImageData(px, 0, 0);
      const url = c.toDataURL('image/png'), res = t.getAttribute('result');
      const im = document.createElementNS(NS, 'feImage');
      let ox = rx, oy = ry;
      if (fine){ const artEl = svg.querySelector('#art') || document.getElementById('art'); const bb = artEl ? artEl.getBBox() : { x: 0, y: 0, width: 0, height: 0 };
        ox = Math.floor((bb.x + bb.width/2) / rw) * rw; oy = Math.floor((bb.y + bb.height/2) / rh) * rh; }
      for (const [k, v] of [['x', ox], ['y', oy], ['width', rw], ['height', rh], ['preserveAspectRatio', 'none']]) im.setAttribute(k, v);
      im.setAttribute('href', url); im.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', url);
      if (!t.isConnected) return;
      if (fine){ im.setAttribute('result', res + '_tile'); const tl = document.createElementNS(NS, 'feTile'); tl.setAttribute('in', res + '_tile'); tl.setAttribute('result', res); t.replaceWith(im, tl); }
      else { im.setAttribute('result', res); t.replaceWith(im); }
    } catch (e) {} };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(src);
  }
}

/* Parse CSS color (#rgb, #rrggbb, rgb(...), light-dark(a, b)) into a #rrggbb hex string for matOf/mix */
function _isDarkScheme(el){
  try {
    const doc = document.documentElement;
    if (doc.dataset.theme === 'dark' || doc.classList.contains('dark')) return true;
    if (doc.dataset.theme === 'light' || doc.classList.contains('light')) return false;
    const cs = getComputedStyle(el || doc);
    if (cs.colorScheme === 'dark') return true;
    if (cs.colorScheme === 'light') return false;
    return typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches;
  } catch (_) { return false; }
}
function _toHex6(raw, el){
  if (!raw) return null;
  let s = raw.trim();
  const ld = s.match(/^light-dark\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)$/i);
  if (ld) s = (_isDarkScheme(el) ? ld[2] : ld[1]).trim();
  if (/^#[0-9a-fA-F]{6}$/.test(s)) return s.toLowerCase();
  if (/^#[0-9a-fA-F]{3}$/.test(s)) return '#' + s.slice(1).split('').map(c => c + c).join('').toLowerCase();
  const m = s.match(/rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i);
  if (m) return '#' + [m[1], m[2], m[3]].map(n => Math.max(0, Math.min(255, +n)).toString(16).padStart(2, '0')).join('');
  return null;
}

function _syncEmDashTokens(rootEl, cfg){
  if (cfg && cfg.tokens === false) return;
  try {
    const cs = getComputedStyle(rootEl || document.documentElement);
    const read = (...names) => { for (const n of names){ const v = cs.getPropertyValue(n).trim(); if (v) return v; } return ''; };
    const inkHex = _toHex6(read('--color-ink', '--color-text'), rootEl);
    if (inkHex) INK = inkHex;
    const shHex = _toHex6(read('--color-shadow'), rootEl);
    if (shHex) SHADOW = shHex;
    const accHex = _toHex6(read('--color-accent', '--color-primary'), rootEl);
    if (accHex) PALS.site = matOf(accHex);
  } catch (_) {}
}

let _activeRoot = null;
const _reducedMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

function mountFigure(cfg){
  const q = new URLSearchParams(location.search);
  const rawTarget = cfg.target || window.__EMDASH_MOTION_TARGET || null;
  const rootEl = typeof rawTarget === 'string' ? document.querySelector(rawTarget) : (rawTarget || document.body);
  _activeRoot = rootEl;
  const isStandalone = rootEl === document.body;
  const chrome = q.get('chrome') || cfg.chrome || (rootEl && rootEl.dataset && rootEl.dataset.chrome) || window.__EMDASH_MOTION_CHROME || (isStandalone ? 'full' : 'storefront');
  const palOverride = q.get('pal') || (rootEl && rootEl.dataset && rootEl.dataset.palette) || window.__EMDASH_MOTION_PALETTE || null;

  if (isStandalone) document.title = cfg.title;
  if (q.has('vw')){
    document.documentElement.style.maxWidth = q.get('vw') + 'px';
    document.body.style.maxWidth = q.get('vw') + 'px';
    document.body.style.margin = '0';
  }
  if (!document.getElementById('cf-core-css')){
    const style = document.createElement('style'); style.id = 'cf-core-css'; style.textContent = CORE_CSS; document.head.appendChild(style);
  }
  if (isStandalone) document.body.classList.add('cf-standalone');
  else rootEl.classList.add('cf-root');
  rootEl.setAttribute('data-chrome', chrome);
  _syncEmDashTokens(rootEl, cfg);

  rootEl.innerHTML = `
    <header><h1>Fig. ${cfg.fig} — ${cfg.title}</h1></header>
    <div class="stage">
      ${cfg.buttons && cfg.buttons.length ? `<div class="actions" id="btns"></div>` : ''}
      ${cfg.stats ? '<div class="stats" id="stats"></div>' : ''}
      <div class="toast" id="toast" role="status"></div>
      <svg id="fig" role="img" aria-label="${cfg.title}"><defs id="fdefs"></defs><g id="art" filter="url(#hand)"></g></svg>
    </div>
    <div id="readout"></div>
    ${cfg.idea ? `<p class="idea"><strong>The big idea</strong>${cfg.idea}</p>` : ''}
    <div class="controls">
      <div class="ctl"><label for="wb">Hand-drawn wobble</label><input id="wb" type="range" min="0" max="7" step="0.1" value="2.4"></div>
      <div class="ctl"><label>Colour</label><div class="row" id="pals"></div></div>
      <div class="ctl"><label>View</label><div class="row"><button id="vreset">Front view</button><button id="vspin" aria-pressed="false">Turntable</button></div></div>
      <div class="ctl" id="lblctl" hidden><label>Labels</label><div class="row"><button id="lbl" aria-pressed="true">On</button></div></div>
    </div>
    ${cfg.credit === false ? '' : '<footer class="made-with"><a href="https://april-zhu.com/colorfigures" target="_blank" rel="noopener">Made with Colorfigures ↗</a></footer>'}`;

  const byId = id => rootEl.querySelector('#' + id) || document.getElementById(id);
  const st = cfg.state || {};
  if (!st.pal) st.pal = cfg.palette || 'mustard';
  if (palOverride && PALS[palOverride]) st.pal = palOverride;
  if (st.az == null) st.az = 105;
  if (q.get('xr') === '1'){ st.xr = 1; st.xrT = 1; }
  CAM_LIM = cfg.turn === 'full' || q.get('free') === '1' ? null : 60;
  if (cfg.params) cfg.params(st, q);

  const [W,D,H] = cfg.size, pts = [];
  OX = OY = 0; RC = cfg.center || [W/2, D/2]; RCZ = H/2;
  VIEW = 0; setCam(YAW0, PITCH0);
  for (const x of [0,W]) for (const y of [0,D]) for (const z of [0,H]) pts.push(P(x,y,z));
  const xs=pts.map(p=>p[0]), ys=pts.map(p=>p[1]);
  const bw = Math.max(...xs)-Math.min(...xs), bh = Math.max(...ys)-Math.min(...ys);
  const PA = window.FIG_A ? FIG_A() : .75, A = PA === .75 ? .75 : Math.min(PA, Math.max(.75, bh/.88/(bw/.74)*1.08)), vbW = Math.max(bw/.74, bh/.88/A), vbH = vbW*A;
  OX = (vbW-bw)/2 + (PA === .75 ? vbW*.06 : 0) - Math.min(...xs); OY = (PA === .75 ? vbH*.04 : (vbH - bh)*.3) - Math.min(...ys);
  const svg = byId('fig');
  svg.setAttribute('viewBox', `0 0 ${f(vbW)} ${f(vbH)}`);
  INK_K = vbW / INK_REF_VB;
  byId('fdefs').innerHTML = filterFor(INK_K);
  bakeNoise(svg);

  const art = byId('art'), readout = byId('readout');
  const ui = { st, rootEl, chrome };
  ui.render = () => {
    _activeRoot = rootEl;
    _clipN = 0;
    const palObj = PALS[st.pal] || PALS.mustard;
    const accFg = _lum(palObj.l) < 0.48 ? '#ffffff' : '#1b222c';
    rootEl.style.setProperty('--accent', palObj.l);
    rootEl.style.setProperty('--accent-fg', accFg);
    if (isStandalone){
      document.documentElement.style.setProperty('--accent', palObj.l);
      document.documentElement.style.setProperty('--accent-fg', accFg);
    }
    art.innerHTML = inkScale(cfg.scene(st, palObj));
    if (!ui._flash) readout.textContent = cfg.readout ? cfg.readout(st) : '';
    if (ui.drawStats) ui.drawStats();
  };

  const statsEl = byId('stats'), prevStats = {};
  ui.drawStats = () => { if (!statsEl) return;
    const list = cfg.stats(st).filter(Boolean), html = list.map(x => `<div class="stat${x.small ? ' small' : ''}"><div class="k">${x.label}</div><div class="v" data-k="${x.label}">${x.value}</div></div>`).join('');
    if (statsEl._html !== html){ statsEl._html = html; statsEl.innerHTML = html;
      statsEl.querySelectorAll('.v').forEach(v => { if (prevStats[v.dataset.k] != null && prevStats[v.dataset.k] !== v.textContent) v.classList.add('bump'); prevStats[v.dataset.k] = v.textContent; }); } };
  let flashT = 0;
  const toast = byId('toast');
  ui.flash = (text, ms=1600) => { ui._flash = true; readout.textContent = text; toast.textContent = text;
    const btnsEl = byId('btns');
    toast.style.top = ((btnsEl ? btnsEl.offsetTop + btnsEl.offsetHeight : 0) + 8) + 'px'; toast.classList.add('show');
    clearTimeout(flashT); flashT = setTimeout(() => { ui._flash = false; toast.classList.remove('show'); ui.render(); }, ms); };

  const steps = new Set(); let driving = false, lastT = 0, fbT = 0;
  const frame = () => { if (!driving) return; driving = false; clearTimeout(fbT);
    const now = performance.now(), dt = Math.max(0, Math.min(.05, (now - lastT) / 1000)); lastT = now;
    for (const s of [...steps]) if (s(dt) === false) steps.delete(s);
    ui.render(); if (steps.size) drive(); };
  const drive = () => { if (driving) return; driving = true; requestAnimationFrame(frame); fbT = setTimeout(frame, 60); };
  ui.animate = step => { if (st.__scrubbed) return; if (!steps.size && !driving) lastT = performance.now(); steps.add(step); drive(); };
  ui.invalidate = () => drive();

  svg.addEventListener('pointerdown', e => { if (e.button) return; const a = e.target.closest('[data-act]'); if (!a || !cfg.acts || !cfg.acts[a.dataset.act]) return;
    e.preventDefault(); st.__scrubbed = false; cfg.acts[a.dataset.act](st, a, ui); ui.render(); });

  let drag = null, spin = false, camAnim = 0;
  const camTo = (y, p, ms=700) => { st.__scrubbed = false; const y0 = YAW, p0 = PITCH, dy = ((y - y0 + 540) % 360) - 180, id = ++camAnim; let t = 0;
    ui.animate(dt => { if (id !== camAnim) return false; t += dt*1000; const k = Math.min(1, t / ms), e = ease(k); setCam(y0 + dy*e, p0 + (p - p0)*e); return k < 1; }); };
  ui.camTo = camTo;
  svg.addEventListener('pointerdown', e => { if (e.button || e.target.closest('[data-act]')) return;
    camAnim++; drag = { x:e.clientX, y:e.clientY, yaw:YAW, pitch:PITCH }; svg.classList.add("drag"); try { svg.setPointerCapture(e.pointerId); } catch {} });
  svg.addEventListener('pointermove', e => { if (!drag) return; const k = 300 / (svg.getBoundingClientRect().width || 600);
    setCam(drag.yaw + (e.clientX - drag.x)*.55*k, drag.pitch + (e.clientY - drag.y)*.35*k); ui.invalidate(); });
  const endDrag = () => { drag = null; svg.classList.remove('drag'); };
  svg.addEventListener('pointerup', endDrag); svg.addEventListener('pointercancel', endDrag);
  svg.addEventListener('dblclick', e => { if (!e.target.closest('[data-act]')) camTo(YAW0, PITCH0); });
  addEventListener('keydown', e => { const k = { ArrowLeft:[-15,0], ArrowRight:[15,0], ArrowUp:[0,8], ArrowDown:[0,-8] }[e.key];
    if (!k || window.GAME_KEYS || /input|textarea/i.test(e.target.tagName)) return; e.preventDefault(); camTo(YAW + k[0], PITCH + k[1], 260); });
  byId('vreset').onclick = () => { spin = false; vsp.setAttribute('aria-pressed', false); camTo(YAW0, PITCH0); };
  const vsp = byId('vspin');
  const startSpin = () => { st.__scrubbed = false; spin = true; vsp.setAttribute('aria-pressed', 'true'); camAnim++;
    let dir = 1;
    ui.animate(dt => { if (!spin) return false; if (!drag){ let y = YAW + dir*dt*18;
      if (CAM_LIM != null && Math.abs(y - YAW0) >= CAM_LIM - .5){ dir = -dir; y = YAW + dir*dt*18; } setCam(y, PITCH); } return true; }); };
  vsp.onclick = () => { if (spin){ spin = false; vsp.setAttribute('aria-pressed', 'false'); camAnim++; } else startSpin(); };
  if ((cfg.autoplaySpin || q.get('spin') === '1') && !_reducedMotion() && !q.has('t')) startSpin();
  if (q.has('yaw') || q.has('pitch')) setCam(+(q.get('yaw') ?? YAW0), +(q.get('pitch') ?? PITCH0));

  const btns = byId('btns');
  const stepEls = [];
  if (btns) cfg.buttons.forEach((b, i) => {
    const wrap = document.createElement('div'); wrap.className = 'stepwrap';
    const el = document.createElement('button'); el.className = 'act';
    el.innerHTML = `${b.label}${b.choices ? '<span class="car">▾</span>' : ''}`;
    wrap.appendChild(el); btns.appendChild(wrap); stepEls.push(el);
    if (!b.choices){ el.onclick = () => { st.__scrubbed = false; closeChips(); b.onClick(st, ui); ui.render(); }; return; }
    const chips = document.createElement('div'); chips.className = 'chips'; wrap.appendChild(chips);
    el.onclick = e => { e.stopPropagation(); const open = !wrap.classList.contains('open'); closeChips();
      if (!open) return;
      chips.innerHTML = '';
      for (const c of b.choices(st)){ const ch = document.createElement('button'); ch.className = 'chip' + (c.current ? ' current' : c.disabled ? ' off' : ''); ch.textContent = c.label;
        if (c.current) ch.setAttribute('aria-pressed', 'true');
        ch.onclick = ev => { ev.stopPropagation(); closeChips();
          if (c.current) return ui.flash(`${c.label} — already set`);
          if (c.disabled) return ui.flash(c.why || `${c.label} isn't possible right now`);
          st.__scrubbed = false; c.onClick(st, ui); ui.render(); }; chips.appendChild(ch); }
      wrap.classList.add('open'); };
  });
  function closeChips(){ rootEl.querySelectorAll('.stepwrap.open').forEach(w => w.classList.remove('open')); }
  document.addEventListener('click', closeChips);

  byId('wb').oninput = e => { const wob = byId('wob'); if (wob) wob.setAttribute('scale', (e.target.value * INK_K).toFixed(2)); };
  const pals = byId('pals');
  for (const [k,p] of Object.entries(PALS)){
    if (k === 'site' && isStandalone && !q.has('pal')) continue;
    const b = document.createElement('button'); b.className='sw'; b.title=k; b.style.background=p.l; b.setAttribute('aria-pressed', k===st.pal);
    b.onclick = () => { st.pal=k; [...pals.children].forEach(c=>c.setAttribute('aria-pressed', c===b)); ui.render(); };
    pals.appendChild(b);
  }
  const lblctl = byId('lblctl'), lbl = byId('lbl');
  const setLabels = on => { if (isStandalone) document.documentElement.classList.toggle('nolabels', !on); rootEl.classList.toggle('nolabels', !on); lbl.textContent = on ? 'On' : 'Off'; lbl.setAttribute('aria-pressed', on); };
  lbl.onclick = () => setLabels(rootEl.classList.contains('nolabels'));
  if (q.get('labels') === '0') setLabels(false);

  // Deterministic ?t=0..1 timeline scrubbing for headless verification & interactive timelines
  ui.setTime = tNorm => {
    const t = Math.max(0, Math.min(1, +tNorm || 0));
    st.__t = t;
    st.__scrubbed = true;
    steps.clear(); driving = false; clearTimeout(fbT);
    if (typeof cfg.scrub === 'function'){
      cfg.scrub(st, t, ui);
    } else {
      // Built-in deterministic state mapping for standard Mode A mechanics
      if ('pos' in st && 'heat' in st && 'bend' in st){
        // Toaster-like thermal/spring cycle across t = 0..1
        if (t === 0){ st.phase = 'idle'; st.pos = 0; st.heat = 0; st.bend = 0; st.latch = 0; st.brown = 0; }
        else if (t < 0.75){
          const k = t / 0.75;
          st.phase = 'toast'; st.pos = Math.min(1, k * 4); st.heat = Math.min(1, k * 2.2);
          st.bend = Math.max(0, (k - 0.2) / 0.8); st.latch = 0; st.brown = k * 0.95;
        } else {
          const k = (t - 0.75) / 0.25;
          st.phase = k < 0.6 ? 'pop' : 'idle'; st.latch = Math.max(0, 1 - k * 1.5);
          st.pos = Math.max(0, 1 - ease(Math.min(1, k * 1.6))); st.heat = Math.max(0, 1 - k);
          st.bend = Math.max(0, 1 - k * 0.8); st.brown = 0.95;
        }
      } else if ('glow' in st && 'ang' in st && Array.isArray(st.ang)){
        // Jointed balanced-arm desk lamp cycle (POSES: read=[62,-12,-84], up=[74,18,-84], low=[40,-10,-86])
        st.on = t >= 0.12 && t <= 0.92;
        st.glow = st.on ? Math.min(1, (t - 0.08) * 4) : 0;
        st.moving = t > 0.2 && t < 0.8;
        const s = Math.sin(t * Math.PI);
        st.ang = [62 - 14 * s, -12 + 16 * s, -84 + 6 * Math.cos(t * Math.PI)];
      } else if (st.claw && typeof st.claw === 'object'){
        // Gantry / claw cycle (HB = 80 cabinet floor, ZTOP = 122, HOME = [67, 13])
        st.drop = { stop: 100, c: null, d: 99, grip: 'miss', oEnd: 0, z0: 104, x0: 40, y0: 43, dur: 1, o0: 0.45 };
        if (t === 0){
          st.phase = 'idle'; st.tokens = 10; st.time = 0;
          st.claw.x = 67; st.claw.y = 13; st.claw.z = 122; st.claw.o = 0;
        } else if (t < 0.35){
          const k = t / 0.35;
          st.phase = 'play'; st.tokens = 9; st.time = Math.round(20 - k * 6);
          st.claw.x = 67 - 27 * k; st.claw.y = 13 + 30 * k; st.claw.z = 122; st.claw.o = 0.2 * k;
        } else if (t < 0.7){
          const k = (t - 0.35) / 0.35, s = Math.sin(k * Math.PI);
          st.phase = k < 0.55 ? 'lower' : 'close'; st.tokens = 9; st.time = 12;
          st.claw.x = 40; st.claw.y = 43; st.claw.z = 122 - 18 * s; st.claw.o = 0.65;
        } else {
          const k = (t - 0.7) / 0.3;
          st.phase = 'carry'; st.tokens = 9; st.time = 0;
          st.claw.x = 40 + 27 * k; st.claw.y = 43 - 30 * k; st.claw.z = 122; st.claw.o = 0.45 * (1 - k);
        }
      }
    }
    ui.render();
  };
  window.__setMotionTime = ui.setTime;
  window.__st = st;

  const noteErr = m => { document.documentElement.dataset.errors = (document.documentElement.dataset.errors || '') + ' ' + m + ';'; };
  const starts = (el, t) => el.textContent.trim().toLowerCase().startsWith(t.trim().toLowerCase());
  if (q.has('press')) q.get('press').split(',').forEach(item => { const [what, ms] = item.split('@'), [label, choice] = what.split('>');
    setTimeout(() => { const b = [...rootEl.querySelectorAll('.act')].find(b => starts(b, label));
      if (!b) return noteErr(`no button "${label}"`);
      b.click(); if (choice == null) return;
      const c = [...b.parentElement.querySelectorAll('.chip')].find(c => starts(c, choice));
      if (c && !c.disabled) c.click(); else noteErr(`no choice "${choice}" in "${label}"`); }, +ms || 0); });

  setLight(st.az);
  if (q.has('t')) ui.setTime(+q.get('t'));
  else ui.render();
  if (art.querySelector('.tag')) lblctl.hidden = false;

  // Observe host theme/preset changes (Light/Dark or playground presets on EmDash sites)
  if (typeof MutationObserver !== 'undefined'){
    new MutationObserver(() => { _syncEmDashTokens(rootEl, cfg); ui.render(); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme', 'data-preset', 'style'] });
  }
  return ui;
}

/* ---------- see-through + labels kit ---------- */
function xrCallouts(items, B){
  const pts = []; for (const x of [B[0], B[1]]) for (const y of [B[2], B[3]]) for (const z of [B[4], B[5]]) pts.push(P(x, y, z));
  const xmin = Math.min(...pts.map(p => p[0])), xmax = Math.max(...pts.map(p => p[0])), cx = (xmin + xmax)/2;
  const k = INK_K, u = window.LBL_U ? LBL_U() : 0, fs = u ? 10*u : 8.6*k, hgt = u ? 17*u : fs*1.8, gap = hgt + (u ? 3*u : 3*k);
  const L = [], R = [];
  const scope = _activeRoot || document;
  const svgEl = scope.querySelector('#fig') || document.getElementById('fig'), vb = svgEl.viewBox.baseVal, btn = scope.querySelector('#btns') || document.getElementById('btns');
  const wMax = u ? hgt*1.3 + 12*k : Math.max(...items.map(it => it.text.length))*fs*.62 + fs*1.5 + 12*k;
  const roomL = xmin - vb.x >= wMax, roomR = vb.x + vb.width - xmax >= wMax;
  for (const it of items){ const [X, Y] = P(...it.at); ((X < cx && roomL) || !roomR ? L : R).push({ ...it, X, Y }); }
  let s = '';
  let top = { [-1]: fs, [1]: fs + 30*k };
  if (btn && svgEl.getScreenCTM()){ const r = btn.getBoundingClientRect(), q = new DOMPoint(r.right, r.bottom + 50).matrixTransform(svgEl.getScreenCTM().inverse());
    if (q.y > 0) top[-1] = q.y + hgt; }
  for (const [col, side] of [[L, -1], [R, 1]]){
    col.sort((a, b) => a.Y - b.Y);
    let y = -1e9; for (const c of col){ c.py = Math.max(c.Y, y + gap, top[side]); y = c.py; }
    const shift = col.length ? Math.max(0, col.reduce((a, c) => a + c.py - c.Y, 0) / col.length) : 0;
    const room = col.length ? col[0].py - top[side] : 0; for (const c of col) c.py -= Math.min(shift, room);
    for (const c of col){
      c.n = ((window.__ln || (window.__ln = {}))[c.text] || (__ln[c.text] = Object.keys(__ln).length + 1)); const w = u ? hgt*(c.n > 9 ? 1.3 : 1) : c.text.length*fs*.62 + fs*1.5;
      let px = side < 0 ? xmin - 10*k - w/2 : xmax + 10*k + w/2; px = Math.max(vb.x + w/2 + 2*k, Math.min(vb.x + vb.width - w/2 - 2*k, px));
      const ex = px - side*w/2;
      s += `<g class="tag${c.on ? ' on' : ''}" data-n="${c.n}" data-t="${c.text}"><path d="M${f(c.X)} ${f(c.Y)}L${f(ex + side*-4*k)} ${f(c.py)}L${f(ex)} ${f(c.py)}" fill="none" stroke="${INK}" stroke-width="1"/>`
        + `<circle cx="${f(c.X)}" cy="${f(c.Y)}" r="${f(1.4*k)}" fill="${INK}"/>`
        + `<rect x="${f(px - w/2)}" y="${f(c.py - hgt/2)}" width="${f(w)}" height="${f(hgt)}" rx="${f(hgt/2)}" fill="${c.on ? 'var(--accent,#f4b829)' : '#fff4d6'}" stroke="${INK}" stroke-width="1.2"/>`
        + `<text x="${f(px)}" y="${f(c.py + fs*.36)}" font-size="${f(fs)}" text-anchor="middle" font-family="ui-monospace,Menlo,monospace" font-weight="800" letter-spacing=".04em" fill="${c.on ? 'var(--accent-fg,#1b222c)' : '#1b222c'}">${u ? c.n : c.text}</text></g>`;
    }
  }
  return s;
}
function xrGhost(body, mech, k, OUTp, x0, x1, m){
  const fF = facing([1,0,0]), fB = facing([-1,0,0]);
  const far = `<g opacity="${f(.5*k)}">` + loft(on(PX(x0), OUTp), on(PX(x1), OUTp), n => mix(toneI(n.map(v => -v), m), '#f2efe7', .55), true)
    + (fF ? fill(pd(on(PX(x0), OUTp)), mix(m.d, '#f2efe7', .5)) : '') + (fB ? fill(pd(on(PX(x1), OUTp)), mix(m.d, '#f2efe7', .5)) : '') + `</g>`;
  return far + mech + `<g opacity="${f(1 - .8*k)}">${body}</g>` + `<g opacity="${f(.6*k)}">` + hullInk([...on(PX(x0), OUTp), ...on(PX(x1), OUTp)], 2.8) + `</g>`;
}
function xrMount(getUI, caption, opt = {}){
  const ui = getUI(), q = new URLSearchParams(location.search), html = document.documentElement, rootEl = ui.rootEl || document.body;
  const isStandalone = rootEl === document.body;
  if (q.get('labels') !== '1'){ if (isStandalone) html.classList.add('nolabels'); rootEl.classList.add('nolabels'); }
  else { if (isStandalone) html.classList.remove('nolabels'); rootEl.classList.remove('nolabels'); }
  if (ui.st.xr == null){ ui.st.xr = 0; ui.st.xrT = 0; }
  if (q.get('xr') === '1') ui.st.xr = ui.st.xrT = 1;
  const old = rootEl.querySelector('#lblctl') || document.getElementById('lblctl'); if (old) old.style.display = 'none';
  const stageEl = rootEl.querySelector('.stage') || document.querySelector('.stage');
  const vset = document.createElement('div'); vset.className = 'vset';
  vset.innerHTML = '<div class="vrow">' + (opt.labelsOnly ? '' : '<button class="act" id="xrb" aria-pressed="false">See-through</button>') + '<button class="act" id="lblb" aria-pressed="false">Labels</button></div>';
  stageEl.appendChild(vset);
  const statsEl = rootEl.querySelector('#stats') || document.getElementById('stats');
  const place = () => { vset.style.top = statsEl ? (statsEl.offsetTop + statsEl.offsetHeight + 10) + 'px' : ''; };
  place(); if (typeof ResizeObserver !== 'undefined') new ResizeObserver(place).observe(statsEl || vset);
  const xrb = vset.querySelector('#xrb'), lblb = vset.querySelector('#lblb');
  const sync = () => { if (xrb) xrb.setAttribute('aria-pressed', !!getUI().st.xrT); lblb.setAttribute('aria-pressed', !rootEl.classList.contains('nolabels')); };
  if (xrb) xrb.onclick = () => { const u = getUI(), st = u.st; st.xr = st.xr || 0; st.xrT = st.xrT ? 0 : 1; sync();
    u.animate(dt => { const g = Math.sign(st.xrT - st.xr); st.xr = Math.min(1, Math.max(0, st.xr + g*dt/.7)); return st.xr !== st.xrT; }); };
  lblb.onclick = () => { const off = rootEl.classList.toggle('nolabels'); if (isStandalone) html.classList.toggle('nolabels', off); sync(); };
  sync();
  const cap = document.createElement('p'); cap.className = 'mcap'; stageEl.after(cap);
  if (!document.getElementById('cf-xr-css')){
    const css = document.createElement('style'); css.id = 'cf-xr-css';
    css.textContent = '.vset{position:absolute;top:4px;right:0;z-index:2}.vrow{display:flex;gap:6px}.vset .act[aria-pressed=true]{background:var(--ink);color:var(--paper)}'
      + 'html.nolabels body.cf-standalone #fig .tag, .cf-root.nolabels #fig .tag{display:none}.mcap{width:100%;max-width:760px;min-height:3em;margin:0 0 14px;font-size:12.5px;line-height:1.5;text-align:center;transition:opacity .3s}'
      + '@media (max-width:560px){.vset{position:static;margin:4px 0}}';
    document.head.appendChild(css);
  }
  const r0 = ui.render; ui.render = () => { r0(); const st = getUI().st; cap.style.opacity = st.xr > .5 ? 1 : 0; cap.textContent = caption ? caption(st) : ''; };
  if (q.has('t') && ui.setTime) ui.setTime(+q.get('t'));
  else ui.render();
}
function xrGhostRings(body, mech, k, A, B, m){
  const far = `<g opacity="${f(.5*k)}">` + loft(A, B, n => mix(toneI(n.map(v => -v), m), '#f2efe7', .55), true) + fill(pd(A), mix(m.d, '#f2efe7', .5)) + `</g>`;
  return far + mech + `<g opacity="${f(1 - .8*k)}">${body}</g>` + `<g opacity="${f(.6*k)}">` + hullInk([...A, ...B], 2.8) + `</g>`;
}
const xrUnder = (svg, mech, k) => `<g opacity="${f(k)}">${mech}</g><g opacity="${f(1 - .62*k)}">${svg}</g>`;
function xrWrap(sceneFn, opts){
  return function(){
    let s = sceneFn.apply(this, arguments);
    const st = opts.getSt(), k = ease(st.xr || 0);
    if (k > 0 && opts.under) s = xrUnder(s, opts.mech(st, k), k);
    else if (k > 0 && !opts.inline) s = `<g opacity="${f(1 - .5*k)}">${s}</g><g opacity="${f(k)}">${opts.mech(st, k)}</g>`;
    if (k > 0 && opts.over) s += opts.over(st, k);
    const items = k > .6 ? opts.inside(st) : opts.surface ? opts.surface(st) : [];
    return s + (items.length ? xrCallouts(items, opts.B) : '');
  };
}

function mountKeypad(spec){
  const scope = _activeRoot || document;
  const host = scope.querySelector('#btns') || document.getElementById('btns'); if (!host) return;
  if (!document.getElementById('cf-kpad-css')){
    const css = document.createElement('style'); css.id = 'cf-kpad-css';
    css.textContent = `.kpad{display:flex;align-items:center;gap:16px;margin-top:6px;padding:10px 12px;border:1.5px solid var(--ink);border-radius:14px;
        background:var(--paper);box-shadow:0 3px 0 var(--ink);touch-action:none;user-select:none;-webkit-user-select:none}
      .kpad .dp{display:grid;grid-template-columns:repeat(3,34px);grid-template-rows:repeat(var(--rows),34px);gap:3px}
      .kpad .k{all:unset;box-sizing:border-box;display:flex;align-items:center;justify-content:center;width:34px;height:34px;cursor:pointer;
        background:#fbf7ea;border:1.5px solid var(--ink);border-radius:7px;box-shadow:0 3px 0 var(--ink);color:var(--ink);font:700 13px ui-monospace,Menlo,monospace;
        transition:transform .05s,box-shadow .05s,background .05s}
      .kpad .hub{width:34px;height:34px;display:flex;align-items:center;justify-content:center}
      .kpad .hub i{width:12px;height:12px;border-radius:50%;border:1.5px solid var(--ink);background:#e6e0d1}
      .kpad .go{all:unset;box-sizing:border-box;width:62px;height:62px;border-radius:50%;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;
        background:#e2483d;border:1.5px solid var(--ink);box-shadow:0 4px 0 var(--ink),inset 0 -5px 0 rgba(0,0,0,.18);color:#fff;font:800 12px ui-monospace,Menlo,monospace;letter-spacing:.06em;
        transition:transform .05s,box-shadow .05s}
      .kpad .go small{font:700 8px ui-monospace,Menlo,monospace;opacity:.85;letter-spacing:.08em;margin-top:2px}
      .kpad .down{transform:translateY(2px);box-shadow:0 1px 0 var(--ink)}
      .kpad .k.down{background:var(--accent,#f4b829)}
      .kpad .go.down{transform:translateY(3px);box-shadow:0 1px 0 var(--ink),inset 0 -3px 0 rgba(0,0,0,.18)}
      @media (max-width:560px){.kpad{gap:22px;padding:10px 16px}.kpad .dp{grid-template-columns:repeat(3,44px);grid-template-rows:repeat(var(--rows),44px)}
        .kpad .k,.kpad .hub{width:44px;height:44px;font-size:15px}.kpad .go{width:74px;height:74px}}`;
    document.head.appendChild(css);
  }
  const pad = document.createElement('div'); pad.className = 'kpad'; pad.setAttribute('role', 'group'); pad.setAttribute('aria-label', 'Keypad');
  const dp = document.createElement('div'); dp.className = 'dp'; dp.style.setProperty('--rows', spec.rows);
  const els = {};
  for (const k of spec.keys){
    const b = document.createElement('button'); b.className = 'k'; b.textContent = k.glyph; b.setAttribute('aria-label', k.name);
    b.style.gridColumn = k.at[0] + 1; b.style.gridRow = k.at[1] + 1; dp.appendChild(b); els[k.key] = b; }
  if (spec.hub){ const h = document.createElement('div'); h.className = 'hub'; h.innerHTML = '<i></i>'; h.style.gridColumn = spec.hub[0] + 1; h.style.gridRow = spec.hub[1] + 1; dp.appendChild(h); }
  const go = document.createElement('button'); go.className = 'go'; go.innerHTML = `${spec.action}<small>SPACE</small>`; go.setAttribute('aria-label', spec.action);
  els[' '] = go;
  pad.append(dp, go); host.appendChild(pad);
  const send = (type, key) => dispatchEvent(new KeyboardEvent(type, { key, bubbles: true }));
  for (const [key, el] of Object.entries(els)){
    let held = null;
    el.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); if (held != null) return; held = e.pointerId;
      try { el.setPointerCapture(e.pointerId); } catch (_) {} send('keydown', key); });
    const release = e => { if (held == null || (e && e.pointerId !== held)) return; held = null; send('keyup', key); };
    el.addEventListener('pointerup', release); el.addEventListener('pointercancel', release); el.addEventListener('lostpointercapture', release);
    el.addEventListener('click', e => e.preventDefault());
    el.addEventListener('keydown', e => { if (e.key === 'Enter'){ e.preventDefault(); send('keydown', key); setTimeout(() => send('keyup', key), 120); } });
  }
  addEventListener('keydown', e => { if (e.key === ' ' && e.target && e.target.closest && e.target.closest('button')) e.preventDefault(); }, true);
  addEventListener('keyup', e => { if (e.key === ' ' && e.target && e.target.closest && e.target.closest('button')) e.preventDefault(); }, true);
  addEventListener('keydown', e => { const el = els[e.key]; if (el) el.classList.add('down'); });
  addEventListener('keyup', e => { const el = els[e.key]; if (el) el.classList.remove('down'); });
  addEventListener('blur', () => Object.values(els).forEach(el => el.classList.remove('down')));
}
