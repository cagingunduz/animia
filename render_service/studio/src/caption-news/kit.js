// Caption News kit for the Animave Style Studio (window.CN): sound-off social news over real footage, after the
// lemo-opuscar "caption-news" style (github.com/lemomo-ai/lemo-opuscar, MIT), laid out for 9:16.
// The footage is a video PLATE under the canvas (built by the server from the shot list); the film draws only the
// graphics on a transparent canvas: captions slammed a chunk at a time with one yellow keyword, rolling numbers,
// source tags, credits, ledger data cards, lower thirds, freeze brackets.
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env } from '../common/lib.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env };

export let SW = 1080, SH = 1920;
export function setScreen(w, h) { SW = w; SH = h; }
export const BAND = 1560;                       // the footage band: y 0..1560 (below it: the caption deck)
export const C = { yellow: '#FFC21A', red: '#FF4A3D', ivory: '#F7F5EF', ink: '#0E0E0C', grey: '#8D8B83', dim: '#5E5C55', paper: '#151512' };
const k = () => SW / 1080;
const F = (w, px) => `${w} ${px * k()}px Inter`;

// start a frame: clear the canvas (the footage plate shows through) and lay the gradients that make type readable
export function begin(ctx, t) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, SW, SH); ctx.globalAlpha = 1;
  const s = k(), g = ctx.createLinearGradient(0, BAND * s - 520 * s, 0, BAND * s);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,.84)'); ctx.fillStyle = g; ctx.fillRect(0, BAND * s - 520 * s, SW, 520 * s);
  ctx.fillStyle = '#0b0b0a'; ctx.fillRect(0, BAND * s, SW, SH - BAND * s);
  const tg = ctx.createLinearGradient(0, 0, 0, 220 * s); tg.addColorStop(0, 'rgba(0,0,0,.55)'); tg.addColorStop(1, 'rgba(0,0,0,0)'); ctx.fillStyle = tg; ctx.fillRect(0, 0, SW, 220 * s);
}

// —— the caption: the line, slammed in chunks; `cap` = 'Bees are dying | {faster} | than ever' (| = chunk, {} = keyword)
function parseCap(cap) { const cs = String(cap).split('|').map(c => c.trim()).filter(Boolean); return cs.map((c, i) => { const m = c.match(/^(.*?)\{(.+?)\}(.*)$/); const ps = m ? [{ s: m[1], key: false }, { s: m[2], key: true }, { s: m[3], key: false }].filter(p => p.s) : [{ s: c, key: false }]; if (i < cs.length - 1) ps.push({ s: ' ', key: false }); return ps; }); }
// layout: chunks flow left to right over up to 3 rows in the deck (x 64..1016), size shrinks to fit
export function caption(ctx, t, cap, t0, t1, o = {}) {
  if (t < t0 - .01 || t >= t1) return;
  const s = k(), chunks = parseCap(cap), gap = o.gap ?? .14;
  let px = o.size ?? 92, rows;
  const layout = () => {
    ctx.font = F(900, px); rows = [[]]; let x = 0;
    for (let ci = 0; ci < chunks.length; ci++) for (const p of chunks[ci]) for (const [wi, word] of p.s.split(/(\s+)/).filter(Boolean).entries()) {
      const w = ctx.measureText(word).width;
      if (x + w > 952 * s && x > 0 && word.trim()) { rows.push([]); x = 0; }
      if (!word.trim() && x === 0) continue;
      rows[rows.length - 1].push({ word, w, key: p.key, ci, x }); x += w;
    }
  };
  for (let i = 0; i < 8; i++) { layout(); if (rows.length <= 3) break; px *= .88; }
  const lh = px * 1.12 * s, y0 = (BAND + 70) * s + (3 - rows.length) * lh * .5;
  const out = 1 - ss(seg(t, t1 - .12, t1));
  ctx.save(); ctx.textBaseline = 'middle'; ctx.font = F(900, px);
  rows.forEach((row, ri) => {
    const y = y0 + ri * lh + lh / 2;
    // keyword blocks behind their words
    const keyRuns = [];
    for (const it of row) { if (!it.key) continue; const last = keyRuns[keyRuns.length - 1]; if (last && last.ci === it.ci && Math.abs(last.x1 - it.x) < 1) last.x1 = it.x + it.w; else keyRuns.push({ ci: it.ci, x0: it.x, x1: it.x + it.w }); }
    for (const r of keyRuns) {
      const ta = t0 + r.ci * gap, u = ss(seg(t, ta + .04, ta + .16)); if (u <= 0) continue;
      ctx.globalAlpha = out; ctx.fillStyle = C.yellow; ctx.fillRect(64 * s + r.x0 - 12 * s, y - px * .58 * s, (r.x1 - r.x0 + 24 * s) * u, px * 1.1 * s);
    }
    for (const it of row) {
      const ta = t0 + it.ci * gap; if (t < ta) continue;
      const u = seg(t, ta, ta + .13), sc = lerp(1.3, 1, back(u, 1.6)), a = Math.min(1, (t - ta) / .04) * out;
      ctx.save(); ctx.globalAlpha = a; ctx.translate(64 * s + it.x, y); ctx.scale(sc, sc);
      if (!it.key) { ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 20 * s; }
      ctx.fillStyle = it.key && t >= ta + .1 ? C.ink : C.ivory; ctx.fillText(it.word, 0, 0); ctx.restore();
    }
  });
  ctx.restore();
}
// captions for every line from T.lines[i].caption (or the line's text), crossing cuts; hold ≥ 1.8 s
export function captions(T, o = {}) {
  const list = T.lines.filter(L => !L.nocap).map(L => ({ t0: L.start - .05, t1: L.end + .35, cap: L.caption || L.text }));
  for (let i = 0; i < list.length - 1; i++) list[i].t1 = Math.min(Math.max(list[i].t1, list[i].t0 + 1.8), list[i + 1].t0 - .02);
  return { list, draw(ctx, t) { for (const c of list) caption(ctx, t, c.cap, c.t0, c.t1, o); } };
}

// —— numbers ——
// a number rolling from `from` to `to` between t0 and t0 + d (ease-out), formatted with decimals and separators
export function roll(t, t0, to, { from = 0, d = .45, dec = 0 } = {}) { const v = lerp(from, to, eo(seg(t, t0, t0 + d))); return v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }); }
// the frame-4 hook: a kicker line, then a giant number in a yellow block rolling to its value, then the unit + subject
export function hook(ctx, t, { t0 = .1, t1 = 3, kicker = '', value = 0, dec = 0, prefix = '', suffix = '', unit = '', y = .38 } = {}) {
  if (t < t0 || t >= t1) return;
  const s = k(), out = 1 - ss(seg(t, t1 - .15, t1)), cy = SH * y;
  ctx.save(); ctx.globalAlpha = out; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
  if (kicker) { ctx.font = F(700, 44); ctx.fillStyle = C.ivory; ctx.shadowColor = 'rgba(0,0,0,.7)'; ctx.shadowBlur = 16 * s; ctx.fillText(kicker.toUpperCase(), 64 * s, cy - 150 * s); ctx.shadowBlur = 0; }
  const txt = prefix + roll(t, t0 + .05, value, { dec }) + suffix, fin = prefix + roll(1e9, 0, value, { dec }) + suffix;
  ctx.font = F(800, 210); const w = ctx.measureText(fin).width + 60 * s, u = eo(seg(t, t0, t0 + .15));
  ctx.fillStyle = C.yellow; ctx.fillRect(40 * s, cy - 120 * s, w * u, 240 * s);
  ctx.fillStyle = C.ink; ctx.fillText(txt, 70 * s, cy + 8 * s);
  if (unit) { const a = ss(seg(t, t0 + .45, t0 + .7)); ctx.globalAlpha = out * a; ctx.font = F(800, 64); ctx.fillStyle = C.ivory; ctx.shadowColor = 'rgba(0,0,0,.7)'; ctx.shadowBlur = 16 * s; ctx.fillText(unit, 64 * s, cy + 190 * s); }
  ctx.restore();
}
// a big stat over footage (no block): value + label, colour turns when it arrives
export function stat(ctx, t, { t0, t1, value, dec = 0, prefix = '', suffix = '', label = '', x = .06, y = .3, color = C.yellow, size = 150 } = {}) {
  if (t < t0 || t >= t1) return; const s = k(), out = 1 - ss(seg(t, t1 - .15, t1)), done = t > t0 + .5;
  ctx.save(); ctx.globalAlpha = out * ss(seg(t, t0, t0 + .08)); ctx.textBaseline = 'alphabetic'; ctx.shadowColor = 'rgba(0,0,0,.7)'; ctx.shadowBlur = 18 * s;
  ctx.font = F(800, size); ctx.fillStyle = done ? color : C.ivory; ctx.fillText(prefix + roll(t, t0, value, { dec }) + suffix, SW * x, SH * y);
  if (label) { ctx.font = F(600, 40); ctx.fillStyle = C.ivory; ctx.fillText(label, SW * x + 4 * s, SH * y + 62 * s); }
  ctx.restore();
}

// —— chrome ——
// the channel bug, top left: a yellow block with a fictional channel name + the topic in small caps
export function bug(ctx, name, topic = '', a = 1) {
  const s = k(); ctx.save(); ctx.globalAlpha = a; ctx.textBaseline = 'middle';
  ctx.font = F(900, 34); const w = ctx.measureText(name.toUpperCase()).width + 36 * s;
  ctx.fillStyle = C.yellow; ctx.fillRect(48 * s, 64 * s, w, 56 * s); ctx.fillStyle = C.ink; ctx.fillText(name.toUpperCase(), 66 * s, 93 * s);
  if (topic) { ctx.font = F(700, 26); ctx.fillStyle = C.ivory; ctx.shadowColor = 'rgba(0,0,0,.7)'; ctx.shadowBlur = 10 * s; ctx.fillText(topic.toUpperCase(), 48 * s + w + 18 * s, 93 * s); }
  ctx.restore();
}
// the source tag under the bug: slides in 0.2 s; show it in every shot with a figure
export function source(ctx, t, text, t0, t1) {
  if (t < t0 || t >= t1) return; const s = k(), u = eo(seg(t, t0, t0 + .2)), out = 1 - ss(seg(t, t1 - .15, t1));
  ctx.save(); ctx.globalAlpha = out; ctx.textBaseline = 'middle'; ctx.font = F(800, 24);
  const lw = ctx.measureText('SOURCE').width + 24 * s; ctx.font = F(600, 26); const tw = ctx.measureText(text).width + 28 * s;
  const x = lerp(-lw - tw, 48 * s, u);
  ctx.fillStyle = C.ivory; ctx.fillRect(x, 136 * s, lw, 44 * s); ctx.fillStyle = 'rgba(14,14,12,.88)'; ctx.fillRect(x + lw, 136 * s, tw, 44 * s);
  ctx.font = F(800, 24); ctx.fillStyle = C.ink; ctx.fillText('SOURCE', x + 12 * s, 158 * s);
  ctx.font = F(600, 26); ctx.fillStyle = C.ivory; ctx.fillText(text, x + lw + 14 * s, 158 * s);
  ctx.restore();
}
// footage credits, top right, from the server's shot list (T.shots[i] = { t0, t1, credit }): call every frame
export function credits(ctx, t, shots) {
  const sh = (shots || []).find(x => t >= x.t0 && t < x.t1); if (!sh || !sh.credit) return; const s = k();
  ctx.save(); ctx.font = F(500, 21); ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
  const w = ctx.measureText(sh.credit).width + 24 * s; ctx.fillStyle = 'rgba(0,0,0,.5)'; ctx.fillRect(SW - 40 * s - w, 72 * s, w, 38 * s);
  ctx.fillStyle = 'rgba(247,245,239,.9)'; ctx.fillText(sh.credit, SW - 52 * s, 91 * s); ctx.restore();
}
// a lower third (a place, a date, a speaker) at the bottom of the footage band
export function lowerThird(ctx, t, label, line, t0, t1) {
  if (t < t0 || t >= t1) return; const s = k(), u = eo(seg(t, t0, t0 + .25)), out = 1 - ss(seg(t, t1 - .15, t1));
  ctx.save(); ctx.globalAlpha = out; ctx.textBaseline = 'middle'; ctx.font = F(800, 40); const w = ctx.measureText(label.toUpperCase()).width + 40 * s;
  const y = (BAND - 230) * s; ctx.fillStyle = C.yellow; ctx.fillRect(48 * s, y, w * u, 64 * s);
  if (u > .6) { ctx.fillStyle = C.ink; ctx.fillText(label.toUpperCase(), 68 * s, y + 33 * s); }
  if (line) { ctx.globalAlpha = out * ss(seg(t, t0 + .2, t0 + .4)); ctx.font = F(500, 32); ctx.fillStyle = C.ivory; ctx.shadowColor = 'rgba(0,0,0,.8)'; ctx.shadowBlur = 12 * s; ctx.fillText(line, 52 * s, y + 104 * s); }
  ctx.restore();
}
// a freeze moment (the plate must freeze too: shot option freeze): white flash, corner brackets closing on a box, a pause chip
export function freeze(ctx, t, t0, t1, box = [.2, .2, .6, .5]) {
  if (t < t0 || t >= t1) return; const s = k(), out = 1 - ss(seg(t, t1 - .15, t1));
  if (t < t0 + .14) { ctx.save(); ctx.globalAlpha = 1 - (t - t0) / .14; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, SW, BAND * s); ctx.restore(); }
  const u = eo(seg(t, t0 + .05, t0 + .4)), [bx, by, bw, bh] = box, x0 = lerp(0, bx * SW, u), y0 = lerp(0, by * BAND * s, u), x1 = lerp(SW, (bx + bw) * SW, u), y1 = lerp(BAND * s, (by + bh) * BAND * s, u), L = 70 * s;
  ctx.save(); ctx.globalAlpha = out; ctx.strokeStyle = C.yellow; ctx.lineWidth = 8 * s; ctx.beginPath();
  for (const [x, y, dx, dy] of [[x0, y0, 1, 1], [x1, y0, -1, 1], [x0, y1, 1, -1], [x1, y1, -1, -1]]) { ctx.moveTo(x + dx * L, y); ctx.lineTo(x, y); ctx.lineTo(x, y + dy * L); }
  ctx.stroke();
  ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(SW - 190 * s, 140 * s, 150 * s, 48 * s); ctx.fillStyle = C.ivory; ctx.fillRect(SW - 172 * s, 152 * s, 8 * s, 24 * s); ctx.fillRect(SW - 158 * s, 152 * s, 8 * s, 24 * s);
  ctx.font = F(700, 24); ctx.textBaseline = 'middle'; ctx.fillText('PAUSED', SW - 140 * s, 165 * s);
  ctx.restore();
}

// —— the ledger data card: covers the footage band, slides in from the right with speed streaks ——
// draw(ctx, u, box) draws the content: u = 0..1 progress through the card's time, box = { x, y, w, h } in pixels
export function ledger(ctx, t, t0, t1, { title = '', sub = '', src = '' } = {}, draw = null) {
  if (t < t0 || t >= t1) return; const s = k(), u = eo(seg(t, t0, t0 + .18)), out = 1 - ss(seg(t, t1 - .12, t1));
  const x = lerp(SW, 0, u), H = BAND * s;
  ctx.save(); ctx.globalAlpha = out; ctx.translate(x, 0);
  ctx.fillStyle = C.paper; ctx.fillRect(0, 0, SW, H);
  ctx.strokeStyle = 'rgba(255,255,255,.045)'; ctx.lineWidth = 1 * s; for (let y = 54 * s; y < H; y += 54 * s) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(SW, y); ctx.stroke(); }
  ctx.strokeStyle = 'rgba(255,74,61,.55)'; ctx.lineWidth = 2 * s; for (const mx of [44, 52]) { ctx.beginPath(); ctx.moveTo(mx * s, 0); ctx.lineTo(mx * s, H); ctx.stroke(); }
  if (u < 1) { ctx.fillStyle = 'rgba(255,194,26,.35)'; for (let i = 0; i < 6; i++) ctx.fillRect(-200 * s * (1 - u) - i * 40 * s, (300 + i * 170) * s, 160 * s * (1 - u), 6 * s); }
  const push = 1 + .03 * seg(t, t0, t1); ctx.translate(SW / 2, H / 2); ctx.scale(push, push); ctx.translate(-SW / 2, -H / 2);
  ctx.textBaseline = 'alphabetic';
  if (title) { ctx.font = F(900, 64); ctx.fillStyle = C.ivory; ctx.fillText(title, 80 * s, 300 * s); }
  if (sub) { ctx.font = F(500, 30); ctx.fillStyle = C.grey; ctx.fillText(sub, 82 * s, 350 * s); }
  if (draw) draw(ctx, seg(t, t0 + .15, t1 - .2), { x: 80 * s, y: 420 * s, w: SW - 140 * s, h: H - 560 * s });
  if (src) { ctx.font = F(500, 24); ctx.fillStyle = C.grey; ctx.fillText('Source: ' + src, 82 * s, H - 70 * s); }
  ctx.restore();
}
// horizontal bars inside a card: items = [{ label, value, hi (the point: yellow) , bad (red) }], max, unit
export function bars(ctx, u, box, items, { max = null, unit = '', dec = 0 } = {}) {
  const s = k(), m = max ?? Math.max(...items.map(i => i.value)), n = items.length, rh = Math.min(150 * s, box.h / n);
  items.forEach((it, i) => {
    const a = eo(clamp((u * (1 + n * .25) - i * .25) / (i === 0 ? 1.2 : 1))), y = box.y + i * rh, w = (box.w - 40 * s) * it.value / m * a;
    ctx.font = F(600, 32); ctx.fillStyle = it.hi ? C.yellow : C.ivory; ctx.fillText(it.label, box.x, y + 38 * s);
    ctx.fillStyle = it.hi ? C.yellow : it.bad ? C.red : C.dim; ctx.fillRect(box.x, y + 56 * s, Math.max(4 * s, w), 50 * s);
    ctx.font = F(800, 40); ctx.fillStyle = it.hi ? C.yellow : C.ivory; ctx.fillText((it.value * a).toLocaleString('en-US', { maximumFractionDigits: dec, minimumFractionDigits: dec }) + unit, box.x + Math.max(4 * s, w) + 16 * s, y + 96 * s);
  });
}
// a line chart inside a card: pts = [[label, value], ...]; key = index of the point that matters (ring + block label)
export function lineChart(ctx, u, box, pts, { key = pts.length - 1, keyLabel = '', min = null, max = null, unit = '' } = {}) {
  const s = k(), vs = pts.map(p => p[1]), lo = min ?? Math.min(...vs) * .9, hi = max ?? Math.max(...vs) * 1.08;
  const X = i => box.x + 30 * s + i / (pts.length - 1) * (box.w - 80 * s), Y = v => box.y + box.h - 80 * s - (v - lo) / (hi - lo) * (box.h - 160 * s);
  ctx.strokeStyle = 'rgba(255,255,255,.12)'; ctx.lineWidth = 2 * s; ctx.beginPath(); ctx.moveTo(box.x, box.y + box.h - 80 * s); ctx.lineTo(box.x + box.w, box.y + box.h - 80 * s); ctx.stroke();
  const n = (pts.length - 1) * eio(clamp(u * 1.3));
  ctx.strokeStyle = C.ivory; ctx.lineWidth = 6 * s; ctx.lineJoin = 'round'; ctx.beginPath();
  for (let i = 0; i <= Math.floor(n); i++) (i ? ctx.lineTo : ctx.moveTo).call(ctx, X(i), Y(vs[i]));
  if (n % 1 > 0) { const i = Math.floor(n), f = n % 1; ctx.lineTo(lerp(X(i), X(i + 1), f), lerp(Y(vs[i]), Y(vs[i + 1]), f)); }
  ctx.stroke();
  ctx.font = F(500, 26); ctx.fillStyle = C.grey; ctx.textAlign = 'center';
  pts.forEach((p, i) => { if (i === 0 || i === pts.length - 1 || i === key) ctx.fillText(p[0], X(i), box.y + box.h - 36 * s); });
  ctx.textAlign = 'left';
  if (n >= key) {
    const a = seg(u * 1.3, key / (pts.length - 1), key / (pts.length - 1) + .3), r = 14 * s + 40 * s * eo(seg(a, 0, .7));
    ctx.fillStyle = C.yellow; ctx.beginPath(); ctx.arc(X(key), Y(vs[key]), 13 * s, 0, TAU); ctx.fill();
    ctx.globalAlpha = 1 - seg(a, 0, .7); ctx.strokeStyle = C.yellow; ctx.lineWidth = 4 * s; ctx.beginPath(); ctx.arc(X(key), Y(vs[key]), r, 0, TAU); ctx.stroke(); ctx.globalAlpha = 1;
    const lab = keyLabel || (vs[key].toLocaleString('en-US') + unit); ctx.font = F(800, 40); const w = ctx.measureText(lab).width + 28 * s;
    const lx = Math.min(X(key) - w / 2, box.x + box.w - w), ly = Y(vs[key]) - 90 * s;
    ctx.fillStyle = C.yellow; ctx.fillRect(lx, ly, w, 58 * s); ctx.fillStyle = C.ink; ctx.fillText(lab, lx + 14 * s, ly + 43 * s);
  }
}
// proportion by darkness: a yellow line sweeps across the footage band to pct; what it passed goes dark
export function proportion(ctx, t, t0, t1, pct, label = '') {
  if (t < t0 || t >= t1) return; const s = k(), u = eio(seg(t, t0, t0 + .9)) * pct / 100, out = 1 - ss(seg(t, t1 - .15, t1)), H = BAND * s;
  ctx.save(); ctx.globalAlpha = out; ctx.fillStyle = 'rgba(10,10,10,.72)'; ctx.fillRect(0, 0, SW * u, H);
  ctx.fillStyle = C.yellow; ctx.fillRect(SW * u - 4 * s, 0, 8 * s, H);
  if (u >= pct / 100 - .001) { ctx.font = F(800, 140); ctx.fillStyle = C.yellow; ctx.textBaseline = 'alphabetic'; ctx.textAlign = SW * u > SW * .5 ? 'right' : 'left'; const x = SW * u > SW * .5 ? SW * u - 30 * s : SW * u + 30 * s; ctx.fillText(Math.round(pct) + '%', x, H * .45); if (label) { ctx.font = F(600, 38); ctx.fillStyle = C.ivory; ctx.fillText(label, x, H * .45 + 60 * s); } }
  ctx.restore();
}

// sound events: [{ t, type, v }] with type in slam (a caption chunk), rattle (a counter rolling; d = length), whoosh
// (a card sliding in), squeak (a highlight), shutter (a freeze), stamp (a big number), pop (a label), riser (into a turn; d)
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
// every caption chunk's slam, for the cues: K.slams(caps.list)
export function slams(list, gap = .14) { const out = []; for (const c of list) parseCap(c.cap).forEach((_, i) => out.push({ t: c.t0 + i * gap, type: 'slam', v: i ? .6 : 1 })); return out; }
