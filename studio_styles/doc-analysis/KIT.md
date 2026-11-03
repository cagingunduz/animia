THE KIT (K = window.DA): the OVERLAY of an analysis documentary. Frame 1920 x 1080 px, (0, 0) top left, y DOWN. You
animate ONE PART (T.lines, 0 to T.end). THE PICTURES ARE ALREADY PLAYING UNDER YOUR CANVAS (the plate): T.shots =
[{ t0, t1, layer: 'A' | 'B', kind: 'video' | 'image', shows, credit, lower }] says what is on screen when. You draw only
typography and marks over them; start every frame with K.clear(ctx) (transparent) and end with K.finish(ctx, t).

THE SHOT PLAN in the notes is binding: what is said is what is shown; each card / mark starts on its word (T.w(i, 'word', nth)).

OVERLAYS (all times in seconds; `out` = when it leaves):
- K.title(ctx, t, 'TEXT', at, { out, hi: ['KEY'], size: 120, over: false, words: T.lines[i].words }) a full-frame
  title / question card (over: true = words over the dimmed picture instead of a dark card). Chapter openers, questions.
- K.lower(ctx, t, { title: 'Süveyş Kanalı · Mısır', sub: '23 Mart 2021 · Kaynak: …', at, out }) on real footage of a
  place / event (use the shot's `lower` / `credit`), 3-4 s.
- K.counter(ctx, t, { to, from: 0, at, dur: 1.5, prefix, suffix, label, x, y, size, dec, out }) every big number.
- K.quote(ctx, t, '“…”', at, { who, out }) real, sourced quotes only.
- K.compare(ctx, t, { left: { title, value, sub }, right: { … }, at, win: 'left' | 'right', out }).
- K.timeline(ctx, t, [{ label, at }, …], { y, out }) dates in order, each landing on its word.
- K.dim(ctx, t, { at, out, amount }) / K.focus(ctx, t, { x, y, w, h, at, out }) darken the picture / spotlight a box.
- Marks on the picture: K.ring(ctx, t, { x, y, w, h, at }), K.arrow(ctx, t, { from, to, at }), K.box(ctx, t, { x, y, w, h, at }),
  K.highlight(ctx, t, { x, y, w, h, at }) (yellow highlighter on a document line). Place them where the subject is in
  the picture (the contact sheet shows each picture); if unsure, use a title card or a lower third instead.
- Maps: K.pin(ctx, t, { x, y, at, label }), K.route(ctx, t, [[x, y], …], at, { dur }) over a map picture.
- K.credit(ctx, t, shot.credit, { at: shot.t0, out: shot.t1 }) small credit bottom right on every layer-B shot.
- K.flash(ctx, t, at) a white flash on a big cut (sparingly). K.finish(ctx, t, { fadeIn: .2, end: T.end }) last.
- Helpers: K.seg, K.ss, K.eo, K.back, K.lerp, K.clamp, K.C (hi yellow, red).

SOUND: cues: K.sounds([{ t, type, v, d }]) with type in type (words landing on a card; d), whoosh (cuts, cards), pop
(pins, numbers), hit (a title's key word, a ring), ding (a counter landing), riser (d, into a reveal), splat (a flash).
sfx: {}.

A WORKED EXAMPLE (3 lines: a cold open over footage, a number, a question card):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w, S = T.shots;
  return {
    seek(t, ctx) {
      K.clear(ctx);
      const sh = S.find(s => t >= s.t0 && t < s.t1);
      if (sh && sh.layer === 'B') { if (sh.lower) K.lower(ctx, t, { ...sh.lower, at: sh.t0 + .3, out: Math.min(sh.t1, sh.t0 + 4) }); K.credit(ctx, t, sh.credit, { at: sh.t0, out: sh.t1 }); }
      K.ring(ctx, t, { x: 980, y: 560, w: 520, h: 220, at: w(0, 'ship'), out: L[1].start });
      K.dim(ctx, t, { at: L[1].start, out: L[2].start, amount: .5 });
      K.counter(ctx, t, { to: 369, at: w(1, '369'), label: 'ships waiting', out: L[2].start });
      K.title(ctx, t, 'How did one ship stop all of this?', L[2].start, { hi: ['ONE', 'SHIP'], words: L[2].words });
      K.finish(ctx, t, { end: T.end });
    },
    cues: K.sounds([{ t: w(0, 'ship'), type: 'hit' }, { t: w(1, '369'), type: 'pop' }, { t: w(1, '369') + 1.5, type: 'ding' },
      { t: L[2].start, type: 'whoosh' }]),
    sfx: {},
  };
}
```
