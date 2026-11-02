// Sports Telestrator kit for the Animave Style Studio (window.TL): the TV analysis segment drawn over the user's own
// match clip, after the lemo-opuscar "telestrator" style (github.com/lemomo-ai/lemo-opuscar, MIT), laid out for 9:16.
// The clip is a video PLATE under the canvas (played, slowed, rewound and frozen by the server from the script's edit),
// shown in a 4:5 window (y 250..1600). The film draws on a transparent canvas in SCREEN pixels.
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env } from '../common/lib.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, TAU, env };

export let SW = 1080, SH = 1920;
export function setScreen(w, h) { SW = w; SH = h; }
export const BAND = { y: 250, h: 1350 };
export const C = { us: '#FFD400', them: '#3FD8FF', space: '#FF3B30', chalk: '#F4F1E8', board: '#0C1411', card: 'rgba(8,12,14,0.9)' };
const BC = (w, px, it = false) => `${it ? 'italic ' : ''}${w} ${px}px BarlowCondensed`;
const MONO = px => `500 ${px}px IBMPlexMono`;

// the shot at t (from T.shots) and where the clip is: { shot, mode: 'live'|'slow'|'rewind'|'freeze'|'card', src: seconds in the clip }
export function at(shots, t) {
  const s = (shots || []).find(x => t >= x.t0 && t < x.t1); if (!s) return { shot: null, mode: 'card', src: 0 };
  const sp = s.speed || 1, frozen = s.freeze != null && t >= s.freeze;
  const run = (frozen ? s.freeze : t) - s.t0;
  const src = s.reverse ? (s.src || 0) + Math.max(0, (s.t1 - s.t0) * sp - run * sp) : (s.src || 0) + run * sp;
  const mode = s.kind !== 'video' ? 'card' : frozen ? 'freeze' : s.reverse ? 'rewind' : sp < .95 ? 'slow' : 'live';
  return { shot: s, mode, src, frozen, t0f: s.freeze };
}

// start a frame: clear (the clip shows through), the dark top and bottom decks, plus the automatic moments:
// a white flash when a freeze starts, the rewind look while the clip runs backwards
export function begin(ctx, t, shots) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, SW, SH); ctx.globalAlpha = 1;
  ctx.fillStyle = '#07090a'; ctx.fillRect(0, 0, SW, BAND.y); ctx.fillRect(0, BAND.y + BAND.h, SW, SH - BAND.y - BAND.h);
  const a = at(shots, t);
  if (a.mode === 'freeze') {
    const u = t - a.t0f;
    if (u < .12) { ctx.fillStyle = `rgba(255,255,255,${.55 * (1 - u / .12)})`; ctx.fillRect(0, BAND.y, SW, BAND.h); }
    const v = ctx.createRadialGradient(SW / 2, BAND.y + BAND.h / 2, BAND.h * .3, SW / 2, BAND.y + BAND.h / 2, BAND.h * .75);
    v.addColorStop(0, 'rgba(0,10,20,0)'); v.addColorStop(1, `rgba(0,10,20,${.45 * ss(seg(u, 0, .3))})`); ctx.fillStyle = v; ctx.fillRect(0, BAND.y, SW, BAND.h);
  }
  if (a.mode === 'rewind') {
    ctx.save(); ctx.fillStyle = 'rgba(255,255,255,.55)';
    for (let i = 0; i < 4; i++) { const y = BAND.y + ((hash(Math.floor(t * 24) + i * 7) * BAND.h) | 0); ctx.fillRect(0, y, SW, 6 + i * 2); }
    ctx.font = BC(800, 120, true); ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 20;
    ctx.fillText('◀◀ REWIND', SW / 2, BAND.y + BAND.h / 2); ctx.restore();
  }
  return a;
}

// the show bug, top: show name on a yellow block + the mode line (LIVE red dot / ANALYSIS yellow / REPLAY cyan)
export function bug(ctx, t, shots, name = 'THE BOARD', { replay = false } = {}) {
  const a = at(shots, t), mode = a.mode === 'live' && !replay ? ['LIVE', '#FF3B30'] : a.mode === 'live' ? ['REPLAY', C.them] : ['ANALYSIS', C.us];
  ctx.save(); ctx.textBaseline = 'middle'; ctx.font = BC(800, 52, true); const w = ctx.measureText(name.toUpperCase()).width + 44;
  ctx.fillStyle = C.us; ctx.fillRect(40, 70, w, 76); ctx.fillStyle = '#080C0E'; ctx.fillText(name.toUpperCase(), 62, 110);
  ctx.fillStyle = '#080C0E'; ctx.fillRect(40 + w, 70, 230, 76);
  if (mode[0] === 'LIVE') { ctx.fillStyle = mode[1]; ctx.beginPath(); ctx.arc(40 + w + 30, 108, 10, 0, TAU); ctx.fill(); }
  ctx.font = BC(800, 40); ctx.fillStyle = mode[1]; ctx.fillText(mode[0], 40 + w + (mode[0] === 'LIVE' ? 52 : 24), 110);
  ctx.restore();
}
// the source clock (clip seconds + frame), hidden in live play: ❚❚ 04.20s F126 / ▶ ½ / ◀◀
export function clock(ctx, t, shots, fps = 30) {
  const a = at(shots, t); if (a.mode === 'live' || a.mode === 'card') return;
  const sym = a.mode === 'freeze' ? '❚❚' : a.mode === 'rewind' ? '◀◀' : '▶ ½';
  const txt = `${sym}  ${a.src.toFixed(2).padStart(5, '0')}s  F${Math.round(a.src * fps)}`;
  ctx.save(); ctx.font = MONO(34); ctx.textBaseline = 'middle'; const w = ctx.measureText(txt).width + 36;
  ctx.fillStyle = C.card; ctx.fillRect(SW - 40 - w, 176, w, 58); ctx.fillStyle = C.chalk; ctx.fillText(txt, SW - 40 - w + 18, 206); ctx.restore();
}
// the score bar, bottom of the window: HOME n – n AWAY + minute; goals = [[t, side 'home'|'away']] flip it on the frame
export function scoreBar(ctx, t, { home = 'HOME', away = 'AWAY', score = [0, 0], minute = '', goals = [] } = {}) {
  const sc = score.slice(); let flash = 0;
  for (const [gt, side] of goals) if (t >= gt) { sc[side === 'home' ? 0 : 1]++; flash = Math.max(flash, 1 - (t - gt) / .5); }
  const y = BAND.y + BAND.h - 96; ctx.save(); ctx.textBaseline = 'middle';
  ctx.fillStyle = '#080C0E'; ctx.fillRect(SW - 520, y, 480, 70);
  ctx.fillStyle = C.us; ctx.fillRect(SW - 520, y, 8, 70);
  ctx.font = BC(800, 40, true); ctx.fillStyle = C.chalk; ctx.textAlign = 'left'; ctx.fillText(home.toUpperCase(), SW - 494, y + 36);
  ctx.textAlign = 'center'; ctx.fillStyle = flash > 0 ? C.us : C.chalk; ctx.font = BC(800, 50, true); ctx.fillText(`${sc[0]} – ${sc[1]}`, SW - 300, y + 36);
  ctx.textAlign = 'right'; ctx.font = BC(800, 40, true); ctx.fillStyle = C.chalk; ctx.fillText(away.toUpperCase(), SW - 150, y + 36);
  if (minute) { ctx.fillStyle = C.us; ctx.font = BC(800, 34, true); ctx.fillText(minute, SW - 56, y + 36); }
  if (flash > 0) { ctx.globalAlpha = flash * .5; ctx.fillStyle = C.us; ctx.fillRect(SW - 520, y, 480, 70); }
  ctx.restore();
}

// —— drawings on the picture (screen pixels; each draws itself in from t0 and fades out at t1) ——
const fade = (t, t0, t1) => Math.min(ss(seg(t, t0, t0 + .2)), t1 == null ? 1 : 1 - ss(seg(t, t1 - .2, t1)));
function wob(pts, k = 3) { return pts.map(([x, y], i) => [x + (hash(i * 3.1 + x) - .5) * k, y + (hash(i * 7.7 + y) - .5) * k]); }
// a marker line through points (drawn along its length over d seconds), arrow head at the end; dash for intended paths
export function arrow(ctx, t, t0, t1, pts, { color = C.us, w = 9, dash = false, head = true, d = .5 } = {}) {
  if (t < t0 || (t1 != null && t >= t1)) return; const a = fade(t, t0, t1), u = eio(seg(t, t0, t0 + d));
  const P = wob(pts.length === 2 ? [pts[0], [(pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2 - Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]) * .08], pts[1]] : pts);
  const seglen = []; let tot = 0; for (let i = 1; i < P.length; i++) { const l = Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]); seglen.push(l); tot += l; }
  const path = [P[0]]; let left = tot * u;
  for (let i = 1; i < P.length && left > 0; i++) { const l = seglen[i - 1], f = Math.min(1, left / l); path.push([lerp(P[i - 1][0], P[i][0], f), lerp(P[i - 1][1], P[i][1], f)]); left -= l; }
  const stroke = (lw, col, blur = 0) => { ctx.lineWidth = lw; ctx.strokeStyle = col; ctx.shadowColor = col; ctx.shadowBlur = blur; ctx.beginPath(); path.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.stroke(); };
  ctx.save(); ctx.globalAlpha = a; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; if (dash) ctx.setLineDash([w * 2.4, w * 1.8]);
  stroke(w + 6, 'rgba(0,0,0,.55)'); stroke(w, color, 18); ctx.shadowBlur = 0; stroke(w * .28, 'rgba(255,255,255,.8)');
  if (head && u > .9) {
    const [x, y] = path[path.length - 1], [px, py] = path[Math.max(0, path.length - 2)], ang = Math.atan2(y - py, x - px), s = w * 3.2 * eo(seg(u, .9, 1));
    ctx.setLineDash([]); ctx.fillStyle = color; ctx.strokeStyle = 'rgba(0,0,0,.55)'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(x + Math.cos(ang) * s * .4, y + Math.sin(ang) * s * .4); ctx.lineTo(x + Math.cos(ang + 2.5) * s, y + Math.sin(ang + 2.5) * s); ctx.lineTo(x + Math.cos(ang - 2.5) * s, y + Math.sin(ang - 2.5) * s); ctx.closePath(); ctx.stroke(); ctx.fill();
  }
  ctx.restore();
}
// a ring under a player's feet (perspective ellipse), drawn clockwise, outer dashed ring turning
export function ring(ctx, t, t0, t1, [x, y], { r = 46, color = C.us } = {}) {
  if (t < t0 || (t1 != null && t >= t1)) return; const a = fade(t, t0, t1), u = eo(seg(t, t0, t0 + .35)), ry = r * .36;
  ctx.save(); ctx.globalAlpha = a; ctx.lineCap = 'round';
  ctx.strokeStyle = 'rgba(0,0,0,.5)'; ctx.lineWidth = 10; ctx.beginPath(); ctx.ellipse(x, y, r, ry, 0, -Math.PI / 2, -Math.PI / 2 + TAU * u); ctx.stroke();
  ctx.strokeStyle = color; ctx.lineWidth = 6; ctx.shadowColor = color; ctx.shadowBlur = 14; ctx.beginPath(); ctx.ellipse(x, y, r, ry, 0, -Math.PI / 2, -Math.PI / 2 + TAU * u); ctx.stroke();
  ctx.setLineDash([10, 10]); ctx.lineDashOffset = -t * 60; ctx.lineWidth = 3; ctx.globalAlpha = a * .8; ctx.beginPath(); ctx.ellipse(x, y, r * 1.35, ry * 1.35, 0, 0, TAU); ctx.stroke();
  ctx.restore();
}
// a link line between players (passing lane, marking), thin, with dots at both ends
export function link(ctx, t, t0, t1, a, b, { color = C.them, dash = true } = {}) {
  if (t < t0 || (t1 != null && t >= t1)) return; const al = fade(t, t0, t1), u = eio(seg(t, t0, t0 + .35));
  ctx.save(); ctx.globalAlpha = al; ctx.strokeStyle = color; ctx.lineWidth = 4; if (dash) ctx.setLineDash([12, 8]);
  ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(lerp(a[0], b[0], u), lerp(a[1], b[1], u)); ctx.stroke();
  ctx.setLineDash([]); ctx.fillStyle = color; for (const p of [a, u > .95 ? b : null]) if (p) { ctx.beginPath(); ctx.arc(p[0], p[1], 7, 0, TAU); ctx.fill(); }
  ctx.restore();
}
// the space nobody covered: a red patch (polygon of screen points) with a dashed edge
export function space(ctx, t, t0, t1, pts, { color = C.space } = {}) {
  if (t < t0 || (t1 != null && t >= t1)) return; const a = fade(t, t0, t1) * ss(seg(t, t0, t0 + .35));
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = color + '5c'; ctx.beginPath(); pts.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fill();
  ctx.setLineDash([14, 10]); ctx.strokeStyle = color; ctx.lineWidth = 4; ctx.stroke(); ctx.restore();
}
// a spotlight: everything outside the ellipse darkens
export function spotlight(ctx, t, t0, t1, [cx, cy, rx, ry]) {
  if (t < t0 || (t1 != null && t >= t1)) return; const a = fade(t, t0, t1) * .58;
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.rect(0, BAND.y, SW, BAND.h); ctx.ellipse(cx, cy, rx, ry, 0, 0, TAU); ctx.fill('evenodd'); ctx.restore();
}
// a label card: the finding in big condensed type + a small spaced line, the left bar in the colour of what it names
export function label(ctx, t, t0, t1, [x, y], text, sub = '', { color = C.us, size = 54 } = {}) {
  if (t < t0 || (t1 != null && t >= t1)) return; const a = fade(t, t0, t1), u = eo(seg(t, t0, t0 + .25));
  ctx.save(); ctx.globalAlpha = a; ctx.textBaseline = 'middle'; ctx.font = BC(800, size, true); const w1 = ctx.measureText(text.toUpperCase()).width;
  ctx.font = BC(600, 26); const w2 = sub ? ctx.measureText(sub.toUpperCase()).width + sub.length * 2 : 0; const w = Math.max(w1, w2) + 52, h = size * 1.15 + (sub ? 40 : 18);
  const X = Math.min(Math.max(20, x), SW - 20 - w);
  ctx.fillStyle = C.card; ctx.fillRect(X, y, w * u, h); ctx.fillStyle = color; ctx.fillRect(X, y, 9, h);
  if (u > .7) { ctx.font = BC(800, size, true); ctx.fillStyle = C.chalk; ctx.fillText(text.toUpperCase(), X + 28, y + size * .62);
    if (sub) { ctx.font = BC(600, 26); ctx.fillStyle = color; if ('letterSpacing' in ctx) ctx.letterSpacing = '2px'; ctx.fillText(sub.toUpperCase(), X + 30, y + size * 1.15 + 14); } }
  ctx.restore();
}
// a stopwatch on frames: runs from t0, stops at t1 and turns yellow; shows the measured seconds
export function stopwatch(ctx, t, t0, t1, tEnd, [x, y] = [60, 1430], { label: lab = 'TIME ON THE BALL' } = {}) {
  if (t < t0 || t >= tEnd) return; const v = Math.max(0, Math.min(t, t1) - t0), done = t >= t1;
  ctx.save(); ctx.globalAlpha = fade(t, t0, tEnd); ctx.fillStyle = C.card; ctx.fillRect(x, y, 330, 120);
  ctx.font = BC(600, 26); ctx.fillStyle = C.chalk; ctx.textBaseline = 'middle'; ctx.fillText(lab, x + 22, y + 28);
  ctx.font = BC(800, 76, true); ctx.fillStyle = done ? C.us : C.chalk; ctx.fillText(v.toFixed(2) + 's', x + 20, y + 80); ctx.restore();
}
// a stamp card (once per film): drops from 1.7x with overshoot, slightly rotated
export function stamp(ctx, t, t0, t1, text, [x, y] = [540, 900], { color = C.us } = {}) {
  if (t < t0 || t >= t1) return; const s = lerp(1.7, 1, back(seg(t, t0, t0 + .3), 2.2)), a = fade(t, t0, t1);
  ctx.save(); ctx.globalAlpha = a; ctx.translate(x, y); ctx.rotate(-.06); ctx.scale(s, s); ctx.font = BC(800, 96, true);
  const w = ctx.measureText(text.toUpperCase()).width + 70; ctx.fillStyle = C.card; ctx.fillRect(-w / 2, -70, w, 140);
  ctx.strokeStyle = color; ctx.lineWidth = 7; ctx.strokeRect(-w / 2 + 10, -60, w - 20, 120); ctx.fillStyle = color; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text.toUpperCase(), 0, 6); ctx.restore();
}
// the packaging wipe between segments: a yellow slanted band crossing the window in 0.34 s, centred on tc
export function wipe(ctx, t, tc) {
  const u = seg(t, tc - .17, tc + .17); if (u <= 0 || u >= 1) return; const x = lerp(-700, SW + 700, eio(u));
  ctx.save(); ctx.beginPath(); ctx.rect(0, BAND.y, SW, BAND.h); ctx.clip(); ctx.translate(x, 0);
  ctx.fillStyle = '#080C0E'; ctx.beginPath(); ctx.moveTo(-460, BAND.y + BAND.h); ctx.lineTo(-140, BAND.y); ctx.lineTo(360, BAND.y); ctx.lineTo(40, BAND.y + BAND.h); ctx.fill();
  ctx.fillStyle = C.us; ctx.beginPath(); ctx.moveTo(-400, BAND.y + BAND.h); ctx.lineTo(-80, BAND.y); ctx.lineTo(300, BAND.y); ctx.lineTo(-20, BAND.y + BAND.h); ctx.fill(); ctx.restore();
}
// a board page (data card) covering the window: rows = [[label, value, note]], key = the index circled in red
export function board(ctx, t, t0, t1, title, rows, { key = -1 } = {}) {
  if (t < t0 || t >= t1) return; const a = fade(t, t0, t1);
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = C.board; ctx.fillRect(0, BAND.y, SW, BAND.h);
  ctx.strokeStyle = 'rgba(255,255,255,.05)'; ctx.lineWidth = 1; for (let x = 0; x < SW; x += 60) { ctx.beginPath(); ctx.moveTo(x, BAND.y); ctx.lineTo(x, BAND.y + BAND.h); ctx.stroke(); } for (let y = BAND.y; y < BAND.y + BAND.h; y += 60) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(SW, y); ctx.stroke(); }
  ctx.textBaseline = 'alphabetic'; ctx.font = BC(800, 84, true); ctx.fillStyle = C.chalk; ctx.fillText(title.toUpperCase(), 70, BAND.y + 150);
  rows.forEach(([lab, val, note], i) => {
    const y = BAND.y + 330 + i * 230, u = eo(seg(t, t0 + .2 + i * .25, t0 + .5 + i * .25)); if (u <= 0) return;
    ctx.save(); ctx.beginPath(); ctx.rect(0, y - 120, SW * u, 230); ctx.clip();
    ctx.font = BC(600, 44); ctx.fillStyle = C.chalk; ctx.fillText(lab.toUpperCase(), 70, y);
    if (note) { ctx.font = BC(600, 30); ctx.fillStyle = 'rgba(244,241,232,.55)'; ctx.fillText(note, 70, y + 46); }
    ctx.font = BC(800, 130, true); ctx.fillStyle = C.us; ctx.textAlign = 'right'; ctx.fillText(String(val), SW - 70, y + 30); ctx.textAlign = 'left';
    if (i === key) { ctx.strokeStyle = C.space; ctx.lineWidth = 7; ctx.beginPath(); ctx.ellipse(SW - 190, y - 10, 170, 95, -.05, 0, TAU * eo(seg(t, t0 + .9, t0 + 1.4))); ctx.stroke(); }
    ctx.restore();
  });
  ctx.restore();
}
// subtitles: a black bar with a yellow edge in the bottom deck
export function subtitles(T, o = {}) {
  const subs = [];
  for (const L of T.lines) {
    if (L.nocap || !L.words || !L.words.length) continue;
    const parts = L.text.split(/(?<=[,.;:!?…])\s+/).reduce((acc, p) => { const last = acc[acc.length - 1]; if (last != null && (last + ' ' + p).length <= (o.maxChars ?? 40)) acc[acc.length - 1] = last + ' ' + p; else acc.push(p); return acc; }, []);
    const ws = L.words, tot = parts.reduce((a, p) => a + p.length, 0); let c0 = 0;
    for (const p of parts) { const f0 = c0 / tot, f1 = (c0 + p.length) / tot; c0 += p.length; const ta = f => ws[Math.min(ws.length - 1, Math.floor(f * ws.length))].s; subs.push({ t0: (f0 === 0 ? ws[0].s : ta(f0)) - .08, t1: f1 >= .999 ? ws[ws.length - 1].e + .4 : ta(f1), text: p }); }
  }
  for (let i = 0; i < subs.length - 1; i++) subs[i].t1 = Math.min(Math.max(subs[i].t1, subs[i].t0 + 1.4), subs[i + 1].t0 - .04);
  return {
    subs,
    draw(ctx, t) {
      const s = subs.find(s => t >= s.t0 && t < s.t1); if (!s) return;
      ctx.save(); ctx.font = BC(600, 50); ctx.textBaseline = 'middle'; ctx.textAlign = 'center';
      let rows = [s.text]; if (ctx.measureText(s.text).width > SW - 120) { const w = s.text.split(' '), m = Math.ceil(w.length / 2); rows = [w.slice(0, m).join(' '), w.slice(m).join(' ')]; }
      const y = BAND.y + BAND.h + 40, h = rows.length * 60 + 36;
      ctx.fillStyle = 'rgba(0,0,0,.64)'; ctx.fillRect(40, y, SW - 80, h); ctx.fillStyle = C.us; ctx.fillRect(40, y, 6, h);
      ctx.fillStyle = C.chalk; rows.forEach((r, i) => ctx.fillText(r, SW / 2, y + 48 + i * 60)); ctx.restore();
    },
  };
}
// sound events: [{ t, type, v, d }] with type in squeak (a marker line; d), pop (a ring), tick (a label), whoosh (a wipe),
// shutter (a freeze: added for you by K.freezeCues), tape (a rewind; d), stopwatch (ticks; d), stamp, hit (a brass stab)
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
// the cues every freeze and rewind needs (shutter + hit on each freeze, tape on each rewind)
export function freezeCues(shots) { const out = []; for (const s of shots || []) { if (s.freeze != null) out.push({ t: s.freeze, type: 'shutter' }, { t: s.freeze, type: 'hit', v: .8 }); if (s.reverse) out.push({ t: s.t0, type: 'tape', d: Math.min(1.2, s.t1 - s.t0) }); } return out; }
