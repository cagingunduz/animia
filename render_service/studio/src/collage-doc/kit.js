// Collage Documentary kit for the Animave Style Studio (window.CD): biography / history reels made like a hand-made
// documentary collage. A paper ground, full-bleed archival photo plates with a slow push, cut-out people and objects
// placed on them with real drop shadows, limbs that move in small stop-motion steps, framed portraits and taped
// documents, big serif words that land exactly as the narrator says them, hand-drawn white rings / underlines /
// arrows, torn-paper cuts, grain and gate weave. The method follows Naomi Metzger's (@naometzger) guide to
// documentary-style reels, rebuilt for our pipeline.
//
// Pictures come from the pipeline as T.img[id] (HTMLImageElement, loaded): plates (backgrounds), cut-outs (alpha),
// portraits and documents. Every drawing function skips a missing picture instead of throwing.
import { clamp, lerp, seg, ss, eo, ei, eio, back, hash, mulberry, TAU, env } from '../common/lib.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, hash, mulberry, TAU, env };

export let SW = 1080, SH = 1920;
export function setScreen(w, h) { SW = w; SH = h; }
export const C = { paper: '#e9e4d8', paperDark: '#26231f', ink: '#1b1916', white: '#f7f4ec', shadow: 'rgba(12,10,8,.55)' };
const cv = (w, h) => new OffscreenCanvas(Math.max(1, Math.ceil(w)), Math.max(1, Math.ceil(h)));
const ok = img => !!(img && (img.naturalWidth || img.width));
const IW = img => img.naturalWidth || img.width, IH = img => img.naturalHeight || img.height;
export const FPS_STEP = 12;
// stop-motion time: held for 1/12 s, then jumps
export const step = (t, fps = FPS_STEP) => Math.floor(t * fps + 1e-6) / fps;
// a tiny per-step wobble ("boil") so pasted things feel alive and hand-placed
const boil = (t, seed, amp = 1) => { const k = Math.floor(t * FPS_STEP); return (hash(k * 7.13 + seed * 3.7) - .5) * 2 * amp; };

// —— paper ground (built once): warm off-white or dark board, fibres, blotches, edge darkening ——
let _paper = {};
function paperTex(tone) {
  if (_paper[tone]) return _paper[tone];
  const W = 1080, H = 1920, p = cv(W, H), g = p.getContext('2d'), R = mulberry(tone === 'dark' ? 41 : 23);
  g.fillStyle = tone === 'dark' ? C.paperDark : C.paper; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 70; i++) {          // blotches
    const x = R() * W, y = R() * H, r = 60 + R() * 260, gr = g.createRadialGradient(x, y, 0, x, y, r);
    const a = .025 + R() * .045, dark = R() < .6;
    gr.addColorStop(0, dark ? `rgba(70,55,35,${a})` : `rgba(255,252,240,${a})`); gr.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = gr; g.fillRect(x - r, y - r, 2 * r, 2 * r);
  }
  g.lineCap = 'round';
  for (let i = 0; i < 1400; i++) {        // fibres
    const x = R() * W, y = R() * H, l = 6 + R() * 22, a = R() * TAU;
    g.strokeStyle = R() < .5 ? `rgba(60,48,32,${.04 + R() * .06})` : `rgba(255,255,248,${.05 + R() * .08})`;
    g.lineWidth = .6 + R() * .9; g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x + Math.cos(a + 1) * l * .5, y + Math.sin(a + 1) * l * .5, x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke();
  }
  const img = g.getImageData(0, 0, W, H), d = img.data;   // fine tooth
  for (let i = 0; i < d.length; i += 4) { const n = (R() - .5) * 16; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
  g.putImageData(img, 0, 0);
  const v = g.createRadialGradient(W / 2, H / 2, H * .35, W / 2, H / 2, H * .78);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, tone === 'dark' ? 'rgba(0,0,0,.45)' : 'rgba(60,45,25,.22)');
  g.fillStyle = v; g.fillRect(0, 0, W, H);
  return (_paper[tone] = p);
}
// the paper ground: tone 'light' (default) or 'dark'
export function paper(ctx, t, { tone = 'light' } = {}) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
  const k = Math.floor(t * FPS_STEP) % 3;    // the sheet shifts a pixel or two per step, like a re-shot frame
  ctx.drawImage(paperTex(tone), -2 + k, -2 + (k * 2) % 3, SW + 4, SH + 4);
}

// —— a slow push on everything drawn inside (a scene's "camera") ——
// K.view(ctx, t, { t0, t1, z0: 1, z1: 1.06, x0: 0, y0: 0, x1: 0, y1: 0 }, () => { ...draw the scene... })
// x/y are the pan in screen px (positive = the picture moves right / down), around the frame centre.
export function view(ctx, t, o, draw) {
  const u = ss(seg(t, o.t0 ?? 0, o.t1 ?? 1)), z = lerp(o.z0 ?? 1, o.z1 ?? 1.06, u);
  ctx.save(); ctx.translate(SW / 2 + lerp(o.x0 || 0, o.x1 || 0, u), SH / 2 + lerp(o.y0 || 0, o.y1 || 0, u)); ctx.scale(z, z); ctx.translate(-SW / 2, -SH / 2);
  draw(); ctx.restore();
}

// —— a full-bleed photo plate (cover-fit), printed onto the paper ——
// K.plate(ctx, t, img, { t0, t1, z0: 1.0, z1: 1.08, x: 0.5, y: 0.5 (focus 0..1 of the image), alpha, dim: 0..1 })
export function plate(ctx, t, img, o = {}) {
  if (!ok(img)) return;
  const u = ss(seg(t, o.t0 ?? 0, o.t1 ?? (o.t0 ?? 0) + 6)), z = lerp(o.z0 ?? 1, o.z1 ?? 1.08, u);
  const s = Math.max(SW / IW(img), SH / IH(img)) * z, w = IW(img) * s, h = IH(img) * s;
  const fx = o.x ?? .5, fy = o.y ?? .5, x = clamp(SW / 2 - fx * w, SW - w, 0), y = clamp(SH / 2 - fy * h, SH - h, 0);
  const k = Math.floor(t * FPS_STEP), wx = (hash(k) - .5) * 3, wy = (hash(k + 9) - .5) * 3;   // gate weave
  ctx.save(); ctx.globalAlpha = o.alpha ?? 1; ctx.drawImage(img, x + wx - 2, y + wy - 2, w + 4, h + 4);
  if (o.dim) { ctx.globalAlpha = clamp(o.dim); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, SW, SH); }
  ctx.restore();
}

// shadow sprites, cached per picture: the silhouette, blurred
const _sh = new WeakMap();
function shadowOf(img, blur) {
  let m = _sh.get(img); if (!m) _sh.set(img, m = {});
  if (m[blur]) return m[blur];
  const sc = Math.min(1, 700 / Math.max(IW(img), IH(img))), pad = blur * 3, w = IW(img) * sc, h = IH(img) * sc;
  const c = cv(w + pad * 2, h + pad * 2), g = c.getContext('2d');
  g.filter = `blur(${blur}px)`; g.drawImage(img, pad, pad, w, h); g.filter = 'none';
  g.globalCompositeOperation = 'source-in'; g.fillStyle = '#000'; g.fillRect(0, 0, c.width, c.height);
  return (m[blur] = { c, sc, pad });
}
function drawShadowed(ctx, img, x, y, w, h, { shadow = 1, dx = 14, dy = 18, blur = 10 } = {}) {
  if (shadow > 0) {
    const S = shadowOf(img, blur), k = w / (IW(img) * S.sc);
    ctx.save(); ctx.globalAlpha *= .55 * shadow;
    ctx.drawImage(S.c, x - S.pad * k + dx * shadow, y - S.pad * k + dy * shadow, S.c.width * k, S.c.height * k); ctx.restore();
  }
  ctx.drawImage(img, x, y, w, h);
}
// entry / exit offsets for a pasted piece, in stop-motion steps
function moveIn(t, at, from, dur) {
  const u = step(t) < at ? -1 : seg(step(t), at, at + dur);
  if (u < 0) return null;
  const e = from === 'pop' ? back(u, 1.6) : eo(u);
  switch (from) {
    case 'left': return { dx: (1 - e) * -900, dy: 0, s: 1, r: (1 - e) * -8 };
    case 'right': return { dx: (1 - e) * 900, dy: 0, s: 1, r: (1 - e) * 8 };
    case 'top': return { dx: 0, dy: (1 - e) * -1400, s: 1, r: (1 - e) * 5 };
    case 'bottom': return { dx: 0, dy: (1 - e) * 1400, s: 1, r: (1 - e) * -5 };
    case 'pop': return { dx: 0, dy: 0, s: .5 + .5 * e, r: (1 - u) * 6 };
    case 'drop': return { dx: 0, dy: (1 - e) * -60, s: 1 + (1 - e) * .12, r: (1 - e) * 4, lift: 1 - e };   // placed down from above the page
    default: return { dx: 0, dy: 0, s: 1, r: 0 };
  }
}
function outOf(t, out, dur = .35) { if (out == null) return 1; return 1 - seg(t, out, out + dur); }

// —— a cut-out pasted into the scene (people, hands, objects, animals...) ——
// K.paste(ctx, t, img, { x, y, h | w, anchor: 'bottom' | 'center' | 'top', at, from: 'drop' | 'pop' | 'left' | 'right' |
//   'top' | 'bottom' | 'none', dur: .5, rot (deg), flip, shadow: 1, out, path: [[t, x, y], ...] (a walk, in steps) })
export function paste(ctx, t, img, o = {}) {
  if (!ok(img)) return;
  const at = o.at ?? 0, mv = moveIn(t, at, o.from || 'drop', o.dur ?? .5); if (!mv) return;
  const a = outOf(t, o.out); if (a <= 0) return;
  let x = o.x ?? SW / 2, y = o.y ?? SH * .8;
  if (o.path && o.path.length) { const q = step(t), P = o.path; let i = 0; while (i < P.length - 1 && q > P[i + 1][0]) i++;
    const A = P[i], B = P[Math.min(i + 1, P.length - 1)], u = B[0] > A[0] ? clamp((q - A[0]) / (B[0] - A[0])) : 1; x = lerp(A[1], B[1], u); y = lerp(A[2], B[2], u); }
  const h = o.h ?? (o.w ? o.w * IH(img) / IW(img) : 700), w = o.w ?? h * IW(img) / IH(img);
  const oy = o.anchor === 'center' ? -h / 2 : o.anchor === 'top' ? 0 : -h;
  const seed = (o.seed ?? IW(img) % 97);
  ctx.save(); ctx.globalAlpha *= a;
  ctx.translate(x + mv.dx + boil(t, seed, .8), y + mv.dy + boil(t, seed + 1, .8));
  ctx.rotate(((o.rot || 0) + mv.r + boil(t, seed + 2, .15)) * Math.PI / 180); ctx.scale(mv.s * (o.flip ? -1 : 1), mv.s);
  drawShadowed(ctx, img, -w / 2, oy, w, h, { shadow: (o.shadow ?? 1) * (1 + (mv.lift || 0) * 1.5), dx: 14 + (mv.lift || 0) * 30, dy: 18 + (mv.lift || 0) * 40, blur: 10 });
  ctx.restore();
}

// —— a limb / hand / object turning about a pivot in small stop-motion steps ——
// K.swing(ctx, t, img, { x, y (where the pivot sits on screen), h | w, pivot: [px, py] (0..1 of the picture), keys:
//   [[t, deg], ...], at, from, shadow, flip })   e.g. an arm clapping: keys [[2.0, -30], [2.25, 0], [2.5, -30], ...]
export function swing(ctx, t, img, o = {}) {
  if (!ok(img)) return;
  const at = o.at ?? 0, mv = moveIn(t, at, o.from || 'none', o.dur ?? .4); if (!mv) return;
  const a = outOf(t, o.out); if (a <= 0) return;
  const q = step(t), K = o.keys || [[0, 0]]; let i = 0; while (i < K.length - 1 && q > K[i + 1][0]) i++;
  const A = K[i], B = K[Math.min(i + 1, K.length - 1)], deg = q <= K[0][0] ? K[0][1] : lerp(A[1], B[1], B[0] > A[0] ? eio(clamp((q - A[0]) / (B[0] - A[0]))) : 1);
  const h = o.h ?? (o.w ? o.w * IH(img) / IW(img) : 600), w = o.w ?? h * IW(img) / IH(img), pv = o.pivot || [.5, 1];
  ctx.save(); ctx.globalAlpha *= a; ctx.translate((o.x ?? SW / 2) + mv.dx, (o.y ?? SH / 2) + mv.dy);
  ctx.rotate((deg + mv.r) * Math.PI / 180); ctx.scale(mv.s * (o.flip ? -1 : 1), mv.s);
  drawShadowed(ctx, img, -pv[0] * w, -pv[1] * h, w, h, { shadow: o.shadow ?? 1 });
  ctx.restore();
}

// —— a printed photo or document with a white border, tape and a shadow ——
// K.photo(ctx, t, img, { x, y (centre), w, rot, at, from: 'drop', border: 18 | 0, tape: true, out, tone: 'sepia' })
export function photo(ctx, t, img, o = {}) {
  if (!ok(img)) return;
  const at = o.at ?? 0, mv = moveIn(t, at, o.from || 'drop', o.dur ?? .45); if (!mv) return;
  const a = outOf(t, o.out); if (a <= 0) return;
  const w = o.w ?? 640, h = o.h ?? w * IH(img) / IW(img), b = o.border ?? 18;
  ctx.save(); ctx.globalAlpha *= a; ctx.translate((o.x ?? SW / 2) + mv.dx, (o.y ?? SH / 2) + mv.dy);
  ctx.rotate(((o.rot ?? -2) + mv.r) * Math.PI / 180); ctx.scale(mv.s, mv.s);
  ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.45)'; ctx.shadowBlur = 26; ctx.shadowOffsetX = 12 + (mv.lift || 0) * 30; ctx.shadowOffsetY = 18 + (mv.lift || 0) * 40;
  ctx.fillStyle = '#f3efe4'; ctx.fillRect(-w / 2 - b, -h / 2 - b, w + 2 * b, h + 2 * b); ctx.restore();
  ctx.drawImage(img, -w / 2, -h / 2, w, h);
  if (o.tape !== false) for (const [tx, ty, tr] of [[-w / 2 + 30, -h / 2 - b + 4, -18], [w / 2 - 30, -h / 2 - b + 4, 16]]) {
    ctx.save(); ctx.translate(tx, ty); ctx.rotate(tr * Math.PI / 180); ctx.fillStyle = 'rgba(236,230,210,.78)';
    ctx.fillRect(-55, -16, 110, 32); ctx.fillStyle = 'rgba(255,255,255,.18)'; ctx.fillRect(-55, -16, 110, 6); ctx.restore();
  }
  ctx.restore();
}

// —— a framed portrait: a gilt or black wooden frame drawn around the picture, hung on the wall ——
// K.frame(ctx, t, img, { x, y (centre), w, at, from: 'drop', style: 'gilt' | 'black', out })
export function frame(ctx, t, img, o = {}) {
  if (!ok(img)) return;
  const at = o.at ?? 0, mv = moveIn(t, at, o.from || 'drop', o.dur ?? .5); if (!mv) return;
  const a = outOf(t, o.out); if (a <= 0) return;
  const w = o.w ?? 560, h = o.h ?? w * IH(img) / IW(img), f = Math.max(26, w * .085), gilt = (o.style || 'gilt') === 'gilt';
  ctx.save(); ctx.globalAlpha *= a; ctx.translate((o.x ?? SW / 2) + mv.dx, (o.y ?? SH / 2) + mv.dy); ctx.rotate(mv.r * Math.PI / 180); ctx.scale(mv.s, mv.s);
  ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 40; ctx.shadowOffsetX = 16; ctx.shadowOffsetY = 26;
  ctx.fillStyle = gilt ? '#7a5a22' : '#141210'; ctx.fillRect(-w / 2 - f, -h / 2 - f, w + 2 * f, h + 2 * f); ctx.restore();
  // moulding: bands with highlights and an ornament dot rhythm
  const bands = gilt ? [['#b58a3a', 0], ['#e6c56e', .18], ['#8a6424', .4], ['#d9b45c', .62], ['#5e4214', .86]] : [['#2a2622', 0], ['#4a443c', .3], ['#191714', .6], ['#3a352f', .85]];
  for (const [col, k] of bands) { const i = f * k; ctx.strokeStyle = col; ctx.lineWidth = f * .22; ctx.strokeRect(-w / 2 - f + i + f * .11, -h / 2 - f + i + f * .11, w + 2 * f - 2 * i - f * .22, h + 2 * f - 2 * i - f * .22); }
  if (gilt) { ctx.fillStyle = 'rgba(255,236,170,.55)'; const n = Math.round((w + h) / 26);
    for (let i = 0; i < n; i++) { const u = i / n, per = 2 * (w + h), d = u * per, p = d < w ? [-w / 2 + d, -h / 2 - f * .5] : d < w + h ? [w / 2 + f * .5, -h / 2 + d - w] : d < 2 * w + h ? [w / 2 - (d - w - h), h / 2 + f * .5] : [-w / 2 - f * .5, h / 2 - (d - 2 * w - h)];
      ctx.beginPath(); ctx.arc(p[0], p[1], f * .07, 0, TAU); ctx.fill(); } }
  ctx.drawImage(img, -w / 2, -h / 2, w, h);
  const gl = ctx.createLinearGradient(-w / 2, -h / 2, w / 2, h / 2); gl.addColorStop(0, 'rgba(255,255,255,.10)'); gl.addColorStop(.5, 'rgba(255,255,255,0)'); ctx.fillStyle = gl; ctx.fillRect(-w / 2, -h / 2, w, h);
  ctx.strokeStyle = 'rgba(0,0,0,.5)'; ctx.lineWidth = 3; ctx.strokeRect(-w / 2, -h / 2, w, h);
  ctx.restore();
}

// —— words ——
const FONT = { display: (px) => `italic 600 ${px}px PlayfairDisplay`, light: (px) => `italic 500 ${px}px Cormorant`, roman: (px) => `600 ${px}px Cormorant` };
const _m = cv(8, 8).getContext('2d');
export function measure(text, size = 120, font = 'display') { _m.font = FONT[font](size); return _m.measureText(text).width; }
function glyphs(ctx, text, x, y, size, font, color, a, s) {
  ctx.save(); ctx.globalAlpha *= a; ctx.translate(x, y); ctx.scale(s, s); ctx.font = FONT[font](size); ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  const light = color !== C.ink && !/^#[0-3]/.test(color);
  ctx.shadowColor = light ? 'rgba(0,0,0,.7)' : 'rgba(255,250,235,.35)'; ctx.shadowBlur = size * .22; ctx.shadowOffsetY = size * .03;
  ctx.fillStyle = color; ctx.fillText(text, 0, 0); ctx.restore();
}
// one word or phrase, landing at `at` (a quick stepped settle), until `out`
// K.word(ctx, t, 'composing', at, { x, y, size: 150, font: 'display' | 'light' | 'roman', color: '#f7f4ec', out, rot })
export function word(ctx, t, text, at, o = {}) {
  if (t < at) return;
  const a = outOf(t, o.out, .25); if (a <= 0) return;
  const u = seg(step(t, 24), at, at + .2), s = lerp(1.18, 1, eo(u));
  ctx.save(); ctx.translate(o.x ?? SW / 2, o.y ?? SH * .3); ctx.rotate((o.rot || 0) * Math.PI / 180);
  glyphs(ctx, text, 0, 0, o.size ?? 150, o.font || 'display', o.color || C.white, a * clamp(u * 3), s); ctx.restore();
}
// a voice line set in the scene, each word appearing exactly as it is spoken, wrapped to maxW and centred
// K.words(ctx, t, T.lines[i], { x, y (first line's baseline), size: 96, maxW: 900, font, color, big: ['word'] (bigger
//   + display italic), only: ['word', ...] (show just these words), out, lead: 1.25 })
export function words(ctx, t, line, o = {}) {
  if (!line || !line.words) return;
  const a = outOf(t, o.out, .25); if (a <= 0) return;
  const size = o.size ?? 96, maxW = o.maxW ?? 900, font = o.font || 'display', lead = o.lead ?? 1.2;
  const norm = s => String(s).toLowerCase().replace(/[^a-z0-9'%-]/g, '');
  const big = new Set((o.big || []).map(norm)), only = o.only ? new Set(o.only.map(norm)) : null;
  const ws = line.words.filter(w => !only || only.has(norm(w.w))).map(w => { const B = big.has(norm(w.w)); const sz = B ? size * 1.45 : size;
    return { ...w, sz, f: B ? 'display' : font, wd: measure(w.w, sz, B ? 'display' : font) }; });
  const rows = [[]]; let rw = 0; const gap = size * .28;
  for (const w of ws) { if (rows[rows.length - 1].length && rw + gap + w.wd > maxW) { rows.push([]); rw = 0; } rows[rows.length - 1].push(w); rw += (rw ? gap : 0) + w.wd; }
  let y = o.y ?? SH * .25;
  for (const r of rows) {
    const tot = r.reduce((s, w, i) => s + w.wd + (i ? gap : 0), 0), rh = Math.max(...r.map(w => w.sz)); let x = (o.x ?? SW / 2) - tot / 2;
    for (const w of r) { if (t >= w.s - .03) { const u = seg(step(t, 24), w.s - .03, w.s + .15); glyphs(ctx, w.w, x + w.wd / 2, y, w.sz, w.f, o.color || C.white, a * clamp(u * 3), lerp(1.15, 1, eo(u))); } x += w.wd + gap; }
    y += rh * lead;
  }
}

// a soft dark band behind words on a busy photo: K.scrim(ctx, { y (centre), h: 420, alpha: .45 })
export function scrim(ctx, o = {}) {
  const y = o.y ?? SH * .3, h = o.h ?? 420, g = ctx.createLinearGradient(0, y - h / 2, 0, y + h / 2);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(.5, `rgba(0,0,0,${o.alpha ?? .45})`); g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.save(); ctx.fillStyle = g; ctx.fillRect(-200, y - h / 2, SW + 400, h); ctx.restore();
}

// —— hand-drawn marks (white chalk / pen) ——
function pen(ctx, pts, u, { color = C.white, width = 7 } = {}) {
  if (u <= 0 || pts.length < 2) return;
  const n = Math.max(2, Math.floor(pts.length * clamp(u)));
  ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.shadowColor = 'rgba(0,0,0,.35)'; ctx.shadowBlur = 6;
  ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < n; i++) ctx.lineTo(pts[i][0], pts[i][1]); ctx.stroke(); ctx.restore();
}
// a loose ellipse around something, drawn on over `dur`, overshooting its start like a real pen
// K.ring(ctx, t, { x, y, w, h, at, dur: .5, rot: -6, color, width: 7, out })
export function ring(ctx, t, o) {
  if (t < o.at) return; const a = outOf(t, o.out, .25); if (a <= 0) return;
  const R = mulberry(Math.round((o.x || 0) * 3 + (o.y || 0) * 7)), pts = [], N = 90, turns = 1.12, a0 = -2.2 + R() * .4, ph = R() * 10;
  for (let i = 0; i <= N; i++) { const k = i / N, th = a0 + k * TAU * turns, wob = 1 + (vn(k * 4 + ph) - .5) * .07 + k * .05;
    pts.push([o.x + Math.cos(th) * o.w / 2 * wob, o.y + Math.sin(th) * o.h / 2 * wob]); }
  const rr = (o.rot ?? -6) * Math.PI / 180, cx = o.x, cy = o.y;
  const P = pts.map(([x, y]) => [cx + (x - cx) * Math.cos(rr) - (y - cy) * Math.sin(rr), cy + (x - cx) * Math.sin(rr) + (y - cy) * Math.cos(rr)]);
  ctx.save(); ctx.globalAlpha *= a; pen(ctx, P, eio(seg(t, o.at, o.at + (o.dur ?? .5))), o); ctx.restore();
}
const vn = x => { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i), hash(i + 1), u); };
// a ring fitted around a word you set with K.word (same text, x, y, size, font): K.ringWord(ctx, t, 'composing', at,
//   { x, y, size: 150, font: 'display', dur: .5, rot: -5, out })
export function ringWord(ctx, t, text, at, o = {}) {
  const size = o.size ?? 150, w = measure(text, size, o.font || 'display');
  ring(ctx, t, { x: o.x ?? SW / 2, y: (o.y ?? SH * .3) - size * .3, w: w + size * .9, h: size * 1.45, at, dur: o.dur, rot: o.rot ?? -5, out: o.out, color: o.color, width: o.width });
}
// a hand-drawn underline under a word: K.underline(ctx, t, { x0, x1, y, at, dur: .35, color, width, out })
export function underline(ctx, t, o) {
  if (t < o.at) return; const a = outOf(t, o.out, .25); if (a <= 0) return;
  const pts = []; for (let i = 0; i <= 40; i++) { const k = i / 40; pts.push([lerp(o.x0, o.x1, k), o.y + Math.sin(k * 3.1) * 6 - k * 8]); }
  ctx.save(); ctx.globalAlpha *= a; pen(ctx, pts, eo(seg(t, o.at, o.at + (o.dur ?? .35))), o); ctx.restore();
}
// a hand-drawn arrow: K.arrow(ctx, t, { from: [x, y], to: [x, y], bend: .2, at, dur: .4, color, width, out })
export function arrow(ctx, t, o) {
  if (t < o.at) return; const a = outOf(t, o.out, .25); if (a <= 0) return;
  const [x0, y0] = o.from, [x1, y1] = o.to, mx = (x0 + x1) / 2 - (y1 - y0) * (o.bend ?? .2), my = (y0 + y1) / 2 + (x1 - x0) * (o.bend ?? .2), pts = [];
  for (let i = 0; i <= 40; i++) { const k = i / 40; pts.push([(1 - k) * (1 - k) * x0 + 2 * (1 - k) * k * mx + k * k * x1, (1 - k) * (1 - k) * y0 + 2 * (1 - k) * k * my + k * k * y1]); }
  const u = seg(t, o.at, o.at + (o.dur ?? .4));
  ctx.save(); ctx.globalAlpha *= a; pen(ctx, pts, eo(u), o);
  if (u >= 1) { const ang = Math.atan2(y1 - my, x1 - mx), L = 34; pen(ctx, [[x1 - Math.cos(ang - .5) * L, y1 - Math.sin(ang - .5) * L], [x1, y1], [x1 - Math.cos(ang + .5) * L, y1 - Math.sin(ang + .5) * L]], 1, o); }
  ctx.restore();
}
// a hand-drawn cross-out over something: K.strike(ctx, t, { x, y, w, at, color, width, out })
export function strike(ctx, t, o) {
  if (t < o.at) return; const a = outOf(t, o.out, .25); if (a <= 0) return;
  const w = o.w ?? 300, u = seg(t, o.at, o.at + .3), v = seg(t, o.at + .15, o.at + .45);
  ctx.save(); ctx.globalAlpha *= a;
  pen(ctx, [[o.x - w / 2, o.y - w * .2], [o.x + w / 2, o.y + w * .15]], eo(u), o); pen(ctx, [[o.x + w / 2, o.y - w * .22], [o.x - w / 2, o.y + w * .2]], eo(v), o);
  ctx.restore();
}

// a small caption, like a museum label: K.caption(ctx, t, 'Ludwig van Beethoven (1770–1827)', at, { x, y, size: 40, color, out })
export function caption(ctx, t, text, at, o = {}) {
  if (t < at) return; const a = outOf(t, o.out, .25) * clamp(seg(t, at, at + .3)); if (a <= 0) return;
  ctx.save(); ctx.globalAlpha *= a; ctx.font = FONT.light(o.size ?? 42); ctx.textAlign = 'center'; ctx.fillStyle = o.color || C.white;
  ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = 8; ctx.fillText(text, o.x ?? SW / 2, o.y ?? SH * .9); ctx.restore();
}

// the picture credits (archive photos under CC BY need them on screen): small lines over the last seconds
// K.credits(ctx, t, T.images, at, { y: 1740, size: 24, color }) — draws nothing if no picture carries a credit
export function credits(ctx, t, images, at, o = {}) {
  if (t < at) return; const list = [...new Set((images || []).map(m => m.credit).filter(Boolean))]; if (!list.length) return;
  const a = clamp(seg(t, at, at + .4)), size = o.size ?? 24, lines = [];
  ctx.save(); ctx.font = FONT.light(size); let cur = 'Pictures: ';
  for (const c of list) { const s = (cur.endsWith(': ') ? '' : ' · ') + c; if (ctx.measureText(cur + s).width > 960 && cur !== 'Pictures: ') { lines.push(cur); cur = c; } else cur += s; }
  lines.push(cur); ctx.globalAlpha *= a * .85; ctx.textAlign = 'center'; ctx.fillStyle = o.color || C.white; ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 6;
  let y = (o.y ?? 1760) - (lines.length - 1) * size * 1.3; for (const l of lines.slice(-4)) { ctx.fillText(l, SW / 2, y); y += size * 1.3; }
  ctx.restore();
}

// —— a torn-paper cut between scenes: call it LAST in the frame, around the cut time `at` ——
// the torn sheet sweeps across (dur 0.5 s): the first half covers the old scene, the second half uncovers the new one
export function tear(ctx, t, at, { dur = .5, dir = 'up', tone = 'light' } = {}) {
  const u = seg(step(t, 24), at - dur / 2, at + dur / 2); if (u <= 0 || u >= 1) return;
  const tex = paperTex(tone), R = mulberry(Math.round(at * 100)), edge = [];
  for (let i = 0; i <= 36; i++) edge.push((R() - .5) * 46 + Math.sin(i * .9) * 12);
  const lead = lerp(SH + 150, -150, u), H = SH * 1.1;   // the sheet: from lead to lead + H (moving up)
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); if (dir === 'down') { ctx.translate(0, SH); ctx.scale(1, -1); }
  const top = lead, bot = lead + H;
  ctx.beginPath(); ctx.moveTo(0, top + edge[0]);
  for (let i = 1; i <= 36; i++) ctx.lineTo(SW * i / 36, top + edge[i]);
  ctx.lineTo(SW, bot - edge[0]); for (let i = 35; i >= 0; i--) ctx.lineTo(SW * i / 36, bot - edge[36 - i]); ctx.closePath();
  ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = 30; ctx.fillStyle = tone === 'dark' ? C.paperDark : C.paper; ctx.fill(); ctx.restore();
  ctx.clip(); ctx.drawImage(tex, 0, 0, SW, SH); ctx.restore();
}

// —— the last layer: grain, a slight gate weave, vignette, fade from / to black ——
let _grain = null, _vig = null;
export function finish(ctx, t, { fadeIn = .4, fadeOut = null, grain = 1 } = {}) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.filter = 'none';
  if (!_grain) { _grain = cv(256, 256); const g = _grain.getContext('2d'), img = g.createImageData(256, 256), R = mulberry(9);
    for (let i = 0; i < 256 * 256; i++) { const v = R() * 255; img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 22; } g.putImageData(img, 0, 0); }
  if (!_vig || _vig.width !== SW) { _vig = cv(SW, SH); const v = _vig.getContext('2d'), g = v.createRadialGradient(SW / 2, SH / 2, SH * .32, SW / 2, SH / 2, SH * .8);
    g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,.38)'); v.fillStyle = g; v.fillRect(0, 0, SW, SH); }
  ctx.drawImage(_vig, 0, 0);
  const k = Math.floor(t * 24) % 5; ctx.save(); ctx.globalAlpha = grain; ctx.fillStyle = ctx.createPattern(_grain, 'repeat'); ctx.translate(k * 41, k * 67); ctx.fillRect(-300, -300, SW + 600, SH + 600); ctx.restore();
  // dust and the odd hair, a few frames at a time
  const R = mulberry(Math.floor(t * 8) + 3); ctx.save(); ctx.fillStyle = 'rgba(255,250,235,.5)';
  for (let i = 0; i < 3; i++) if (R() < .5) { ctx.beginPath(); ctx.arc(R() * SW, R() * SH, 1 + R() * 2.2, 0, TAU); ctx.fill(); }
  ctx.restore();
  let f = 0; if (fadeIn) f = Math.max(f, 1 - seg(t, 0, fadeIn)); if (fadeOut) f = Math.max(f, seg(t, fadeOut[0], fadeOut[1]));
  if (f > 0) { ctx.globalAlpha = f; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, SW, SH); ctx.globalAlpha = 1; }
}

// sound cues: paper (a piece lands), pen (a mark is drawn; d), word (a big word lands), tear (a torn-paper cut),
// frame (a frame hangs / a photo drops), swing (a limb moves; soft), hit (the last line), riser (d)
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
