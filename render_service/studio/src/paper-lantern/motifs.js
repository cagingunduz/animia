// Paper motifs for the lightbox: each one paints a silhouette on a sheet's context g in world units (y down).
// Fill colour does not matter (the sheet colours it); use cut(g, fn) for holes. `base` = the ground line's y.
import { mulberry, lerp, clamp, TAU } from '../common/lib.js';
import { cut } from './lantern.js';

const fillDown = (g, x0, x1, base, deep = 2400) => { g.lineTo(x1, base + deep); g.lineTo(x0, base + deep); g.closePath(); g.fill(); };

// rolling hills / a ridge line: amp = height of the bumps, len = their width
export function hills(g, { x0 = -1600, x1 = 1600, base = 400, amp = 80, len = 500, seed = 1 } = {}) {
  const R = mulberry(seed), ph = [R() * TAU, R() * TAU, R() * TAU];
  const y = u => base - amp * (.55 * Math.sin(u / len * TAU * .5 + ph[0]) + .3 * Math.sin(u / len * TAU * 1.13 + ph[1]) + .15 * Math.sin(u / len * TAU * 2.7 + ph[2]));
  g.beginPath(); g.moveTo(x0, y(x0)); for (let u = x0; u <= x1; u += 8) g.lineTo(u, y(u)); fillDown(g, x0, x1, base);
  return y;
}
// mountain peaks: list = [[cx, height, halfWidth], ...]; slits = carved snow-line cuts that let the light through
export function peaks(g, { x0 = -1600, x1 = 1600, base = 300, list = [[-300, 600, 500], [250, 800, 600]], slits = true, seed = 2 } = {}) {
  const R = mulberry(seed);
  const h = u => { let y = 0; for (const [cx, hh, w] of list) { const d = Math.abs(u - cx) / w; y = Math.max(y, hh * Math.max(0, 1 - Math.pow(d, 1.25))); } return y; };
  g.beginPath(); g.moveTo(x0, base - h(x0)); for (let u = x0; u <= x1; u += 4) g.lineTo(u, base - h(u) - 1.5 * Math.sin(u * .2 + seed)); fillDown(g, x0, x1, base);
  if (slits) cut(g, () => {   // one carved snow line below each summit, only where that peak is the outline
    g.lineWidth = 5; g.lineCap = 'round';
    for (const [cx, hh, w] of list) {
      const top = u => hh * Math.max(0, 1 - Math.pow(Math.abs(u - cx) / w, 1.25));
      g.beginPath(); let st = false;
      for (let u = cx - w * .6; u <= cx + w * .6; u += 4) {
        const own = top(u), y = base - own * .74 - 10 * Math.sin(u * .025 + cx);
        if (own >= h(u) - 1 && own * .26 > 30) { st ? g.lineTo(u, y) : g.moveTo(u, y); st = true; } else st = false;
      }
      g.stroke();
      g.beginPath(); g.moveTo(cx, base - hh + 26); g.lineTo(cx + w * .12 * (R() - .3), base - hh * .8); g.stroke();
    }
  });
}
// a row of conifers on a ground line
export function firs(g, { x0 = -1600, x1 = 1600, base = 600, h = 180, gap = 60, seed = 3, roll = 12 } = {}) {
  const R = mulberry(seed), gy = u => base + roll * Math.sin(u * .01 + seed);
  g.beginPath(); g.moveTo(x0, gy(x0)); for (let u = x0; u <= x1; u += 8) g.lineTo(u, gy(u)); fillDown(g, x0, x1, base);
  for (let u = x0 + R() * gap; u < x1; u += gap * (.6 + R() * .8)) fir(g, u, gy(u) + 2, h * (.6 + R() * .6));
}
export function fir(g, x, base, h) {
  const w = h * .32; g.beginPath(); g.moveTo(x, base - h);
  for (let k = 0; k < 4; k++) { const t1 = (k + 1) / 4; g.lineTo(x + w * (.35 + .65 * t1), base - h * (1 - t1)); g.lineTo(x + w * .3 * (1 - t1) + w * .12, base - h * (1 - t1) - h * .04); }
  g.lineTo(x + 6, base + 4); g.lineTo(x - 6, base + 4);
  for (let k = 3; k >= 0; k--) { const t1 = (k + 1) / 4; g.lineTo(x - w * .3 * (1 - t1) - w * .12, base - h * (1 - t1) - h * .04); g.lineTo(x - w * (.35 + .65 * t1), base - h * (1 - t1)); }
  g.closePath(); g.fill();
}
// a round broadleaf tree (lace holes cut in the crown)
export function tree(g, x, base, h, seed = 4) {
  const R = mulberry(seed), r = h * .34;
  g.beginPath(); g.moveTo(x - h * .035, base); g.lineTo(x - h * .02, base - h * .55); g.lineTo(x + h * .02, base - h * .55); g.lineTo(x + h * .035, base); g.closePath(); g.fill();
  for (let i = 0; i < 7; i++) { const a = i / 7 * TAU, rr = r * (.55 + R() * .2); g.beginPath(); g.arc(x + Math.cos(a) * r * .55, base - h * .66 + Math.sin(a) * r * .45, rr, 0, TAU); g.fill(); }
  cut(g, () => { for (let i = 0; i < 9; i++) { g.beginPath(); g.ellipse(x + (R() - .5) * r * 1.4, base - h * .66 + (R() - .5) * r * 1.0, 6 + R() * 8, 4 + R() * 5, R() * 3, 0, TAU); g.fill(); } });
}
// a row of houses; windows = true cuts the window holes (paint the same row with houseWindows() in the sheet's glow)
function houseList(x0, x1, seed, h) { const R = mulberry(seed), out = []; let x = x0; while (x < x1) { const w = h * (.7 + R() * .8), hh = h * (.7 + R() * .6), roof = R() < .5 ? 'gable' : (R() < .5 ? 'flat' : 'eave'); out.push({ x, w, hh, roof, wins: Math.max(1, Math.round(w / 70)), rows: Math.max(1, Math.round(hh / 90)), on: [...Array(12)].map(() => R()) }); x += w + h * (.05 + R() * .3); } return out; }
export function houses(g, { x0 = -1200, x1 = 1200, base = 700, h = 160, seed = 5, windows = true } = {}) {
  const L = houseList(x0, x1, seed, h);
  g.fillRect(x0 - 50, base, x1 - x0 + 100, 2400);
  for (const b of L) {
    g.fillRect(b.x, base - b.hh, b.w, b.hh + 2);
    g.beginPath();
    if (b.roof === 'gable') { g.moveTo(b.x - 10, base - b.hh); g.lineTo(b.x + b.w / 2, base - b.hh - b.w * .45); g.lineTo(b.x + b.w + 10, base - b.hh); }
    else if (b.roof === 'eave') { g.moveTo(b.x - b.w * .18, base - b.hh + 8); g.quadraticCurveTo(b.x + b.w * .1, base - b.hh - 6, b.x + b.w * .25, base - b.hh - b.w * .22); g.lineTo(b.x + b.w * .75, base - b.hh - b.w * .22); g.quadraticCurveTo(b.x + b.w * .9, base - b.hh - 6, b.x + b.w * 1.18, base - b.hh + 8); }
    else { g.rect(b.x - 6, base - b.hh - 12, b.w + 12, 14); }
    g.closePath(); g.fill();
  }
  if (windows) cut(g, () => houseWindows(g, { x0, x1, base, h, seed, all: true }));
}
// the windows of the same row of houses: lit = fraction of windows that burn (0..1), all = every window
export function houseWindows(g, { x0 = -1200, x1 = 1200, base = 700, h = 160, seed = 5, lit = 1, all = false } = {}) {
  for (const b of houseList(x0, x1, seed, h)) {
    let k = 0;
    for (let r = 0; r < b.rows; r++) for (let c = 0; c < b.wins; c++) {
      const on = b.on[k++ % 12]; if (!all && on > lit) continue;
      const ww = Math.min(26, b.w / (b.wins * 2.2)), wh = ww * 1.35, cx = b.x + (c + .5) * b.w / b.wins, cy = base - b.hh + (r + .45) * b.hh / (b.rows + .3);
      g.fillRect(cx - ww / 2, cy - wh / 2, ww, wh);
    }
  }
}
// waves: a sea band with curling crests
export function waves(g, { x0 = -1600, x1 = 1600, base = 900, amp = 26, len = 180, phase = 0, curls = true } = {}) {
  g.beginPath(); g.moveTo(x0, base);
  for (let u = x0; u <= x1; u += 6) g.lineTo(u, base - amp * Math.sin((u / len + phase) * TAU) * .5 - amp * .5 * Math.pow(Math.max(0, Math.sin((u / len + phase) * TAU)), 6));
  fillDown(g, x0, x1, base);
  if (curls) cut(g, () => { g.lineWidth = 5; g.lineCap = 'round'; for (let u = x0 + ((-phase * len) % len + len) % len; u < x1; u += len) { g.beginPath(); g.arc(u + len * .22, base + amp * .9, amp * .55, Math.PI * 1.1, Math.PI * 2.2); g.stroke(); } });
}
// an auspicious curl cloud (剪纸-style), s = size
export function cloud(g, x, y, s = 1) {
  const c = (cx, cy, r) => { g.beginPath(); g.arc(x + cx * s, y + cy * s, r * s, 0, TAU); g.fill(); };
  c(0, 0, 46); c(-58, 14, 34); c(58, 12, 38); c(-108, 26, 22); c(104, 26, 24); g.fillRect(x - 112 * s, y + 18 * s, 224 * s, 30 * s);
  cut(g, () => { g.lineWidth = 6 * s; g.lineCap = 'round'; for (const [cx, cy, r] of [[0, 0, 26], [-58, 14, 18], [58, 12, 20]]) { g.beginPath(); g.arc(x + cx * s, y + cy * s, r * s, Math.PI * .9, Math.PI * 2.3); g.stroke(); } });
}
// a crescent / full moon cut-out hole helper (cut from a sky-coloured front sheet)
export function moonHole(g, x, y, r, phase = 0) { cut(g, () => { g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill(); }); if (phase) { g.beginPath(); g.arc(x + phase * r * 1.1, y - r * .1, r * 1.02, 0, TAU); g.fill(); } }
// birds in flight: list of [x, y, size, wingPhase]
export function birds(g, list) { for (const [x, y, s = 1, p = 0] of list) { const k = Math.sin(p * TAU) * .5; g.beginPath(); g.moveTo(x - 30 * s, y - 10 * s * (1 + k)); g.quadraticCurveTo(x - 12 * s, y - 14 * s * k, x, y); g.quadraticCurveTo(x + 12 * s, y - 14 * s * k, x + 30 * s, y - 10 * s * (1 + k)); g.quadraticCurveTo(x + 12 * s, y - 4 * s * k + 4 * s, x, y + 5 * s); g.quadraticCurveTo(x - 12 * s, y - 4 * s * k + 4 * s, x - 30 * s, y - 10 * s * (1 + k)); g.fill(); } }
// a small boat with a sail; lantern = its lit window area (paint again in glow)
export function boat(g, x, y, s = 1, { sail = true, lamp = false } = {}) {
  g.beginPath(); g.moveTo(x - 110 * s, y - 30 * s); g.lineTo(x + 120 * s, y - 34 * s); g.quadraticCurveTo(x + 80 * s, y + 8 * s, x + 60 * s, y + 10 * s); g.lineTo(x - 70 * s, y + 10 * s); g.quadraticCurveTo(x - 95 * s, y - 4 * s, x - 110 * s, y - 30 * s); g.fill();
  g.fillRect(x - 3 * s, y - 210 * s, 6 * s, 180 * s);
  if (sail) { g.beginPath(); g.moveTo(x + 6 * s, y - 200 * s); g.quadraticCurveTo(x + 90 * s, y - 120 * s, x + 96 * s, y - 46 * s); g.lineTo(x + 6 * s, y - 46 * s); g.fill(); }
  if (lamp) { g.fillRect(x - 60 * s, y - 70 * s, 34 * s, 40 * s); }
}
// a hanging paper lantern (body = holes when cut: paint the same in glow)
export function lantern(g, x, y, s = 1) {
  g.fillRect(x - 1.5 * s, y - 120 * s, 3 * s, 90 * s);
  g.beginPath(); g.ellipse(x, y, 34 * s, 42 * s, 0, 0, TAU); g.fill(); g.fillRect(x - 20 * s, y - 50 * s, 40 * s, 10 * s); g.fillRect(x - 20 * s, y + 40 * s, 40 * s, 10 * s);
  g.fillRect(x - 2 * s, y + 50 * s, 4 * s, 40 * s);
}
// an arched stone bridge between x0 and x1 with its deck at y
export function bridge(g, x0, x1, y, { arches = 3, thick = 40 } = {}) {
  const w = x1 - x0; g.fillRect(x0, y, w, thick); g.fillRect(x0, y + thick, w, 300);
  cut(g, () => { for (let i = 0; i < arches; i++) { const cx = x0 + (i + .5) * w / arches, r = w / arches * .38; g.beginPath(); g.arc(cx, y + thick + 300, r, Math.PI, 0); g.lineTo(cx + r, y + thick + 320); g.lineTo(cx - r, y + thick + 320); g.fill(); } });
  for (let i = 0; i <= w / 40; i++) g.fillRect(x0 + i * 40, y - 22, 6, 22); g.fillRect(x0, y - 26, w, 6);
}
// a pagoda / tiered tower; windows = its lit openings (paint again in glow with windows: true only)
export function pagoda(g, x, base, s = 1, { tiers = 4, only = false } = {}) {
  for (let i = 0; i < tiers; i++) {
    const w = (150 - i * 22) * s, y = base - i * 110 * s;
    if (!only) {
      g.fillRect(x - w * .38, y - 80 * s, w * .76, 80 * s);
      g.beginPath(); g.moveTo(x - w * .78, y - 70 * s); g.quadraticCurveTo(x - w * .5, y - 82 * s, x - w * .3, y - 112 * s); g.lineTo(x + w * .3, y - 112 * s); g.quadraticCurveTo(x + w * .5, y - 82 * s, x + w * .78, y - 70 * s); g.lineTo(x + w * .5, y - 88 * s); g.lineTo(x - w * .5, y - 88 * s); g.closePath(); g.fill();
    }
    if (only) g.fillRect(x - 10 * s, y - 62 * s, 20 * s, 34 * s);
  }
  if (!only) { g.fillRect(x - 3 * s, base - tiers * 110 * s - 70 * s, 6 * s, 70 * s); cut(g, () => pagoda(g, x, base, s, { tiers, only: true })); }
}
// a lighthouse; beam the light with a glow-painted lamp room
export function lighthouse(g, x, base, s = 1, { only = false } = {}) {
  if (only) { g.fillRect(x - 24 * s, base - 420 * s, 48 * s, 40 * s); return; }
  g.beginPath(); g.moveTo(x - 60 * s, base); g.lineTo(x - 36 * s, base - 380 * s); g.lineTo(x + 36 * s, base - 380 * s); g.lineTo(x + 60 * s, base); g.fill();
  g.fillRect(x - 46 * s, base - 386 * s, 92 * s, 10 * s); g.fillRect(x - 30 * s, base - 430 * s, 60 * s, 50 * s);
  g.beginPath(); g.moveTo(x - 36 * s, base - 430 * s); g.lineTo(x, base - 470 * s); g.lineTo(x + 36 * s, base - 430 * s); g.fill();
  cut(g, () => { g.fillRect(x - 24 * s, base - 420 * s, 48 * s, 40 * s); for (let i = 0; i < 4; i++) g.fillRect(x - 6 * s, base - (330 - i * 80) * s, 12 * s, 26 * s); });
}

// —— figures: jointed silhouettes in the Reiniger manner (profile, long limbs), h = height ——
// pose: 'stand' | 'walk' (phase 0..1 = the step) | 'sit' | 'reach' | 'run'; face: 1 right, -1 left; kind: 'adult' | 'child' | 'elder'
export function person(g, x, base, h = 300, { pose = 'stand', phase = 0, face = 1, kind = 'adult', hat = false, dress = false, bag = false } = {}) {
  g.save(); g.translate(x, base); g.scale(face * h / 300, h / 300);
  const lean = kind === 'elder' ? .14 : pose === 'run' ? .2 : pose === 'walk' ? .05 : 0;
  const limb = (ax, ay, bx, by, w0, w1) => { const dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L; g.beginPath(); g.moveTo(ax + nx * w0, ay + ny * w0); g.lineTo(bx + nx * w1, by + ny * w1); g.arc(bx, by, w1, Math.atan2(ny, nx), Math.atan2(ny, nx) + Math.PI); g.lineTo(ax - nx * w0, ay - ny * w0); g.arc(ax, ay, w0, Math.atan2(-ny, -nx), Math.atan2(-ny, -nx) + Math.PI); g.fill(); };
  const s = Math.sin(phase * TAU), c = Math.cos(phase * TAU);
  const hipY = pose === 'sit' ? -95 : -150, hip = [0, hipY], sh = [lean * 130, hipY - 105];
  // legs
  if (pose === 'sit') { limb(0, hipY, 70, hipY, 13, 11); limb(70, hipY, 72, -4, 11, 9); limb(-6, hipY, 60, hipY + 4, 13, 11); limb(60, hipY + 4, 58, -4, 11, 9); }
  else {
    const st = pose === 'run' ? 46 : pose === 'walk' ? 30 : 6;
    for (const k of [1, -1]) { const sw = s * k, kx = sw * st * .55 + 4, fx = sw * st, lift = Math.max(0, -c * k) * (pose === 'run' ? 34 : 14); limb(0, hipY, kx, hipY / 2 - lift * .3, 13, 11); limb(kx, hipY / 2 - lift * .3, fx, -6 - lift, 11, 8); g.beginPath(); g.ellipse(fx + 10, -5 - lift, 15, 6, 0, 0, TAU); g.fill(); }
  }
  // body
  g.beginPath(); g.moveTo(-18, hipY + 6); g.lineTo(sh[0] - 20, sh[1] + 10); g.quadraticCurveTo(sh[0], sh[1] - 12, sh[0] + 20, sh[1] + 10); g.lineTo(22, hipY + 6); g.closePath(); g.fill();
  if (dress) { g.beginPath(); g.moveTo(-14, hipY - 30); g.lineTo(-42, hipY + 70); g.quadraticCurveTo(0, hipY + 80, 46, hipY + 70); g.lineTo(18, hipY - 30); g.fill(); }
  // arms
  const reach = pose === 'reach';
  for (const k of [1, -1]) { const sw = pose === 'walk' || pose === 'run' ? -s * k : 0; const el = reach && k === 1 ? [sh[0] + 45, sh[1] - 25] : [sh[0] + sw * 26, sh[1] + 50]; const hd = reach && k === 1 ? [sh[0] + 90, sh[1] - 55] : [sh[0] + sw * 46 + 6, sh[1] + 98]; limb(sh[0], sh[1] + 8, el[0], el[1], 9, 8); limb(el[0], el[1], hd[0], hd[1], 8, 6.5); }
  if (bag) { g.beginPath(); g.roundRect(sh[0] - 46, sh[1] + 20, 30, 50, 6); g.fill(); }
  // head: neck, skull, nose, a hint of hair
  const hx = sh[0] + 8, hy = sh[1] - 34 - (kind === 'child' ? -6 : 0), hr = kind === 'child' ? 30 : 25;
  limb(sh[0], sh[1] + 4, hx, hy + 10, 8, 8);
  g.beginPath(); g.arc(hx, hy, hr, 0, TAU); g.fill();
  g.beginPath(); g.moveTo(hx + hr * .8, hy - 6); g.lineTo(hx + hr + 9, hy + 6); g.lineTo(hx + hr * .7, hy + 10); g.fill();
  if (kind === 'elder') { g.beginPath(); g.ellipse(hx - 14, hy - 4, 18, 22, -.4, 0, TAU); g.fill(); }
  if (hat) { g.beginPath(); g.ellipse(hx, hy - hr * .7, hr * 1.8, 6, 0, 0, TAU); g.fill(); g.fillRect(hx - hr * .8, hy - hr * 1.5, hr * 1.6, hr * .85); }
  g.restore();
}
// a cat sitting (tail curl) or walking
export function cat(g, x, base, s = 1, { face = 1 } = {}) {
  g.save(); g.translate(x, base); g.scale(face * s, s);
  g.beginPath(); g.ellipse(0, -40, 34, 40, 0, 0, TAU); g.fill(); g.beginPath(); g.arc(12, -96, 22, 0, TAU); g.fill();
  g.beginPath(); g.moveTo(0, -110); g.lineTo(4, -132); g.lineTo(14, -116); g.moveTo(18, -116); g.lineTo(30, -132); g.lineTo(32, -108); g.fill();
  g.lineWidth = 9; g.lineCap = 'round'; g.beginPath(); g.moveTo(-28, -10); g.quadraticCurveTo(-80, -6, -66, -56); g.stroke();
  g.restore();
}
