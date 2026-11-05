// Cinecode Film kit for the Animave long-video studio (window.CC): 1920 x 1080 films drawn entirely in code, in one of
// the looks of github.com/sarpstar/cinecode (MIT; its library recipes after github.com/lemomo-ai/lemo-opuscar, MIT).
// Two engines under one look: a three.js stage with the cinecode look chain (pmndrs/postprocessing, Zlib) and the
// cinecode camera moves, and a Canvas 2D layer (the look's ground, paper cards, statements, labels, marker strokes,
// charts, counters, UI panels) with the same palette, type and grain. Every frame is a pure function of t.
import * as THREE from 'three';
import { LOOKS as PRESETS, makeMaterial, buildLook } from './looks.js';
import * as MOVE from './camera.js';
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env } from '../common/lib.js';
export { THREE, MOVE, clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env };

export let SW = 1920, SH = 1080;
export function setScreen(w, h) { SW = w; SH = h; }

// —— the looks (cinecode recipes, carried into this kit's two engines) ——
// pal: bg (the frame's ground), paper (cards), ink (type and lines), main / second (fills), accent (the one signal colour)
// type: display / text / mono / hand = [weight, family, caps?]; mode: '2d' or '3d' (the engine the recipe is built in)
const F = (w, f, caps = false) => [w, f, caps];
export const FILMS = {
  'vox-explainer': { mode: '2d', base: 'papercut-collage', ground: 'paper', hold: 2,
    pal: { bg: '#F1E6D0', paper: '#FBF7EE', ink: '#14213D', main: '#3f6f73', second: '#F2C230', accent: '#B8312A', soft: '#d9c9a8' },
    type: { display: F(800, 'BarlowCondensed', true), text: F(600, 'Inter'), mono: F(500, 'IBMPlexMono'), hand: F(400, 'AD') },
    grain: { a: .06, size: 2 }, vignette: .22 },
  'iso-infographic': { mode: '3d', base: 'glossy-commercial', ground: 'flat', ortho: true, hold: 1,
    pal: { bg: '#EFE9DC', paper: '#FFFDF7', ink: '#2B2D42', main: '#3E7CB1', second: '#E9B44C', accent: '#D1495B', soft: '#9BC1BC', leaf: '#5C946E' },
    type: { display: F(700, 'Inter', true), text: F(500, 'Inter'), mono: F(500, 'JetBrainsMono'), hand: F(600, 'Inter') },
    shading: { shading: 'toon', steps: 3 }, light: { azimuthDeg: 135, elevationDeg: 55, intensity: 2.4, ambient: .75 },
    post: { tone: 'NONE', saturation: 0, contrast: .04, brightness: .02, bloom: null, outline: null, vignette: { offset: .5, darkness: .15 }, grain: { intensity: .02, size: 1.4 } },
    grain: { a: .02, size: 1.4 }, vignette: .1 },
  'lowpoly-island': { mode: '3d', base: 'pastel-storybook', ground: 'sky', ortho: true, hold: 1,
    pal: { bg: '#BFE3F2', paper: '#FFF8EC', ink: '#2E3A59', main: '#7FBF7F', second: '#F2D27A', accent: '#F28C6B', soft: '#E9D8B4', sea: '#5EC4D6' },
    type: { display: F(800, '"Baloo 2"', false), text: F(600, 'Inter'), mono: F(500, 'JetBrainsMono'), hand: F(800, '"Baloo 2"') },
    shading: { shading: 'pbr', roughness: .9, flat: true }, light: { azimuthDeg: 120, elevationDeg: 42, intensity: 2.6, ambient: .65 },
    post: { tone: 'AGX', saturation: .05, contrast: .02, brightness: .03, bloom: { threshold: .85, smoothing: .4, intensity: .25, radius: .7 },
      tiltShift: { focusArea: .5, feather: .35 }, vignette: { offset: .45, darkness: .2 }, grain: { intensity: .015, size: 1.4 } },
    grain: { a: .015, size: 1.4 }, vignette: .12 },
  'hologram-hud': { mode: '3d', base: 'retro-synthwave-vhs', ground: 'dark', hold: 1,
    pal: { bg: '#04121A', paper: '#0B2430', ink: '#BFFCF0', main: '#3CF2C8', second: '#1E8C7E', accent: '#FF8A3D', soft: '#0F3B44' },
    type: { display: F(600, 'BarlowCondensed', true), text: F(600, 'BarlowCondensed', true), mono: F(500, 'JetBrainsMono'), hand: F(600, 'BarlowCondensed', true) },
    shading: { shading: 'unlit' }, light: { azimuthDeg: 180, elevationDeg: 20, intensity: 1, ambient: .3 },
    post: { tone: 'ACES_FILMIC', saturation: .05, contrast: .08, brightness: 0, bloom: { threshold: .25, smoothing: .5, intensity: 1.3, radius: .8 },
      chromatic: .8, scanline: { density: 1.4, opacity: .06 }, vignette: { offset: .3, darkness: .6 }, grain: { intensity: .035, size: 1.2 } },
    grain: { a: .035, size: 1.2 }, vignette: .45 },
  'blueprint': { mode: '2d', base: 'handmade-ink', ground: 'cyanotype', hold: 2,
    pal: { bg: '#1D3F80', paper: '#2A58A6', ink: '#E7F0F9', main: '#E7F0F9', second: '#9DB8DE', accent: '#D7263D', soft: '#18336B' },
    type: { display: F(400, 'AD', true), text: F(400, 'AD'), mono: F(500, 'IBMPlexMono'), hand: F(400, 'AD') },
    grain: { a: .07, size: 2.2 }, vignette: .35 },
  'dataviz': { mode: '2d', base: 'handmade-ink', ground: 'paper', hold: 1,
    pal: { bg: '#F4EEDF', paper: '#FBF8F0', ink: '#22252B', main: '#2B6CB0', second: '#9CC3E6', accent: '#C0392B', soft: '#E3D9C3' },
    type: { display: F(600, 'PlayfairDisplay', false), text: F(500, 'Inter'), mono: F(500, 'IBMPlexMono'), hand: F(400, 'AD') },
    grain: { a: .045, size: 1.8 }, vignette: .15 },
  'dark-keynote': { mode: '2d', base: 'glossy-commercial', ground: 'dark', hold: 1,
    pal: { bg: '#0A0C10', paper: '#151922', ink: '#F2F4F8', main: '#8A93A6', second: '#2A303C', accent: '#B7F34A', soft: '#1C212B', bad: '#FF5A5F' },
    type: { display: F(800, 'Inter', false), text: F(500, 'Inter'), mono: F(500, 'JetBrainsMono'), hand: F(600, 'Inter') },
    grain: { a: .02, size: 1.2 }, vignette: .35 },
  'swiss-motion': { mode: '2d', base: 'glossy-commercial', ground: 'flat', hold: 1,
    pal: { bg: '#EAE9E5', paper: '#FFFFFF', ink: '#111111', main: '#8C8C8C', second: '#CFCFCB', accent: '#E30613', soft: '#DADAD5' },
    type: { display: F(800, 'Inter', false), text: F(600, 'Inter'), mono: F(500, 'JetBrainsMono'), hand: F(500, 'Inter') },
    grain: { a: 0, size: 1 }, vignette: 0 },
};
export let LOOK = FILMS['vox-explainer'], P = LOOK.pal, LOOK_ID = 'vox-explainer';
// the pipeline sets the look (T.look) before film() runs; a film may also call K.use('blueprint')
export function use(id) { if (FILMS[id]) { LOOK_ID = id; LOOK = FILMS[id]; P = LOOK.pal; } return LOOK; }

// —— checks the pipeline reads back (window.__kCues 'warn') ——
const _warned = new Set();
export function warn(msg) { if (_warned.has(msg) || typeof window === 'undefined' || !window.__kCues) return; _warned.add(msg); window.__kCues.push({ t: 0, kind: 'warn', msg }); }
const cv = (w, h) => new OffscreenCanvas(Math.max(1, Math.ceil(w)), Math.max(1, Math.ceil(h)));
const _m = cv(8, 8).getContext('2d');

// —— type: font(role, px) in the look's faces; fit() shrinks text into a box and reports what still overflows ——
export function font(role = 'text', px = 40, weight) { const r = LOOK.type[role] || LOOK.type.text; return `${weight ?? r[0]} ${px}px ${r[1]}, Inter, sans-serif`; }
const caps = (role, s) => ((LOOK.type[role] || [])[2] ? String(s).toLocaleUpperCase('en') : String(s));
function wrap(g, text, maxW) { const out = []; for (const para of String(text).split('\n')) { let cur = ''; for (const w of para.split(' ')) { const tr = cur ? cur + ' ' + w : w; if (g.measureText(tr).width > maxW && cur) { out.push(cur); cur = w; } else cur = tr; } out.push(cur); } return out; }
export function fit(text, role, size, maxW, maxH, lead = 1.1) {
  let s = size, lines = [];
  for (let i = 0; i < 26; i++) { _m.font = font(role, s); lines = wrap(_m, caps(role, text), maxW);
    if (lines.length * s * lead <= maxH && lines.every(l => _m.measureText(l).width <= maxW)) return { size: s, lines, fits: true }; s *= .92; if (s < 18) break; }
  return { size: s, lines, fits: false };
}
export function measure(text, role = 'text', px = 40) { _m.font = font(role, px); return _m.measureText(caps(role, text)).width; }

// —— time: drawn things in a look with hold 2 move on twos (24 fps); cameras stay on ones ——
export const held = t => { const h = LOOK.hold || 1; return Math.floor(t * 24 / h) * h / 24; };
// an appearance envelope: 0 before at, eased in over dur, out over .3 s before out
const vis = (t, at = 0, out = null, dur = .35) => (t < at || (out != null && t > out)) ? 0 : Math.min(eo(seg(t, at, at + dur)), out != null ? 1 - seg(t, out - .3, out) : 1);

// ════════════════════════════ 2D ════════════════════════════

// the look's ground over the whole frame (paper with fibre, cyanotype with a grid, a dark stage, a flat page)
const _grounds = {};
export function bg(ctx) {
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  const key = LOOK_ID + SW + 'x' + SH;
  if (!_grounds[key]) {
    const c = cv(SW, SH), g = c.getContext('2d'), R = mulberry(11);
    g.fillStyle = P.bg; g.fillRect(0, 0, SW, SH);
    if (LOOK.ground === 'paper') {
      for (let i = 0; i < 900; i++) { g.fillStyle = `rgba(${R() < .5 ? '120,90,50' : '255,255,255'},${.008 + R() * .014})`; g.beginPath(); g.ellipse(R() * SW, R() * SH, 30 + R() * 160, 20 + R() * 90, R() * 3, 0, TAU); g.fill(); }
    } else if (LOOK.ground === 'cyanotype') {
      const gr = g.createRadialGradient(SW * .45, SH * .4, 0, SW / 2, SH / 2, SW * .75); gr.addColorStop(0, P.paper); gr.addColorStop(1, P.soft); g.fillStyle = gr; g.fillRect(0, 0, SW, SH);
      for (let i = 0; i < 260; i++) { g.fillStyle = `rgba(10,25,70,${.03 + R() * .05})`; g.beginPath(); g.ellipse(R() * SW, R() * SH, 30 + R() * 200, 20 + R() * 120, R() * 3, 0, TAU); g.fill(); }
      g.strokeStyle = 'rgba(231,240,249,.07)'; g.lineWidth = 1; for (let x = 0; x <= SW; x += 48) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, SH); g.stroke(); } for (let y = 0; y <= SH; y += 48) { g.beginPath(); g.moveTo(0, y); g.lineTo(SW, y); g.stroke(); }
      g.strokeStyle = 'rgba(231,240,249,.55)'; g.lineWidth = 3; g.strokeRect(36, 36, SW - 72, SH - 72); g.lineWidth = 1; g.strokeRect(48, 48, SW - 96, SH - 96);
    } else if (LOOK.ground === 'dark') {
      const gr = g.createRadialGradient(SW * .5, SH * .35, 0, SW / 2, SH / 2, SW * .7); gr.addColorStop(0, P.soft); gr.addColorStop(1, P.bg); g.fillStyle = gr; g.fillRect(0, 0, SW, SH);
      g.strokeStyle = 'rgba(255,255,255,.035)'; g.lineWidth = 1; for (let x = 0; x <= SW; x += 64) { g.beginPath(); g.moveTo(x + .5, 0); g.lineTo(x + .5, SH); g.stroke(); } for (let y = 0; y <= SH; y += 64) { g.beginPath(); g.moveTo(0, y + .5); g.lineTo(SW, y + .5); g.stroke(); }
    }
    _grounds[key] = c;
  }
  ctx.drawImage(_grounds[key], 0, 0); ctx.restore();
}

// a 2D camera over a world drawn in frame px (at zoom 1 the world point (cx, cy) is the frame centre)
// keys: [[t, cx, cy, zoom], ...] eased between keys (in-out); always drift a little within a shot
export function cam2(t, keys) {
  if (!keys || !keys.length) return { x: SW / 2, y: SH / 2, z: 1 };
  let i = 0; while (i < keys.length - 1 && t > keys[i + 1][0]) i++;
  const A = keys[i], B = keys[Math.min(i + 1, keys.length - 1)], u = B[0] > A[0] ? MOVE.EASE.inOut(clamp((t - A[0]) / (B[0] - A[0]))) : 1;
  return { x: lerp(A[1], B[1], u), y: lerp(A[2], B[2], u), z: lerp(A[3] ?? 1, B[3] ?? 1, u) };
}
export function view(ctx, c, draw) {
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.translate(SW / 2, SH / 2); ctx.scale(c.z || 1, c.z || 1); ctx.translate(-c.x, -c.y);
  draw && draw(ctx); ctx.restore();
}

// a seeded torn-edge rectangle path
function tornPath(g, x, y, w, h, seed, teeth = 4) {
  const R = mulberry(seed | 0), pts = [], step = 14;
  for (let i = 0; i <= w; i += step) pts.push([x + i, y + (R() - .5) * teeth]);
  for (let i = 0; i <= h; i += step) pts.push([x + w + (R() - .5) * teeth, y + i]);
  for (let i = w; i >= 0; i -= step) pts.push([x + i, y + h + (R() - .5) * teeth]);
  for (let i = h; i >= 0; i -= step) pts.push([x + (R() - .5) * teeth, y + i]);
  g.beginPath(); pts.forEach(([a, b], k) => k ? g.lineTo(a, b) : g.moveTo(a, b)); g.closePath();
}
// a card (paper / panel / tile, by the look): drops in from just above with a small overshoot and a soft shadow.
// K.card(ctx, t, { x, y (centre), w, h, at, out, rot (deg), color, torn: true, draw: g => {...} (in card px, 0..w, 0..h) })
export function card(ctx, t, o) {
  const a = vis(t, o.at ?? 0, o.out, .3); if (a <= 0) return;
  const th = held(t), u = seg(th, o.at ?? 0, (o.at ?? 0) + .45), drop = (1 - back(u, 1.6)) * -60, w = o.w ?? 480, h = o.h ?? 320;
  const dark = LOOK.ground === 'dark', torn = o.torn ?? (LOOK.ground === 'paper');
  ctx.save(); ctx.globalAlpha *= LOOK_ID === 'vox-explainer' ? Math.min(1, a * 3) : a; ctx.translate(o.x, o.y + drop); ctx.rotate(((o.rot ?? 0) * Math.PI) / 180); ctx.translate(-w / 2, -h / 2);
  ctx.shadowColor = dark ? 'rgba(0,0,0,.55)' : 'rgba(40,30,20,.28)'; ctx.shadowBlur = 16; ctx.shadowOffsetY = 8;
  ctx.fillStyle = o.color || P.paper;
  if (torn) tornPath(ctx, 0, 0, w, h, Math.round(o.x * 3 + o.y)); else { ctx.beginPath(); ctx.roundRect(0, 0, w, h, LOOK.ground === 'dark' ? 18 : LOOK_ID === 'swiss-motion' ? 0 : 8); }
  ctx.fill(); ctx.shadowColor = 'transparent';
  if (dark) { ctx.strokeStyle = 'rgba(255,255,255,.10)'; ctx.lineWidth = 1.5; ctx.stroke(); }
  if (LOOK.ground === 'cyanotype') { ctx.strokeStyle = P.ink; ctx.globalAlpha *= .8; ctx.lineWidth = 2; ctx.stroke(); }
  if (o.draw) { ctx.save(); ctx.clip(); o.draw(ctx, w, h); ctx.restore(); }
  ctx.restore();
}
// type in a box: K.text(ctx, t, { text, x, y (top-left; or centre with align 'center'), w (max width), h (max height),
//   size: 64, role: 'display' | 'text' | 'mono' | 'hand', color, align: 'left' | 'center' | 'right', at, out, reveal: 'words' | 'fade' | 'wipe' })
// Words land one by one (reveal 'words', default for display) on the look's timing. Returns { w, h } of the set text.
export function text(ctx, t, o) {
  const role = o.role || 'text', a = vis(t, o.at ?? 0, o.out, .25); if (a <= 0 || !String(o.text ?? '').trim()) return { w: 0, h: 0 };
  const W = o.w ?? SW * .7, H = o.h ?? (o.size ?? 64) * 3.4, f = fit(o.text, role, o.size ?? 64, W, H);
  if (!f.fits) warn(`K.text "${String(o.text).slice(0, 40)}" at ${(o.at ?? 0).toFixed(1)} s does not fit ${Math.round(W)} x ${Math.round(H)} px even at ${Math.round(f.size)} px: shorten it or give it a bigger box`);
  const lead = f.size * 1.1, align = o.align || 'left', reveal = o.reveal || (role === 'display' ? 'words' : 'fade');
  ctx.save(); ctx.globalAlpha *= reveal === 'fade' ? a : (o.out != null ? Math.min(1, 1 - seg(t, o.out - .3, o.out)) : 1);
  ctx.font = font(role, f.size); ctx.fillStyle = o.color || P.ink; ctx.textBaseline = 'top'; ctx.textAlign = align;
  if (o.halo) { ctx.shadowColor = typeof o.halo === 'string' ? o.halo : P.bg; ctx.shadowBlur = 14; }
  const y0 = o.y - (o.valign === 'middle' ? f.lines.length * lead / 2 : 0);
  const th = held(t); let wi = 0; let maxw = 0;
  f.lines.forEach((ln, i) => {
    const y = y0 + i * lead; maxw = Math.max(maxw, ctx.measureText(ln).width);
    if (reveal === 'words') {
      const words = ln.split(' '), full = ctx.measureText(ln).width;
      let x = align === 'center' ? o.x - full / 2 : align === 'right' ? o.x - full : o.x; ctx.textAlign = 'left';
      for (const w of words) { const k = eo(seg(th, (o.at ?? 0) + wi * .09, (o.at ?? 0) + wi * .09 + .22)); wi++;
        if (k > 0) { ctx.save(); ctx.globalAlpha *= k; ctx.fillText(w, x, y + (1 - k) * f.size * .25); ctx.restore(); } x += ctx.measureText(w + ' ').width; }
      ctx.textAlign = align;
    } else if (reveal === 'wipe') {
      const k = eio(seg(t, (o.at ?? 0) + i * .12, (o.at ?? 0) + i * .12 + .5)), lw = ctx.measureText(ln).width, x0 = align === 'center' ? o.x - lw / 2 : align === 'right' ? o.x - lw : o.x;
      ctx.save(); ctx.beginPath(); ctx.rect(x0 - 4, y - 4, (lw + 8) * k, lead + 8); ctx.clip(); ctx.fillText(ln, o.x, y); ctx.restore();
    } else ctx.fillText(ln, o.x, y);
  });
  ctx.restore();
  return { w: maxw, h: f.lines.length * lead, size: f.size };
}
// a statement: the look's big type on its strip (torn paper strip / white sheet note / dark toast / flush-left block)
// K.statement(ctx, t, { text, x, y (centre), w: 1100, size: 120, at, out, color, strip })
export function statement(ctx, t, o) {
  const a = vis(t, o.at ?? 0, o.out, .2); if (a <= 0) return;
  const w = o.w ?? 1100, f = fit(o.text, 'display', o.size ?? 120, w - 80, (o.size ?? 120) * 3.4);
  if (!f.fits) warn(`K.statement "${String(o.text).slice(0, 40)}" at ${(o.at ?? 0).toFixed(1)} s is too long for one statement (3 short lines at most)`);
  const h = f.lines.length * f.size * 1.1 + 70;
  if (o.strip !== false && LOOK_ID !== 'swiss-motion') card(ctx, t, { x: o.x ?? SW / 2, y: o.y ?? SH / 2, w, h, at: o.at, out: o.out, rot: o.rot ?? (LOOK.ground === 'paper' ? -1.2 : 0), color: o.bg });
  text(ctx, t, { text: o.text, role: 'display', size: f.size, x: LOOK_ID === 'swiss-motion' ? (o.x ?? SW / 2) - w / 2 : (o.x ?? SW / 2), y: (o.y ?? SH / 2) - h / 2 + 35 + (held(t) < (o.at ?? 0) + .45 ? 0 : 0),
    w: w - 80, h: h, align: LOOK_ID === 'swiss-motion' ? 'left' : 'center', at: (o.at ?? 0) + .12, out: o.out, color: o.color });
}
// a self-drawing stroke (marker / pencil / white ink): K.stroke(ctx, t, { pts: [[x,y],...] | circle: { x, y, r } |
//   arrow: [[x0,y0],[x1,y1]], at, dur: .6, color, width: 8, wobble: 1, dash })
export function stroke(ctx, t, o) {
  const at = o.at ?? 0; if (t < at || (o.out != null && t > o.out)) return;
  let pts = o.pts;
  if (o.circle) { const { x, y, r } = o.circle, R = mulberry(Math.round(x + y)), n = 48; pts = []; for (let i = 0; i <= n + 6; i++) { const q = i / n * TAU - .9, rr = r * (1 + (R() - .5) * .06 * (o.wobble ?? 1) + i / n * .05); pts.push([x + Math.cos(q) * rr * 1.15, y + Math.sin(q) * rr * .9]); } }
  if (o.arrow) { const [p, q] = o.arrow, mx = (p[0] + q[0]) / 2 - (q[1] - p[1]) * .15, my = (p[1] + q[1]) / 2 + (q[0] - p[0]) * .15; pts = []; for (let i = 0; i <= 24; i++) { const u = i / 24; pts.push([(1 - u) * (1 - u) * p[0] + 2 * u * (1 - u) * mx + u * u * q[0], (1 - u) * (1 - u) * p[1] + 2 * u * (1 - u) * my + u * u * q[1]]); } }
  if (!pts || pts.length < 2) return;
  let total = 0; const L = [0]; for (let i = 1; i < pts.length; i++) { total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); L.push(total); }
  const k = eio(seg(t, at, at + (o.dur ?? .6))), lim = total * k;
  ctx.save(); ctx.strokeStyle = o.color || P.accent; ctx.lineWidth = o.width ?? 8; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; if (o.dash) ctx.setLineDash(o.dash);
  if (LOOK.ground === 'cyanotype' || LOOK.ground === 'dark') { ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = 10; }
  ctx.beginPath(); ctx.moveTo(...pts[0]); let end = pts[0];
  for (let i = 1; i < pts.length; i++) { if (L[i] <= lim) { ctx.lineTo(...pts[i]); end = pts[i]; } else { const u = (lim - L[i - 1]) / (L[i] - L[i - 1] || 1); end = [lerp(pts[i - 1][0], pts[i][0], u), lerp(pts[i - 1][1], pts[i][1], u)]; ctx.lineTo(...end); break; } }
  ctx.stroke();
  if (o.arrow && k > .95) { const p = pts[pts.length - 2], q = pts[pts.length - 1], ang = Math.atan2(q[1] - p[1], q[0] - p[0]), s = (o.width ?? 8) * 3.2;
    ctx.beginPath(); ctx.moveTo(q[0] - Math.cos(ang - .5) * s, q[1] - Math.sin(ang - .5) * s); ctx.lineTo(q[0], q[1]); ctx.lineTo(q[0] - Math.cos(ang + .5) * s, q[1] - Math.sin(ang + .5) * s); ctx.stroke(); }
  ctx.restore();
}
// a highlighter bar laid behind a word (draw it before the text): K.highlight(ctx, t, { x, y, w, h, at, dur: .5, color })
export function highlight(ctx, t, o) {
  if (t < (o.at ?? 0) || (o.out != null && t > o.out)) return; const k = eio(seg(t, o.at ?? 0, (o.at ?? 0) + (o.dur ?? .5)));
  ctx.save(); ctx.globalAlpha *= LOOK.ground === 'dark' ? .35 : .55; ctx.fillStyle = o.color || P.second;
  ctx.beginPath(); ctx.moveTo(o.x, o.y + 4); ctx.lineTo(o.x + o.w * k, o.y); ctx.lineTo(o.x + o.w * k + 3, o.y + o.h - 2); ctx.lineTo(o.x - 2, o.y + o.h); ctx.closePath(); ctx.fill(); ctx.restore();
}
// a label with a leader: K.label(ctx, t, { x, y (the point), text, at, out, dx: 120, dy: -90 (where the tag sits), color })
export function label(ctx, t, o) {
  const a = vis(t, o.at ?? 0, o.out, .3); if (a <= 0) return;
  const size = o.size ?? 34, tw0 = Math.min(measure(o.text, 'mono', size), 560) + 36;
  let dx = o.dx ?? 120, dy = o.dy ?? -90; const k = eo(seg(t, o.at ?? 0, (o.at ?? 0) + .35));
  if (ctx.getTransform().isIdentity) {         // in frame px: flip the tag to the side that keeps it on screen
    if (dx >= 0 && o.x + dx + tw0 > SW - 40) dx = -Math.abs(dx); else if (dx < 0 && o.x + dx - tw0 < 40) dx = Math.abs(dx);
    if (o.y + dy - size < 30) dy = Math.abs(dy); else if (o.y + dy + size > SH - 30) dy = -Math.abs(dy); }
  ctx.save(); ctx.globalAlpha *= a; ctx.strokeStyle = o.color || P.ink; ctx.fillStyle = o.color || P.ink; ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.arc(o.x, o.y, 7, 0, TAU); ctx.fill();
  ctx.beginPath(); ctx.moveTo(o.x, o.y); ctx.lineTo(o.x + dx * .4 * k, o.y + dy * k); ctx.lineTo(o.x + dx * k, o.y + dy * k); ctx.stroke(); ctx.restore();
  if (k > .6) { const tw = tw0, left = dx >= 0;
    card(ctx, t, { x: o.x + dx + (left ? tw / 2 : -tw / 2), y: o.y + dy, w: tw, h: size * 1.7, at: (o.at ?? 0) + .2, out: o.out, torn: false, color: o.bg });
    text(ctx, t, { text: o.text, role: 'mono', size, x: o.x + dx + (left ? tw / 2 : -tw / 2), y: o.y + dy, valign: 'middle', w: 560, h: size * 1.5, align: 'center', at: (o.at ?? 0) + .25, out: o.out, color: o.color }); }
}
// a number that counts: K.counter(ctx, t, { x, y (centre), from: 0, to, at, dur: 1.6, size: 160, prefix, suffix, decimals, color, role: 'display' })
export function counter(ctx, t, o) {
  const a = vis(t, o.at ?? 0, o.out, .2); if (a <= 0) return;
  const k = eo(seg(t, o.at ?? 0, (o.at ?? 0) + (o.dur ?? 1.6))), v = lerp(o.from ?? 0, o.to, k), d = o.decimals ?? (Math.abs(o.to) < 10 && o.to % 1 ? 1 : 0);
  const s = (o.prefix || '') + v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) + (o.suffix || '');
  ctx.save(); ctx.globalAlpha *= a; ctx.font = font(o.role || 'display', o.size ?? 160); ctx.fillStyle = o.color || (k >= 1 ? P.accent : P.ink);
  ctx.textAlign = o.align || 'center'; ctx.textBaseline = 'middle'; ctx.fillText(s, o.x, o.y); ctx.restore();
}
// bars from the real numbers: K.bars(ctx, t, { x, y (bottom-left of the plot), w, h, values, labels, at, stagger: .12,
//   max, color, accentIndex, unit, horizontal })
export function bars(ctx, t, o) {
  const vals = o.values || [], n = vals.length; if (!n || t < (o.at ?? 0) || (o.out != null && t > o.out)) return;
  const max = o.max ?? Math.max(...vals.map(Math.abs), 1e-9), gap = .28, bw = o.w / (n + (n - 1) * gap), th = held(t), a = vis(t, o.at ?? 0, o.out, .2);
  ctx.save(); ctx.globalAlpha *= a; ctx.strokeStyle = P.ink; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(o.x - 10, o.y); ctx.lineTo(o.x + o.w + 10, o.y); ctx.stroke();
  vals.forEach((v, i) => {
    const k = eo(seg(th, (o.at ?? 0) + i * (o.stagger ?? .12), (o.at ?? 0) + i * (o.stagger ?? .12) + .6)), bh = o.h * Math.abs(v) / max * k, x = o.x + i * bw * (1 + gap);
    ctx.fillStyle = i === o.accentIndex ? P.accent : (o.color || P.main); ctx.fillRect(x, o.y - bh, bw, bh);
    ctx.font = font('mono', Math.min(30, bw * .32)); ctx.fillStyle = P.ink; ctx.textAlign = 'center';
    if (k > .9) ctx.fillText((o.prefix || '') + v.toLocaleString('en-US') + (o.unit || ''), x + bw / 2, o.y - bh - 14);
    if (o.labels && o.labels[i] != null) { ctx.textBaseline = 'top'; ctx.fillText(String(o.labels[i]).slice(0, 14), x + bw / 2, o.y + 14); ctx.textBaseline = 'alphabetic'; }
  });
  ctx.restore();
}
// a line drawn point by point: K.plot(ctx, t, { x, y (bottom-left), w, h, values, min, max, at, dur: 2, color, labels: [first, last], dots })
export function plot(ctx, t, o) {
  const v = o.values || []; if (v.length < 2 || t < (o.at ?? 0) || (o.out != null && t > o.out)) return;
  const lo = o.min ?? Math.min(...v), hi = o.max ?? Math.max(...v), pts = v.map((y, i) => [o.x + o.w * i / (v.length - 1), o.y - o.h * (y - lo) / ((hi - lo) || 1)]);
  ctx.save(); ctx.globalAlpha *= vis(t, o.at ?? 0, o.out, .2); ctx.strokeStyle = P.ink; ctx.globalAlpha *= .5; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(o.x, o.y - o.h); ctx.lineTo(o.x, o.y); ctx.lineTo(o.x + o.w, o.y); ctx.stroke(); ctx.restore();
  stroke(ctx, t, { pts, at: o.at, dur: o.dur ?? 2, color: o.color || P.main, width: o.width ?? 6, out: o.out });
  const k = seg(t, o.at ?? 0, (o.at ?? 0) + (o.dur ?? 2));
  if (o.dots !== false && k >= 1) { ctx.save(); ctx.fillStyle = P.accent; const p = pts[pts.length - 1]; ctx.beginPath(); ctx.arc(p[0], p[1], 10, 0, TAU); ctx.fill(); ctx.restore(); }
  if (o.labels) { ctx.save(); ctx.font = font('mono', 28); ctx.fillStyle = P.ink; ctx.textBaseline = 'top'; ctx.textAlign = 'left'; ctx.fillText(String(o.labels[0] ?? ''), o.x, o.y + 12); ctx.textAlign = 'right'; ctx.fillText(String(o.labels[1] ?? ''), o.x + o.w, o.y + 12); ctx.restore(); }
}
// an Isotype grid: K.grid(ctx, t, { x, y (top-left), cols, rows, n (how many lit), size: 34, gap: 14, at, stagger: .02, shape: 'dot' | 'person' | 'square', mark: [i, ...] (in accent) })
export function grid(ctx, t, o) {
  if (t < (o.at ?? 0) || (o.out != null && t > o.out)) return; const s = o.size ?? 34, gp = o.gap ?? 14, total = (o.cols ?? 10) * (o.rows ?? 10), mark = new Set(o.mark || []);
  ctx.save(); ctx.globalAlpha *= vis(t, o.at ?? 0, o.out, .2);
  for (let i = 0; i < total; i++) {
    const c = i % (o.cols ?? 10), r = Math.floor(i / (o.cols ?? 10)), x = o.x + c * (s + gp) + s / 2, y = o.y + r * (s + gp) + s / 2;
    const k = back(seg(held(t), (o.at ?? 0) + i * (o.stagger ?? .02), (o.at ?? 0) + i * (o.stagger ?? .02) + .3), 2); if (k <= 0) continue;
    ctx.fillStyle = mark.has(i) ? P.accent : i < (o.n ?? total) ? (o.color || P.main) : (LOOK.ground === 'dark' ? P.second : P.soft);
    ctx.save(); ctx.translate(x, y); ctx.scale(k, k);
    if ((o.shape || 'dot') === 'square') ctx.fillRect(-s / 2, -s / 2, s, s);
    else if (o.shape === 'person') { ctx.beginPath(); ctx.arc(0, -s * .3, s * .2, 0, TAU); ctx.fill(); ctx.beginPath(); ctx.roundRect(-s * .28, -s * .06, s * .56, s * .56, s * .14); ctx.fill(); }
    else { ctx.beginPath(); ctx.arc(0, 0, s / 2, 0, TAU); ctx.fill(); }
    ctx.restore();
  }
  ctx.restore();
}
// a UI panel / window (dark-keynote, hologram): K.panel(ctx, t, { x, y (centre), w, h, at, out, title, draw: (g, w, h) => {} })
export function panel(ctx, t, o) {
  card(ctx, t, { ...o, torn: false, draw: (g, w, h) => {
    if (o.title) { g.fillStyle = LOOK.ground === 'dark' ? 'rgba(255,255,255,.05)' : 'rgba(0,0,0,.05)'; g.fillRect(0, 0, w, 56);
      g.font = font('mono', 22); g.fillStyle = P.main; g.textBaseline = 'middle'; g.fillText(caps('mono', o.title), 22, 28);
      [0, 1, 2].forEach(i => { g.beginPath(); g.arc(w - 30 - i * 24, 28, 6, 0, TAU); g.fillStyle = i === 2 ? P.accent : P.second; g.fill(); }); }
    o.draw && o.draw(g, w, h);
  } });
}
// a chapter title (the part's opening card): K.title(ctx, t, { text, kicker: 'PART 2', at, out })
export function title(ctx, t, o) {
  const a = vis(t, o.at ?? 0, o.out, .3); if (a <= 0) return;
  const y = SH * .5;
  if (o.kicker) text(ctx, t, { text: o.kicker, role: 'mono', size: 30, x: SW / 2, y: y - 150, align: 'center', w: 900, h: 50, at: o.at, out: o.out, color: P.accent });
  statement(ctx, t, { text: o.text, x: SW / 2, y, w: 1300, size: 110, at: (o.at ?? 0) + .1, out: o.out, strip: o.strip });
}

// ════════════════════════════ 3D ════════════════════════════
// const S = K.stage({ fov: 35, ortho: LOOK.ortho, scale: .7, bg: P.bg, fog: 0 }) once in film(); then each frame:
//   K.MOVE.apply(S.cam, { position, target, fov }) (or S.iso(target, size, azimuthDeg, elevationDeg) for ortho), then S.render(ctx, t)
// The look chain (tone, bloom, outline, tilt-shift, vignette, grain) comes from the look; S.toggle('bloom', false) per shot.
export function stage(o = {}) {
  const base = PRESETS[LOOK.base] || PRESETS['glossy-commercial'];
  const look = { ...base, palette: [P.bg, P.soft, P.main, P.second, P.accent], materials: { ...base.materials, ...(LOOK.shading || {}) },
    light: { ...base.light, ...(LOOK.light || {}) }, post: { ...base.post, ...(LOOK.post || {}), msaa: 0, halfFloat: o.halfFloat ?? false } };
  for (const k of Object.keys(look.post)) if (look.post[k] == null) delete look.post[k];
  if (look.post.tone === 'NEUTRAL') look.post.tone = 'NONE';           // three r160 has no Neutral tone mapping: exact colours instead
  const rs = o.scale ?? .7, canvas = document.createElement('canvas'); canvas.width = Math.round(SW * rs); canvas.height = Math.round(SH * rs);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(1); renderer.setSize(canvas.width, canvas.height, false); renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = o.shadows !== false; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene(); scene.background = new THREE.Color(o.bg || P.bg);
  if (o.fog || look.light.fog) scene.fog = new THREE.FogExp2(new THREE.Color(o.bg || P.bg), o.fog || look.light.fog);
  const ortho = o.ortho ?? !!LOOK.ortho, asp = SW / SH;
  const cam = ortho ? new THREE.OrthographicCamera(-10 * asp, 10 * asp, 10, -10, -500, 2000) : new THREE.PerspectiveCamera(o.fov ?? 35, asp, .05, 4000);
  const L = look.light, ex = L.exposure ?? 1;
  const sun = new THREE.DirectionalLight('#fff4e6', (L.intensity ?? 2.5) * ex);
  sun.position.setFromSphericalCoords(40, THREE.MathUtils.degToRad(90 - (L.elevationDeg ?? 45)), THREE.MathUtils.degToRad(L.azimuthDeg ?? 135));
  sun.castShadow = renderer.shadowMap.enabled; sun.shadow.mapSize.set(1024, 1024); sun.shadow.bias = -.0005; sun.shadow.radius = 4;
  const sc = sun.shadow.camera; sc.left = -30; sc.right = 30; sc.top = 30; sc.bottom = -30; sc.near = 1; sc.far = 120;
  const hemi = new THREE.HemisphereLight('#ffffff', P.soft, (L.ambient ?? .5) * ex * 2);
  scene.add(sun, sun.target, hemi);
  const chain = buildLook({ renderer, scene, camera: cam, look, fps: 24, seed: 7 });
  const S = {
    THREE, scene, cam, renderer, sun, hemi, look, canvas, ortho,
    add(...objs) { for (const x of objs) { scene.add(x); x.traverse?.(m => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } }); } return objs[0]; },
    // an orthographic isometric view: target [x, y, z], size = world units of the frame's height, angles in degrees
    iso(target = [0, 0, 0], size = 20, az = 45, el = 35.264) {
      const h = size / 2; cam.left = -h * asp; cam.right = h * asp; cam.top = h; cam.bottom = -h; cam.updateProjectionMatrix();
      const p = new THREE.Vector3().setFromSphericalCoords(200, THREE.MathUtils.degToRad(90 - el), THREE.MathUtils.degToRad(az));
      cam.position.set(target[0] + p.x, target[1] + p.y, target[2] + p.z); cam.up.set(0, 1, 0); cam.lookAt(...target);
    },
    toggle: chain.toggle, focus: chain.focus,
    // world [x, y, z] -> frame px [x, y] (labels and marks over the 3D picture)
    project(p) { const v = (p.isVector3 ? p.clone() : new THREE.Vector3(...p)).project(cam); return [(v.x * .5 + .5) * SW, (-v.y * .5 + .5) * SH]; },
    render(ctx, t) {
      sun.target.position.copy(S._focus || new THREE.Vector3()); sun.position.copy(sun.target.position).add(new THREE.Vector3().setFromSphericalCoords(40, THREE.MathUtils.degToRad(90 - (L.elevationDeg ?? 45)), THREE.MathUtils.degToRad(L.azimuthDeg ?? 135)));
      chain.render(Math.round(t * 24), t);
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.imageSmoothingQuality = 'high'; ctx.drawImage(canvas, 0, 0, SW, SH); ctx.restore();
    },
    // keep the sun's shadow box on what the shot looks at
    lookAt(p) { S._focus = new THREE.Vector3(...p); },
  };
  return S;
}
// materials that follow the look (toon steps / flat pbr / unlit), and simple parametric shapes (metres, sitting on y = 0)
export function mat(color, opts = {}) {
  const base = PRESETS[LOOK.base] || PRESETS['glossy-commercial'], m = makeMaterial({ materials: { ...base.materials, ...(LOOK.shading || {}) } }, new THREE.Color(color || P.main), opts);
  if (LOOK.shading?.flat) m.flatShading = true; return m;
}
const mesh = (geo, m, y) => { const x = new THREE.Mesh(geo, m); x.position.y = y; const g = new THREE.Group(); g.add(x); return g; };
export const box = (w = 1, h = 1, d = 1, o = {}) => mesh(new THREE.BoxGeometry(w, h, d), o.m || mat(o.color), h / 2);
export const ball = (r = .5, o = {}) => mesh(new THREE.IcosahedronGeometry(r, o.detail ?? (LOOK.shading?.flat ? 1 : 4)), o.m || mat(o.color), r);
export const cyl = (r = .5, h = 1, o = {}) => mesh(new THREE.CylinderGeometry(o.top ?? r, r, h, o.seg ?? (LOOK.shading?.flat ? 8 : 40)), o.m || mat(o.color), h / 2);
export const cone = (r = .5, h = 1, o = {}) => mesh(new THREE.ConeGeometry(r, h, o.seg ?? (LOOK.shading?.flat ? 7 : 40)), o.m || mat(o.color), h / 2);
export const ground = (size = 60, o = {}) => { const x = new THREE.Mesh(new THREE.PlaneGeometry(size, size), o.m || mat(o.color || P.soft)); x.rotation.x = -Math.PI / 2; x.receiveShadow = true; x.userData.noOutline = true; return x; };
export const group = (...kids) => { const g = new THREE.Group(); kids.forEach(k => k && g.add(k)); return g; };
// a stylised person (no face): body, head, arms; h metres tall
export function person(o = {}) {
  const h = o.h ?? 1.75, c = o.color || P.main, skin = o.skin || '#e8c6a0', g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(h * .13, h * .34, 4, LOOK.shading?.flat ? 6 : 16), mat(c)); body.position.y = h * .45;
  const head = new THREE.Mesh(new THREE.IcosahedronGeometry(h * .11, LOOK.shading?.flat ? 1 : 3), mat(skin)); head.position.y = h * .86;
  const legs = new THREE.Mesh(new THREE.CylinderGeometry(h * .1, h * .08, h * .28, 10), mat(o.legs || P.ink)); legs.position.y = h * .14;
  g.add(body, head, legs); return g;
}
// a house / building block with a pitched or flat roof
export function building(w = 2, h = 3, d = 2, o = {}) {
  const g = box(w, h, d, { color: o.color || P.paper });
  if (o.roof !== 'flat') { const r = new THREE.Mesh(new THREE.ConeGeometry(Math.hypot(w, d) / 2 * 1.02, w * .5, 4), mat(o.roofColor || P.accent)); r.rotation.y = Math.PI / 4; r.position.y = h + w * .25; r.scale.set(1, 1, d / w); g.add(r); }
  return g;
}
export function tree(h = 2, o = {}) { const g = cyl(h * .06, h * .4, { color: o.trunk || '#8a6a4a' }); const top = cone(h * .3, h * .7, { color: o.color || P.main }); top.position.y = h * .3; g.add(top); return g; }
// wireframe edges on every mesh of an object (hologram scans); the edges ride with their meshes: K.wire(obj, { color, opacity, angle })
export function wire(obj, o = {}) {
  const meshes = []; obj.traverse(m => { if (m.isMesh) meshes.push(m); });
  for (const m of meshes) { const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, o.angle ?? 20), new THREE.LineBasicMaterial({ color: o.color || P.main, transparent: true, opacity: o.opacity ?? 1 })); e.userData.noOutline = true; m.add(e); }
  return obj;
}
// 3D text-free markers: a flat ring on the ground (a station, a target): K.ring(r, { color, width })
export function ring(r = 1, o = {}) { const x = new THREE.Mesh(new THREE.RingGeometry(r - (o.width ?? .08), r, 64), new THREE.MeshBasicMaterial({ color: o.color || P.accent, side: THREE.DoubleSide, transparent: true })); x.rotation.x = -Math.PI / 2; x.position.y = .02; x.userData.noOutline = true; return x; }
// arrivals in 3D: scale with a little overshoot from `at` (call every frame): K.pop(obj, t, at, { dur: .5, from: 0, out })
export function pop(obj, t, at, o = {}) {
  const th = held(t), on = th >= at && (o.out == null || t < o.out); obj.visible = on; if (!on) return 0;
  const k = o.how === 'rise' ? eo(seg(th, at, at + (o.dur ?? .6))) : back(seg(th, at, at + (o.dur ?? .5)), 2.2), s = lerp(o.from ?? 0, 1, k);
  if (o.how === 'rise') { obj.position.y = (obj.userData.y0 ??= obj.position.y) - (1 - k) * (o.depth ?? 2); obj.scale.setScalar(1); } else obj.scale.setScalar(Math.max(.0001, s));
  return k;
}

// ════════════════════════════ finishing ════════════════════════════
// the look's grain and vignette over a 2D frame (the 3D stage already has its own in the chain; call it after the overlays)
let _grain = null;
export function grade(ctx, t) {
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (LOOK.vignette) { const v = ctx.createRadialGradient(SW / 2, SH / 2, Math.min(SW, SH) * .42, SW / 2, SH / 2, Math.hypot(SW, SH) * .6); v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, `rgba(0,0,0,${LOOK.vignette})`); ctx.fillStyle = v; ctx.fillRect(0, 0, SW, SH); }
  if (LOOK.grain && LOOK.grain.a > 0) {
    if (!_grain) { const N = 256, c = cv(N, N), g = c.getContext('2d'), im = g.createImageData(N, N), R = mulberry(5); for (let i = 0; i < N * N; i++) { const v = R() * 255; im.data[i * 4] = im.data[i * 4 + 1] = im.data[i * 4 + 2] = v; im.data[i * 4 + 3] = 255; } g.putImageData(im, 0, 0); _grain = c; }
    const f = Math.floor(held(t) * 24), R = mulberry(f * 31 + 3), s = LOOK.grain.size || 1.5; ctx.globalAlpha = LOOK.grain.a * 2.2; ctx.globalCompositeOperation = 'overlay';
    const pat = ctx.createPattern(_grain, 'repeat'); pat.setTransform(new DOMMatrix().translate(R() * 256, R() * 256).scale(s, s)); ctx.fillStyle = pat; ctx.fillRect(0, 0, SW, SH);
  }
  ctx.restore();
}
// a cut wipe between big ideas, in the look's colour: K.wipe(ctx, t, at) (covers [at - .25, at + .25])
export function wipe(ctx, t, at, o = {}) {
  const u = seg(t, at - .28, at + .28); if (u <= 0 || u >= 1) return;
  const k = u < .5 ? eio(u * 2) : 1 - eio((u - .5) * 2), x = u < .5 ? 0 : SW * (1 - k);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = o.color || P.accent;
  if (LOOK.ground === 'paper') { tornPath(ctx, u < .5 ? -20 : SW - SW * k - 20, -20, SW * k + 40, SH + 40, 77, 30); ctx.fill(); } else ctx.fillRect(x, 0, SW * k, SH);
  ctx.restore();
}
export function finish(ctx, t, { fadeIn = .25, end = null } = {}) {
  const a = Math.max(1 - seg(t, 0, fadeIn), end != null ? seg(t, end - .3, end) : 0); if (a <= 0) return;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a; ctx.fillStyle = P.bg; ctx.fillRect(0, 0, SW, SH); ctx.restore();
}
// sound cues (the same names as the Flat Explainer foley): type (text landing), whoosh (a camera move, a wipe), pop (a card,
// a label, an arrival), hit (a verdict), ding (a counter landing, a tick), splat (a big wipe), jump
export const typeTime = (text, cps = 30) => String(text).length / cps;
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
