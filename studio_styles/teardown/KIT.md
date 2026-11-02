THE KIT (K = window.TD): a three.js studio packshot. You build the product ONCE in film() from parametric parts in
MILLIMETRES (y up, the floor is y = 0, the product centred on x = z = 0), then every frame you set the explode amount,
move the camera, render, and draw labels and dimension lines on top.

BUILD (in film(), once):
- const S = K.studio({ accent: '#ff6b3d', bg: ['#34363a', '#0d0e10'], exposure: 1 }) the studio: a graphite sweep,
  a warm key light with a soft contact shadow, a cool rim that follows the camera, studio reflections.
- S.add(part) puts a part in the scene and returns it. Every part is a THREE.Group sitting on y = 0, centred in x / z;
  place it with part.position.set(x, y, z), turn it with part.rotation.y = angle (radians).
- Parts (all sizes in mm; m = a material):
  K.block(w, h, d, { r: corner radius, m }) a rounded block (lids, housings, chips, buttons, batteries);
  K.shell(w, h, d, { t: wall, r: corner radius, m }) an open tray (a bottom case: walls + floor);
  K.plate(w, d, thickness, { r, holes: [[x, z, radius], ...], m }) a flat plate with holes (frames, shields);
  K.board(w, d, { t: 1.6, seed, color: '#1f5b3a', chips: [[x, z, w, d, h], ...] }) a circuit board with traces, pads
    and silkscreen painted in code, and its chips placed on it (positions relative to the board centre);
  K.cyl(r, h, { axis: 'y' | 'x' | 'z', m }) a cylinder (cells, motors, knobs, wheels, capacitors; axis 'z' lies along z);
  K.screw(length, headRadius); K.lens(r, h); K.keycap(w, d, h, { m }); K.fan(r, blades, { m });
  K.ribbon([x, y, z], [x, y, z], width) a flex cable arching between two points;
  K.grid(make, rows, cols, pitchX, pitchZ) the same part repeated (keys, cells): make(r, c) returns a part;
    grid.userData.items = the parts (for K.wave).
  Raw three.js works too: K.THREE (e.g. new K.THREE.Mesh(new K.THREE.TorusGeometry(...), K.mat.metal())).
- Materials: K.mat.plastic(color, roughness .55-.7), K.mat.metal(color, roughness), K.mat.anodized(color),
  K.mat.rubber(color), K.mat.glass(), K.mat.screen(color, glowColor, k), K.mat.emissive(color, k) (LEDs),
  K.mat.copper(), K.mat.gold(), K.mat.chip(). Black plastics: use a dark grey ('#2c2f34'), never pure black.
- The explode: const explode = K.stack([{ obj, y: assembled height of its base, gap: how far it lifts }, ...]) listed
  BOTTOM FIRST; explode(k, t) with k 0 = assembled, 1 = apart (the top layer leaves first; when apart, layers float
  gently). K.wave(items, k, { lift, spread, from: [x, z] }) lifts repeated parts in a wave.
- The camera: const cam = K.orbit([[t, azimuthDeg, elevationDeg, distance, [targetX, targetY, targetZ]], ...]) eased
  without overshoot; cam(S, t) every frame. azimuth 0 = from the front (+z), 90 = from the right; elevation 15-50.
- subs = K.subtitles(T).

PER FRAME (seek(t, ctx)), in this order:
    explode(k, t); cam(S, t); S.render(ctx);           // the 3D picture
    K.label(ctx, S, point, { idx: '01', name, spec, side: 'left' | 'right', y: 0.25..0.7, a: 0..1 });
    K.dimension(ctx, S, [x, y, z], [x, y, z], '35 mm', { a: 0..1, off: [dx, dy, dz] });
    K.title(ctx, 'Title', 'SUBLINE', a);              // only while the product is closed, first 2-3 s
    subs.draw(ctx, t);                                  // last
- point = a 3D point on the part: K.worldOf(part, [localX, localY, localZ]) follows the part as it lifts.
- a (appearance) = K.ss(K.seg(t, t0, t0 + .7)) * (1 - K.ss(K.seg(t, t1 - .3, t1))) to open a label on its word and
  close it before the parts move again. At most 2 labels open at once, on opposite sides.
- Helpers: K.seg(t, a, b), K.ss, K.eo, K.ei, K.eio, K.lerp, K.clamp, K.mulberry(seed) (build time only).

SOUND: cues: K.sounds([{ t, type, v, d }]) with type in lift (layers rising), land (a layer seating), clack (plastic),
click (a switch), tick (a label opening), hiss (a dimension line drawing; d = length), thud (the case closing),
whoosh (a camera dive). sfx: {}.

COST: CPU rendering; keep the scene under ~150 parts (a grid of 60 keys is fine), no more than 2 boards.

A WORKED EXAMPLE (a wireless mouse, 5 layers):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w;
  const S = K.studio({ accent: '#ff6b3d' });
  // a wireless mouse, 62 x 35 x 112 mm, built from published-style dimensions (a model)
  const base = S.add(K.shell(62, 9, 112, { t: 2, r: 26, m: K.mat.plastic('#2c2f34', .6) }));
  const battery = S.add(K.cyl(7.2, 50, { axis: 'z', m: K.mat.metal('#c9a24a', .35) }));
  battery.position.set(0, 0, 18);
  const pcb = S.add(K.board(52, 70, { seed: 7, chips: [[8, -18, 7, 7, 1.2], [-10, 6, 9, 6, 1.6], [12, 14, 4, 3, .8]] }));
  const wheel = S.add(K.cyl(9, 7, { axis: 'x', m: K.mat.rubber('#3a3a3c') }));
  const top = S.add(K.block(62, 12, 112, { r: 8, m: K.mat.plastic('#e7e4dd', .55) }));
  const layers = [
    { obj: base, y: 0, gap: 0 },
    { obj: battery, y: 3, gap: 34 },
    { obj: pcb, y: 17, gap: 70 },
    { obj: wheel, y: 19, gap: 104 },
    { obj: top, y: 23, gap: 140 },
  ];
  const explode = K.stack(layers);
  const OPEN = w(1, 'lifts'), CLOSE = L[6].start - 1.6;
  const cam = K.orbit([
    [0, 30, 24, 520, [0, 15, 0]], [OPEN, 40, 24, 600, [0, 60, 0]], [L[2].start, 55, 24, 640, [0, 80, 0]],
    [L[3].start, 65, 34, 440, [0, 80, 0]], [L[4].start + .5, 70, 48, 300, [0, 88, -10]], [L[5].start, 90, 20, 520, [0, 50, 10]],
    [CLOSE, 110, 24, 560, [0, 40, 0]], [T.end, 130, 26, 480, [0, 18, 0]],
  ]);
  const subs = K.subtitles(T);
  const lab = (t, a0, a1) => K.ss(K.seg(t, a0, a0 + .7)) * (1 - K.ss(K.seg(t, a1 - .3, a1)));
  return {
    seek(t, ctx) {
      explode(K.seg(t, OPEN, OPEN + 2.2) * (1 - K.seg(t, CLOSE, CLOSE + 1.3)), t);
      cam(S, t);
      S.render(ctx);
      K.label(ctx, S, K.worldOf(top, [0, 12, -20]), { idx: '01', name: 'Top shell', spec: 'ABS · 2 buttons', side: 'right', y: .3, a: lab(t, L[1].start + .5, L[2].start + .2) });
      K.label(ctx, S, K.worldOf(wheel, [0, 9, 0]), { idx: '02', name: 'Scroll wheel', spec: 'rubber tyre · Ø18 mm', side: 'left', y: .32, a: lab(t, w(2, 'scroll'), L[3].start + .2) });
      K.label(ctx, S, K.worldOf(pcb, [-10, 3, 6]), { idx: '03', name: 'Radio chip', spec: '2.4 GHz', side: 'left', y: .55, a: lab(t, w(3, 'radio'), L[4].end) });
      K.label(ctx, S, K.worldOf(pcb, [8, 3, -18]), { idx: '04', name: 'Optical sensor', spec: 'images the desk', side: 'right', y: .62, a: lab(t, w(3, 'optical'), L[4].end) });
      K.label(ctx, S, K.worldOf(battery, [0, 14, 0]), { idx: '05', name: 'AA cell', spec: '1.5 V · 50 x 14 mm', side: 'right', y: .5, a: lab(t, w(5, 'AA'), L[6].start) });
      K.dimension(ctx, S, [40, 0, 56], [40, 35, 56], '35 mm', { a: K.seg(t, w(6, 'thirty'), w(6, 'thirty') + 1.2) });
      K.title(ctx, 'Inside a mouse', 'TEARDOWN · 5 LAYERS', K.ss(K.seg(t, .2, .8)) * (1 - K.ss(K.seg(t, OPEN - .4, OPEN))));
      subs.draw(ctx, t);
    },
    cues: K.sounds([{ t: OPEN, type: 'lift' }, { t: OPEN + .3, type: 'lift', v: .7 }, { t: L[1].start + .5, type: 'tick' }, { t: w(2, 'scroll'), type: 'tick' },
      { t: w(3, 'radio'), type: 'tick' }, { t: w(3, 'optical'), type: 'tick' }, { t: w(4, 'pictures'), type: 'whoosh' }, { t: w(5, 'AA'), type: 'tick' },
      { t: CLOSE + .9, type: 'land' }, { t: CLOSE + 1.1, type: 'clack' }, { t: CLOSE + 1.3, type: 'thud' }, { t: w(6, 'thirty'), type: 'hiss', d: 1.0 }]),
    sfx: {},
  };
}
```
