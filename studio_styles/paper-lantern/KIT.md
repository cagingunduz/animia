THE KIT (K = window.LB): a paper-cut lightbox. You build a BOX of flat paper SHEETS at different depths once in
film(); every frame you set a few numbers on them (light, reveal, offsets) and render the box through a camera.
World units are pixels of the front sheet at the default camera; y DOWN; (0, 0) = the centre of the frame.

BUILD (in film(), once):
- const b = K.box({ light: [x, y], lightR: 900, lightCol: '#ffd9a0', floor: .3, bg: '#04060f' })
  the backlight behind the sheets: its centre, radius of its falloff, colour (warm amber for interiors and lamps,
  pale blue-white for moonlit nights), floor = how lit the sheets are far from it.
- K.sky(b, { z: 900, stops: [[0, top], [.5, mid], [1, horizon]], stars: 0..400 }) the flat back panel.
- K.moon(b, { x, y, z: 850, r: 60, phase: 0 (or .4 for a crescent), core, edge, haloCol }) a disc that burns (a sun
  too: core '#fff3c8', edge '#ffb04a'); .k = brightness 0..1 per frame.
- const s = K.sheet(b, { z, color, trans, x0, y0, w, h, draw: g => {...}, glow: (g, frame) => {...}, glowCol,
  soft, frames, shadow, rim })
  z depth (0 front .. 700 far), color one flat paper colour (follow the ladder: far = light and cool, front = almost
  black), trans how much light passes (far .85, mid .55, story .3, front .08), [x0, y0, w, h] the world area the sheet
  covers (only as big as needed; far sheets bigger), draw paints the silhouette (any fill colour: the kit colours it;
  K.cut(g, () => ...) punches holes), glow paints the burning windows / lanterns / fires in white (they must also be
  holes or pale areas in draw), glowCol their colour ('#ffb862' warm windows, '#ffd080' fire), soft = baked blur
  (2-4 for far sheets), frames = a flip-book: draw(g, f) / glow(g, f) are called for f = 0..frames-1 and you pick the
  frame per seek with s.frame = n (walk cycles, windows lighting one by one, waves). shadow: false for mist.
- K.paperText(b, 'Words', { z: 120, x, y, size: 80, paper: '#efe2c4', glow: false }) a cream strip with the words
  cut out (a title, a name, a date): it grows from its left edge, set .reveal 0..1.

PAINTING (inside draw / glow; g is a 2D context in world units, y down; base = the ground line's y):
- K.hills(g, { x0, x1, base, amp, len, seed }) -> returns y(x), the ridge height at x (use it to seat a house).
- K.peaks(g, { x0, x1, base, list: [[cx, height, halfWidth], ...], slits: true }) mountains with carved snow lines.
- K.firs(g, { x0, x1, base, h, gap, seed }) a forest row; K.fir(g, x, base, h) one fir; K.tree(g, x, base, h, seed)
  a round tree with lace holes.
- K.houses(g, { x0, x1, base, h, seed }) a row of houses with the window holes cut; in glow:
  K.houseWindows(g, { same x0, x1, base, h, seed, lit: 0..1 }) the windows that burn (lit = the fraction).
- K.waves(g, { x0, x1, base, amp, len, phase }) a sea band (animate with frames: phase = f / frames).
- K.cloud(g, x, y, s) a curled auspicious cloud; K.birds(g, [[x, y, s, wingPhase], ...]);
  K.boat(g, x, y, s, { sail, lamp }); K.lantern(g, x, y, s) (paint the same in glow to light it);
  K.bridge(g, x0, x1, y, { arches }); K.pagoda(g, x, base, s, { tiers }) (glow: K.pagoda(g, x, base, s, { only: true }));
  K.lighthouse(g, x, base, s) (glow: K.lighthouse(g, x, base, s, { only: true })).
- K.person(g, x, base, h, { pose: 'stand' | 'walk' | 'run' | 'sit' | 'reach', phase: 0..1, face: 1 | -1, kind:
  'adult' | 'child' | 'elder', hat, dress, bag }) a jointed silhouette in profile (walk = a sheet with frames: 8 and
  phase = f / 8); K.cat(g, x, base, s, { face }).
- K.seal(g, x, y, size) a small square seal (draw it on a red sheet: the one accent colour).
- Plain canvas calls work too: g.fillRect, g.beginPath / moveTo / lineTo / quadraticCurveTo / arc / ellipse / fill.

PER FRAME (in seek(t, ctx)):
- K.lightUp(b, t, t0, { stagger: .35 }) the lamp turns on at t0 (source, then sheets back to front, then windows);
  pass { off: t1 } to turn it off at t1. Or set by hand: b.lit (0..1 master), s.litK (0..1 a sheet's backlight),
  s.glowK (0..1 its windows), moon.k.
- A sheet's motion (paper on a stick only: slide, turn, grow): s.x, s.y (offsets), s.rot with s.pivot = [x, y],
  s.sx / s.sy, s.alpha, s.reveal (0..1) with s.revealFrom 'left' | 'right' | 'top' | 'bottom', s.frame.
- const cam = K.camPath([[t, x, y, d], ...]) at build; then b.render(ctx, t, K.drift(cam(t), t)).
  d = 1600 the whole box, 1000 closer, 700 one window; moves are slow and short.
- K.lens(ctx, { fade, vig: 1, warm: .12 }) after render: vignette, warm grade, fade from / to black (fade 0..1).
- Dissolve between two boxes: K.dissolve(ctx, k, c => boxA.render(c, t, camA), c => boxB.render(c, t, camB)) then
  K.lens. A film may build 2-4 boxes (scenes) and dissolve between them (0.6-1.2 s), or keep one box and move.
- subs = K.subtitles(T) at build; subs.draw(ctx, t) last.

SOUND: cues: K.sounds([{ t, type, v, d }]) with type in click (the lamp switch), shimmer (light rising; d = length),
rustle, slide (a sheet sliding in), tap (card on card), chime (a reveal), whoosh (a curtain), thud (a lid). sfx: {}.

COST: every sheet is baked to bitmaps once (bigger sheets and more frames cost memory): keep sheets ≤ 2400 x 2800
units, frames ≤ 12, and ≤ 12 sheets in the whole film.

A WORKED EXAMPLE (a moonlit village whose windows answer an old woman's lamp):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w;
  const b = K.box({ light: [120, -100], lightR: 900, lightCol: '#c8d0f0', floor: .35, bg: '#04060f' });
  K.sky(b, { z: 900, stops: [[0, '#060b22'], [.45, '#0d1a40'], [.8, '#1c2d5e'], [1, '#2c4074']], stars: 260 });
  const mn = K.moon(b, { x: 260, y: -700, z: 860, r: 60, k: 1 });
  K.sheet(b, { z: 650, color: '#6a86c2', trans: .85, soft: 2, x0: -1100, y0: -800, w: 2200, h: 2600,
    draw: g => K.peaks(g, { x0: -1100, x1: 1100, base: 20, list: [[-700, 300, 380], [-250, 420, 420], [300, 520, 480], [820, 340, 380]] }) });
  const hillY = 150, HX = -230;
  let HY = 0;   // the hilltop under the old woman's house (set when the hill is cut)
  const hill = K.sheet(b, { z: 380, color: '#3f5a92', trans: .55, x0: -1000, y0: -400, w: 2000, h: 2200, glowCol: '#ffb862',
    draw: g => { const ry = K.hills(g, { x0: -1000, x1: 1000, base: hillY + 120, amp: 140, len: 900, seed: 3 }); HY = ry(HX) + 6;
      g.fillRect(HX - 40, HY - 70, 80, 72); g.beginPath(); g.moveTo(HX - 56, HY - 68); g.lineTo(HX, HY - 115); g.lineTo(HX + 56, HY - 68); g.fill();
      K.cut(g, () => g.fillRect(HX - 12, HY - 52, 24, 28)); },
    glow: g => g.fillRect(HX - 12, HY - 52, 24, 28) });
  // the village: a flip-book of how many windows burn (frame 0 none .. 7 all)
  const VB = 560;
  const village = K.sheet(b, { z: 200, color: '#26386a', trans: .3, frames: 8, x0: -900, y0: 200, w: 1800, h: 1400, glowCol: '#ffb862',
    draw: g => { K.houses(g, { x0: -760, x1: 760, base: VB, h: 120, seed: 9 }); K.tree(g, -820, VB + 4, 220); K.tree(g, 820, VB + 4, 200, 7); },
    glow: (g, f) => K.houseWindows(g, { x0: -760, x1: 760, base: VB, h: 120, seed: 9, lit: f / 7 }) });
  const front = K.sheet(b, { z: 40, color: '#0e1532', trans: .08, x0: -800, y0: 400, w: 1600, h: 1000,
    draw: g => K.firs(g, { x0: -800, x1: 800, base: 800, h: 260, gap: 70, seed: 4, roll: 20 }) });
  const title = K.paperText(b, 'The First Light', { z: 120, x: 0, y: -380, size: 92, paper: '#efe2c4' });
  const subs = K.subtitles(T);
  const cam = K.camPath([[0, 0, 0, 1600], [L[1].start, 0, -40, 1500], [L[1].start + 2.2, HX + 40, HY - 40, 760], [L[2].start + .6, HX + 40, HY - 40, 740],
    [L[3].start, 0, 160, 1350], [L[4].start, 0, 120, 1500], [T.end, 0, 0, 1700]]);
  const lamp = w(1, 'lamp'), first = w(2, 'window'), all = w(3, 'glowing');
  return {
    seek(t, ctx) {
      K.lightUp(b, t, 0, { stagger: .3 });
      b.lit = .55 + .45 * K.ss(K.seg(t, lamp, lamp + 1.2));          // the valley brightens from the old woman's lamp
      hill.glowK = K.ss(K.seg(t, lamp - .1, lamp + .3));
      village.glowK = 1;
      village.frame = Math.round(7 * (t < first ? 0 : t < w(2, 'another') ? 1 : K.clamp(2 + 5 * K.seg(t, w(2, 'another'), all))));
      title.reveal = K.eo(K.seg(t, L[5].end - .2, L[5].end + 1.2));
      mn.k = .8 + .2 * K.ss(K.seg(t, lamp, lamp + 2));
      b.render(ctx, t, K.drift(cam(t), t));
      K.lens(ctx, { fade: K.ss(K.seg(t, 0, .8)) * (1 - K.ss(K.seg(t, T.end - .6, T.end))) });
      subs.draw(ctx, t);
    },
    cues: K.sounds([{ t: 0.2, type: 'shimmer', d: 2 }, { t: lamp - .05, type: 'click' }, { t: lamp, type: 'shimmer' }, { t: first, type: 'chime', v: .6 },
      { t: w(2, 'another'), type: 'chime', v: .5 }, { t: L[5].end - .2, type: 'slide' }, { t: L[5].end + .9, type: 'tap' }]),
    sfx: {},
  };
}
```
