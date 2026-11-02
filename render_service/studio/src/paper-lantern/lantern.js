// Paper-cut Lightbox engine for the Animave Style Studio, a Canvas2D port of the look of the lemo-opuscar
// "paper-lantern" style (github.com/lemomo-ai/lemo-opuscar, MIT; its demo renders with three.js shaders, this one is
// made for CPU rendering): parallel sheets of cut card in a shallow box, lit from behind, each sheet casting a soft
// shadow onto the ones behind it.
//
// World units: at the default camera (d = 1600) the front sheet (z = 0) shows 1 unit = 1 px of a 1080 x 1920 frame,
// centred on (0, 0), y DOWN. Sheets sit behind the front at depth z (0 .. ~800). A sheet at depth z appears at
// scale F / (d + z) with F = 1600, so moving the camera gives real parallax.
import { clamp, lerp, mulberry, hash, vnoise, TAU } from '../common/lib.js';

export let SW = 1080, SH = 1920;
export function setScreen(w, h) { SW = w; SH = h; }
export const F = 1600;

export function cv(w, h) { const c = new OffscreenCanvas(Math.max(1, Math.ceil(w)), Math.max(1, Math.ceil(h))); return c; }

// —— textures (after paper.js in lemo-opuscar) ——
let _grain = null, _cloud = null;
function grain() {
  if (_grain) return _grain;
  const n = 256, c = cv(n, n), x = c.getContext('2d'), R = mulberry(7), img = x.createImageData(n, n), d = img.data;
  for (let i = 0; i < n * n; i++) { const v = R(); d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = v < .5 ? 0 : 255; d[i * 4 + 3] = Math.abs(v - .5) * 34; }
  x.putImageData(img, 0, 0); x.lineCap = 'round';
  for (let i = 0; i < n * 1.4; i++) {
    const px = R() * n, py = R() * n, a = R() * TAU, l = 5 + R() * 22;
    x.strokeStyle = R() < .5 ? 'rgba(40,30,20,.10)' : 'rgba(255,255,255,.16)'; x.lineWidth = .5 + R() * .8;
    x.beginPath(); x.moveTo(px, py); x.quadraticCurveTo(px + Math.cos(a + .5) * l * .5, py + Math.sin(a + .5) * l * .5, px + Math.cos(a) * l, py + Math.sin(a) * l); x.stroke();
  }
  return (_grain = c);
}
function cloud() {   // the flocculent pulp seen when paper is backlit (tileable)
  if (_cloud) return _cloud;
  const n = 384, R = mulberry(3), c = cv(n, n), x = c.getContext('2d');
  x.fillStyle = '#808080'; x.fillRect(0, 0, n, n);
  for (const [cnt, rmin, rmax, a] of [[50, 30, 90, .25], [200, 8, 30, .18], [700, 2, 8, .12]]) {
    for (let i = 0; i < cnt; i++) {
      const px = R() * n, py = R() * n, r = rmin + R() * (rmax - rmin), v = R() < .5 ? 0 : 255;
      for (const ox of [-n, 0, n]) for (const oy of [-n, 0, n]) {
        if (px + ox + r < 0 || px + ox - r > n || py + oy + r < 0 || py + oy - r > n) continue;
        const g = x.createRadialGradient(px + ox, py + oy, 0, px + ox, py + oy, r);
        g.addColorStop(0, `rgba(${v},${v},${v},${a})`); g.addColorStop(1, `rgba(${v},${v},${v},0)`);
        x.fillStyle = g; x.fillRect(px + ox - r, py + oy - r, r * 2, r * 2);
      }
    }
  }
  return (_cloud = c);
}

// cut holes: inside fn, everything drawn removes paper (windows, slits, lace)
export function cut(g, fn) { g.save(); g.globalCompositeOperation = 'destination-out'; g.fillStyle = '#000'; g.strokeStyle = '#000'; fn(g); g.restore(); }

// a light-coloured version of a hex colour mixed toward another
export function mix(a, b, k) {
  const p = s => { s = s.replace('#', ''); if (s.length === 3) s = s.split('').map(c => c + c).join(''); return [0, 2, 4].map(i => parseInt(s.slice(i, i + 2), 16)); };
  const A = p(a), B = p(b); return '#' + A.map((v, i) => Math.round(lerp(v, B[i], k)).toString(16).padStart(2, '0')).join('');
}

// —— the camera ——
// cam = { x, y, d, roll }: the world point at the screen centre, the distance (1600 = default; smaller = closer), roll
export function project(cam, z) { return F / Math.max(50, cam.d + z); }
export function toScreen(cam, x, y, z) { const s = project(cam, z) * SW / 1080; return [SW / 2 + (x - cam.x) * s, SH / 2 + (y - cam.y) * s]; }
// a hand-held drift keeps a locked frame alive
export function drift(cam, t, amt = 1) { return { ...cam, x: cam.x + (vnoise(t * .35 + 3) - .5) * 3 * amt, y: cam.y + (vnoise(t * .35 + 17) - .5) * 3 * amt }; }

// —— the box ——
export class Box {
  // o: { light: [x, y] (world, behind the sheets), lightR (falloff radius), lightCol, floor (light far from the centre), bg }
  constructor(o = {}) {
    this.o = { light: [0, -200], lightR: 900, lightCol: '#ffd9a0', floor: .3, bg: '#05060d', ...o };
    this.sheets = []; this.lit = 1;
  }
  add(s) { this.sheets.push(s); this.sheets.sort((a, b) => b.z - a.z); return s; }
  // draw the whole box at time t through camera cam
  render(ctx, t, cam, o = {}) {
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = this.o.bg; ctx.fillRect(0, 0, SW, SH);
    const lit = this.lit * (o.lit ?? 1);
    for (const s of this.sheets) s.draw(ctx, t, cam, lit, this);
    ctx.restore();
  }
}

// —— a sheet of cut paper ——
// o: { z, color, x0, y0, w, h (the area it covers, world units), draw(g, frame) (paint the silhouette in any colour,
//      cut holes with cut()), glow(g, frame) (paint windows/lanterns in white: they burn), glowCol, trans (0..1 how much
//      backlight passes: back sheets .7-.9, front .05-.15), soft (px of baked blur: depth of field for far sheets),
//      shadow (cast a shadow, default true), res (bitmap px per unit, default from depth), frames (flip-book count),
//      rim (top edge light 0..1), x, y, rot, pivot [x, y], alpha, reveal }
export class Sheet {
  constructor(box, o) {
    Object.assign(this, { z: 0, color: '#333', x0: -800, y0: -1200, w: 1600, h: 2400, trans: .3, soft: 0, shadow: true, frames: 1, rim: .35, glowCol: '#ffc46a',
      x: 0, y: 0, rot: 0, sx: 1, sy: 1, pivot: null, alpha: 1, glowK: 1, litK: 1, reveal: 1, revealFrom: 'left', visible: true }, o);
    delete this.draw; delete this.glow;          // the paint functions must not shadow the draw() method
    this.paintFn = o.draw || (() => {}); this.glowFn = o.glow || null;
    this.box = box;
    this.res = o.res ?? clamp(1.15 * F / (1600 * .62 + this.z), .35, 1.4);
    this.bm = [];
    for (let f = 0; f < this.frames; f++) this.bm.push(this._bake(f));
  }
  _paint(fn, f, res) {
    const c = cv(this.w * res, this.h * res), g = c.getContext('2d');
    g.setTransform(res, 0, 0, res, -this.x0 * res, -this.y0 * res);
    g.fillStyle = '#000'; g.strokeStyle = '#000'; fn(g, f);
    return c;
  }
  _bake(f) {
    const res = this.res, W = Math.ceil(this.w * res), H = Math.ceil(this.h * res);
    // the silhouette, coloured, with grain, a lit top rim and a dark bottom band
    const shape = this._paint(this.paintFn, f, res);
    const base = cv(W, H), b = base.getContext('2d');
    b.drawImage(shape, 0, 0); b.globalCompositeOperation = 'source-in'; b.fillStyle = this.color; b.fillRect(0, 0, W, H);
    b.globalCompositeOperation = 'source-atop'; b.globalAlpha = .9; b.fillStyle = b.createPattern(grain(), 'repeat'); b.fillRect(0, 0, W, H); b.globalAlpha = 1;
    const band = (dy, col, blur) => {
      const t = cv(W, H), y = t.getContext('2d');
      y.drawImage(shape, 0, 0); y.globalCompositeOperation = 'destination-out'; y.drawImage(shape, 0, dy);
      y.globalCompositeOperation = 'source-in'; y.fillStyle = col; y.fillRect(0, 0, W, H);
      b.save(); b.globalCompositeOperation = 'source-atop'; b.filter = `blur(${blur}px)`; b.drawImage(t, 0, 0); b.restore();
    };
    if (this.rim) band(Math.max(2, 3 * res), `rgba(255,236,200,${this.rim})`, .7);
    band(-Math.max(2, 3 * res), 'rgba(0,0,0,.3)', .9);
    // the backlight through the paper: light colour x paper colour x pulp mottle x falloff around the box light
    const L = this.box.o, glow = cv(W, H), gl = glow.getContext('2d');
    gl.drawImage(shape, 0, 0); gl.globalCompositeOperation = 'source-in';
    const lx = (L.light[0] - this.x0) * res, ly = (L.light[1] - this.y0) * res, R = L.lightR * res;
    const tint = mix(this.color, L.lightCol, .35), fl = Math.round(clamp(L.floor) * 255).toString(16).padStart(2, '0');
    const gr = gl.createRadialGradient(lx, ly, 0, lx, ly, R);
    gr.addColorStop(0, tint); gr.addColorStop(.55, tint + 'b0'); gr.addColorStop(1, tint + fl);
    gl.fillStyle = tint + fl; gl.fillRect(0, 0, W, H); gl.fillStyle = gr; gl.fillRect(0, 0, W, H);
    gl.globalCompositeOperation = 'multiply'; gl.fillStyle = gl.createPattern(cloud(), 'repeat'); gl.fillRect(0, 0, W, H);
    gl.globalCompositeOperation = 'destination-in'; gl.drawImage(shape, 0, 0);
    // the shadow it casts on the sheets behind (soft, half resolution)
    let sh = null;
    if (this.shadow) {
      const k = .5; sh = cv(W * k, H * k); const s = sh.getContext('2d');
      s.filter = `blur(${Math.max(2, 9 * res * k)}px)`; s.drawImage(shape, 0, 0, W * k, H * k); s.filter = 'none';
      s.globalCompositeOperation = 'source-in'; s.fillStyle = 'rgba(0,0,0,.55)'; s.fillRect(0, 0, W * k, H * k);
    }
    // the windows: an emissive layer and its bloom
    let em = null, bloom = null;
    if (this.glowFn) {
      const e = this._paint((g, ff) => { g.fillStyle = '#fff'; this.glowFn(g, ff); }, f, res);
      em = cv(W, H); const ex = em.getContext('2d');
      ex.drawImage(e, 0, 0); ex.globalCompositeOperation = 'source-in'; ex.fillStyle = this.glowCol; ex.fillRect(0, 0, W, H);
      const k = .25; bloom = cv(W * k, H * k); const bx = bloom.getContext('2d');
      bx.filter = `blur(${Math.max(3, 22 * res * k)}px)`; bx.drawImage(em, 0, 0, W * k, H * k); bx.filter = `blur(${Math.max(2, 6 * res * k)}px)`; bx.drawImage(em, 0, 0, W * k, H * k);
    }
    const soften = c => { if (!this.soft || !c) return c; const o = cv(c.width, c.height), x = o.getContext('2d'); x.filter = `blur(${this.soft * res}px)`; x.drawImage(c, 0, 0); return o; };
    return { base: soften(base), glow: soften(glow), sh, em: soften(em), bloom };
  }
  // per-frame transform into screen space for this sheet
  _place(ctx, cam) {
    const s = project(cam, this.z) * SW / 1080, res = this.res;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.translate(SW / 2, SH / 2); if (cam.roll) ctx.rotate(cam.roll);
    ctx.scale(s, s); ctx.translate(-cam.x + this.x, -cam.y + this.y);
    if (this.pivot) { ctx.translate(this.pivot[0], this.pivot[1]); ctx.rotate(this.rot); ctx.scale(this.sx, this.sy); ctx.translate(-this.pivot[0], -this.pivot[1]); }
    else if (this.rot || this.sx !== 1 || this.sy !== 1) { const cx = this.x0 + this.w / 2, cy = this.y0 + this.h / 2; ctx.translate(cx, cy); ctx.rotate(this.rot); ctx.scale(this.sx, this.sy); ctx.translate(-cx, -cy); }
    ctx.translate(this.x0, this.y0); ctx.scale(1 / res, 1 / res);
    return s;
  }
  draw(ctx, t, cam, lit, box) {
    if (!this.visible || this.alpha <= .001 || this.reveal <= .001) return;
    const b = this.bm[this.frames > 1 ? (((this.frame ?? Math.floor(t * 12)) % this.frames) + this.frames) % this.frames : 0];
    const W = b.base.width, H = b.base.height;
    ctx.save();
    if (this.reveal < 1) {   // paper that grows out of its anchor edge
      this._place(ctx, cam); ctx.beginPath();
      const r = this.reveal, f = this.revealFrom;
      if (f === 'left') ctx.rect(0, 0, W * r, H); else if (f === 'right') ctx.rect(W * (1 - r), 0, W * r, H);
      else if (f === 'top') ctx.rect(0, 0, W, H * r); else ctx.rect(0, H * (1 - r), W, H * r);
      ctx.clip();
    }
    if (b.sh) {   // the shadow falls down and a little back
      this._place(ctx, cam); ctx.globalAlpha = this.alpha * .9;
      ctx.translate(6 * this.res, 22 * this.res); ctx.drawImage(b.sh, 0, 0, W, H); ctx.translate(-6 * this.res, -22 * this.res);
    }
    this._place(ctx, cam); ctx.globalAlpha = this.alpha;
    ctx.drawImage(b.base, 0, 0);
    const k = this.trans * lit * this.litK;
    if (k > .002) { ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = this.alpha * clamp(k * this.trans * .75); ctx.drawImage(b.glow, 0, 0); ctx.globalCompositeOperation = 'source-over'; }
    if (b.em && this.glowK > .002) {
      const flick = 1 + .06 * Math.sin(7.3 * t + this.z) * Math.sin(3.1 * t + this.z * .3);
      ctx.globalAlpha = this.alpha * clamp(this.glowK); ctx.drawImage(b.em, 0, 0);
      ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = this.alpha * clamp(this.glowK * .9 * flick); ctx.drawImage(b.bloom, 0, 0, W, H);
      ctx.globalCompositeOperation = 'source-over';
    }
    ctx.restore();
  }
}

// a sky: the back panel, a flat gradient of the ladder's lightest values, optional stars; it is unlit by the box
export class Sky {
  constructor(box, o) {
    Object.assign(this, { z: 900, stops: [[0, '#0a1330'], [1, '#2c4074']], stars: 0, w: 3000, h: 4600, seed: 5, x: 0, y: 0, alpha: 1, gain: 1 }, o);
    const res = .5, W = this.w * res, H = this.h * res, c = cv(W, H), g = c.getContext('2d');
    const gr = g.createLinearGradient(0, 0, 0, H); this.stops.forEach(([p, col]) => gr.addColorStop(p, col));
    g.fillStyle = gr; g.fillRect(0, 0, W, H);
    const R = mulberry(this.seed);
    for (let i = 0; i < this.stars; i++) { const px = R() * W, py = R() * H * (this.starsTo ?? .6), r = .4 + R() * R() * 1.6; g.fillStyle = `rgba(255,246,220,${.25 + R() * .6})`; g.beginPath(); g.arc(px, py, r, 0, TAU); g.fill(); }
    g.globalAlpha = .5; g.globalCompositeOperation = 'overlay'; g.fillStyle = g.createPattern(grain(), 'repeat'); g.fillRect(0, 0, W, H);
    this.c = c; this.res = res; this.box = box;
  }
  draw(ctx, t, cam, lit) {
    const s = project(cam, this.z) * SW / 1080;
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.translate(SW / 2, SH / 2); if (cam.roll) ctx.rotate(cam.roll);
    ctx.scale(s, s); ctx.translate(-cam.x + this.x - this.w / 2, -cam.y + this.y - this.h / 2);
    ctx.globalAlpha = this.alpha; ctx.drawImage(this.c, 0, 0, this.w, this.h);
    if (this.gain * lit < 1) { ctx.globalAlpha = 1 - this.gain * lit; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, this.w, this.h); }
    ctx.restore();
  }
}

// the moon (or sun, a lamp, a lighthouse): a disc that burns with a halo; it sits at depth z like a sheet
export class Moon {
  constructor(box, o) {
    Object.assign(this, { x: 0, y: -600, z: 850, r: 70, core: '#fffaf0', edge: '#f7dca4', halo: 5, haloCol: '#ffd9a0', k: 1, phase: 0 }, o);
    const res = 1, R = this.r, n = Math.ceil(R * 2.1 * res), c = cv(n, n), g = c.getContext('2d');
    const gr = g.createRadialGradient(n / 2 - R * .2, n / 2 - R * .25, 0, n / 2, n / 2, R);
    gr.addColorStop(0, this.core); gr.addColorStop(.75, mix(this.core, this.edge, .5)); gr.addColorStop(1, this.edge);
    g.fillStyle = gr; g.beginPath(); g.arc(n / 2, n / 2, R, 0, TAU); g.fill();
    g.globalCompositeOperation = 'source-atop';
    for (const [px, py, rr, a] of [[-.3, -.25, .32, .10], [.2, -.35, .22, .08], [.28, .1, .3, .09], [-.15, .35, .25, .07]]) {
      const q = g.createRadialGradient(n / 2 + px * R, n / 2 + py * R, 0, n / 2 + px * R, n / 2 + py * R, rr * R);
      q.addColorStop(0, `rgba(190,150,100,${a})`); q.addColorStop(1, 'rgba(190,150,100,0)'); g.fillStyle = q; g.fillRect(0, 0, n, n);
    }
    if (this.phase) { g.globalCompositeOperation = 'destination-out'; g.beginPath(); g.arc(n / 2 + this.phase * R * 1.1, n / 2 - R * .1, R * 1.02, 0, TAU); g.fill(); }
    this.c = c;
    const hn = 128, h = cv(hn, hn), hx = h.getContext('2d'), hg = hx.createRadialGradient(hn / 2, hn / 2, 0, hn / 2, hn / 2, hn / 2);
    hg.addColorStop(0, this.haloCol); hg.addColorStop(.35, this.haloCol + '5a'); hg.addColorStop(1, this.haloCol + '00');
    hx.fillStyle = hg; hx.fillRect(0, 0, hn, hn); this.h = h;
  }
  draw(ctx, t, cam, lit) {
    const s = project(cam, this.z) * SW / 1080, [sx, sy] = toScreen(cam, this.x, this.y, this.z), k = this.k * lit;
    if (k <= .001) return;
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (cam.roll) { ctx.translate(SW / 2, SH / 2); ctx.rotate(cam.roll); ctx.translate(-SW / 2, -SH / 2); }
    const HR = this.r * this.halo * s;
    ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = clamp(k * .55); ctx.drawImage(this.h, sx - HR / 2, sy - HR / 2, HR, HR);
    ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = clamp(k); const D = this.c.width * s; ctx.drawImage(this.c, sx - D / 2, sy - D / 2, D, D);
    ctx.restore();
  }
}

// —— the lens: vignette, a warm grade, grain (cached), a fade ——
let _vig = null;
export function lens(ctx, o = {}) {
  if (!_vig || _vig.width !== SW) {
    _vig = cv(SW, SH); const g = _vig.getContext('2d'), r = Math.hypot(SW, SH) / 2;
    const gr = g.createRadialGradient(SW / 2, SH * .48, r * .35, SW / 2, SH / 2, r);
    gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(0,0,0,.62)'); g.fillStyle = gr; g.fillRect(0, 0, SW, SH);
    g.globalAlpha = .18; g.globalCompositeOperation = 'overlay'; g.fillStyle = g.createPattern(grain(), 'repeat'); g.fillRect(0, 0, SW, SH);
  }
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = o.vig ?? 1; ctx.drawImage(_vig, 0, 0);
  if (o.warm !== 0) { ctx.globalCompositeOperation = 'soft-light'; ctx.globalAlpha = o.warm ?? .12; ctx.fillStyle = '#ffb060'; ctx.fillRect(0, 0, SW, SH); ctx.globalCompositeOperation = 'source-over'; }
  if ((o.fade ?? 1) < 1) { ctx.globalAlpha = 1 - clamp(o.fade); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, SW, SH); }
  ctx.restore();
}

// dissolve between two pictures: drawA and drawB each draw a full frame on the context they are given
let _buf = null;
export function dissolve(ctx, k, drawA, drawB) {
  k = clamp(k);
  if (k <= 0) { drawA(ctx); return; }
  if (k >= 1) { drawB(ctx); return; }
  if (!_buf || _buf.width !== SW) _buf = cv(SW, SH);
  const b = _buf.getContext('2d'); b.setTransform(1, 0, 0, 1, 0, 0); b.globalAlpha = 1; b.globalCompositeOperation = 'source-over';
  drawA(ctx); drawB(b);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = k; ctx.drawImage(_buf, 0, 0); ctx.restore();
}
