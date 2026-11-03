THE KIT (K = window.CD): a hand-made documentary collage. Screen pixels: the frame is 1920 x 1080 (a 16:9 long video; you animate ONE PART of it: T.lines, 0 to T.end), (0, 0) top left,
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
- K.credits(ctx, t, T.images, at, { color }) the picture credits in small type (on light paper pass color: K.C.ink):
  ALWAYS call it for the last 2.5 s
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

LAYOUT: keep words inside x 120-1800 and y 120-960 (the bottom 120 px stays clear for the player bar). Cut-outs stand on
y 1000-1080 (or bleed off the bottom); a photo print is 700-1100 px wide. Big words go beside the subject, not on it.

(Use the reel example's structure: a scene per picture-track entry, cut on its word; coordinates for 1920 x 1080.)
