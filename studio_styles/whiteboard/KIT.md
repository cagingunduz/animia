THE KIT: window.WB (passed to your film as K). The lemo-opuscar whiteboard engine, deterministic in t.

THE SCREEN IS TALL AND NARROW (1080 x 1920), NOT 1920 x 1080. At zoom z the camera shows 1080 / z board units across
and 1920 / z down, centred on the camera key's (x, y). So at zoom 1 everything the viewer must see in a shot fits in
x = camX ± 450 and y = camY - 800 .. camY + 650 (the bottom 300 px are the subtitles). Lay the board out as a tall
column: one region under the other (about 900 wide, 800-1200 tall each), all centred on the same x (e.g. 1500), and
point each camera key at the centre of the region being drawn. Never place two things side by side wider than 900
units at zoom 1; for a wider drawing, zoom out (z = 900 / its width). Text caps: 120-170 for a title, 50-90 for labels.

SHAPES (world units; they return Stroke or Stroke[]; options: w (width, 6-11 for drawing), color, jitter, over
(corner overshoot), bow, lap (circle overlap past closure), alpha):
- K.line(x0, y0, x1, y1, o), K.poly([[x, y], ...], o), K.curve([[x, y], ...], o) (smoothed), K.arc(cx, cy, r, a0, a1, o),
  K.circle(cx, cy, r, o), K.rect(x, y, w, h, o) (four strokes), K.roundRect(x, y, w, h, r, o) (one stroke),
  K.arrow(x0, y0, x1, y1, { curve: [cx, cy], head: 34, ...o }) (shaft + two head strokes), K.dashed([[x, y], ...], { dash, gap }),
  K.hatch(polygonPoints, o) (a zig-zag scribble fill).
- K.text(str, x, y, { h: capHeight, align: 'left' | 'center' | 'right', color, w }) handwriting in stroke order (y is
  the baseline). It returns strokes with .width (world units) so you can lay out next to it.
- Colours: K.INK.black '#23262c', K.INK.blue '#2a5cb3', K.INK.orange '#d97757', K.INK.red '#c8413a', K.INK.green '#2e7a4d'.

PENS AND TIME
- const B = new K.Pen('black', K.INK.black), O = new K.Pen('orange', K.INK.orange), U = new K.Pen('blue', K.INK.blue);
  (ids 'black' / 'orange' / 'blue' pick the marker sound). A pen floats in, draws, hops and parks off-frame by itself.
- const tl = new K.Timeline(); tl.draw(pen, shapes, t0, { by: t1 }) schedules the strokes from t0 and solves the hand
  speed so they finish exactly at t1 (keep t1 - t0 ≥ 0.3 s for a word, ≥ 1.2 s for a drawing; one pen can't draw two
  things at once: give overlapping jobs to another pen). Without by, it draws at a natural speed. Returns the end time.
- tl.erase(K.zigzag(x, y, w, h, 5), t, dur, { width: 150, strength: .9 }) wipes a box with the felt eraser (a ghost
  remains). tl.cue(t, 'magnet' | 'erase' | 'rewind' | 'whoosh', { big: 1 }) adds a prop sound. Call tl.end() after the
  last draw.

THE BOARD, CAMERA AND OVERLAYS
- const board = new K.Board(tl, { W: 3000, H: 7000, ghosts: K.ghosts(3000, 7000, 36) }) (W x H = board size).
- const cam = new K.Camera([[t, x, y, zoom, roll, ease], ...]): keys in time order; (x, y) is the board point at the
  centre of the screen; ease 'io' (default) | 'i' | 'o' | 'l' (linear) | 'h' (hold then cut). Moves interpolate in 1/z,
  so pushes feel like dollies. Keep zoom 0.7-1.4 for reading; 0.25-0.4 for a full-board view.
- board.objs.push({ draw: (ctx, t, c) => { ... } }) draws physical things in world: the markers
  (for (const p of [B, O, U]) K.drawMarker(ctx, p, K.penPose(p, t, cam), c, t)), the eraser
  (for (const e of tl.erasers) K.drawEraser(ctx, e, t, c)), magnets (K.drawPinMagnet(ctx, x, y, c, { size: 150, lift: 0..1,
  color })). Move a magnet by computing its x, y and lift from t yourself (drop: lift 1 -> 0 over 0.25 s + a 'magnet' cue).
- board.overlays.push(K.subtitles(T)) burns the subtitles (always add it, last).
- const render = K.renderer(board, cam) renders a frame with camera motion blur on whips.
- Helpers: K.clamp, K.lerp, K.seg(t, a, b) (0..1), K.ss (smoothstep), K.eio, K.eo, K.ei, K.back, K.spring, K.mulberry(seed).

YOUR FILM returns { seek: (t, ctx) => render(ctx, t), cues: K.soundCues(tl, cam), sfx: {} }.
`cues` makes every stroke, wipe and magnet sound; sfx can add effects keyed to words:
{ sfx: [{ at: 'word@lineIndex', type: 'whoosh' | 'pop' | 'chime' | 'impact' | 'tick', vol: 0.6 }] } (few, 0-6).

WORKED EXAMPLE (a different topic: copy the technique, never the content)
```js
function film(K, T, c) {
  const INK = K.INK, tl = new K.Timeline();
  const B = new K.Pen('black', INK.black), O = new K.Pen('orange', INK.orange), U = new K.Pen('blue', INK.blue);
  const BW = 3000, BH = 7000;
  // region 1 (top): the question, written on the words that say it
  tl.draw(B, K.text('Why is the', 1500, 900, { h: 120, align: 'center' }), T.w(0, 'why') - 0.1, { by: T.w(0, 'sky') });
  tl.draw(B, K.text('sky blue?', 1500, 1100, { h: 160, align: 'center' }), T.w(0, 'sky'), { by: T.lines[0].end + 0.2 });
  tl.draw(O, K.circle(1500, 1010, 470, { w: 10, lap: .3 }), T.lines[0].end + 0.2, { by: T.lines[0].end + 1.0 });
  // region 2 (below): the sun and its colours, the camera travels down to it
  const sun = [K.circle(1250, 2350, 130, { w: 11 })];
  for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4; sun.push(K.line(1250 + Math.cos(a) * 170, 2350 + Math.sin(a) * 170, 1250 + Math.cos(a) * 230, 2350 + Math.sin(a) * 230, { w: 9 })); }
  tl.draw(B, sun, T.w(1, 'sunlight'), { by: T.w(1, 'sunlight') + 1.1 });
  ['#c8413a', '#d97757', '#e0b23a', '#2e7a4d', '#2a5cb3'].forEach((col, i) =>
    tl.draw(U, K.arrow(1500, 2300 + i * 30, 1900, 2150 + i * 90, { w: 8, color: col }), T.w(1, 'colours') + i * 0.16, { by: T.w(1, 'colours') + i * 0.16 + 0.3 }));
  tl.draw(B, K.text('all colours', 1500, 2750, { h: 80, align: 'center' }), T.w(1, 'all'), { by: T.lines[1].end });
  tl.end();
  const board = new K.Board(tl, { W: BW, H: BH, ghosts: K.ghosts(BW, BH, 36) });
  const cam = new K.Camera([
    [0, 1500, 1050, 1.0], [T.lines[1].start - 0.2, 1500, 1050, 1.0],
    [T.lines[1].start + 0.4, 1520, 2450, 1.05],                 // travel down to region 2
    [T.end, 1500, 2600, 0.6],                                   // pull back at the end
  ]);
  board.objs.push({ draw: (ctx, t, cc) => { for (const p of [B, O, U]) K.drawMarker(ctx, p, K.penPose(p, t, cam), cc, t); } });
  board.overlays.push(K.subtitles(T));
  const render = K.renderer(board, cam);
  return { seek: (t, ctx) => render(ctx, t), cues: K.soundCues(tl, cam), sfx: {} };
}
```