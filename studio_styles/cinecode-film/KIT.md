THE KIT (K = window.CC): cinecode films drawn in code. Frame 1920 x 1080 px, (0, 0) top left, y DOWN. Draw every frame
from scratch. You animate ONE PART of a long video: its lines are T.lines, it starts at 0 and ends at T.end. The look is
already set (T.look; K.LOOK_ID); its palette is K.P = { bg, paper, ink, main, second, accent, soft } and its type roles
are 'display' | 'text' | 'mono' | 'hand'. Use only these colours (plus K.P.* tints of them); some looks add named
extras the recipe needs (e.g. K.P.hi, K.P.leaf, K.P.sea, K.P.road, K.P.high, K.P.glass, K.P.wood, K.P.plate, K.P.deep).
Print looks (halftone-dossier, risograph) print display type twice with an offset plate; sticker-explainer cards
carry a thick white sticker border on their own.
THE LOOK'S ENGINE: K.LOOK.mode is '3d' (build the subject in three.js on K.stage, 2D type and marks over it) or '2d'
(a 2D world under K.cam2 / K.view). Follow it; a 2D look may still use a small K.stage for one 3D object, and a 3D look
uses 2D cards for statements and numbers.

THE SHOT PLAN in the notes is binding: what is said is what is shown, each shot starting on its word (T.w(i, 'word', nth));
build what the shot names, with its device, its camera line and its text.

2D (any look):
  K.bg(ctx)                                         the look's ground (paper, cyanotype sheet, dark stage, flat page,
                                                    light table, marker board, halftone newsprint, orbital terrain, studio sweep)
  const cm = K.cam2(t, [[t, cx, cy, zoom], ...])    a camera over a WORLD drawn in px (zoom 1 = the frame); keys eased
  K.view(ctx, cm, g => { ...draw in world px... })  everything inside moves with the camera; the world can be wider
                                                    than the frame (lay shots out side by side and travel between them)
  K.card(g, t, { x, y (centre), w, h, at, out, rot, color, torn, draw: (q, w, h) => {} })   a card / tile / sheet that
                                                    drops in (q draws inside it in card px)
  K.text(g, t, { text, x, y (top), w, h (the box), size, role, color, align, valign: 'middle', at, out,
                 reveal: 'words' | 'fade' | 'wipe', halo })   returns { w, h, size }; shrinks to fit, reports overflow
  K.statement(g, t, { text, x, y (centre), w: 1100, size: 120, at, out, color })   the one line to remember, on its strip
  K.title(ctx, t, { text, kicker: 'PART 2', at, out })                               a chapter card (only at a part start)
  K.stroke(g, t, { pts: [[x, y], ...] | circle: { x, y, r } | arrow: [[x0, y0], [x1, y1]], at, dur, color, width, dash })
                                                    a line / marker circle / curved arrow that draws itself
  K.highlight(g, t, { x, y, w, h, at, dur })        a highlighter bar (draw it BEFORE the words it marks)
  K.label(g, t, { x, y (the point), text, at, out, dx: 120, dy: -90 })               a dot, a leader and a tag
  K.counter(g, t, { x, y (centre), from: 0, to, at, dur: 1.6, size: 160, prefix, suffix, decimals, role, align, group })
                                                    (a bare year 1000-2199 counts without a comma; group forces it)
  K.bars(g, t, { x, y (bottom-left), w, h, values, labels, at, stagger, max, accentIndex, unit, prefix })
  K.plot(g, t, { x, y (bottom-left), w, h, values, min, max, at, dur: 2, labels: [first, last] })
  K.grid(g, t, { x, y (top-left), cols, rows, n (lit), size, gap, at, shape: 'dot' | 'person' | 'square', mark: [i] })
  K.panel(g, t, { x, y (centre), w, h, at, out, title, draw: (q, w, h) => {} })     a UI window
  K.measure(text, role, px), K.fit(text, role, size, maxW, maxH), K.font(role, px)
3D (K.LOOK.mode '3d', or one object in a 2D look):
  const S = K.stage({ fov: 35, ortho })             ONCE in film(); the look's light, materials and post chain
  S.add(obj, ...)                                   meshes cast / receive shadows
  K.ground(size, { color }), K.box(w, h, d, { color }), K.ball(r, { color }), K.cyl(r, h, { color, top }),
  K.cone(r, h, { color }), K.building(w, h, d, { roof: 'flat' | 'pitched', color, roofColor }), K.tree(h),
  K.person({ h: 1.75, color }) (no face), K.ring(r, { color }) (a flat ring on the ground), K.group(...kids),
  K.wire(obj, { color, opacity }) (glowing edges, for hologram), K.mat(color) (a material in the look), K.THREE
  K.scan(obj, { n: 30000, size: .06, axis: 'x', colors: [low, high] }) → THREE.Points: the object's surfaces as a lidar
  point cloud coloured by height (lidar-survey; S.add the points, not the meshes); pts.userData.sweep(k) each frame shows
  the share k of the points in order along the axis (the scanner's front passing)
  Everything sits on y = 0, in metres. Build the whole part's world in film(); per frame only move / show things.
  K.pop(obj, t, at, { how: 'pop' | 'rise', dur, out })   arrival (scale with overshoot, or rise from below); hides it
                                                    before `at` and after `out`
  Per frame: set the camera, then S.render(ctx, t), then the 2D overlays:
    S.iso([x, y, z], size, azimuthDeg = 45, elevationDeg = 35)        ortho looks (iso-infographic, lowpoly-island)
    K.MOVE.apply(S.cam, { position, target, fov, roll, offset })      perspective looks, with the cinecode moves:
      K.MOVE.dolly(pos, target, e, d0, d1) · truck(pos, target, e, a, b) → { position, target } · crane(...) → {..} ·
      pan / tilt(pos, target, e, a, b) · orbit(target, e, r, az0, az1, h) · dollyZoom(e, d0, d1, fov0) → { distance, fov }
      · pushTo(pos, target, detail, e, endDistance) → { position, target } · handheld(t, amount) → { offset, roll }
      · K.MOVE.EASE.inOut / out / in / inertia(k), K.MOVE.progress(t, from, to)
  S.lookAt([x, y, z]) keeps the shadow on what the shot looks at; S.project([x, y, z]) → [px, py] for labels;
  S.toggle('bloom' | 'vignette' | 'grain', on)
FINISH (after everything): K.grade(ctx, t) in 2D looks (grain, vignette; 3D has it in the chain), K.wipe(ctx, t, at)
(between big ideas only), K.finish(ctx, t, { end: T.end }) last.
Helpers: K.held(t) (the look's stepped time: use it for drawn things in looks with hold 2), K.seg, K.ss, K.eo, K.eio,
K.back, K.lerp, K.clamp, K.mulberry(seed), K.typeTime(text).

RULES: keep text inside x 96..1824, y 54..1026 and off the subject; at most one statement on screen; labels on leader
lines next to the thing they name; a fresh framing at every shot (a new camera key or a new place in the world).

SOUND: cues: K.sounds([{ t, type, v, d }]) with type in type (text landing; d = K.typeTime(text)), whoosh (a camera move,
a wipe), pop (a card, a label, an arrival), hit (a verdict, a key number), ding (a counter landing), splat (K.wipe).
sfx: {}.

A WORKED EXAMPLE (2D look, 3 lines: a hook number, a chart, a statement):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w, s1 = L[1].start, s2 = L[2].start;
  return {
    seek(t, ctx) {
      K.bg(ctx);
      const cm = K.cam2(t, [[0, 960, 540, 1.04], [s1 - .3, 1000, 540, 1], [s1 + .4, 2900, 560, 1], [s2 - .3, 2960, 540, 1.05], [s2 + .4, 4800, 540, 1], [T.end, 4840, 540, 1.04]]);
      K.view(ctx, cm, g => {
        K.counter(g, t, { x: 960, y: 480, to: 2.1, decimals: 1, suffix: ' billion', at: w(0, 'billion') - .6, size: 170 });
        K.text(g, t, { text: 'cups of coffee a day', x: 960, y: 600, w: 900, h: 80, size: 54, align: 'center', at: w(0, 'cups') });
        K.bars(g, t, { x: 2500, y: 820, w: 800, h: 460, values: [12, 19, 41], labels: ['1990', '2005', '2024'], unit: '%', accentIndex: 2, at: w(1, 'rose') });
        K.stroke(g, t, { circle: { x: 3240, y: 420, r: 110 }, at: w(1, 'doubled') });
        K.statement(g, t, { text: 'THE CUP GOT SMALLER', x: 4800, y: 540, at: s2 + .2 });
      });
      K.grade(ctx, t);
      K.finish(ctx, t, { end: T.end });
    },
    cues: K.sounds([{ t: w(0, 'billion') - .6, type: 'pop' }, { t: w(0, 'billion') + 1, type: 'ding' }, { t: s1 - .3, type: 'whoosh' },
      { t: w(1, 'doubled'), type: 'hit' }, { t: s2 - .3, type: 'whoosh' }, { t: s2 + .2, type: 'pop' }]),
    sfx: {},
  };
}
```
A 3D look builds its world once (`const S = K.stage({}); S.add(K.ground(80), ...)`), then per frame: K.pop(...) for each
arrival, the camera for the current shot (one move per shot, keyed to its word), S.render(ctx, t), labels at
S.project(...), statements and counters in 2D, K.finish.
