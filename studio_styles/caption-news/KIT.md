THE KIT (K = window.CN): graphics for a sound-off news reel over real footage. The FOOTAGE is not yours to draw:
the server cuts the chosen clips to the lines and plays them as a video plate UNDER your canvas, in a band at the top
(y 0..1560 of 1920). Your canvas is transparent: never fill the whole frame except with a data card.

T.shots = [{ t0, t1, kind: 'video' | 'image' | 'card', credit }]: the plate's shots (one per line, from the line's
start to the next line's start; lines on the same picture are merged). A 'card' shot has no footage (black): cover
it with a K.ledger card. T.lines[i].caption = the line's caption ('Chunk one | chunk {key} | three').

EVERY FRAME (seek(t, ctx)), in this order:
    K.begin(ctx, t);              // clear (the footage shows through), readability gradients, the dark caption deck
    ...cards, stats, hook, lower thirds, freeze...
    K.bug(ctx, 'Channel', 'Topic');   // the fictional channel bug, top left, always
    K.credits(ctx, t, T.shots);       // the footage credit of the current shot, top right, always
    caps.draw(ctx, t);                // the captions, last (caps = K.captions(T) built once in film())

GRAPHICS (times in seconds; each draws only between its t0 and t1):
- K.hook(ctx, t, { t0: .1, t1, kicker: 'SINCE 1980', value: 48, dec: 0, prefix: '', suffix: '%', unit: 'of colonies lost',
  y: .3 }) the frame-4 hook: a giant number in a yellow block rolling to its value. Line 1 only.
- K.stat(ctx, t, { t0, t1, value, dec, prefix, suffix, label, x: .06, y: .3, color: K.C.yellow | K.C.red, size: 150 })
  a big rolling number over footage.
- K.source(ctx, t, 'NOAA', t0, t1) the source tag (under the bug): in EVERY shot that shows a figure.
- K.lowerThird(ctx, t, 'Label', 'one line', t0, t1) a place / date / speaker; never the main sentence.
- K.proportion(ctx, t, t0, t1, 72, 'of the coast') a yellow line sweeps across the footage to 72 %; the swept part goes dark.
- K.freeze(ctx, t, t0, t1, [x, y, w, h]) flash, corner brackets closing on a box (0..1 of the band), a PAUSED chip.
  (The footage freezes only if the script asked for it in visual_notes; otherwise it is a graphics-only stop.)
- K.ledger(ctx, t, t0, t1, { title: '≤ 3 words', sub: 'one grey line', src: 'Agency' }, (g, u, box) => { ... }) the data
  card: a dark ruled sheet sliding in from the right over the band; inside, draw with u = 0..1 progress and box =
  { x, y, w, h } (pixels). Use it on 'card' shots, for 3-4.5 s. Inside:
    K.bars(g, u, box, [{ label, value, hi: true (the point, yellow), bad: true (red) }, ...], { max, unit, dec })
    K.lineChart(g, u, box, [[label, value], ...], { key: index, keyLabel: '+0.6°C', min, max, unit })
- K.roll(t, t0, value, { from, d, dec }) -> the rolling number as text, for your own type.
- Colours: K.C.yellow (the point), K.C.red (losses), K.C.ivory (text), K.C.grey (labels), K.C.ink (on yellow).
- Raw canvas drawing is fine for anything else (fonts: '800 64px Inter', weights 500-900). Keep text out of the top
  140 px right half (credits) and left 0..200 px top (bug, source).

SOUND: cues: K.sounds([...K.slams(caps.list), { t, type, v, d }, ...]) with type in slam (caption chunks: K.slams adds
them all), rattle (a counter rolling; d), whoosh (a card sliding in), squeak, shutter (a freeze), stamp (a big number
landing), pop (a label), riser (into the turn; d). sfx: {}.

A WORKED EXAMPLE:
```js
function film(K, T, c) {
  const L = T.lines, w = T.w, S = T.shots;
  const caps = K.captions(T);
  const card = S.find(s => s.kind === 'card');
  return {
    seek(t, ctx) {
      K.begin(ctx, t);
      K.hook(ctx, t, { t0: .1, t1: L[0].end - 1.2, kicker: 'Since 1980', value: 40, suffix: '+', unit: 'years of satellite records', y: .3 });
      K.ledger(ctx, t, card.t0, card.t1, { title: 'Ocean surface', sub: 'Global sea surface temperature vs 1980', src: 'NOAA' }, (g, u, box) =>
        K.lineChart(g, u, box, [['1980', 0], ['1990', .15], ['2000', .3], ['2010', .4], ['2020', .55], ['2024', .62]], { keyLabel: '+0.6°C', min: -.1, max: .8 }));
      K.source(ctx, t, 'NOAA', card.t0 + .2, card.t1);
      K.lowerThird(ctx, t, 'From orbit', 'Satellite view · NASA', S[4].t0 + .2, S[4].t1 - .3);
      K.freeze(ctx, t, w(5, 'harder'), T.end, [.15, .15, .7, .55]);
      K.bug(ctx, 'Fast Facts', 'Climate');
      K.credits(ctx, t, S);
      caps.draw(ctx, t);
    },
    cues: K.sounds([...K.slams(caps.list), { t: .1, type: 'rattle', d: .45 }, { t: .55, type: 'stamp' },
      { t: card.t0, type: 'whoosh' }, { t: card.t0 + .2, type: 'pop' }, { t: w(5, 'harder'), type: 'shutter' }, { t: w(2, 'fuel') - 1, type: 'riser', d: 1 }]),
    sfx: {},
  };
}
```
