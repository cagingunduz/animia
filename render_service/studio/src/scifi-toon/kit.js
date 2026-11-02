// Sci-Fi Sitcom Toon kit for the Animave Style Studio: the lemo-opuscar toon engine (toon.js: constant-width boiling
// ink lines, flat colour, hard shadow blocks), its cast (chars.js) and worlds (worlds.js), plus the parts of the demo
// film every film needs (camera, default poses with lip sync and blinks, portal wipes, dimension tags, speaker
// subtitles, title card) adapted to any screen size and to our timing (T.lines[i] = { who, start, end, words },
// T.lips = mouth openness 0..1 per 1/24 s of the whole voice track). Exposed as window.TOON.
import * as Tn from './toon.js';
import * as Ch from './chars.js';
import * as Wd from './worlds.js';
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU } from '../common/lib.js';

export * from './toon.js';
export * from './chars.js';
export * from './worlds.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU };
export { env } from '../common/lib.js';

const { push, pop, translate, rotate, scale, reset, shape, stroke, text, rr, arc, ell, screenRect } = Tn;

// characters and their limbs step at 12 fps (on twos); camera, portal and effects move every frame
export const q = t => Math.floor(t * 12 + 1e-6) / 12;

// start a frame: bind the context, set the boil state, clear to black
export function begin(t, ctx, bg = '#000') { Tn.use(ctx); Tn.frame(t); screenRect(bg); }

// camera: the world point (cx, cy) at the centre of the screen, zoom z (1 = one world unit per pixel)
export function cam(cx, cy, z, o = {}) {
  reset(); translate(Tn.W / 2, Tn.H / 2);
  if (o.shake) { const f = Math.floor((o.t || 0) * 24); translate((hash(f) - .5) * o.shake * 2, (hash(f + 77) - .5) * o.shake * 2); }
  scale(z); if (o.rot) rotate(o.rot); translate(-cx, -cy);
}
// a camera that eases between keys [[t, cx, cy, z], ...] (holds before the first and after the last)
export function camPath(keys) {
  return t => {
    if (t <= keys[0][0]) return keys[0].slice(1);
    for (let i = 0; i < keys.length - 1; i++) {
      const a = keys[i], b = keys[i + 1];
      if (t < b[0]) { const u = eio(clamp((t - a[0]) / Math.max(1e-6, b[0] - a[0]))); return [lerp(a[1], b[1], u), lerp(a[2], b[2], u), Math.exp(lerp(Math.log(a[3]), Math.log(b[3]), u))]; }
    }
    return keys[keys.length - 1].slice(1);
  };
}

// —— lip sync ——
// the speaker's mouth at time t: { o: openness 0..1, w: width, talking } (stepped at 12 fps like the drawings)
export function talk(T, who, t) {
  const tq = q(t), W_ = String(who).toUpperCase();
  for (const L of T.lines) {
    if (String(L.who || '').toUpperCase() !== W_) continue;
    if (tq >= L.start && tq < L.end + .04) {
      const k = Math.floor(tq * 24), lp = T.lips;
      const o = lp && lp.length ? (lp[k] ?? 0) : .5 * (1 + Math.sin(tq * 20)) / 2;
      const b = hash(k * 1.91);
      return { o, w: .8 + .45 * b - .2 * o, talking: true };
    }
  }
  return { o: 0, w: 1, talking: false };
}
// who is speaking at t ('' between lines)
export function speaker(T, t) { const L = T.lines.find(L => t >= L.start && t < L.end + .1); return L ? String(L.who || '').toUpperCase() : ''; }
// seeded blinks: true on the frames a character's eyes are shut
export function blink(t, seed = 1) { const k = Math.floor(t * 12), n = Math.floor(k / 26); return hash(n * 7.1 + seed * 3.3) > .4 && (k % 26 === (seed * 5) % 26 || k % 26 === ((seed * 5) + 1) % 26); }

// —— default poses (spread your own fields over them: V(T, t, { x, look, armR, ... })) ——
export const FLOOR = 900;
export const armRest = { R: { h: [22, 168], bend: 18 }, L: { h: [-22, 168], bend: -18 } };
export function V(T, t, o = {}) {
  const m = talk(T, 'VASK', t), tq = q(t);
  return { x: 1180, y: FLOOR, s: 1, face: -1, lid: .47, look: [0, 0], armR: armRest.R, armL: armRest.L, blink: blink(t, 2),
    mouth: { o: m.o, w: m.w, sm: -.35 }, sq: 1 + .008 * Math.sin(tq * 2.3), headTilt: .12 + (m.talking ? (m.o - .3) * .07 : 0), ...o };
}
export function G(T, t, o = {}) {
  const m = talk(T, 'GARY', t), tq = q(t);
  return { x: 760, y: FLOOR, s: 1, face: 1, t, nerv: .4, look: [.5, -.2], blink: blink(t, 1),
    mouth: { o: m.o * 1.15, w: m.w, sm: -.5 }, armR: { h: [-44, 76], bend: 20 }, armL: { h: [44, 76], bend: -20 },
    sq: 1 + .012 * Math.sin(tq * 3.1), headTilt: m.talking ? (m.o - .3) * .1 : Math.sin(tq * 1.7) * .03, ...o };
}
// Decaf, the talking coffee cup: options for coffeeCup(x, y, s, P)
export function C(T, t, o = {}) { const m = talk(T, 'DECAF', t); return { rise: 1, eyes: 1, o: m.o, t, blink: blink(t, 3), arms: m.talking ? .6 : .2, ...o }; }

// —— motion helpers ——
export const walk = (t, t0, t1, a, b) => lerp(a, b, ss(seg(t, t0, t1)));
export const legsWalk = (tq, on, amp = 22) => on ? [[Math.sin(tq * 12) * amp, -Math.max(0, Math.cos(tq * 12)) * 14], [-Math.sin(tq * 12) * amp, -Math.max(0, -Math.cos(tq * 12)) * 14]] : [[0, 0], [0, 0]];
export const landSq = (t, tl) => { const u = t - tl; if (u < 0 || u > .5) return 1; return 1 - .22 * Math.exp(-u * 9) * Math.cos(u * 30); };
export const arcPos = (t, t0, t1, a, b, h) => { const u = clamp((t - t0) / (t1 - t0)); return [lerp(a[0], b[0], u), lerp(a[1], b[1], u) - Math.sin(u * Math.PI) * h]; };
export const popOpen = x => x <= 0 ? 0 : back(clamp(x / .32), 1.7);
// pulled into a portal at (px, py) between t0 and t1
export function sucked(P, t, t0, t1, px, py) {
  const u = ei(seg(t, t0, t1)); if (u <= 0) return P;
  return { ...P, x: lerp(P.x, px, u), y: lerp(P.y, py + 200, u), s: (P.s ?? 1) * (1 - u * .95), sq: 1 + u * .6, lean: (P.lean || 0) + u * .4 };
}
// spat out of a portal at `from`, landing on P's own spot at tl (null before t0: not drawn yet)
export function spit(P, t, t0, tl, from, h = 160) {
  if (t < t0) return null;
  if (t < tl) { const [x, y] = arcPos(t, t0, tl, from, [P.x, P.y], h); const u = seg(t, t0, tl); return { ...P, x, y, sq: 1.25 - u * .25, lean: (P.lean || 0) + (1 - u) * .5 * (P.face || 1), s: (P.s ?? 1) * lerp(.4, 1, eo(u * 2)), armR: { h: [60, -150], bend: 30 }, armL: { h: [-60, -150], bend: -30 } }; }
  return { ...P, sq: landSq(t, tl) };
}

// —— screen layer ——
// full-screen portal wipe centred on the screen at each cut time tc (half-width hw seconds)
export function wipe(t, cuts, hw = .2) {
  for (const c of cuts) {
    const tc = Array.isArray(c) ? c[0] : c, h = Array.isArray(c) ? c[1] : hw, d = Math.abs(t - tc); if (d > h) continue;
    const u = 1 - d / h, R = Math.hypot(Tn.W, Tn.H) * .72 * Math.pow(u, .6);
    reset(); Wd.portal(Tn.W / 2, Tn.H / 2, R, t, { open: 1, sx: 1, spin: 2.2 });
    if (d < .03) screenRect('#dcffa8', .7);
  }
}
// universe label: a retro terminal readout typed out, top left. tags = [[t0, t1, 'DIMENSION J-9', 'EVERYTHING IS JELLY', bg, fg], ...]
export function tag(t, tags) {
  for (const [a, b, id, desc, bg = '#ff4f9a', fg = '#fff'] of tags) {
    if (t < a || t >= b) continue;
    const g = Tn.g, n = Math.floor((t - a) * (b - a < 1.5 ? 110 : 40)), s1 = id.slice(0, n), s2 = desc.slice(0, Math.max(0, n - id.length));
    reset();
    const pop_ = back(seg(t, a, a + .18), 2.2), k = Tn.W / 1080;
    push(); translate(54 * k, Tn.H * .075); scale(pop_ * k);
    g.font = '400 58px VT323'; const w1 = Math.max(g.measureText('▶ ' + id).width, g.measureText(desc).width * 40 / 58) + 70;
    shape(rr(0, 0, Math.max(360, w1), 118, 12), { fill: bg, lw: 7 });
    text('▶ ' + s1 + (n < id.length && Math.floor(t * 6) % 2 ? '█' : ''), 24, 38, { font: '400 54px VT323', fill: fg, align: 'left' });
    text(s2, 26, 86, { font: '400 40px VT323', fill: fg, align: 'left' });
    pop();
  }
}
// speaker subtitles: bold rounded white type, thick ink outline, a boiling name chip in the speaker's colour
export const WHO_COL = { VASK: '#2a9d8f', GARY: '#ef5b3f', DECAF: '#8a5431' };
export function subtitles(T, o = {}) {
  const cols = { ...WHO_COL, ...(o.colors || {}) }, cuts = (o.cuts || []).slice().sort((a, b) => a - b);
  const subs = T.lines.filter(L => !L.nocap).map(L => {
    let t1 = L.end + .35; const cut = cuts.find(c => c > L.start + .1); if (cut && t1 > cut) t1 = Math.max(cut - .02, L.end + .05);
    return { t0: L.start - .03, t1, who: String(L.who || '').toUpperCase(), text: L.text };
  });
  for (let i = 0; i < subs.length - 1; i++) subs[i].t1 = Math.min(subs[i].t1, subs[i + 1].t0 - .02);
  const px = 62, maxW = 880;
  const wrap = str => {
    const g = Tn.g; g.setTransform(1, 0, 0, 1, 0, 0); g.font = `800 ${px}px "Baloo 2"`;
    const ws = str.split(' '), rows = []; let cur = '';
    for (const w of ws) { const nx = cur ? cur + ' ' + w : w; if (g.measureText(nx).width > maxW && cur) { rows.push(cur); cur = w; } else cur = nx; }
    if (cur) rows.push(cur);
    return rows;
  };
  return {
    subs,
    draw(t) {
      const s = subs.find(s => t >= s.t0 && t < s.t1); if (!s) return;
      const g = Tn.g, k = Tn.W / 1080, rows = wrap(s.text), lh = px * 1.12;
      const y1 = Tn.H * (o.y ?? .86) / k, y0 = y1 - (rows.length - 1) * lh;
      reset(); scale(k);
      const pop_ = back(seg(t, s.t0, s.t0 + .12), 2);
      if (s.who) {
        g.setTransform(1, 0, 0, 1, 0, 0); g.font = '800 34px "Baloo 2"'; const nw = g.measureText(s.who).width + 40;
        push(); translate(540, y0 - px * 1.05); scale(pop_);
        shape(rr(-nw / 2, -26, nw, 52, 16), { fill: cols[s.who] || '#5e4b8b', lw: 5 });
        text(s.who, 0, 3, { font: '800 34px "Baloo 2"', fill: '#fff' });
        pop();
      }
      rows.forEach((r, i) => text(r, 540, y0 + i * lh, { font: `800 ${px}px "Baloo 2"`, fill: '#fff', outlineW: 13 }));
    },
  };
}
// title card: cream block letters with a hard magenta drop shadow and a cyan orbit ring (atomic-age TV), at (x, y)
export function titleArt(str, x, y, t, s = 1) {
  reset(); translate(x, y); scale(s * Tn.W / 1080);
  const g = Tn.g; g.setTransform(1, 0, 0, 1, 0, 0); g.font = '400 120px Bungee';
  const words = String(str).toUpperCase().split(' '), rows = [];
  let cur = ''; for (const w of words) { const nx = cur ? cur + ' ' + w : w; if (g.measureText(nx).width > 900 && cur) { rows.push(cur); cur = w; } else cur = nx; } if (cur) rows.push(cur);
  const fs = Math.min(120, 900 / Math.max(...rows.map(r => g.measureText(r).width)) * 120), lh = fs * 1.05, h = (rows.length - 1) * lh;
  const rx = 470, ry = 70 + h * .5, orb = t * 1.6;
  const ring = (a0, a1) => { const P = arc(0, 6, rx, ry, a0, a1, 40); stroke(P, 21, { boil: .5 }); stroke(P, 9, { line: '#5ee6ff', boil: .5 }); };
  rotate(-.05);
  push(); rotate(.12); ring(Math.PI, TAU); pop();
  rows.forEach((r, i) => {
    const yy = -h / 2 + i * lh;
    text(r, 10, yy + 10, { font: `400 ${fs}px Bungee`, fill: '#ff4fa3', outlineW: 20, outlineCol: Tn.INK });
    text(r, 0, yy, { font: `400 ${fs}px Bungee`, fill: '#fff3d6', outlineW: 20, outlineCol: Tn.INK });
  });
  push(); rotate(.12); ring(0, Math.PI);
  const bx = Math.cos(orb) * rx, by = 6 + Math.sin(orb) * ry;
  push(); translate(bx, by); rotate(orb + 1.2); shape(ell(0, 0, 26, 18), { fill: '#ffe066', lw: 6 }); pop();
  pop();
}
// a title card shown between a and b, popping in on twos
export function titleCard(t, str, a, b, o = {}) {
  if (t < a || t >= b) return;
  const u = seg(q(t), a, a + .25), s = (u < 1 ? back(u, 2.4) : 1) * (1 - seg(t, b - .2, b));
  if (s <= .001) return;
  titleArt(str, Tn.W / 2, o.y ?? Tn.H * .2, t, s);
}

// sound events for the foley track, from your own list: [{ t, type, v }] with type in
// pop, boing, suck, whoosh, portalOpen, portalClose, click, slam, thud, squish, blip, gulp, step
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1 })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
