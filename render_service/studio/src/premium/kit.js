// Premium Faceless Reel kit for the Animave Style Studio (window.PR): kinetic type that sharpens letter by letter, one
// accent colour, glossy tilted cards holding live UI diagrams (tables, dashboards, search results, maps, profiles,
// networks, chats), depth from blurred accent shapes and bokeh, one continuous camera with motion blur, an end card.
// The look follows the "premium faceless Reels" workflow published by @aygramm.ai, rebuilt for our pipeline.
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env } from '../common/lib.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env };

export let SW = 1080, SH = 1920;
export function setScreen(w, h) { SW = w; SH = h; }
export const C = { bg: '#ffffff', ink: '#0d0d12', grey: '#9a9aa6', soft: '#ececf2', line: '#e3e3ea', accent: '#5B21B6' };
export function setAccent(hex) { if (/^#[0-9a-f]{6}$/i.test(hex || '')) C.accent = hex; }
const SANS = (w, px) => `${w} ${px}px Inter`, SERIF = px => `italic 600 ${px}px PlayfairDisplay`;
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };
const mixHex = (a, b, k) => { const p = h => [0, 2, 4].map(i => parseInt(h.slice(1 + i, 3 + i), 16)); const A = p(a), B = p(b); return '#' + A.map((v, i) => Math.round(lerp(v, B[i], k)).toString(16).padStart(2, '0')).join(''); };
const cv = (w, h) => new OffscreenCanvas(Math.max(1, Math.ceil(w)), Math.max(1, Math.ceil(h)));

// —— the camera: keys [[t, x, y, zoom, rotDeg], ...] eased (in-out cubic), never parked: a slow drift is added ——
export function camera(keys, { drift = 1 } = {}) {
  return t => {
    let a = keys[0], b = keys[keys.length - 1], u = 0;
    if (t <= keys[0][0]) b = a; else if (t >= b[0]) a = b;
    else for (let i = 0; i < keys.length - 1; i++) if (t < keys[i + 1][0]) { a = keys[i]; b = keys[i + 1]; u = eio(seg(t, a[0], b[0])); break; }
    const z = Math.exp(lerp(Math.log(a[3] ?? 1), Math.log(b[3] ?? 1), u));
    return { x: lerp(a[1], b[1], u) + Math.sin(t * .31) * 14 * drift, y: lerp(a[2], b[2], u) + Math.cos(t * .23) * 10 * drift, z: z * (1 + .012 * Math.sin(t * .17) * drift),
      rot: (lerp(a[4] || 0, b[4] || 0, u) + Math.sin(t * .19) * .5 * drift) * Math.PI / 180 };
  };
}
function apply(ctx, c) { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.translate(SW / 2, SH / 2); ctx.rotate(c.rot); ctx.scale(c.z * SW / 1080, c.z * SW / 1080); ctx.translate(-c.x, -c.y); }

// —— the background: white, a far layer of big blurred accent shapes, a near layer of bokeh (cached sprites) ——
let _blob = null, _bokeh = null, _grain = null, _vig = null;
function sprites() {
  if (_blob && _blob.acc === C.accent) return;
  _blob = cv(512, 512); const b = _blob.getContext('2d'), g = b.createRadialGradient(256, 256, 0, 256, 256, 256);
  g.addColorStop(0, rgba(C.accent, .55)); g.addColorStop(.6, rgba(C.accent, .18)); g.addColorStop(1, rgba(C.accent, 0)); b.fillStyle = g; b.fillRect(0, 0, 512, 512); _blob.acc = C.accent;
  _bokeh = cv(128, 128); const k = _bokeh.getContext('2d'), h = k.createRadialGradient(64, 64, 20, 64, 64, 64);
  h.addColorStop(0, rgba(C.accent, .22)); h.addColorStop(.8, rgba(C.accent, .14)); h.addColorStop(1, rgba(C.accent, 0)); k.fillStyle = h; k.fillRect(0, 0, 128, 128);
  _grain = cv(256, 256); const gr = _grain.getContext('2d'), img = gr.createImageData(256, 256), R = mulberry(5);
  for (let i = 0; i < 256 * 256; i++) { const v = R() * 255; img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 14; }
  gr.putImageData(img, 0, 0);
}
export function begin(ctx, t, cam) {
  sprites(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, SW, SH);
  const R = mulberry(17), px = cam ? cam.x : 0, py = cam ? cam.y : 0;
  for (let i = 0; i < 5; i++) {   // far: big soft shapes, slow parallax
    const s = (700 + R() * 600) * SW / 1080, x = ((R() * 1.6 - .3) * SW - px * .15 + Math.sin(t * .1 + i) * 60) % (SW * 1.6), y = ((R() * 1.4 - .2) * SH - py * .15 + Math.cos(t * .08 + i) * 80);
    ctx.globalAlpha = .2; ctx.drawImage(_blob, x - s / 2, y - s / 2, s, s);
  }
  for (let i = 0; i < 9; i++) {  // near: bokeh drifting faster
    const s = (60 + R() * 160) * SW / 1080, x = (((R() * SW - px * .6 + t * (8 + R() * 14)) % (SW + 200)) + SW + 200) % (SW + 200) - 100, y = (((R() * SH - py * .6 - t * (6 + R() * 10)) % (SH + 200)) + SH + 200) % (SH + 200) - 100;
    ctx.globalAlpha = .32; ctx.drawImage(_bokeh, x - s / 2, y - s / 2, s, s);
  }
  ctx.globalAlpha = 1;
}
// film grain + vignette, last
export function finish(ctx, t, { fade = 1 } = {}) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
  if (!_vig || _vig.width !== SW) { _vig = cv(SW, SH); const v = _vig.getContext('2d'), g = v.createRadialGradient(SW / 2, SH / 2, SH * .3, SW / 2, SH / 2, SH * .75); g.addColorStop(0, 'rgba(20,10,40,0)'); g.addColorStop(1, 'rgba(20,10,40,.16)'); v.fillStyle = g; v.fillRect(0, 0, SW, SH); }
  ctx.drawImage(_vig, 0, 0);
  const o = Math.floor(t * 24) % 4; ctx.fillStyle = ctx.createPattern(_grain, 'repeat'); ctx.save(); ctx.translate(o * 37, o * 53); ctx.fillRect(-200, -200, SW + 400, SH + 400); ctx.restore();
  if (fade < 1) { ctx.globalAlpha = 1 - clamp(fade); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, SW, SH); ctx.globalAlpha = 1; }
}
// draw the world through the camera, with motion blur on fast moves (sub-frames)
let _mb = null;
export function world(ctx, t, cam, draw, { maxSub = 5 } = {}) {
  const a = cam(t), b = cam(Math.max(0, t - 1 / 30));
  const sp = Math.hypot((a.x - b.x) * a.z, (a.y - b.y) * a.z) + Math.abs(Math.log(a.z / b.z)) * 1400 + Math.abs(a.rot - b.rot) * 900;
  const N = sp > 18 ? Math.min(maxSub, Math.ceil(sp / 22)) : 1;
  if (N === 1) { ctx.save(); apply(ctx, a); draw(ctx, t, a); ctx.restore(); return a; }
  // draw the world ONCE at the current camera, then smear that picture along the camera's path (cheap motion blur)
  if (!_mb || _mb.width !== SW) _mb = cv(SW, SH);
  ctx.save(); apply(ctx, a); draw(ctx, t, a); ctx.restore();          // the picture, on the page canvas (fast path)
  const m = _mb.getContext('2d'); m.setTransform(1, 0, 0, 1, 0, 0); m.clearRect(0, 0, SW, SH); m.drawImage(ctx.canvas, 0, 0, SW, SH);
  const M = c => { const d = new DOMMatrix(); d.translateSelf(SW / 2, SH / 2); d.rotateSelf(c.rot * 180 / Math.PI); d.scaleSelf(c.z * SW / 1080, c.z * SW / 1080); d.translateSelf(-c.x, -c.y); return d; };
  const inv = M(a).inverse();
  for (let i = 1; i < N; i++) {
    const ci = cam(t - (1 / 30) * .6 * i / Math.max(1, N - 1)), d = M(ci).multiply(inv);
    ctx.setTransform(d.a, d.b, d.c, d.d, d.e, d.f); ctx.globalAlpha = 1 / (i + 1); ctx.drawImage(_mb, 0, 0);
  }
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1; return a;
}

// —— kinetic type: each letter arrives grey and blurred, then sharpens to its colour, synced to the spoken words ——
// line = T.lines[i]; o: { x, y (centre, world), size: 64, maxW: 860, key: ['word', ...] (accent + serif italic), out: t1 (fade/blur out),
//        lead: .05 (letters start this long before their word), color }
export function type(ctx, t, line, o = {}) {
  const toks = String(line.text).split(/\s+/).filter(Boolean);
  let words = (line.words && line.words.length ? line.words : toks.map((w, i) => ({ w, s: line.start + i * .25, e: line.start + i * .25 + .2 })));
  if (toks.length === words.length) words = words.map((x, i) => ({ ...x, w: toks[i] }));   // keep the script's punctuation
  const size = o.size ?? 64, maxW = o.maxW ?? 860, keys = (o.key || []).map(k => String(k).toLowerCase().replace(/[^a-z0-9%$€£.-]/g, ''));
  const isKey = w => keys.includes(String(w).toLowerCase().replace(/[^a-z0-9%$€£.-]/g, ''));
  if (t < words[0].s - .4) return;
  const out = o.out != null ? clamp((t - o.out) / .35) : 0; if (out >= 1) return;
  // layout rows
  const meas = w => { ctx.font = isKey(w) ? SERIF(size * 1.08) : SANS(500, size); return ctx.measureText(w).width; };
  ctx.save(); const sp = size * .28, rows = [[]]; let rw = 0;
  for (const w of words) { const ww = meas(w.w); if (rw + ww > maxW && rows[rows.length - 1].length) { rows.push([]); rw = 0; } rows[rows.length - 1].push({ ...w, ww }); rw += ww + sp; }
  const lh = size * 1.22, y0 = (o.y ?? 0) - (rows.length - 1) * lh / 2;
  rows.forEach((row, ri) => {
    const W = row.reduce((a, w) => a + w.ww + (isKey(w.w) ? size * .12 : 0), 0) + sp * (row.length - 1); let x = (o.x ?? 0) - W / 2;
    for (const w of row) {
      const key = isKey(w.w), font = key ? SERIF(size * 1.08) : SANS(500, size); ctx.font = font; ctx.textBaseline = 'middle';
      const chars = [...w.w], dur = Math.max(.12, (w.e - w.s) * .9), lead = o.lead ?? .05;
      let cx = x;
      chars.forEach((ch, ci) => {
        const t0 = w.s - lead + dur * ci / chars.length, u = clamp((t - t0) / .22); const cw = ctx.measureText(ch).width;
        if (u > 0) {
          const blur = (1 - eo(u)) * 10, col = key ? C.accent : (o.color || C.ink);
          ctx.globalAlpha = Math.min(1, u * 2.2) * (1 - out);
          ctx.fillStyle = u < 1 ? mixHex('#b9b9c4', col, eo(u)) : col;
          if (blur > 1) ctx.filter = `blur(${blur.toFixed(1)}px)`;
          ctx.fillText(ch, cx, y0 + ri * lh + (1 - eo(u)) * 10 - out * 20);
          ctx.filter = 'none';
        }
        cx += cw;
      });
      x += w.ww + sp + (key ? size * .12 : 0);
    }
  });
  ctx.restore();
}
// one huge blurred word that resolves (the opening), centred at (x, y)
export function bigWord(ctx, t, word, t0, t1, { x = 0, y = 0, size = 260, key = true } = {}) {
  if (t < t0 - .3 || t > t1) return; const u = clamp((t - t0 + .3) / .9), out = clamp((t - (t1 - .35)) / .35);
  ctx.save(); ctx.font = key ? SERIF(size) : SANS(600, size); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.globalAlpha = eo(u) * (1 - out); ctx.fillStyle = key ? C.accent : C.ink; ctx.filter = `blur(${((1 - eo(u)) * 26 + out * 20).toFixed(1)}px)`;
  ctx.translate(x, y); const s = lerp(1.25, 1, eo(u)) * (1 + out * .2); ctx.scale(s, s); ctx.fillText(word, 0, 0); ctx.restore();
}

// —— glossy cards: soft gradient fill, glossy top highlight, 3-4 layered accent-tinted shadows, 3D tilt as they enter ——
// o: { x, y (centre), w, h, t0 (enter), t1 (leave), from: 'bottom' | 'right' | 'left' | 'top', r: 34, tint: 0..1 accent fill }
// inside(ctx, t, box) draws the card's content with box = { x, y, w, h } (top-left based, card space)
export function card(ctx, t, o, inside) {
  const t0 = o.t0 ?? 0, t1 = o.t1 ?? 1e9; if (t < t0 - .05 || t > t1 + .4) return;
  const u = eo(seg(t, t0, t0 + .55)), out = ss(seg(t, t1, t1 + .4)), w = o.w, h = o.h, r = o.r ?? 34;
  const dir = { bottom: [0, 1], top: [0, -1], right: [1, 0], left: [-1, 0] }[o.from || 'bottom'];
  ctx.save(); ctx.translate(o.x + dir[0] * (1 - u) * 260 - (out ? dir[0] * out * 200 : 0), o.y + dir[1] * (1 - u) * 260 + out * 80);
  // fake 3D tilt: a vertical squash and a skew that flatten out as it lands, plus the idle float
  const tilt = (1 - u) * .5 + Math.sin(t * .9 + o.x * .01) * .025;
  ctx.transform(1, 0, (dir[0] ? -dir[0] : .4) * tilt * .35, 1 - tilt * .25, 0, 0); ctx.rotate((1 - u) * (dir[0] || .6) * .06 + Math.sin(t * .7 + o.y * .01) * .006);
  ctx.globalAlpha = u * (1 - out);
  const X = -w / 2, Y = -h / 2;
  for (const [dy, bl, a] of [[6, 10, .10], [18, 30, .10], [40, 60, .10], [70, 110, .08]]) { ctx.shadowColor = rgba(C.accent, a); ctx.shadowBlur = bl; ctx.shadowOffsetY = dy; ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.roundRect(X, Y, w, h, r); ctx.fill(); }
  ctx.shadowColor = 'transparent';
  const g = ctx.createLinearGradient(0, Y, 0, Y + h); g.addColorStop(0, '#ffffff'); g.addColorStop(1, o.tint ? mixHex('#f6f4fb', C.accent, o.tint * .12) : '#f6f5fa'); ctx.fillStyle = g; ctx.beginPath(); ctx.roundRect(X, Y, w, h, r); ctx.fill();
  const hl = ctx.createLinearGradient(0, Y, 0, Y + h * .35); hl.addColorStop(0, 'rgba(255,255,255,.95)'); hl.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = hl; ctx.beginPath(); ctx.roundRect(X + 2, Y + 2, w - 4, h * .35, [r - 2, r - 2, 0, 0]); ctx.fill();
  ctx.strokeStyle = 'rgba(20,10,60,.08)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.roundRect(X, Y, w, h, r); ctx.stroke();
  ctx.filter = 'none';
  if (inside) {   // the content is drawn at o.scale (default 1.35) so phone screens can read it
    const k = o.scale ?? 1.35; ctx.save(); ctx.beginPath(); ctx.roundRect(X, Y, w, h, r); ctx.clip(); ctx.scale(k, k);
    inside(ctx, t, { x: (X + 40) / k, y: (Y + 40) / k, w: (w - 80) / k, h: (h - 80) / k }); ctx.restore();
  }
  ctx.restore();
}

// —— UI diagrams (drawn inside a card; `at` = the times each item appears, usually T.w(i, 'word') values) ——
const at_ = (o, i, t0) => (o.at && o.at[i] != null ? o.at[i] : (o.t0 ?? t0) + i * (o.stagger ?? .18));
const pop = (t, a) => eo(seg(t, a, a + .3));
function pill(ctx, x, y, text, { bg = C.accent, fg = '#fff', size = 24 } = {}) { ctx.font = SANS(600, size); const w = ctx.measureText(text).width + size * 1.1; ctx.fillStyle = bg; ctx.beginPath(); ctx.roundRect(x, y, w, size * 1.6, size * .8); ctx.fill(); ctx.fillStyle = fg; ctx.textBaseline = 'middle'; ctx.fillText(text, x + size * .55, y + size * .82); return w; }
function header(ctx, box, title, sub) { ctx.textBaseline = 'alphabetic'; ctx.font = SANS(700, 34); ctx.fillStyle = C.ink; ctx.fillText(title, box.x, box.y + 34); if (sub) { ctx.font = SANS(500, 24); ctx.fillStyle = C.grey; ctx.fillText(sub, box.x, box.y + 70); } return sub ? 100 : 62; }
const fmt = (v, dec = 0) => Number(v).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
export const ui = {
  // a comparison / pricing table: cols = ['Plan', 'Price', ...], rows = [['Basic', '$9'], ...], hi = row index in accent
  table(ctx, t, box, { title = '', sub = '', cols = [], rows = [], hi = -1, ...o } = {}) {
    let y = box.y + header(ctx, box, title, sub); const cw = box.w / Math.max(1, cols.length), rh = Math.min(86, (box.h - (y - box.y) - 50) / Math.max(1, rows.length));
    ctx.font = SANS(600, 22); ctx.fillStyle = C.grey; cols.forEach((c, i) => ctx.fillText(c.toUpperCase(), box.x + i * cw, y + 26)); y += 46;
    rows.forEach((r, ri) => { const a = pop(t, at_(o, ri, 0)); if (a <= 0) return; ctx.globalAlpha = a; const yy = y + ri * rh + (1 - a) * 20;
      if (ri === hi) { ctx.fillStyle = rgba(C.accent, .1); ctx.beginPath(); ctx.roundRect(box.x - 14, yy, box.w + 28, rh - 8, 16); ctx.fill(); }
      r.forEach((c, ci) => { ctx.font = SANS(ci ? 600 : 500, 30); ctx.fillStyle = ri === hi ? C.accent : C.ink; ctx.fillText(String(c), box.x + ci * cw, yy + rh / 2 + 6); });
      ctx.globalAlpha = 1; ctx.fillStyle = C.line; ctx.fillRect(box.x, yy + rh - 4, box.w, 2); });
  },
  // search results that re-sort: results = [{ title, sub, score }]; at resort (time) they slide into the order of `order` (indices)
  search(ctx, t, box, { query = '', results = [], order = null, resort = 1e9, hi = -1, ...o } = {}) {
    ctx.fillStyle = '#fff'; ctx.strokeStyle = C.line; ctx.lineWidth = 2; ctx.beginPath(); ctx.roundRect(box.x, box.y, box.w, 76, 38); ctx.fill(); ctx.stroke();
    const n = Math.floor(query.length * clamp((t - (o.t0 ?? 0)) / .8)); ctx.font = SANS(500, 30); ctx.fillStyle = C.ink; ctx.textBaseline = 'middle'; ctx.fillText(query.slice(0, n) + (n < query.length && Math.floor(t * 4) % 2 ? '|' : ''), box.x + 74, box.y + 39);
    ctx.strokeStyle = C.grey; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(box.x + 40, box.y + 36, 13, 0, TAU); ctx.moveTo(box.x + 50, box.y + 46); ctx.lineTo(box.x + 60, box.y + 56); ctx.stroke();
    const rh = Math.min(130, (box.h - 110) / Math.max(1, results.length)), k = eio(seg(t, resort, resort + .6));
    results.forEach((r, i) => { const a = pop(t, at_(o, i, .9)); if (a <= 0) return; const j = order ? order.indexOf(i) : i, slot = lerp(i, j < 0 ? i : j, k), y = box.y + 106 + slot * rh;
      ctx.globalAlpha = a; ctx.fillStyle = i === hi && k > .5 ? rgba(C.accent, .08) : '#fff'; ctx.beginPath(); ctx.roundRect(box.x, y, box.w, rh - 14, 18); ctx.fill();
      ctx.fillStyle = i === hi && k > .5 ? C.accent : C.ink; ctx.font = SANS(600, 30); ctx.textBaseline = 'alphabetic'; ctx.fillText(r.title, box.x + 24, y + 46);
      if (r.sub) { ctx.font = SANS(500, 22); ctx.fillStyle = C.grey; ctx.fillText(r.sub, box.x + 24, y + 80); }
      if (r.score != null) { ctx.font = SANS(700, 30); ctx.textAlign = 'right'; ctx.fillStyle = i === hi && k > .5 ? C.accent : C.ink; ctx.fillText(String(r.score), box.x + box.w - 24, y + 56); ctx.textAlign = 'left'; }
      ctx.globalAlpha = 1; });
  },
  // a dashboard: kpis = [{ label, value, prefix, suffix, dec, up: true }], bars = [numbers], line = [numbers]; counters roll from t0
  dashboard(ctx, t, box, { title = '', kpis = [], bars = [], line = [], ...o } = {}) {
    let y = box.y + (title ? header(ctx, box, title) : 0); const kw = box.w / Math.max(1, kpis.length);
    kpis.forEach((k, i) => { const a0 = at_(o, i, 0), u = eo(seg(t, a0, a0 + .9)); if (t < a0) return;
      ctx.font = SANS(500, 22); ctx.fillStyle = C.grey; ctx.textBaseline = 'alphabetic'; ctx.fillText(k.label, box.x + i * kw, y + 26);
      ctx.font = SANS(700, 52); ctx.fillStyle = u >= 1 && k.hi ? C.accent : C.ink; ctx.fillText((k.prefix || '') + fmt(k.value * u, k.dec || 0) + (k.suffix || ''), box.x + i * kw, y + 86);
      if (k.up != null) { ctx.fillStyle = k.up ? '#16a34a' : '#dc2626'; ctx.font = SANS(700, 22); ctx.fillText(k.up ? '▲' : '▼', box.x + i * kw, y + 118); } });
    if (kpis.length) y += 150;
    const ch = box.y + box.h - y; if (ch < 120) return;
    if (bars.length) { const m = Math.max(...bars), bw = box.w / bars.length; bars.forEach((v, i) => { const a0 = (o.barsAt ?? (o.t0 ?? 0) + .3) + i * .06, u = eo(seg(t, a0, a0 + .5)), hh = (ch - 40) * v / m * u; ctx.fillStyle = i === bars.length - 1 ? C.accent : rgba(C.accent, .25); ctx.beginPath(); ctx.roundRect(box.x + i * bw + bw * .18, box.y + box.h - hh, bw * .64, hh, 10); ctx.fill(); }); }
    else if (line.length) { const m = Math.max(...line), mn = Math.min(...line), u = eio(seg(t, o.lineAt ?? (o.t0 ?? 0) + .3, (o.lineAt ?? (o.t0 ?? 0) + .3) + 1.2)), n = (line.length - 1) * u;
      const P = i => [box.x + i / (line.length - 1) * box.w, box.y + box.h - 20 - (line[i] - mn) / Math.max(1e-6, m - mn) * (ch - 60)];
      ctx.strokeStyle = C.accent; ctx.lineWidth = 7; ctx.lineJoin = ctx.lineCap = 'round'; ctx.beginPath(); for (let i = 0; i <= Math.floor(n); i++) (i ? ctx.lineTo : ctx.moveTo).apply(ctx, P(i));
      if (n % 1) { const i = Math.floor(n), a = P(i), b = P(i + 1); ctx.lineTo(lerp(a[0], b[0], n % 1), lerp(a[1], b[1], n % 1)); } ctx.stroke();
      if (u >= 1) { const p = P(line.length - 1); ctx.fillStyle = C.accent; ctx.beginPath(); ctx.arc(p[0], p[1], 12, 0, TAU); ctx.fill(); ctx.strokeStyle = rgba(C.accent, .4 * (1 - (t * 1.2) % 1)); ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(p[0], p[1], 12 + ((t * 1.2) % 1) * 30, 0, TAU); ctx.stroke(); } }
  },
  // a market map: dots = [[x, y, label?], ...] in 0..1, hi = indices in accent; axes labels
  map(ctx, t, box, { title = '', x = '', y = '', dots = [], hi = [], ...o } = {}) {
    const top = box.y + (title ? header(ctx, box, title) : 0), H = box.y + box.h - top;
    ctx.strokeStyle = C.line; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(box.x, top + H / 2); ctx.lineTo(box.x + box.w, top + H / 2); ctx.moveTo(box.x + box.w / 2, top); ctx.lineTo(box.x + box.w / 2, top + H); ctx.stroke();
    ctx.font = SANS(500, 20); ctx.fillStyle = C.grey; ctx.fillText(x, box.x + box.w - ctx.measureText(x).width, top + H / 2 - 12); ctx.fillText(y, box.x + box.w / 2 + 12, top + 22);
    dots.forEach((d, i) => { const a = pop(t, at_(o, i, 0)); if (a <= 0) return; const h = hi.includes(i), px = box.x + d[0] * box.w, py = top + (1 - d[1]) * H;
      ctx.globalAlpha = a; ctx.fillStyle = h ? C.accent : '#c9c9d4'; ctx.beginPath(); ctx.arc(px, py, (h ? 18 : 12) * back(a, 2), 0, TAU); ctx.fill();
      if (h) { ctx.strokeStyle = rgba(C.accent, .35 * (1 - (t * 1.1 + i * .3) % 1)); ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(px, py, 18 + ((t * 1.1 + i * .3) % 1) * 34, 0, TAU); ctx.stroke(); }
      if (d[2]) { ctx.font = SANS(h ? 700 : 500, 22); ctx.fillStyle = h ? C.accent : C.grey; ctx.fillText(d[2], px + 24, py + 8); } ctx.globalAlpha = 1; });
  },
  // a profile card: name, role, tags (pills), stats [[label, value]]
  profile(ctx, t, box, { name = '', role = '', tags = [], stats = [], ...o } = {}) {
    const a0 = o.t0 ?? 0; ctx.fillStyle = rgba(C.accent, .15); ctx.beginPath(); ctx.arc(box.x + 56, box.y + 56, 56, 0, TAU); ctx.fill();
    ctx.font = SANS(700, 44); ctx.fillStyle = C.accent; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText((name[0] || '?').toUpperCase(), box.x + 56, box.y + 58); ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic'; ctx.font = SANS(700, 38); ctx.fillStyle = C.ink; ctx.fillText(name, box.x + 140, box.y + 50); ctx.font = SANS(500, 26); ctx.fillStyle = C.grey; ctx.fillText(role, box.x + 140, box.y + 90);
    let x = box.x; tags.forEach((g, i) => { const a = pop(t, at_(o, i, a0 + .2)); if (a <= 0) return; ctx.globalAlpha = a; x += pill(ctx, x, box.y + 150, g, { bg: i === 0 ? C.accent : C.soft, fg: i === 0 ? '#fff' : C.ink }) + 12; ctx.globalAlpha = 1; });
    const sw = box.w / Math.max(1, stats.length); stats.forEach(([l, v], i) => { const a = pop(t, a0 + .5 + i * .15); ctx.globalAlpha = a; ctx.font = SANS(700, 44); ctx.fillStyle = C.ink; ctx.fillText(String(v), box.x + i * sw, box.y + 290); ctx.font = SANS(500, 22); ctx.fillStyle = C.grey; ctx.fillText(l, box.x + i * sw, box.y + 324); ctx.globalAlpha = 1; });
  },
  // a network with pulses: nodes = [[x, y, label], ...] in 0..1, edges = [[a, b], ...], hub = index; pulses run along the edges
  network(ctx, t, box, { nodes = [], edges = [], hub = 0, ...o } = {}) {
    const P = n => [box.x + nodes[n][0] * box.w, box.y + nodes[n][1] * box.h];
    edges.forEach(([a, b], i) => { const u = eo(seg(t, at_(o, i, .2), at_(o, i, .2) + .4)); if (u <= 0) return; const A = P(a), B = P(b);
      ctx.strokeStyle = rgba(C.accent, .3); ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(lerp(A[0], B[0], u), lerp(A[1], B[1], u)); ctx.stroke();
      if (u >= 1) { const k = (t * .8 + i * .37) % 1; ctx.fillStyle = C.accent; ctx.beginPath(); ctx.arc(lerp(A[0], B[0], k), lerp(A[1], B[1], k), 8, 0, TAU); ctx.fill(); } });
    nodes.forEach((n, i) => { const a = pop(t, (o.t0 ?? 0) + i * .08); if (a <= 0) return; const [x, y] = P(i), h = i === hub;
      ctx.globalAlpha = a; ctx.fillStyle = h ? C.accent : '#fff'; ctx.strokeStyle = h ? C.accent : C.line; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(x, y, h ? 42 : 30, 0, TAU); ctx.fill(); ctx.stroke();
      if (n[2]) { ctx.font = SANS(600, 22); ctx.fillStyle = h ? C.accent : C.ink; ctx.textAlign = 'center'; ctx.fillText(n[2], x, y + (h ? 76 : 62)); ctx.textAlign = 'left'; } ctx.globalAlpha = 1; });
  },
  // a chat: msgs = [{ me: true, text }], each bubble appears at its time (a typing dot shows first)
  chat(ctx, t, box, { msgs = [], ...o } = {}) {
    let y = box.y;
    msgs.forEach((m, i) => { const a0 = at_(o, i, 0); if (t < a0 - .5) return; ctx.font = SANS(500, 28); const lines = [], words = m.text.split(' '); let cur = '';
      for (const w of words) { const nx = cur ? cur + ' ' + w : w; if (ctx.measureText(nx).width > box.w * .66 && cur) { lines.push(cur); cur = w; } else cur = nx; } lines.push(cur);
      const bw = Math.max(...lines.map(l => ctx.measureText(l).width)) + 48, bh = lines.length * 38 + 30, x = m.me ? box.x + box.w - bw : box.x;
      if (t < a0) { ctx.fillStyle = C.soft; ctx.beginPath(); ctx.roundRect(x, y, 110, 60, 30); ctx.fill(); for (let k = 0; k < 3; k++) { ctx.fillStyle = C.grey; ctx.beginPath(); ctx.arc(x + 32 + k * 23, y + 30 + Math.sin(t * 9 + k) * 4, 7, 0, TAU); ctx.fill(); } y += 80; return; }
      const a = pop(t, a0); ctx.globalAlpha = a; ctx.fillStyle = m.me ? C.accent : C.soft; ctx.beginPath(); ctx.roundRect(x, y + (1 - a) * 16, bw, bh, 28); ctx.fill();
      ctx.fillStyle = m.me ? '#fff' : C.ink; ctx.textBaseline = 'alphabetic'; lines.forEach((l, k) => ctx.fillText(l, x + 24, y + 46 + k * 38 + (1 - a) * 16)); ctx.globalAlpha = 1; y += bh + 22; });
  },
  // a checklist: items = ['...'], done = indices ticked (tick draws at its `at` time)
  checklist(ctx, t, box, { title = '', items = [], ...o } = {}) {
    let y = box.y + (title ? header(ctx, box, title) : 0); const rh = Math.min(96, (box.y + box.h - y) / Math.max(1, items.length));
    items.forEach((it, i) => { const a0 = at_(o, i, 0), a = pop(t, a0 - .2); if (a <= 0) return; const k = eo(seg(t, a0, a0 + .3)); ctx.globalAlpha = a;
      ctx.fillStyle = k > .5 ? C.accent : '#fff'; ctx.strokeStyle = k > .5 ? C.accent : C.line; ctx.lineWidth = 4; ctx.beginPath(); ctx.roundRect(box.x, y + 12, 52, 52, 14); ctx.fill(); ctx.stroke();
      if (k > 0) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 7; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(box.x + 14, y + 38); ctx.lineTo(box.x + 14 + 9 * Math.min(1, k * 2), y + 38 + 9 * Math.min(1, k * 2)); if (k > .5) ctx.lineTo(box.x + 23 + 16 * (k - .5) * 2, y + 47 - 20 * (k - .5) * 2); ctx.stroke(); }
      ctx.font = SANS(500, 32); ctx.fillStyle = C.ink; ctx.textBaseline = 'middle'; ctx.fillText(it, box.x + 78, y + 38); ctx.globalAlpha = 1; y += rh; });
  },
  // two columns side by side: left / right = { title, items: [...] }, the right one is the good one (accent)
  compare(ctx, t, box, { left = {}, right = {}, ...o } = {}) {
    const cw = (box.w - 24) / 2;
    [[left, 0], [right, 1]].forEach(([col, k]) => { const x = box.x + k * (cw + 24), a = pop(t, at_(o, k, 0)); if (a <= 0) return; ctx.globalAlpha = a;
      ctx.fillStyle = k ? rgba(C.accent, .08) : C.soft; ctx.beginPath(); ctx.roundRect(x, box.y, cw, box.h, 24); ctx.fill();
      ctx.font = SANS(700, 32); ctx.fillStyle = k ? C.accent : C.grey; ctx.textBaseline = 'alphabetic'; ctx.fillText(col.title || '', x + 24, box.y + 54);
      (col.items || []).forEach((it, i) => { const b = pop(t, at_(o, 2 + k * 10 + i, 0) + (o.at ? 0 : k * .4)); ctx.globalAlpha = a * b; ctx.font = SANS(500, 26); ctx.fillStyle = C.ink; ctx.fillText((k ? '✓  ' : '✕  ') + it, x + 24, box.y + 112 + i * 54); });
      ctx.globalAlpha = 1; });
  },
  // a notification stack: items = [{ title, sub }] sliding in from the top
  notifs(ctx, t, box, { items = [], ...o } = {}) {
    items.forEach((n, i) => { const a = pop(t, at_(o, i, 0)); if (a <= 0) return; const y = box.y + i * 150 - (1 - a) * 60; ctx.globalAlpha = a;
      ctx.fillStyle = '#fff'; ctx.strokeStyle = C.line; ctx.lineWidth = 2; ctx.beginPath(); ctx.roundRect(box.x, y, box.w, 124, 28); ctx.fill(); ctx.stroke();
      ctx.fillStyle = C.accent; ctx.beginPath(); ctx.roundRect(box.x + 24, y + 26, 72, 72, 18); ctx.fill();
      ctx.font = SANS(700, 28); ctx.fillStyle = C.ink; ctx.textBaseline = 'alphabetic'; ctx.fillText(n.title, box.x + 118, y + 56); ctx.font = SANS(500, 22); ctx.fillStyle = C.grey; ctx.fillText(n.sub || '', box.x + 118, y + 92); ctx.globalAlpha = 1; });
  },
};

// the end card: the handle as a text wordmark that flickers in
export function endCard(ctx, t, t0, handle, { y = 0 } = {}) {
  if (t < t0 || !handle) return; const u = t - t0, on = u > .5 || [.05, .12, .2, .27, .38].some((a, i) => u > a && (i % 2 === 0));
  if (!on) return; ctx.save(); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.font = SANS(700, 76); ctx.fillStyle = C.ink; ctx.globalAlpha = u > .5 ? 1 : .8; ctx.fillText(handle, 0, y);
  ctx.fillStyle = C.accent; ctx.fillRect(-ctx.measureText(handle).width / 2, y + 56, ctx.measureText(handle).width * eo(seg(u, .5, 1.1)), 8); ctx.restore();
}
// sound events: [{ t, type, v, d }] with type in tick (a UI tick), type (letters typing; d), slide (a panel sliding in),
// whip (a glitchy whip on a camera move), count (a counter rolling; d), pop, riser (d), hit (the last word)
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
