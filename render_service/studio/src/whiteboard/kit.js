// Whiteboard Explainer kit for the Animave Style Studio: the lemo-opuscar whiteboard engine (wb.js) plus the parts of its
// demo film that every film needs (subtitles, camera motion blur, sound events), adapted to any screen size and to our
// narration timing (T.lines[i].words = [{ w, s, e }] in absolute seconds). Exposed as window.WB.
import * as W from './wb.js';
import { clamp, lerp, mulberry } from '../common/lib.js';

export * from './wb.js';
export { clamp, lerp, mulberry };
export { seg, ss, eio, eo, ei, back, spring, env } from '../common/lib.js';

// subtitles split at clauses, ≤ 32 characters a row on a vertical frame, held ≥ 1.4 s, bottom 14 % of the frame
export function subtitles(T, o = {}) {
  const subs = [];
  for (const L of T.lines) {
    if (L.nocap || !L.words || !L.words.length) continue;
    const ws = L.words, cum = [0];
    ws.forEach(w => cum.push(cum[cum.length - 1] + String(w.w).length + 1));
    const tot = cum[cum.length - 1];
    const timeAt = f => { const c = f * tot; let i = 0; while (i < ws.length - 1 && cum[i + 1] <= c) i++; const u = clamp((c - cum[i]) / Math.max(1e-6, cum[i + 1] - cum[i])); return lerp(ws[i].s, ws[i].e, u); };
    const max = o.maxChars ?? 34;
    // clauses end at punctuation followed by a space (so 2.45 or 3:30 stay whole)
    const parts = (L.text.split(/(?<=[,.;:!?…])\s+/).map(p => p + ' ')).reduce((acc, p) => {
      const last = acc[acc.length - 1];
      if (last != null && ((last + p).trim().length <= max || ((last.trim().length < 16 || p.trim().length < 16) && (last + p).trim().length <= max * 1.9))) acc[acc.length - 1] += p; else acc.push(p);
      return acc;
    }, []);
    let c0 = 0;
    for (const p of parts) {
      const f0 = c0 / L.text.length, f1 = (c0 + p.trimEnd().length) / L.text.length; c0 += p.length;
      subs.push({ t0: (f0 === 0 ? ws[0].s : timeAt(f0)) - .05, t1: (f1 >= .999 ? ws[ws.length - 1].e : timeAt(f1)) + .35, text: p.trim() });
    }
  }
  for (let i = 0; i < subs.length - 1; i++) subs[i].t1 = Math.min(Math.max(subs[i].t1, subs[i].t0 + 1.4), subs[i + 1].t0 - .04);
  const accent = o.accent || W.INK.orange, font = o.font || 'AD';
  return {
    subs,
    draw(ctx, t) {
      const s = subs.find(s => t >= s.t0 && t < s.t1); if (!s) return;
      const SW = W.SW, SH = W.SH, px = Math.round(SW * 0.046), maxW = SW * 0.84;
      const a = Math.min(1, (t - s.t0) / .12, (s.t1 - t) / .12);
      ctx.save();
      ctx.font = `${px}px ${font}`;
      let rows = [s.text];
      if (ctx.measureText(s.text).width > maxW) {      // two balanced rows
        const ws = s.text.split(' '); let best = 1, bd = 1e9;
        for (let i = 1; i < ws.length; i++) { const d = Math.abs(ctx.measureText(ws.slice(0, i).join(' ')).width - ctx.measureText(ws.slice(i).join(' ')).width); if (d < bd) { bd = d; best = i; } }
        rows = [ws.slice(0, best).join(' '), ws.slice(best).join(' ')];
      }
      const lh = px * 1.18, w = Math.max(...rows.map(r => ctx.measureText(r).width)) + px * 1.4, h = px * 1.6 + (rows.length - 1) * lh, y0 = SH * 0.885 - h;
      ctx.globalAlpha = a * .9; ctx.fillStyle = '#fdfcf8'; ctx.shadowColor = 'rgba(30,30,40,.18)'; ctx.shadowBlur = 18; ctx.shadowOffsetY = 4;
      ctx.beginPath(); ctx.roundRect(SW / 2 - w / 2, y0, w, h, 16); ctx.fill();
      ctx.shadowColor = 'transparent'; ctx.globalAlpha = a;
      ctx.fillStyle = accent; ctx.fillRect(SW / 2 - w / 2 + 22, y0 + h - 12, 40, 4);
      ctx.fillStyle = '#23262c'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      rows.forEach((r, i) => ctx.fillText(r, SW / 2, y0 + px * 0.82 + i * lh));
      ctx.restore();
    },
  };
}

// a render function with real camera motion blur on whips (sub-frames ≤ 4 px apart), overlays drawn once on top
export function renderer(board, cam, o = {}) {
  const off = new OffscreenCanvas(W.SW, W.SH), oc = off.getContext('2d'), fps = o.fps ?? 30;
  return (ctx, t) => {
    const dt = 1 / fps, a = cam.at(t), b = cam.at(Math.max(0, t - dt));
    const sp = Math.hypot((a.x - b.x) * a.z, (a.y - b.y) * a.z) + Math.abs(Math.log(a.z / b.z)) * 900;
    const N = sp > 14 ? Math.min(o.maxSub ?? 8, Math.ceil(sp * .5 / 4)) : 1;
    if (N === 1) { board.render(ctx, t, cam); return; }
    const ov = board.overlays; board.overlays = [];
    for (let i = 0; i < N; i++) { board.render(oc, t - dt * .5 * i / (N - 1), cam); ctx.globalAlpha = 1 / (i + 1); ctx.drawImage(off, 0, 0); }
    ctx.globalAlpha = 1; board.overlays = ov;
    for (const ov1 of ov) { ctx.save(); ov1.draw(ctx, t); ctx.restore(); }
  };
}

// the timeline's events with the stroke's screen pan and the camera zoom, for the sound designer (marker foley)
export function soundCues(tl, cam) {
  const out = [];
  for (const e of tl.ev) {
    const c = { ...e };
    if (e.x != null) {
      const k = cam.at(e.t), [px, py] = W.toScreen(k, e.x, e.y);
      c.pan = +clamp((px - W.SW / 2) / (W.SW * 0.73), -.7, .7).toFixed(2); c.z = +k.z.toFixed(2);
      c.on = px > -100 && px < W.SW + 100 && py > -100 && py < W.SH + 100 ? 1 : 0;
    }
    out.push(c);
  }
  return out;
}

// ghost marks: the faint residue of old lessons (a seeded scatter over the board)
export function ghosts(boardW, boardH, n = 40, seed = 99) {
  const gR = mulberry(seed), out = [];
  for (let i = 0; i < n; i++) {
    const x = gR() * (boardW - 400) + 200, y = gR() * (boardH - 400) + 200, k = gR();
    const o = { w: 12, alpha: .05 + gR() * .05, color: gR() < .2 ? '#8aa0c8' : '#9aa0a8' };
    if (k < .3) out.push(...W.text(['x = 4', 'lab 3', 'TUE', 'q.2', 'f(x)', 'pH 7', 'due fri', '→ 12', 'ok!'][i % 9], x, y, { h: 50 + gR() * 40, ...o }));
    else if (k < .55) out.push(W.circle(x, y, 40 + gR() * 110, o));
    else if (k < .8) out.push(...W.arrow(x, y, x + (gR() - .5) * 500, y + (gR() - .5) * 300, o));
    else out.push(W.line(x, y, x + 200 + gR() * 500, y + (gR() - .5) * 80, o));
  }
  return out;
}
