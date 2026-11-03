// Documentary Analysis kit for the Animave long-video studio (window.DA): the overlay layer of a 16:9 analysis
// documentary. The pictures (real archive footage / photos and generated illustrations) play in the plate UNDER the
// canvas; this kit draws only what goes over them: title and question cards, lower thirds, counters, quotes,
// comparisons, timelines, map pins and routes, marks on the picture (rings, arrows, boxes, highlighter), a dim, flash
// cuts, grain and vignette. The canvas starts transparent every frame, so the plate shows through.
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env } from '../common/lib.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env };

export let SW = 1920, SH = 1080;
export function setScreen(w, h) { SW = w; SH = h; }
export const C = { ink: '#0f1013', paper: '#f2f0ea', white: '#ffffff', grey: '#9a9ca6', hi: '#e8c547', red: '#e04848', card: '#121317', card2: '#1c1e24' };
const H = (w, px) => `${w} ${px}px Inter`, Q = px => `italic 600 ${px}px PlayfairDisplay`, M = px => `500 ${px}px IBMPlexMono`;
const cv = (w, h) => new OffscreenCanvas(Math.max(1, Math.ceil(w)), Math.max(1, Math.ceil(h)));

// start of every frame: transparent, so the plate (footage) shows
export function clear(ctx) { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.clearRect(0, 0, SW, SH); }
// darken the picture (behind titles, for focus): K.dim(ctx, t, { at, out, amount: .55 })
export function dim(ctx, t, { at = 0, out = null, amount = .55 } = {}) {
  const a = amount * Math.min(eo(seg(t, at, at + .3)), out == null ? 1 : 1 - seg(t, out, out + .3)); if (a <= 0) return;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = `rgba(8,9,12,${a})`; ctx.fillRect(0, 0, SW, SH); ctx.restore();
}
// a spotlight on part of the picture (the rest darkens): K.focus(ctx, t, { x, y, w, h, at, out })
export function focus(ctx, t, o) {
  const a = .62 * Math.min(eo(seg(t, o.at, o.at + .35)), o.out == null ? 1 : 1 - seg(t, o.out, o.out + .3)); if (a <= 0) return;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = `rgba(6,7,10,${a})`; ctx.beginPath(); ctx.rect(0, 0, SW, SH); ctx.rect(o.x + o.w, o.y, -o.w, o.h); ctx.fill('evenodd'); ctx.restore();
}

// words land one by one as spoken (scale 1.3 -> 1, 0.12 s): used by the cards
function landWords(ctx, t, words, x, y, size, maxW, { font = 'title', color = C.white, hi = [], align = 'center' } = {}) {
  const f = font === 'quote' ? Q : (px => H(900, px));
  ctx.save(); ctx.font = f(size); ctx.textBaseline = 'middle';
  const gap = size * .28, norm = s => String(s).toLowerCase().replace(/[^a-z0-9ğüşıöçâî%]/gi, '');
  const W = words.map(w => ctx.measureText(w.w).width), rows = [[]]; let rw = 0;
  words.forEach((w, i) => { if (rows[rows.length - 1].length && rw + gap + W[i] > maxW) { rows.push([]); rw = 0; } rows[rows.length - 1].push(i); rw += (rw ? gap : 0) + W[i]; });
  const lh = size * 1.08, y0 = y - (rows.length - 1) * lh / 2;
  rows.forEach((r, ri) => {
    const tot = r.reduce((s, i, k) => s + W[i] + (k ? gap : 0), 0); let cx = align === 'left' ? x : x - tot / 2;
    for (const i of r) {
      const w = words[i]; if (t >= w.s) {
        const u = seg(t, w.s, w.s + .12), s = lerp(1.3, 1, eo(u)), isHi = hi.map(norm).includes(norm(w.w));
        ctx.save(); ctx.translate(cx + W[i] / 2, y0 + ri * lh); ctx.scale(s, s); ctx.globalAlpha *= clamp(u * 3);
        if (isHi) { ctx.fillStyle = C.hi; ctx.fillRect(-W[i] / 2 - 8, -size * .5, W[i] + 16, size * 1.02); ctx.fillStyle = C.ink; } else ctx.fillStyle = color;
        ctx.fillText(w.w, -W[i] / 2, 0); ctx.restore();
      }
      cx += W[i] + gap;
    }
  });
  ctx.restore();
}
const toWords = (text, at, step = .12) => String(text).split(/\s+/).filter(Boolean).map((w, i) => ({ w, s: at + i * step }));

// a full-frame title / question card (dark, the picture faintly behind): K.title(ctx, t, 'KANAL 6 GÜN KAPALI', at,
//   { out, hi: ['6', 'GÜN'], size: 120, over: false (true = no card, words over the picture with a dim), words: T.lines[i].words })
export function title(ctx, t, text, at, o = {}) {
  if (t < at || (o.out != null && t > o.out + .25)) return;
  const a = o.out == null ? 1 : 1 - seg(t, o.out, o.out + .25);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a;
  if (o.over) { ctx.fillStyle = 'rgba(8,9,12,.55)'; ctx.fillRect(0, 0, SW, SH); }
  else { ctx.fillStyle = C.card; ctx.fillRect(0, 0, SW, SH); const g = ctx.createRadialGradient(SW / 2, SH / 2, 50, SW / 2, SH / 2, SW * .7); g.addColorStop(0, 'rgba(255,255,255,.05)'); g.addColorStop(1, 'rgba(0,0,0,.3)'); ctx.fillStyle = g; ctx.fillRect(0, 0, SW, SH); }
  const words = o.words ? o.words.map(w => ({ w: w.w.toUpperCase(), s: w.s })) : toWords(String(text).toUpperCase(), at);
  landWords(ctx, t, words, SW / 2, SH / 2, o.size ?? 120, SW * .78, { hi: (o.hi || []).map(s => String(s).toUpperCase()) });
  ctx.restore();
}
// a lower third: place / date / source over footage: K.lower(ctx, t, { title: 'Süveyş Kanalı · Mısır', sub: '23 Mart 2021 · Kaynak: …', at, out })
export function lower(ctx, t, o) {
  if (t < o.at || (o.out != null && t > o.out + .3)) return;
  const u = eo(seg(t, o.at, o.at + .3)), v = o.out == null ? 0 : eo(seg(t, o.out, o.out + .3)), dx = (1 - u) * -60 - v * 60, a = u * (1 - v);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a; ctx.textBaseline = 'middle';
  ctx.font = H(800, 34); const tw = ctx.measureText(String(o.title).toUpperCase()).width; ctx.font = H(500, 22); const sw = o.sub ? ctx.measureText(o.sub).width : 0;
  const x = 80 + dx, y = SH - 190;
  ctx.fillStyle = C.white; ctx.fillRect(x, y, tw + 36, 58); ctx.fillStyle = C.ink; ctx.font = H(800, 34); ctx.fillText(String(o.title).toUpperCase(), x + 18, y + 30);
  if (o.sub) { ctx.fillStyle = 'rgba(12,13,16,.88)'; ctx.fillRect(x, y + 58, sw + 36, 42); ctx.fillStyle = '#d9dae0'; ctx.font = H(500, 22); ctx.fillText(o.sub, x + 18, y + 80); }
  ctx.fillStyle = C.hi; ctx.fillRect(x - 10, y, 6, o.sub ? 100 : 58);
  ctx.restore();
}
// a big number rolling up, with a label (on a dim): K.counter(ctx, t, { to, from: 0, at, dur: 1.5, prefix, suffix, label, x, y, size: 170, dec })
export function counter(ctx, t, o) {
  if (t < o.at || (o.out != null && t > o.out)) return; const u = eo(seg(t, o.at, o.at + (o.dur ?? 1.5))), v = lerp(o.from ?? 0, o.to, u);
  const txt = (o.prefix || '') + (o.dec ? v.toFixed(o.dec) : Math.round(v).toLocaleString('tr-TR')) + (o.suffix || '');
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  const x = o.x ?? SW / 2, y = o.y ?? SH / 2 - 30, land = u >= 1 ? 1 + .06 * Math.max(0, 1 - (t - o.at - (o.dur ?? 1.5)) * 6) : 1;
  ctx.translate(x, y); ctx.scale(land, land); ctx.font = H(900, o.size ?? 170); ctx.fillStyle = C.white; ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = 30; ctx.fillText(txt, 0, 0);
  if (o.label) { ctx.shadowBlur = 0; ctx.font = H(600, 30); ctx.fillStyle = '#cfd0d6'; ctx.fillText(String(o.label).toUpperCase(), 0, (o.size ?? 170) * .72); }
  ctx.restore();
}
// a quote card (real, sourced quotes only): K.quote(ctx, t, '“…”', at, { who: 'Kanal İdaresi Başkanı', out })
export function quote(ctx, t, text, at, o = {}) {
  if (t < at || (o.out != null && t > o.out + .25)) return; const a = eo(seg(t, at, at + .35)) * (o.out == null ? 1 : 1 - seg(t, o.out, o.out + .25));
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a; ctx.fillStyle = 'rgba(10,11,14,.82)'; ctx.fillRect(0, 0, SW, SH);
  ctx.fillStyle = C.hi; ctx.fillRect(SW * .14, SH * .3, 8, SH * .36);
  landWords(ctx, t, toWords(text, at + .1, .09), SW * .14 + 44, SH * .46, 58, SW * .68, { font: 'quote', align: 'left' });
  if (o.who) { ctx.font = H(600, 26); ctx.fillStyle = '#b9bac2'; ctx.textBaseline = 'middle'; ctx.fillText('— ' + o.who, SW * .14 + 44, SH * .68); }
  ctx.restore();
}
// two panels compared: K.compare(ctx, t, { left: { title, value, sub }, right: { title, value, sub }, at, win: 'left' | 'right', out })
export function compare(ctx, t, o) {
  if (t < o.at || (o.out != null && t > o.out + .25)) return;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = o.out == null ? 1 : 1 - seg(t, o.out, o.out + .25);
  const sides = [['left', 0, '#20232b'], ['right', SW / 2, '#2b2519']];
  sides.forEach(([k, x, col], i) => {
    const s = o[k] || {}, at = o.at + i * .35, u = eo(seg(t, at, at + .35)); if (u <= 0) return;
    ctx.save(); ctx.translate(0, (1 - u) * 60); ctx.globalAlpha *= u; ctx.fillStyle = col; ctx.fillRect(x, 0, SW / 2, SH);
    if (o.win === k) { ctx.fillStyle = C.hi; ctx.fillRect(x, SH - 14, SW / 2, 14); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#c9cad1'; ctx.font = H(700, 34); ctx.fillText(String(s.title || '').toUpperCase(), x + SW / 4, SH * .3);
    ctx.fillStyle = C.white; ctx.font = H(900, 120); ctx.fillText(String(s.value ?? ''), x + SW / 4, SH * .5);
    if (s.sub) { ctx.fillStyle = '#9fa1aa'; ctx.font = H(500, 28); ctx.fillText(s.sub, x + SW / 4, SH * .64); }
    ctx.restore();
  });
  ctx.restore();
}
// a timeline strip of dates: K.timeline(ctx, t, [{ label: '23 Mart', at }, ...], { y: 860, active: index, out })
export function timeline(ctx, t, items, o = {}) {
  if (!items.length || t < items[0].at - .3 || (o.out != null && t > o.out + .25)) return;
  const y = o.y ?? SH - 170, x0 = 160, x1 = SW - 160, a = eo(seg(t, items[0].at - .3, items[0].at)) * (o.out == null ? 1 : 1 - seg(t, o.out, o.out + .25));
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a; ctx.fillStyle = 'rgba(8,9,12,.6)'; ctx.fillRect(0, y - 90, SW, 170);
  ctx.strokeStyle = '#6b6e78'; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
  let cur = -1; items.forEach((it, i) => { if (t >= it.at) cur = i; });
  items.forEach((it, i) => {
    const x = lerp(x0, x1, items.length === 1 ? .5 : i / (items.length - 1)), on = t >= it.at, s = on ? back(seg(t, it.at, it.at + .3), 2) : 0;
    if (!on) return; const act = i === cur;
    ctx.fillStyle = act ? C.hi : '#cfd0d6'; ctx.beginPath(); ctx.arc(x, y, (act ? 16 : 10) * s, 0, TAU); ctx.fill();
    ctx.font = H(act ? 800 : 600, act ? 34 : 26); ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillStyle = act ? C.white : '#b0b2ba'; ctx.fillText(it.label, x, y - 28);
  });
  ctx.restore();
}
// marks on the picture: a ring, an arrow, a box, a highlighter stroke (in frame px)
function stroke(ctx, pts, u, col, w) { if (u <= 0) return; const n = Math.max(2, Math.floor(pts.length * clamp(u))); ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.strokeStyle = col; ctx.lineWidth = w; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.shadowColor = 'rgba(0,0,0,.5)'; ctx.shadowBlur = 8; ctx.beginPath(); ctx.moveTo(...pts[0]); for (let i = 1; i < n; i++) ctx.lineTo(...pts[i]); ctx.stroke(); ctx.restore(); }
export function ring(ctx, t, { x, y, w, h, at, dur = .45, color = C.red, width = 9, out }) {
  if (t < at || (out != null && t > out)) return; const pts = []; for (let i = 0; i <= 80; i++) { const k = i / 80, a = -2 + k * TAU * 1.08; pts.push([x + Math.cos(a) * w / 2 * (1 + k * .04), y + Math.sin(a) * h / 2 * (1 + k * .04)]); }
  stroke(ctx, pts, eio(seg(t, at, at + dur)), color, width);
}
export function arrow(ctx, t, { from, to, at, dur = .35, color = C.red, width = 10, out }) {
  if (t < at || (out != null && t > out)) return; const u = eo(seg(t, at, at + dur)), x = lerp(from[0], to[0], u), y = lerp(from[1], to[1], u);
  stroke(ctx, [from, [x, y]], 1, color, width);
  if (u >= 1) { const a = Math.atan2(to[1] - from[1], to[0] - from[0]), L = 34; stroke(ctx, [[to[0] - Math.cos(a - .5) * L, to[1] - Math.sin(a - .5) * L], to, [to[0] - Math.cos(a + .5) * L, to[1] - Math.sin(a + .5) * L]], 1, color, width); }
}
export function box(ctx, t, { x, y, w, h, at, dur = .4, color = C.hi, width = 6, out }) {
  if (t < at || (out != null && t > out)) return; stroke(ctx, [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]], eo(seg(t, at, at + dur)), color, width);
}
export function highlight(ctx, t, { x, y, w, h, at, dur = .4, out }) {
  if (t < at || (out != null && t > out)) return; const u = eo(seg(t, at, at + dur));
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = 'rgba(232,197,71,.85)'; ctx.fillRect(x, y, w * u, h); ctx.restore();
}
// a map pin and a route (over a map picture in the plate): K.pin(ctx, t, { x, y, at, label }), K.route(ctx, t, [[x, y], ...], at, { dur: 1.2 })
export function pin(ctx, t, { x, y, at, label, out }) {
  if (t < at || (out != null && t > out)) return; const s = back(seg(t, at, at + .35), 2.2), pulse = (t - at) % 1.4 / 1.4;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.strokeStyle = `rgba(224,72,72,${.6 * (1 - pulse)})`; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(x, y, 14 + pulse * 46, 0, TAU); ctx.stroke();
  ctx.fillStyle = C.red; ctx.beginPath(); ctx.arc(x, y, 13 * s, 0, TAU); ctx.fill(); ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(x, y, 5 * s, 0, TAU); ctx.fill();
  if (label) { ctx.font = H(800, 30); ctx.textBaseline = 'middle'; const w = ctx.measureText(label.toUpperCase()).width; ctx.globalAlpha = clamp(seg(t, at + .15, at + .4)); ctx.fillStyle = 'rgba(10,11,14,.85)'; ctx.fillRect(x + 26, y - 24, w + 28, 48); ctx.fillStyle = '#fff'; ctx.fillText(label.toUpperCase(), x + 40, y); }
  ctx.restore();
}
export function route(ctx, t, pts, at, { dur = 1.2, color = C.hi, width = 7, out } = {}) {
  if (t < at || (out != null && t > out) || pts.length < 2) return; const dense = [];
  for (let i = 0; i < pts.length - 1; i++) for (let k = 0; k < 20; k++) dense.push([lerp(pts[i][0], pts[i + 1][0], k / 20), lerp(pts[i][1], pts[i + 1][1], k / 20)]);
  dense.push(pts[pts.length - 1]); ctx.save(); ctx.setLineDash([22, 14]); stroke(ctx, dense, eio(seg(t, at, at + dur)), color, width); ctx.restore();
}
// a hard cut with a white flash (call it last, around the cut time): K.flash(ctx, t, at)
export function flash(ctx, t, at) { const u = 1 - Math.abs(t - at) / .08; if (u <= 0) return; ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = `rgba(255,255,255,${.85 * u})`; ctx.fillRect(0, 0, SW, SH); ctx.restore(); }
// last: grain + vignette over everything (and a fade at the very start / end of the part)
let _grain = null, _vig = null;
export function finish(ctx, t, { fadeIn = .2, end = null } = {}) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
  if (!_grain) { _grain = cv(256, 256); const g = _grain.getContext('2d'), img = g.createImageData(256, 256), R = mulberry(4); for (let i = 0; i < 65536; i++) { const v = R() * 255; img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 16; } g.putImageData(img, 0, 0); }
  if (!_vig || _vig.width !== SW) { _vig = cv(SW, SH); const v = _vig.getContext('2d'), g = v.createRadialGradient(SW / 2, SH / 2, SH * .35, SW / 2, SH / 2, SW * .62); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,.42)'); v.fillStyle = g; v.fillRect(0, 0, SW, SH); }
  ctx.drawImage(_vig, 0, 0); const k = Math.floor(t * 24) % 4; ctx.save(); ctx.fillStyle = ctx.createPattern(_grain, 'repeat'); ctx.translate(k * 53, k * 31); ctx.fillRect(-300, -300, SW + 600, SH + 600); ctx.restore();
  let f = 0; if (fadeIn) f = 1 - seg(t, 0, fadeIn); if (end) f = Math.max(f, seg(t, end - .4, end));
  if (f > 0) { ctx.fillStyle = `rgba(0,0,0,${f})`; ctx.fillRect(0, 0, SW, SH); }
}
// small credits line for the archive pictures on screen now: K.credit(ctx, t, 'Wikimedia Commons · CC BY 4.0', { at, out })
export function credit(ctx, t, text, { at = 0, out = null } = {}) {
  if (!text || t < at || (out != null && t > out)) return; ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = .8 * clamp(seg(t, at, at + .3));
  ctx.font = H(500, 18); ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'; ctx.fillStyle = '#e6e6ea'; ctx.shadowColor = 'rgba(0,0,0,.8)'; ctx.shadowBlur = 6; ctx.fillText(text, SW - 40, SH - 30); ctx.restore();
}
// sound cues: type (words landing; d), whoosh (a cut / a card), pop (a pin, a number), hit (a title word, a ring), ding
// (a counter landing), riser (d, into a reveal), splat (a flash cut)
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
