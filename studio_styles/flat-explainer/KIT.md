THE KIT (K = window.FX): flat vector explainer scenes. Frame 1920 x 1080 px, (0, 0) top left, y DOWN. Draw every
frame from scratch. You animate ONE PART of a long video: its lines are T.lines, it starts at 0 and ends at T.end.

THE PICTURES: T.img[id] (already loaded). T.images = [{ id, kind: 'place' | 'character' | 'prop', w, h, boards, use }].
- place: a full plate (an empty location). boards = its blank surfaces measured in frame px: [{ kind: 'board' |
  'screen', x, y, w, h }] (also drawn and numbered on the contact sheet; some may be false, e.g. a white doorway: only
  use the ones that really are boards, signs or screens).
- character: a cut-out in one pose (feet at the bottom of the picture). prop: an object cut-out.
Use only ids from the list; every K function skips a missing picture.

TEXT LENGTHS (the kit shrinks text to fit and reports anything still too long): a board / sign 1-5 words, a headline
2-7 words, a date card a year or a short date. Characters: only ids that exist in T.img (the list and the contact sheet);
every shot that names a character shows it, standing on the floor, never cropped by the frame edge.

THE SHOT PLAN in the notes is binding: what is said is what is shown, each shot starting on its word (T.w(i, 'word',
nth)); the place, who acts, the text and its surface, the marks.

A SCENE (the plate and everything on it, through one drifting camera):
    const cm = K.cam(t, { t0, t1, z0: 1, z1: 1.04, x0: .5, y0: .5, x1: .5, y1: .5 })   // zoom 1-1.08, focus 0..1
    K.scene(ctx, t, T.img.lab, cm, g => {
      K.write(g, t, board, 'TEXT', at)          // on one of the plate's measured boards (frame px, moves with the plate)
      K.char(g, t, T.img.sci_point, { x, y (feet), h, at, arrive: 'spring' | 'squash' | 'puff' | 'pop' | 'none', flip,
        talk: [t0, t1], jump: [t, ...], turn: [t, ...], walk: [[t, x], ...], lean, out })
      K.prop(g, t, T.img.coin, { x, y (centre), h, at, arrive, rot, float, out })
      K.sign(g, t, { kind: 'post' | 'hanging' | 'board' | 'chalk' | 'screen', x, y (face centre), w, h, text, at, out })
      K.redX(g, t, { x, y, size: 260, at }); K.tick(g, t, { x, y, size, at }); K.bang(g, t, { x, y, at, ch: '!' })
      K.counter(g, t, { x, y, from: 0, to, at, dur: 1.6, size: 90, prefix, suffix, color })
      K.puff(g, t, { x, y, at, size })
    })
Characters stand on the plate's floor: feet y ≈ 960-1050, height 520-820 px (a near character is taller). Keep faces
clear of text and of the frame edge. One character talks at a time (talk: the span of their line).

FULL-FRAME, after the scene:
- K.dateCard(ctx, t, '1858', at) a white card top left with an orange calendar (every date).
- K.spot(ctx, t, { x, y, r: 300, at }) a spotlight reveal (the subject under it).
- K.headline(ctx, t, 'SO HOW DOES IT WORK?', at, { bg: 'orange' | 'purple', marks: '?' | '!' | '' }) instead of a scene
  for its shot (it fills the frame).
- K.splat(ctx, t, at) a white splat wipe around `at` (between big ideas only).
- K.finish(ctx, t, { fadeIn: .2, end: T.end }) last (a short white fade at the very start / end of the part).
- Helpers: K.typeTime(text, cps) (how long typing takes), K.seg, K.ss, K.eo, K.back, K.lerp, K.clamp, K.C.

SOUND: cues: K.sounds([{ t, type, v, d }]) with type in type (typing a sign; d = K.typeTime(text)), whoosh (a cut with
a move, a drop, a wipe), pop (a sign, an icon, an arrival), hit (a red X), ding (a tick, a counter landing), splat (a
wipe), jump. sfx: {}.

A WORKED EXAMPLE (3 lines: a hook, the wrong idea X'd, a headline):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w, I = T.img, box = id => (T.images.find(m => m.id === id) || {}).boards || [];
  const s1 = L[1].start, s2 = L[2].start;
  return {
    seek(t, ctx) {
      if (t < s2) {
        const cm = K.cam(t, { t0: 0, t1: s2, z0: 1, z1: 1.05, x0: .45, x1: .52 });
        K.scene(ctx, t, I.lab, cm, g => {
          K.write(g, t, box('lab')[0], 'YOU USE 10% OF YOUR BRAIN', w(0, 'use'));
          K.char(g, t, I.viewer_front, { x: 1450, y: 1040, h: 640, at: 0, arrive: 'squash', talk: [L[0].start, L[0].end], jump: [s1 + .2] });
          K.char(g, t, I.scientist_point, { x: 420, y: 1040, h: 760, at: s1 - .2, arrive: 'puff', talk: [s1, L[1].end] });
          K.redX(g, t, { x: 965, y: 415, size: 300, at: w(1, 'wrong') });
          K.bang(g, t, { x: 1450, y: 360, at: w(1, 'wrong') + .2 });
        });
      } else K.headline(ctx, t, 'So what does the rest do?', s2, { bg: 'purple', marks: '?' });
      K.splat(ctx, t, s2);
      K.finish(ctx, t, { end: T.end });
    },
    cues: K.sounds([{ t: w(0, 'use'), type: 'type', d: K.typeTime('YOU USE 10% OF YOUR BRAIN') }, { t: s1 - .2, type: 'pop' },
      { t: w(1, 'wrong'), type: 'hit' }, { t: s2, type: 'splat' }, { t: s2, type: 'type', d: K.typeTime('So what does the rest do?') }]),
    sfx: {},
  };
}
```
