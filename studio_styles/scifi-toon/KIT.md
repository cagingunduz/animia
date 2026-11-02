THE KIT (K = window.TOON): the lemo-opuscar toon engine. You draw in WORLD coordinates through a camera; the kit
transforms every shape to the screen, boils its outline at 12 fps and strokes it at a constant ink width.

EVERY FRAME, in seek(t, ctx), in this order:
    K.begin(t, ctx);                 // bind the canvas, set the boil drawing, clear to black (always first)
    K.cam(cx, cy, z);                // the world point at the screen centre, zoom (see STYLE §10 for framings)
    ...the world, then props behind, then characters, then props in front...
    K.wipe(t, [cutTimes]);           // portal swirl wipes (full screen) centred on each cut time
    K.titleCard(t, 'Title', a, b);   // optional, first 2-3 s
    K.tag(t, tags);                  // world readouts
    subs.draw(t);                    // subtitles last (subs = K.subtitles(T, { cuts }) built once in film())
Call K.cam() again (or K.reset()) before drawing a new layer with another camera. Build lists, paths and seeds in
film(), not in seek().

TIME
- K.q(t): t stepped to 12 fps. Use it for character poses, walk cycles, gestures (characters animate on twos);
  use plain t for camera moves, portal swirl, flying props.
- K.seg(t, a, b) 0..1 ramp; K.ss / K.eo / K.ei / K.eio / K.back(u, s) / K.spring(t, k, d) easings; K.lerp, K.clamp,
  K.hash(n) deterministic 0..1, K.mulberry(seed) seeded random (build time only).
- K.camPath([[t, cx, cy, z], ...]) -> f(t) = [cx, cy, z] eased between keys: K.cam(...path(t)).
  Camera shake on one word: K.cam(cx, cy, z, { shake: 12, t }).

THE CAST (only these three speak; T.lines[i].who is 'VASK', 'GARY' or 'DECAF')
- K.vask(P), K.gary(P): draw the character with pose P. Always build P with the default-pose helpers, which add
  breathing, blinks and LIP SYNC from the voice track automatically:
    K.vask(K.V(T, t, { x: 1220, look: [-.4, .1] }));
    K.gary(K.G(T, t, { x: 700, nerv: 1 }));
  Pose fields (all optional): x, y (feet; ground is y = 900 = K.FLOOR), s (scale), face (1 faces right, -1 left;
  Vask defaults to -1, Gary to 1), lean, bob, sq (squash), headTilt, look [-1..1, -1..1] (pupils), lid 0..1 (Vask's heavy
  lids, .47 normal), brow (Vask: 0 flat, + raised; Gary: 1 worried, 1.5 panicked), blink, closed (Vask's contented closed
  eyes), twitch (eye twitch timer), mouth { o, w, sm (+ smile, − frown), skew } (set only sm to keep the lip sync:
  mouth: { ...K.V(T, t).mouth, sm: .5 }), armR / armL { h: [dx, dy] hand offset from the shoulder, bend }, legL / legR
  [dx, dy] foot offsets (K.legsWalk(K.q(t), walking) gives a walk cycle pair), sweat (a running number: drops fall),
  Vask only: holdR / holdL = 'mug' | 'remote' | 'cup' (cupP = Decaf's options), press (remote button 0..1), mugFull;
  Gary only: nerv 0..2 (jitter), eyeS (eye size), pupil (size, smaller = scared), mouthS (mouth size for screams).
  Heights: Vask ≈ 600 units (head centre ≈ y 420 at y = 900), Gary ≈ 400 (head ≈ y 600).
- K.coffeeCup(x, y, s, K.C(T, t, { happy, arms, look, rise, eyes })): DECAF, the talking coffee cup (y = cup bottom;
  s .5 in a hand, 1 on a table). K.C adds his lip sync and blinks. rise 0 = plain cup, 1 = the creature risen.
- K.talk(T, who, t) -> { o, w, talking }; K.speaker(T, t) -> who is speaking now ('' between lines). Use it for
  reactions: the listener looks at the speaker.
- Motion: K.walk(tq, t0, t1, xa, xb) eased x; K.landSq(t, tLand) landing squash factor (multiply sq);
  K.arcPos(t, t0, t1, [x, y], [x, y], h) parabola; K.spit(P, t, t0, tLand, [px, py], h) thrown out of a portal at
  (px, py) to land on P's spot (returns null before t0: draw only if not null); K.sucked(P, t, t0, t1, px, py) pulled
  into a portal; K.popOpen(t - tOpen) portal opening 0..1 with a gentle overshoot.
- Props: K.mug(x, y, a, { empty, steam }), K.remote(x, y, a, { press, glow }), K.hand(x, y, ang, r, col, { fist }).
- Face parts for your own creatures: K.eye(cx, cy, rx, ry, { lid, look, pupil, closed }), K.mouth(cx, cy, width,
  { o, w, sm, skew, teeth, tongue }). K.PAL = the cast's colours.

WORLDS (each fills the screen at z ≥ 1.0 around x 0..1920; skies to y −1200, ground to 1800)
- K.lab(t, { potDrops, green, clockMin, screen }): home, a sage-green lab (green 0..1 = portal light wash).
- K.jelly(t, { counter }), K.jellyCounter(t), K.blobby(x, y, s, t, { look, blink, o, lean }), K.jellyCup(x, y, s, t)
- K.mugWorld(t), K.mugGuy(x, y, s, t, {...}), K.glassGuy(x, y, s, t, {...}), K.umbrella(x, y, s, col), K.table(x, y, s)
- K.teethWorld(t), K.tooth(x, y, s), K.molar(x, y, s, t, { chomp }); K.pigeonWorld(t), K.pigeon(x, y, s, t, { tie, coo })
- K.vaskCafe(t, { turn, seats }) (a world where everyone is Vask); K.normalCafe(t), K.cafeCounter(t),
  K.barista(x, y, s, t, { arm, o }) (the suspiciously normal world)
These are the demo's worlds: reuse them only when they fit the joke. Most films need NEW worlds about the topic:
build them from the shapes below (a flat-band sky, a ground shape, 2-4 props, one creature with K.eye + K.mouth).

SHAPES (world coordinates; all strokes boil and keep a constant screen width)
- point lists: K.rect(x, y, w, h), K.rr(x, y, w, h, r), K.ell(cx, cy, rx, ry), K.arc(cx, cy, rx, ry, a0, a1),
  K.spline([[x, y], ...], closed = true) (smooth Catmull-Rom), K.quad(a, ctrl, b), K.noodle(a, b, bend, w0, w1) (a
  tapered limb / tentacle / hose).
- K.shape(points, { fill, lw = 7, line = K.INK, shade: () => {...}, boil = 1, alpha, closed }) draws a filled,
  outlined shape; inside `shade` draw hard-edged shadow blocks with K.fillOnly(points, colour, { boil: .3 }) (they are
  clipped to the shape). K.fillOnly(points, colour) fill without outline; K.stroke(points, lw, { line }) an open line;
  K.dot(x, y, r, colour); K.bands([colours top→bottom], y0, y1) a flat banded sky; K.text(str, x, y, { font, fill,
  align, outlineW }) world-space signs (fonts: '800 40px "Baloo 2"', '400 60px Bungee', '400 40px VT323',
  '400 50px "Titan One"').
- K.push(), K.pop(), K.translate(x, y), K.rotate(a), K.scale(sx, sy): the matrix stack (always pair push/pop).
- K.portal(cx, cy, r, t, { open: 0..1, sx = .74, spin }): THE only glowing thing. Open it with K.popOpen.
- K.screenRect(colour, alpha) a flat full-screen wash (flash); K.INK the line colour.

SCREEN LAYER
- K.wipe(t, [tc, ...]) a full-screen portal swirl centred on each cut time (± 0.2 s): cut worlds exactly at tc.
- K.tag(t, [[t0, t1, 'DIMENSION X-3', 'WHERE EVERYTHING IS SOUP', bg, fg], ...]) typed terminal readout, top left.
- K.titleCard(t, 'Title', a, b) atomic-age title card at the top (pops in on twos).
- subs = K.subtitles(T, { cuts: [world cut times] }) once in film(); subs.draw(t) last in seek.

SOUND: return cues: K.sounds([{ t, type, v }]) with type in pop, boing, suck, whoosh, portalOpen, portalClose,
click, slam, thud, squish, blip, gulp, step (v = volume, 1 default). Put one on every portal open/close, every
landing, every button press, every pop-in; a whoosh 0.16 s before each wipe. sfx: {} (leave empty).

A WORKED EXAMPLE (a short reel: lab → a world with no air):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w;
  const OPEN = w(4, 'out') + 0.25, CUT = L[5].start - 0.25;
  const subs = K.subtitles(T, { cuts: [CUT] });
  const tags = [[CUT + 0.25, CUT + 3.2, 'DIMENSION 0-A', 'NO AIR AT ALL', '#3b3f8f', '#fff']];
  const moon = (t) => {                          // a new world: flat sky, stars, a ground shape with craters
    K.fillOnly(K.rect(-1400, -1200, 4800, 2100), '#0d0b1a', { boil: 0 });
    for (let i = 0; i < 60; i++) K.dot(-400 + K.hash(i) * 2800, -900 + K.hash(i + 9) * 1700, 3 + K.hash(i + 3) * 3, '#fff');
    K.shape(K.spline([[-1400, 840], [600, 860], [1500, 790], [3400, 850], [3400, 1800], [-1400, 1800]]), { fill: '#9a96a8', lw: 7,
      shade: () => { for (const [x, y, r] of [[200, 980, 90], [1500, 960, 120]]) K.fillOnly(K.ell(x, y, r, r * .35, 24), '#7d7990', { boil: .3 }); } });
  };
  return {
    seek(t, ctx) {
      K.begin(t, ctx);
      const tq = K.q(t);
      if (t < CUT) {
        if (t < L[1].start) K.cam(960, 540, 1.3);                  // two-shot
        else if (t < L[3].start) K.cam(1120, 420, 2.1);            // Vask close-up
        else K.cam(960, 520, 1.15, { shake: t > OPEN && t < OPEN + .4 ? 12 : 0, t });
        K.lab(t, { potDrops: 1, green: K.seg(t, OPEN, OPEN + .2) });
        if (t > OPEN) K.portal(960, 560, 230, t, { open: K.popOpen(t - OPEN) });
        const press = tq >= w(4, 'out') && tq < w(4, 'out') + .2 ? 1 : 0;
        K.gary(K.G(T, t, { x: 740, look: K.speaker(T, t) === 'VASK' ? [.8, -.3] : [.3, -.1], nerv: t > OPEN ? 1 : .4 }));
        K.vask(K.V(T, t, { x: 1180, holdR: 'remote', armR: press ? { h: [80, -20], bend: 40 } : { h: [40, 110], bend: 40 }, press, look: [-.4, .1] }));
      } else {
        K.cam(960, 600, 1.3);
        moon(t);
        const gp = K.spit(K.G(T, t, { x: 740, nerv: 1.4, eyeS: 1.25, pupil: 2.2, sweat: t, mouthS: 1.4 }), t, CUT + .3, CUT + .8, [960, 300], 120);
        const vp = K.spit(K.V(T, t, { x: 1180, holdR: 'cup', cupP: K.C(T, t, {}) }), t, CUT + .45, CUT + .95, [960, 300], 100);
        if (gp) K.gary(gp);
        if (vp) K.vask(vp);
        K.portal(960, 300, 160, t, { open: 1 - K.ei(K.seg(t, CUT + 1.0, CUT + 1.3)) });
      }
      K.wipe(t, [CUT]);
      K.titleCard(t, 'Why Is The Sky Blue?', 0.2, 2.3);
      K.tag(t, tags);
      subs.draw(t);
    },
    cues: K.sounds([{ t: w(4, 'out'), type: 'click' }, { t: OPEN, type: 'portalOpen' }, { t: CUT - .16, type: 'whoosh' },
      { t: CUT + .3, type: 'pop' }, { t: CUT + .8, type: 'boing' }, { t: CUT + .95, type: 'thud' }, { t: CUT + 1.25, type: 'portalClose' }]),
    sfx: {},
  };
}
```
