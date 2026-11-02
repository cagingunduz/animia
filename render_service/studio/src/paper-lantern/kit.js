// Paper-cut Lightbox kit for the Animave Style Studio (window.LB): the lightbox engine (lantern.js), paper motifs
// (motifs.js), and what every film needs: camera paths, light cues, paper text strips, quiet serif subtitles, sounds.
import * as E from './lantern.js';
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, vnoise, TAU, env } from '../common/lib.js';

export * from './lantern.js';
export * from './motifs.js';
export { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, vnoise, TAU, env };

export const box = o => new E.Box(o);
export const sheet = (b, o) => b.add(new E.Sheet(b, o));
export const sky = (b, o) => b.add(new E.Sky(b, o));
export const moon = (b, o) => b.add(new E.Moon(b, o));

// a camera that eases between keys [[t, x, y, d], ...] (d = distance, 1600 default; 1100 = a slow dolly in)
export function camPath(keys) {
  return t => {
    if (t <= keys[0][0]) return { x: keys[0][1], y: keys[0][2], d: keys[0][3] };
    for (let i = 0; i < keys.length - 1; i++) {
      const a = keys[i], b = keys[i + 1];
      if (t < b[0]) { const u = eio(clamp((t - a[0]) / Math.max(1e-6, b[0] - a[0]))); return { x: lerp(a[1], b[1], u), y: lerp(a[2], b[2], u), d: lerp(a[3], b[3], u) }; }
    }
    const k = keys[keys.length - 1]; return { x: k[1], y: k[2], d: k[3] };
  };
}

// the lamp turns on at t0: the light source first, then each sheet back to front (stagger s), then the windows
// sets box.lit, each sheet's litK and glowK; call it every frame before box.render
export function lightUp(b, t, t0, { stagger = .35, windows = .6, off = null } = {}) {
  const on = ss(seg(t, t0, t0 + .5)), sheets = b.sheets.filter(s => s instanceof E.Sheet);
  const back2front = sheets.slice().sort((a, c) => c.z - a.z);
  const out = off != null ? 1 - ss(seg(t, off, off + .8)) : 1;
  b.lit = on * out;
  back2front.forEach((s, i) => { s.litK = ss(seg(t, t0 + .2 + i * stagger * .4, t0 + .6 + i * stagger * .4)) * out; s.glowK = ss(seg(t, t0 + .3 + back2front.length * stagger * .4 + windows * (i / Math.max(1, back2front.length)), t0 + .7 + back2front.length * stagger * .4 + windows * (i / Math.max(1, back2front.length)))) * out; });
}

// a paper strip with words cut in a serif, growing out of its left edge on cue: returns the sheet (set .reveal)
export function paperText(b, str, o = {}) {
  const size = o.size ?? 64, font = o.font ?? `600 ${size}px Cormorant`, pad = size * .45;
  const c = E.cv(10, 10).getContext('2d'); c.font = font; const tw = c.measureText(str).width;
  const w = tw + pad * 2, h = size * 1.55, x = o.x ?? 0, y = o.y ?? 0;
  return sheet(b, {
    z: o.z ?? 0, color: o.paper ?? '#efe2c4', trans: o.trans ?? .35, shadow: true, rim: .2, res: o.res ?? 1.5,
    x0: x - w / 2, y0: y - h / 2, w, h, revealFrom: 'left', reveal: 0,
    draw: g => { g.beginPath(); g.roundRect(x - w / 2, y - h / 2, w, h, 6); g.fill();
      E.cut(g, () => { g.font = font; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(str, x, y + size * .04); }); },
    glow: o.glow ? (g => { g.font = font; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(str, x, y + size * .04); }) : null,
    glowCol: o.glowCol ?? '#ffcf8a', ...o.sheet,
  });
}
// a small red seal (the accent) — draw it inside a sheet's draw(): K.seal(g, x, y, size)
export function seal(g, x, y, s = 60) { g.beginPath(); g.roundRect(x - s / 2, y - s / 2, s, s, s * .12); g.fill(); E.cut(g, () => { g.lineWidth = s * .08; g.strokeRect(x - s * .32, y - s * .32, s * .64, s * .64); g.fillRect(x - s * .04, y - s * .32, s * .08, s * .64); g.fillRect(x - s * .32, y - s * .04, s * .64, s * .08); }); }

// quiet burned-in subtitles: warm off-white serif on a faint dark band near the bottom; clauses of ≤ 34 characters
export function subtitles(T, o = {}) {
  const subs = [];
  for (const L of T.lines) {
    if (L.nocap || !L.words || !L.words.length) continue;
    const parts = L.text.split(/(?<=[,.;:!?…])\s+/).reduce((acc, p) => { const last = acc[acc.length - 1]; if (last != null && (last + ' ' + p).length <= (o.maxChars ?? 34)) acc[acc.length - 1] = last + ' ' + p; else acc.push(p); return acc; }, []);
    const ws = L.words, tot = parts.reduce((a, p) => a + p.length, 0); let c0 = 0;
    for (const p of parts) {
      const f0 = c0 / tot, f1 = (c0 + p.length) / tot; c0 += p.length;
      const at = f => { const i = Math.min(ws.length - 1, Math.floor(f * ws.length)); return ws[i].s; };
      subs.push({ t0: (f0 === 0 ? ws[0].s : at(f0)) - .15, t1: f1 >= .999 ? ws[ws.length - 1].e + .4 : at(f1), text: p });
    }
  }
  for (let i = 0; i < subs.length - 1; i++) subs[i].t1 = Math.min(Math.max(subs[i].t1, subs[i].t0 + 1.4), subs[i + 1].t0 - .05);
  const px = o.size ?? 54;
  return {
    subs,
    draw(ctx, t) {
      const s = subs.find(s => t >= s.t0 && t < s.t1); if (!s) return;
      const a = Math.min(ss(seg(t, s.t0, s.t0 + .2)), 1 - ss(seg(t, s.t1 - .22, s.t1)));
      const SW = E.SW, SH = E.SH, k = SW / 1080;
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.font = `600 ${px * k}px Cormorant`;
      let rows = [s.text];
      if (ctx.measureText(s.text).width > SW * .84) { const ws = s.text.split(' '), m = Math.ceil(ws.length / 2); rows = [ws.slice(0, m).join(' '), ws.slice(m).join(' ')]; }
      const lh = px * 1.2 * k, y0 = SH * (o.y ?? .9) - (rows.length - 1) * lh, w = Math.max(...rows.map(r => ctx.measureText(r).width)) + 70 * k;
      ctx.globalAlpha = a * .5; ctx.fillStyle = 'rgb(6,9,30)'; ctx.shadowColor = 'rgba(6,9,30,.8)'; ctx.shadowBlur = 40 * k;
      ctx.beginPath(); ctx.roundRect(SW / 2 - w / 2, y0 - px * .8 * k, w, (rows.length - 1) * lh + px * 1.6 * k, 16 * k); ctx.fill();
      ctx.globalAlpha = a; ctx.shadowColor = 'rgba(0,0,0,.85)'; ctx.shadowBlur = 10 * k; ctx.shadowOffsetY = 2 * k;
      ctx.fillStyle = '#fbf3e4'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      rows.forEach((r, i) => ctx.fillText(r, SW / 2, y0 + i * lh));
      ctx.restore();
    },
  };
}

// sound events for the foley track: [{ t, type, v }] with type in
// click (a lamp switch), shimmer (light rising), rustle, slide (paper sliding), tap (card on card), chime, whoosh, thud
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
