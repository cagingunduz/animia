// Flat Explainer kit for the Animave long-video studio (window.FX): 1920 x 1080 flat vector explainers. Full illustrated
// places (generated plates) with characters (generated cut-outs) acting the line out, text only on things in the world
// (signs on posts, hanging boards, chalkboards, screens) typed letter by letter in Montserrat 800, red X strokes over
// wrong ideas, date cards, full-colour headline cards, a spotlight reveal, counters, flat icons, white puffs and splat
// wipes, a camera that always drifts. Every frame is a pure function of t.
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env } from '../common/lib.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env };

export let SW = 1920, SH = 1080;
export function setScreen(w, h) { SW = w; SH = h; }
export const C = { ink: '#2b2d42', white: '#ffffff', red: '#d62828', orange: '#f4a261', headOrange: '#e2552f', headPurple: '#5b3fa6',
  gear: '#6a4cb6', board: '#ffffff', post: '#5c6378', chalk: '#2f4a3f', screen: '#1f2433', blue: '#6c8ead', teal: '#4f7c82', beige: '#e8dcc5', navy: '#2e3a59' };
const FONT = px => `800 ${px}px Montserrat`;
const ok = img => !!(img && (img.naturalWidth || img.width));
const IW = img => img.naturalWidth || img.width, IH = img => img.naturalHeight || img.height;
const cv = (w, h) => new OffscreenCanvas(Math.max(1, Math.ceil(w)), Math.max(1, Math.ceil(h)));

// —— the camera: a scene's view of its plate, always drifting 2-4 % (zoom) or panning, clamped to the plate ——
// const cam = K.cam(t, { t0, t1, z0: 1.0, z1: 1.04, x0: .5, y0: .5, x1: .5, y1: .5 })  (x / y = the focus, 0..1 of the plate)
export function cam(t, o = {}) {
  const u = ss(seg(t, o.t0 ?? 0, o.t1 ?? (o.t0 ?? 0) + 4));
  return { z: lerp(o.z0 ?? 1.0, o.z1 ?? 1.04, u), fx: lerp(o.x0 ?? .5, o.x1 ?? o.x0 ?? .5, u), fy: lerp(o.y0 ?? .5, o.y1 ?? o.y0 ?? .5, u) };
}
// draw the plate and everything on it through the same camera: K.scene(ctx, t, plateImg, cam, (g) => { ...draw in PLATE px... })
// Inside, coordinates are the plate's own 1920 x 1080 space (the plate is scaled to cover the frame), so things stay
// glued to the art while the camera drifts. Returns nothing.
export function scene(ctx, t, img, c, draw) {
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  const z = Math.max(1, c?.z ?? 1), vw = SW / z, vh = SH / z;
  const cx = clamp((c?.fx ?? .5) * SW, vw / 2, SW - vw / 2), cy = clamp((c?.fy ?? .5) * SH, vh / 2, SH - vh / 2);
  ctx.translate(SW / 2, SH / 2); ctx.scale(z, z); ctx.translate(-cx, -cy);
  if (ok(img)) { const s = Math.max(SW / IW(img), SH / IH(img)), w = IW(img) * s, h = IH(img) * s; ctx.drawImage(img, (SW - w) / 2, (SH - h) / 2, w, h); }
  else { ctx.fillStyle = C.beige; ctx.fillRect(0, 0, SW, SH); }
  draw && draw(ctx);
  ctx.restore();
}

// —— arrivals: never a fade. spring (overshoot), squash (lands and squashes), puff (a white puff), pop (scale up) ——
function arrive(t, at, how, dur = .45) {
  if (t < at) return null;
  const u = seg(t, at, at + dur);
  switch (how) {
    case 'squash': { const k = Math.sin(clamp(u * 1.6) * Math.PI) * (1 - u); return { sx: 1 + .22 * k, sy: 1 - .22 * k, dy: -(1 - eo(clamp(u * 1.8))) * 260 }; }
    case 'pop': { const s = back(u, 2.2); return { sx: s, sy: s, dy: 0 }; }
    case 'puff': return { sx: 1, sy: 1, dy: 0, puff: u };
    case 'none': return { sx: 1, sy: 1, dy: 0 };
    default: { const s = spring(t - at, 9, .38); return { sx: lerp(.4, 1, clamp(s)) * (s > 1 ? s : 1), sy: lerp(.4, 1, clamp(s)) * (s > 1 ? s : 1), dy: 0 }; }
  }
}
// a white puff cloud (arrivals, exits, landings)
export function puff(ctx, t, { x, y, at, size = 220, dur = .45 }) {
  const u = seg(t, at, at + dur); if (u <= 0 || u >= 1) return;
  const R = mulberry(Math.round(x * 7 + y * 3)); ctx.save(); ctx.fillStyle = '#ffffff';
  for (let i = 0; i < 9; i++) { const a = R() * TAU, d = size * (.2 + .6 * eo(u)) * (.6 + R() * .5), r = size * (.22 + R() * .12) * (1 - u * .85);
    ctx.globalAlpha = 1 - u * .7; ctx.beginPath(); ctx.arc(x + Math.cos(a) * d, y + Math.sin(a) * d * .7, Math.max(1, r), 0, TAU); ctx.fill(); }
  ctx.restore();
}

// —— characters (cut-outs) acting the line: they breathe, bob, turn, jump, walk ——
// K.char(ctx, t, img, { x, y (feet), h: 520, at, arrive: 'spring' | 'squash' | 'puff' | 'pop' | 'none', flip, out,
//   jump: [t, ...] (little jumps), walk: [[t, x], ...] (walks along x, bobbing), turn: [t, ...] (flips at each t),
//   lean: deg, talk: [t0, t1] (a speaking bounce) })
export function char(ctx, t, img, o = {}) {
  if (!ok(img)) return;
  const at = o.at ?? 0, a = arrive(t, at, o.arrive || 'spring'); if (!a) return;
  if (o.out != null && t > o.out) return;
  const h = o.h ?? 520, w = h * IW(img) / IH(img); let x = o.x ?? SW / 2, y = o.y ?? SH * .9, flip = !!o.flip, walking = false;
  if (o.walk && o.walk.length) { const P = o.walk; let i = 0; while (i < P.length - 1 && t > P[i + 1][0]) i++;
    const A = P[i], B = P[Math.min(i + 1, P.length - 1)], u = B[0] > A[0] ? clamp((t - A[0]) / (B[0] - A[0])) : 1;
    x = lerp(A[1], B[1], u); walking = t > A[0] && t < B[0] && A[1] !== B[1]; if (walking) flip = B[1] < A[1] ? !o.flip : !!o.flip; }
  for (const tt of o.turn || []) if (t >= tt) flip = !flip;
  let dy = a.dy, sx = a.sx, sy = a.sy, rot = (o.lean || 0) * Math.PI / 180;
  const seed = (IW(img) % 31) * .37;
  sy *= 1 + .012 * Math.sin(t * 2.6 + seed);                                // breathing
  if (walking) { const ph = t * 7.5; dy -= Math.abs(Math.sin(ph)) * h * .035; rot += Math.sin(ph) * .035; }
  if (o.talk && t > o.talk[0] && t < o.talk[1]) { sy *= 1 + .02 * Math.abs(Math.sin(t * 11)); rot += .03 * Math.sin(t * 5.3 + seed); }
  for (const j of o.jump || []) { const u = seg(t, j, j + .45); if (u > 0 && u < 1) { dy -= Math.sin(u * Math.PI) * h * .22; if (u < .15) { sy *= 1 - .1; sx *= 1.08; } } }
  ctx.save(); ctx.translate(x, y + dy); ctx.rotate(rot + .012 * Math.sin(t * 1.7 + seed)); ctx.scale(sx * (flip ? -1 : 1), sy);
  ctx.save(); ctx.globalAlpha = .18; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.ellipse(0, 0, w * .32, h * .025, 0, 0, TAU); ctx.fill(); ctx.restore();
  ctx.drawImage(img, -w / 2, -h, w, h); ctx.restore();
  if (a.puff != null) puff(ctx, t, { x, y: y - h * .45, at, size: h * .55 });
}
// any prop / object cut-out: K.prop(ctx, t, img, { x, y (centre), h, at, arrive, rot, out, float })
export function prop(ctx, t, img, o = {}) {
  if (!ok(img)) return;
  const at = o.at ?? 0, a = arrive(t, at, o.arrive || 'pop'); if (!a) return;
  if (o.out != null && t > o.out) return;
  const h = o.h ?? 260, w = h * IW(img) / IH(img), fl = o.float ? Math.sin(t * 2.2) * 8 : 0;
  ctx.save(); ctx.translate(o.x ?? SW / 2, (o.y ?? SH / 2) + a.dy + fl); ctx.rotate((o.rot || 0) * Math.PI / 180); ctx.scale(a.sx, a.sy);
  ctx.drawImage(img, -w / 2, -h / 2, w, h); ctx.restore();
  if (a.puff != null) puff(ctx, t, { x: o.x ?? SW / 2, y: o.y ?? SH / 2, at, size: h * .7 });
}
// a "!" (or "?") that pops over a head: K.bang(ctx, t, { x, y, at, ch: '!' })
export function bang(ctx, t, { x, y, at, ch = '!', size = 120, out }) {
  if (t < at || (out != null && t > out)) return; const s = back(seg(t, at, at + .3), 2.6);
  ctx.save(); ctx.translate(x, y - 20 * s); ctx.scale(s, s); ctx.rotate(Math.sin(t * 9) * .06);
  ctx.font = FONT(size); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = C.red; ctx.fillText(ch, 0, 0); ctx.restore();
}

// —— text in the world ——
// typed letter by letter at cps (26-34 / s): each letter arrives 1.45x big and 0.7 em to the right, settles in 0.18 s
function typed(ctx, t, text, x, y, size, at, { cps = 30, color = C.ink, align = 'center', maxW = 1e9 } = {}) {
  ctx.save(); ctx.font = FONT(size); ctx.textBaseline = 'middle'; ctx.fillStyle = color;
  const lines = wrap(ctx, String(text), maxW), lh = size * 1.12; let k = 0;
  lines.forEach((ln, li) => {
    const W = ctx.measureText(ln).width; let cx = align === 'center' ? x - W / 2 : align === 'right' ? x - W : x;
    const cy = y + (li - (lines.length - 1) / 2) * lh;
    for (const ch of ln) {
      const t0 = at + k / cps, u = seg(t, t0, t0 + .18), cw = ctx.measureText(ch).width; k++;
      if (t >= t0) { const e = eo(u), s = lerp(1.45, 1, e), dx = lerp(.7 * size, 0, e);
        ctx.save(); ctx.translate(cx + cw / 2 + dx, cy); ctx.scale(s, s); ctx.fillText(ch, -cw / 2, 0); ctx.restore(); }
      cx += cw;
    }
  });
  ctx.restore(); return k / cps;
}
function wrap(ctx, text, maxW) {
  const out = []; for (const para of text.split('\n')) { let cur = '';
    for (const w of para.split(' ')) { const tr = cur ? cur + ' ' + w : w; if (ctx.measureText(tr).width > maxW && cur) { out.push(cur); cur = w; } else cur = tr; }
    out.push(cur); } return out;
}
// how long a text takes to type: K.typeTime('LONDON, 1858', 30)
export const typeTime = (text, cps = 30) => String(text).length / cps;
// a sign in the world, drawn flat (no outlines, a darker shade for form), text typed on it:
// K.sign(ctx, t, { kind: 'post' | 'board' | 'hanging' | 'chalk' | 'screen' | 'panel', x, y (centre of the face), w, h,
//   text, at, size, cps, color, arrive: 'pop' | 'drop' | 'none', out })
export function sign(ctx, t, o) {
  const at = o.at ?? 0; if (t < at - .35 || (o.out != null && t > o.out)) return;
  const k = o.kind || 'board', w = o.w ?? 560, h = o.h ?? 200, x = o.x ?? SW / 2, y = o.y ?? SH * .3;
  const arr = o.arrive ?? (k === 'hanging' ? 'drop' : k === 'post' ? 'pop' : 'none');
  const u = seg(t, at - .35, at); let s = 1, dy = 0;
  if (arr === 'pop') s = back(u, 2); else if (arr === 'drop') dy = -(1 - eo(u)) * 400 + Math.sin(clamp(u * 3) * Math.PI) * 10;
  ctx.save(); ctx.translate(x, y + dy); ctx.scale(s, s);
  const face = k === 'chalk' ? C.chalk : k === 'screen' ? C.screen : C.board, shade = k === 'chalk' ? '#243a31' : k === 'screen' ? '#151925' : '#d9dde6';
  if (k === 'post') { ctx.fillStyle = C.post; ctx.fillRect(-14, h / 2 - 4, 28, 520); ctx.fillStyle = '#4a5063'; ctx.fillRect(2, h / 2 - 4, 12, 520); }
  if (k === 'hanging') { ctx.strokeStyle = '#3b3f52'; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(-w * .32, -h / 2); ctx.lineTo(-w * .32, -h / 2 - 900); ctx.moveTo(w * .32, -h / 2); ctx.lineTo(w * .32, -h / 2 - 900); ctx.stroke(); }
  if (k === 'chalk' || k === 'screen' || k === 'panel') { ctx.fillStyle = k === 'screen' ? '#2b3042' : '#8a6a4a'; rr(ctx, -w / 2 - 22, -h / 2 - 22, w + 44, h + 44, 14); ctx.fill(); }
  ctx.fillStyle = shade; rr(ctx, -w / 2 + 8, -h / 2 + 10, w, h, 12); ctx.fill();
  ctx.fillStyle = face; rr(ctx, -w / 2, -h / 2, w, h, 12); ctx.fill();
  if (o.text) typed(ctx, t, o.text, 0, 0, o.size ?? Math.min(h * .42, 64), at, { cps: o.cps ?? 30, color: o.color ?? (k === 'chalk' || k === 'screen' ? '#f1f1ea' : C.ink), maxW: w * .86 });
  ctx.restore();
}
function rr(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

// write on a blank surface that is part of the plate (its measured box from T.images[id].boards, in plate px; draw it
// inside K.scene so it moves with the camera): K.write(ctx, t, box, 'LONDON, 1858', at, { size (auto-fit), color, cps, pad })
export function write(ctx, t, box, text, at, o = {}) {
  if (!box || t < at || (o.out != null && t > o.out)) return;
  const pad = o.pad ?? .1, maxW = box.w * (1 - 2 * pad), maxH = box.h * (1 - 2 * pad);
  let size = o.size ?? Math.min(96, maxH * .45);
  ctx.save(); ctx.font = FONT(size);
  for (let i = 0; i < 12; i++) { const lines = wrap(ctx, String(text), maxW); if (lines.length * size * 1.12 <= maxH && lines.every(l => ctx.measureText(l).width <= maxW)) break; size *= .88; ctx.font = FONT(size); }
  ctx.restore();
  typed(ctx, t, text, box.x + box.w / 2, box.y + box.h / 2, size, at, { cps: o.cps ?? 30, color: o.color ?? (box.kind === 'screen' ? '#e9f0ff' : C.ink), maxW });
}
// a red X over a wrong idea: two round strokes of 0.11 s each. K.redX(ctx, t, { x, y, size: 260, at, out })
export function redX(ctx, t, { x, y, size = 260, at, out, width = 30 }) {
  if (t < at || (out != null && t > out)) return; const a = seg(t, at, at + .11), b = seg(t, at + .11, at + .22), r = size / 2;
  ctx.save(); ctx.strokeStyle = C.red; ctx.lineWidth = width; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(x - r, y - r); ctx.lineTo(x - r + 2 * r * a, y - r + 2 * r * a); ctx.stroke();
  if (b > 0) { ctx.beginPath(); ctx.moveTo(x + r, y - r); ctx.lineTo(x + r - 2 * r * b, y - r + 2 * r * b); ctx.stroke(); }
  ctx.restore();
}
// a green tick: K.tick(ctx, t, { x, y, size, at })
export function tick(ctx, t, { x, y, size = 200, at, out }) {
  if (t < at || (out != null && t > out)) return; const u = seg(t, at, at + .25), r = size / 2;
  ctx.save(); ctx.strokeStyle = '#2a9d5c'; ctx.lineWidth = 28; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath();
  const p = [[x - r, y], [x - r * .25, y + r * .7], [x + r, y - r * .7]], L1 = Math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]), L2 = Math.hypot(p[2][0] - p[1][0], p[2][1] - p[1][1]), d = u * (L1 + L2);
  ctx.moveTo(...p[0]); if (d <= L1) ctx.lineTo(lerp(p[0][0], p[1][0], d / L1), lerp(p[0][1], p[1][1], d / L1)); else { ctx.lineTo(...p[1]); ctx.lineTo(lerp(p[1][0], p[2][0], (d - L1) / L2), lerp(p[1][1], p[2][1], (d - L1) / L2)); }
  ctx.stroke(); ctx.restore();
}
// every date gets a white 330 x 120 card top left with an orange calendar: K.dateCard(ctx, t, '1858', at, { out })
export function dateCard(ctx, t, text, at, { out } = {}) {
  if (t < at || (out != null && t > out)) return; const s = back(seg(t, at, at + .35), 2);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.translate(60 + 165, 60 + 60); ctx.scale(s, s);
  ctx.fillStyle = 'rgba(0,0,0,.12)'; rr(ctx, -165 + 6, -60 + 8, 330, 120, 16); ctx.fill();
  ctx.fillStyle = '#fff'; rr(ctx, -165, -60, 330, 120, 16); ctx.fill();
  ctx.fillStyle = C.orange; rr(ctx, -140, -38, 76, 76, 10); ctx.fill(); ctx.fillStyle = '#e07b33'; ctx.fillRect(-140, -38, 76, 18);
  ctx.fillStyle = '#fff'; ctx.fillRect(-128, -12, 16, 14); ctx.fillRect(-108, -12, 16, 14); ctx.fillRect(-88, -12, 16, 14); ctx.fillRect(-128, 8, 16, 14); ctx.fillRect(-108, 8, 16, 14);
  typed(ctx, t, text, 50, 4, 50, at + .1, { cps: 30 }); ctx.restore();
}
// a full-frame headline card: white caps on a flat colour; orange with drifting lighter puffs, or purple with turning
// gears. K.headline(ctx, t, 'SO HOW DOES IT WORK?', at, { bg: 'orange' | 'purple', size: 94, marks: '?' | '!' | '' })
export function headline(ctx, t, text, at, o = {}) {
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  const purple = o.bg === 'purple'; ctx.fillStyle = purple ? C.headPurple : C.headOrange; ctx.fillRect(0, 0, SW, SH);
  const R = mulberry(purple ? 7 : 3);
  if (purple) { for (let i = 0; i < 6; i++) gear(ctx, R() * SW, R() * SH, 90 + R() * 160, (R() < .5 ? 1 : -1) * t * (.15 + R() * .2), C.gear); }
  else { ctx.fillStyle = 'rgba(255,255,255,.12)'; for (let i = 0; i < 9; i++) { const x = (R() * SW + t * (20 + R() * 30)) % (SW + 300) - 150, y = R() * SH, r = 70 + R() * 130;
    for (let j = 0; j < 4; j++) { ctx.beginPath(); ctx.arc(x + (j - 1.5) * r * .55, y + (j % 2) * r * .2, r * .55, 0, TAU); ctx.fill(); } } }
  typed(ctx, t, String(text).toUpperCase(), SW / 2, SH / 2, o.size ?? 94, at, { cps: o.cps ?? 30, color: '#fff', maxW: SW * .8 });
  if (o.marks) { const done = at + typeTime(text, o.cps ?? 30), R2 = mulberry(11);
    for (let i = 0; i < 6; i++) { const tt = done + i * .12; if (t < tt) continue; const s = back(seg(t, tt, tt + .3), 2.4), x = SW * (.12 + .76 * R2()), y = SH * (.15 + .7 * (R2() < .5 ? R2() * .25 : .75 + R2() * .25));
      ctx.save(); ctx.translate(x, y); ctx.rotate((R2() - .5) * .6 + Math.sin(t * 3 + i) * .08); ctx.scale(s, s); ctx.font = FONT(110); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#fff'; ctx.fillText(o.marks, 0, 0); ctx.restore(); } }
  ctx.restore();
}
function gear(ctx, x, y, r, a, col) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(a); ctx.fillStyle = col; ctx.beginPath();
  for (let i = 0; i < 24; i++) { const th = i / 24 * TAU, rad = i % 2 ? r : r * 1.18; ctx.lineTo(Math.cos(th) * rad, Math.sin(th) * rad); }
  ctx.closePath(); ctx.fill(); ctx.fillStyle = C.headPurple; ctx.beginPath(); ctx.arc(0, 0, r * .35, 0, TAU); ctx.fill(); ctx.restore();
}
// a spotlight reveal: everything outside the circle darkens. K.spot(ctx, t, { x, y, r: 300, at, out })
export function spot(ctx, t, { x, y, r = 300, at, out }) {
  if (t < at || (out != null && t > out)) return; const u = eo(seg(t, at, at + .4));
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); const g = ctx.createRadialGradient(x, y, r * .9, x, y, r * 1.25);
  g.addColorStop(0, 'rgba(10,12,24,0)'); g.addColorStop(1, `rgba(10,12,24,${.78 * u})`); ctx.fillStyle = g; ctx.fillRect(0, 0, SW, SH);
  ctx.globalAlpha = .18 * u; ctx.fillStyle = '#fff8dc'; ctx.beginPath(); ctx.moveTo(x - r * .25, -40); ctx.lineTo(x + r * .25, -40); ctx.lineTo(x + r, y); ctx.lineTo(x - r, y); ctx.closePath(); ctx.fill(); ctx.restore();
}
// a counter rolling up to the big number, typed in the world: K.counter(ctx, t, { x, y, from: 0, to, at, dur: 1.6, size: 90, prefix, suffix, color })
export function counter(ctx, t, o) {
  if (t < o.at) return; const u = eo(seg(t, o.at, o.at + (o.dur ?? 1.6))), v = lerp(o.from ?? 0, o.to, u);
  const txt = (o.prefix || '') + (Number.isInteger(o.to) ? Math.round(v).toLocaleString('en-US') : v.toFixed(o.dec ?? 1)) + (o.suffix || '');
  ctx.save(); ctx.font = FONT(o.size ?? 90); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = o.color || C.ink;
  const s = 1 + .08 * Math.sin(clamp(u) * Math.PI * 6) * (1 - u); ctx.translate(o.x, o.y); ctx.scale(s, s); ctx.fillText(txt, 0, 0); ctx.restore();
}
// flat icons drawn in code (no outlines), popping in: K.icon(ctx, t, 'skull', { x, y, size: 140, at, out })
// names: skull, heart, coin, clock, globe, bolt, warning, person, house, money, fire, drop, star, question, check, cross
export function icon(ctx, t, name, o) {
  if (t < o.at || (o.out != null && t > o.out)) return; const s = back(seg(t, o.at, o.at + .3), 2.4) * (o.size ?? 140) / 100;
  ctx.save(); ctx.translate(o.x, o.y + Math.sin(t * 2.4 + o.x) * 4); ctx.scale(s, s); (ICONS[name] || ICONS.star)(ctx); ctx.restore();
}
const disc = (ctx, x, y, r, c) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill(); };
const ICONS = {
  skull: c => { disc(c, 0, -8, 42, '#eeeae0'); c.fillStyle = '#eeeae0'; c.fillRect(-24, 20, 48, 26); disc(c, -15, -8, 11, C.ink); disc(c, 15, -8, 11, C.ink); c.fillStyle = C.ink; c.fillRect(-14, 30, 6, 14); c.fillRect(-3, 30, 6, 14); c.fillRect(8, 30, 6, 14); },
  heart: c => { c.fillStyle = '#d64545'; c.beginPath(); c.moveTo(0, 40); c.bezierCurveTo(-60, 0, -40, -50, 0, -20); c.bezierCurveTo(40, -50, 60, 0, 0, 40); c.fill(); },
  coin: c => { disc(c, 0, 0, 46, '#e9b949'); disc(c, 0, 0, 34, '#f2cd63'); c.fillStyle = '#c99a2e'; c.font = FONT(44); c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('$', 0, 2); },
  money: c => { c.fillStyle = '#5f9e6e'; rr(c, -56, -32, 112, 64, 8); c.fill(); disc(c, 0, 0, 18, '#8cc39a'); c.fillStyle = '#4a835a'; c.fillRect(-56, -32, 112, 10); },
  clock: c => { disc(c, 0, 0, 46, '#f3efe6'); disc(c, 0, 0, 38, '#ffffff'); c.strokeStyle = C.ink; c.lineWidth = 7; c.lineCap = 'round'; c.beginPath(); c.moveTo(0, 0); c.lineTo(0, -26); c.moveTo(0, 0); c.lineTo(18, 8); c.stroke(); },
  globe: c => { disc(c, 0, 0, 46, '#5b8fb9'); c.fillStyle = '#7fb069'; c.beginPath(); c.ellipse(-12, -10, 18, 24, .4, 0, TAU); c.fill(); c.beginPath(); c.ellipse(20, 16, 14, 12, 0, 0, TAU); c.fill(); },
  bolt: c => { c.fillStyle = '#f4c542'; c.beginPath(); c.moveTo(8, -50); c.lineTo(-26, 6); c.lineTo(-2, 6); c.lineTo(-10, 50); c.lineTo(28, -8); c.lineTo(4, -8); c.closePath(); c.fill(); },
  warning: c => { c.fillStyle = '#f4a261'; c.beginPath(); c.moveTo(0, -48); c.lineTo(50, 40); c.lineTo(-50, 40); c.closePath(); c.fill(); c.fillStyle = C.ink; c.fillRect(-5, -16, 10, 34); disc(c, 0, 28, 6, C.ink); },
  person: c => { disc(c, 0, -26, 20, '#f2a28f'); c.fillStyle = '#6c8ead'; c.beginPath(); c.ellipse(0, 26, 32, 30, 0, Math.PI, 0); c.fill(); c.fillRect(-32, 26, 64, 18); },
  house: c => { c.fillStyle = '#e8dcc5'; c.fillRect(-40, -6, 80, 52); c.fillStyle = '#c25b4a'; c.beginPath(); c.moveTo(-52, -4); c.lineTo(0, -48); c.lineTo(52, -4); c.closePath(); c.fill(); c.fillStyle = '#6c8ead'; c.fillRect(-10, 16, 20, 30); },
  fire: c => { c.fillStyle = '#e2552f'; c.beginPath(); c.moveTo(0, -52); c.bezierCurveTo(40, -10, 40, 44, 0, 46); c.bezierCurveTo(-40, 44, -40, -6, 0, -52); c.fill(); c.fillStyle = '#f4c542'; c.beginPath(); c.moveTo(0, -10); c.bezierCurveTo(20, 10, 20, 40, 0, 40); c.bezierCurveTo(-20, 40, -20, 10, 0, -10); c.fill(); },
  drop: c => { c.fillStyle = '#5b8fb9'; c.beginPath(); c.moveTo(0, -50); c.bezierCurveTo(36, 0, 36, 44, 0, 44); c.bezierCurveTo(-36, 44, -36, 0, 0, -50); c.fill(); },
  star: c => { c.fillStyle = '#f4c542'; c.beginPath(); for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, r = i % 2 ? 22 : 50; c.lineTo(Math.cos(a) * r, Math.sin(a) * r); } c.closePath(); c.fill(); },
  question: c => { disc(c, 0, 0, 46, '#5b3fa6'); c.fillStyle = '#fff'; c.font = FONT(62); c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('?', 0, 4); },
  check: c => { disc(c, 0, 0, 46, '#2a9d5c'); c.strokeStyle = '#fff'; c.lineWidth = 12; c.lineCap = 'round'; c.beginPath(); c.moveTo(-20, 0); c.lineTo(-5, 16); c.lineTo(22, -14); c.stroke(); },
  cross: c => { disc(c, 0, 0, 46, C.red); c.strokeStyle = '#fff'; c.lineWidth = 12; c.lineCap = 'round'; c.beginPath(); c.moveTo(-16, -16); c.lineTo(16, 16); c.moveTo(16, -16); c.lineTo(-16, 16); c.stroke(); },
};
export const ICON_NAMES = Object.keys(ICONS);

// —— a white splat wipe between big sections (0.2 s in, 0.2 s out around `at`); call it last ——
export function splat(ctx, t, at) {
  const u = seg(t, at - .2, at), v = seg(t, at, at + .2); if ((u <= 0 && v <= 0) || v >= 1) return;
  const k = v > 0 ? 1 - v : u, R = mulberry(Math.round(at * 10)); ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#fff';
  ctx.beginPath(); const n = 18, r0 = Math.hypot(SW, SH) * .62 * eo(k);
  for (let i = 0; i <= n; i++) { const a = i / n * TAU, r = r0 * (i % 2 ? .78 + R() * .2 : 1.05 + R() * .15); ctx.lineTo(SW / 2 + Math.cos(a) * r, SH / 2 + Math.sin(a) * r); }
  ctx.closePath(); ctx.fill();
  for (let i = 0; i < 8; i++) disc(ctx, SW / 2 + Math.cos(i * .8) * r0 * 1.15, SH / 2 + Math.sin(i * .8) * r0 * 1.15, r0 * .08 * (.5 + R()), '#fff');
  ctx.restore();
}
// last: a light vignette and a fade from / to white at the very start / end: K.finish(ctx, t, { fadeIn: .2, end })
export function finish(ctx, t, { fadeIn = .2, end = null } = {}) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  let f = 0; if (fadeIn) f = 1 - seg(t, 0, fadeIn); if (end) f = Math.max(f, seg(t, end - .3, end));
  if (f > 0) { ctx.globalAlpha = f; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, SW, SH); ctx.globalAlpha = 1; }
}
// sound cues: type (a sign being typed; d), whoosh (wipes, drops), pop (signs, icons, arrivals), hit (the red X), ding
// (a tick, a counter landing), splat (a section wipe), jump (a character jumps)
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
