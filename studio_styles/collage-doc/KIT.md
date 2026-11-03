THE KIT (K = window.CD): a hand-made documentary collage. Screen pixels: the frame is 1080 x 1920, (0, 0) top left,
y DOWN. Draw every frame from scratch, back to front.

THE PICTURE TRACK in the notes is binding: what the narrator says is what is on screen. Each entry gives a time (the
moment its word is spoken: use T.w(i, 'word')), the pictures, the big words and a ring or none. Cut or bring the picture
in at exactly that time and keep it until the next entry; a line with two entries changes picture mid-line. NO PICTURE
FOUND = keep the previous picture dimmed (or paper) with the big words; never fill in with an unrelated picture.

THE PICTURES: T.img[id] (already loaded; the list with sizes and a contact sheet comes with the script). Kinds:
plate (a full-bleed photo of a place), cutout (transparent PNG: a person, an arm, an object), document (a flat
letter / paper / map, rectangular), portrait (a real portrait, rectangular; frame it, caption it with the credit).
Use only ids from the list. Every K function skips a missing picture, so never test for them.

THE GROUND
- K.paper(ctx, t, { tone: 'light' | 'dark' }) the paper sheet (light = warm off-white; dark = dark board). Call it first
  every frame (it resets the canvas).
- K.plate(ctx, t, img, { t0, t1, z0: 1, z1: 1.08, x: .5, y: .5, dim: 0..1 }) a photo plate, full-bleed (cover), with
  its own slow push from t0 to t1; x / y = the focus point 0..1; dim darkens it (for words).
- K.view(ctx, t, { t0, t1, z0: 1, z1: 1.06, x0, y0, x1, y1 }, () => { ... }) a slow push (and pan, px) on everything
  drawn inside: wrap each scene in one. Push in (z1 > z0) or pull back (z0 > z1); never a static frame.

PIECES (each lands in stop-motion steps at `at`; shadows are automatic; `out` = when it leaves, fading)
- K.paste(ctx, t, img, { x, y, h | w, anchor: 'bottom' (x, y = where its feet touch) | 'center' | 'top', at,
  from: 'drop' (placed down onto the page, default) | 'pop' | 'left' | 'right' | 'top' | 'bottom' | 'none', dur: .5,
  rot (deg), flip, shadow: 1, out, path: [[t, x, y], ...] (it walks along these points in steps) })
- K.swing(ctx, t, img, { x, y (where the pivot sits on screen), h | w, pivot: [px, py] (0..1 of the picture: the
  shoulder of an arm, e.g. [.5, 1] when the arm enters from the bottom), keys: [[t, deg], ...], at, from, flip, out })
  an arm / hand / lever turning about its pivot in small steps: claps, waves, a hand reaching, a door. Key the hits to
  words (T.w).
- K.photo(ctx, t, img, { x, y (centre), w, rot: -2, at, from: 'drop', border: 18, tape: true, out }) a printed
  photo / document with a white border and tape.
- K.frame(ctx, t, img, { x, y (centre), w, at, style: 'gilt' | 'black', out }) a framed portrait hung on the wall.

WORDS (Playfair Display italic; white with a soft shadow by default: pass color: K.C.ink on light paper)
- K.words(ctx, t, T.lines[i], { x: 540, y (first baseline), size: 96, maxW: 900, big: ['word'], only: ['word', ...],
  color, font: 'display' | 'light' | 'roman', out }) the line's words appear EXACTLY as they are spoken, wrapped and
  centred; `big` = bigger; `only` = show just those words (e.g. only: ['no', 'sound']).
- K.word(ctx, t, 'never sent', at, { x, y, size: 150, color, rot, out }) one word / phrase landing at `at`.
- K.caption(ctx, t, 'Ludwig van Beethoven (1770–1827)', at, { x, y, size: 42, color }) a small museum-label line
  (use it under the portrait; add the credit line under it, size 26).
- K.measure(text, size, font) -> its width in px (to place a ring around a word).
- K.scrim(ctx, { y, h: 420, alpha: .45 }) a soft dark band behind words on a busy photo.
- K.credits(ctx, t, T.images, at, { y: 1760 }) the picture credits in small type: ALWAYS call it for the last 2.5 s
  (at = T.end - 2.5), after the scenes and before K.finish (archive photos must be credited on screen).

HAND-DRAWN MARKS (white pen, drawn on over `dur`; color / width optional)
- K.ringWord(ctx, t, 'never sent', at, { x, y, size, font }) a ring fitted around a word set with K.word at the same
  x, y, size (use this for words: it always sits on the word).
- K.ring(ctx, t, { x, y (centre), w, h, at, dur: .5, rot: -6, out }) a loose ring around an object in a picture (its
  box on screen).
- RINGS ONLY WHERE THE SCENE PLAN SAYS "ring: <word>", at the moment that word is spoken, around that word or object.
  "ring: none" = no ring in that scene. Never a ring around empty space or as decoration.
- K.underline(ctx, t, { x0, x1, y, at, dur: .35 }), K.arrow(ctx, t, { from: [x, y], to: [x, y], bend: .2, at }),
  K.strike(ctx, t, { x, y, w, at }) (a cross-out).

CUTS AND FINISH
- K.tear(ctx, t, at, { dur: .5, tone: 'light' | 'dark' }) a torn-paper cut: call it AFTER the scenes (near the end of
  seek) for each torn cut time; the sheet covers the old scene and uncovers the new one around `at`.
- K.finish(ctx, t, { fadeIn: .4, fadeOut: [t0, t1] }) grain, dust, vignette, fades. Call it LAST.
- Helpers: K.seg, K.ss, K.eo, K.eio, K.back, K.lerp, K.clamp, K.step(t) (stop-motion time), K.C (paper, ink, white).

SOUND: cues: K.sounds([{ t, type, v, d }]) with type in paper (a piece lands), pen (a mark is drawn; d = its dur), word
(a big word lands), tear (a torn cut), frame (a frame / photo lands), swing (an arm moves; on each hit), riser (d, into
the last line), hit (the last word). sfx: {}.

LAYOUT: keep words inside x 90-990 and y 200-1650 (the bottom is under the phone UI). Pieces may bleed off the edges
(arms entering from the sides look right). Big words go where the picture is calm (sky, wall, floor, dark paper).

A WORKED EXAMPLE (4 lines: the applause, no sound, the letter, the portrait):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w, I = T.img;
  const cut = [0, L[1].start, L[2].start, L[3].start, T.end];       // a scene per line, cut on its first word
  const clap = w(0, 'applause');
  return {
    seek(t, ctx) {
      if (t < cut[1]) {                     // 1: two giant arms clap over a tiny man on paper
        K.paper(ctx, t);
        K.view(ctx, t, { t0: 0, t1: cut[1], z0: 1, z1: 1.06 }, () => {
          K.paste(ctx, t, I.man_back, { x: 540, y: 1480, h: 320, at: .1 });
          K.swing(ctx, t, I.arm, { x: 150, y: 1180, h: 900, pivot: [.5, 1], at: .2, from: 'left',
            keys: [[0, -20], [clap, 4], [clap + .25, -16], [clap + .5, 4]] });
          K.swing(ctx, t, I.arm, { x: 930, y: 1180, h: 900, pivot: [.5, 1], flip: true, at: .2, from: 'right',
            keys: [[0, 20], [clap, -4], [clap + .25, 16], [clap + .5, -4]] });
          K.words(ctx, t, L[0], { y: 330, size: 92, color: K.C.ink, big: ['applause'] });
        });
      } else if (t < cut[2]) {              // 2: the hall from the stage
        K.paper(ctx, t);
        K.view(ctx, t, { t0: cut[1], t1: cut[2], z0: 1, z1: 1.1 }, () => {
          K.plate(ctx, t, I.hall_from_stage, { t0: cut[1], t1: cut[2] });
          K.paste(ctx, t, I.man_back, { x: 560, y: 1940, h: 1050, at: cut[1], from: 'bottom', dur: .35 });
          K.word(ctx, t, 'no sound', w(1, 'no'), { y: 400, size: 170 });
        });
      } else if (t < cut[3]) {              // 3: the letter, a ring around "never sent"
        K.paper(ctx, t, { tone: 'dark' });
        K.view(ctx, t, { t0: cut[2], t1: cut[3], z0: 1, z1: 1.06 }, () => {
          K.photo(ctx, t, I.letter, { x: 540, y: 900, w: 820, rot: -3, at: cut[2] });
          K.scrim(ctx, { y: 1500, h: 380 });
          K.word(ctx, t, 'never sent', w(2, 'never'), { y: 1540, size: 150 });
          K.ringWord(ctx, t, 'never sent', w(2, 'sent'), { y: 1540, size: 150 });
        });
      } else {                              // 4: the payoff: the real face, framed
        K.paper(ctx, t, { tone: 'dark' });
        K.view(ctx, t, { t0: cut[3], t1: T.end, z0: 1.1, z1: 1 }, () => {
          K.frame(ctx, t, I.portrait, { x: 540, y: 860, w: 640, at: cut[3] });
          K.caption(ctx, t, 'Ludwig van Beethoven (1770–1827)', cut[3] + .6, { y: 1420 });
          K.caption(ctx, t, T.images.find(m => m.id === 'portrait')?.credit || '', cut[3] + .6, { y: 1470, size: 26 });
        });
      }
      K.tear(ctx, t, cut[2]);               // one torn-paper cut; the others are hard cuts
      K.credits(ctx, t, T.images, T.end - 2.5);
      K.finish(ctx, t, { fadeOut: [T.end - .5, T.end] });
    },
    cues: K.sounds([{ t: .1, type: 'paper' }, { t: clap, type: 'swing' }, { t: clap + .5, type: 'swing' },
      { t: cut[1], type: 'paper' }, { t: w(1, 'no'), type: 'word' }, { t: cut[2], type: 'tear' },
      { t: w(2, 'sent'), type: 'pen', d: .5 }, { t: cut[3], type: 'frame' }, { t: cut[3] - 1.2, type: 'riser', d: 1.2 },
      { t: w(3, L[3].words.at(-1).w), type: 'hit' }]),
    sfx: {},
  };
}
```
