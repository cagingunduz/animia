THE KIT (K = window.PR): kinetic type, glossy cards with live UI diagrams, a continuous camera, depth, an end card.
World units: at zoom 1 one unit = one pixel of the 1080 x 1920 frame; (0, 0) is a block's centre; y DOWN.

BUILD (in film(), once):
- K.setAccent(T.options.accent) first (the user's accent colour; a default is used if missing).
- const cam = K.camera([[t, x, y, zoom, rotDeg], ...]): eased keys; a slow drift is always added (never parked). Give
  two keys per block (arrive, then hold-with-drift), a short fast move (0.3-0.5 s) between blocks, a few degrees of
  rotation on some moves (whip-rotate), zoom 2.0 on the opening word then pull back to 1.0.

EVERY FRAME (seek(t, ctx)):
    const cc = cam(t);
    K.begin(ctx, t, cc);                                   // white ground, blurred accent shapes, bokeh
    K.world(ctx, t, cam, (g, t) => { ...draw the blocks on g... });   // camera + motion blur on fast moves
    K.finish(ctx, t, { fade: K.seg(t, 0, .3) });            // grain, vignette, fade in from white

IN THE WORLD (draw on g, the context world() gives you):
- K.type(g, t, T.lines[i], { x: 0, y, size: 76, maxW: 860, key: ['word'], out: tOut }) the line typed on letter by
  letter in sync with its words (the key words in the accent + serif italic); out = when it fades away (before the
  next line in the same place).
- K.bigWord(g, t, 'word', t0, t1, { x, y, size: 150 }) one huge blurred word that resolves (the opening).
- K.card(g, t, { x, y (centre), w, h, t0, t1, from: 'bottom' | 'right' | 'left' | 'top', tint: 0..1, scale: 1.35 },
  (g, t, box) => { ...a diagram... }) a glossy card that tilts in at t0 and leaves at t1. Inside, draw in box =
  { x, y, w, h } (content is scaled 1.35x so phones can read it; design for box.w ≈ 610).
- Diagrams (inside a card; `at` = the times each item appears: use T.w(i, 'word') so they land on their words):
    K.ui.dashboard(g, t, box, { title, kpis: [{ label, value, prefix, suffix, dec, up, hi }], line: [..] | bars: [..], at, lineAt | barsAt })
    K.ui.table(g, t, box, { title, sub, cols: [...], rows: [[...]], hi: rowIndex, at })
    K.ui.search(g, t, box, { query, results: [{ title, sub, score }], order: [newIndexOrder], resort: time, hi, t0, at })
    K.ui.map(g, t, box, { title, x: 'axis', y: 'axis', dots: [[x01, y01, 'label'], ...], hi: [indices], at })
    K.ui.profile(g, t, box, { name, role, tags: [...], stats: [[label, value]], t0, at })
    K.ui.network(g, t, box, { nodes: [[x01, y01, 'label'], ...], edges: [[a, b], ...], hub, t0, at })
    K.ui.chat(g, t, box, { msgs: [{ me: true, text }], at })
    K.ui.checklist(g, t, box, { title, items: [...], at })
    K.ui.compare(g, t, box, { left: { title, items }, right: { title, items }, at: [tLeft, tRight] })   (right = the good one)
    K.ui.notifs(g, t, box, { items: [{ title, sub }], at })
- K.endCard(g, t, t0, T.options.handle, { y }) the handle wordmark flickering in (only if a handle was given).
- Helpers: K.seg, K.ss, K.eo, K.eio, K.lerp, K.clamp, K.C (colours: K.C.accent, K.C.ink, K.C.grey).

SOUND: cues: K.sounds([{ t, type, v, d }]) with type in type (typing ticks while a line types; d = its length),
tick, slide (a card entering), whip (a camera move between blocks), count (a counter rolling; d), pop, riser (d, into
the last line), hit (the last word). Put a type on every line, a whip on every move, a slide on every card. sfx: {}.

A WORKED EXAMPLE (8 lines, 6 blocks):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w, O = T.options || {};
  K.setAccent(O.accent || '#5B21B6');
  // one block per beat, down a tall column; the camera travels between them and never parks
  const Y = [0, 1500, 3000, 4500, 6000, 7500];   // one block per beat
  const cam = K.camera([
    [0, 0, -380, 2.0], [1.0, 0, -380, 2.0], [L[0].start + 1.6, 0, 0, 1.0],
    [L[1].start - .3, 0, 60, 1.0], [L[1].start + .2, 0, 1500, 1.0, -3], [L[3].start - .3, 0, 1560, 1.02, -1],
    [L[3].start + .2, 0, 3000, 1.0, 2], [L[4].start - .3, 0, 3060, 1.03],
    [L[4].start + .2, 0, 4500, 1.0, -2], [L[6].start - .3, 0, 4560, 1.03],
    [L[6].start + .2, 0, 6000, 1.0, 2], [L[7].start - .3, 0, 6060, 1.02],
    [L[7].start + .2, 0, 7500, 1.0], [T.end, 0, 7500, .92],
  ]);
  const text = (ctx, t, i, y, o = {}) => K.type(ctx, t, L[i], { x: 0, y, size: 76, ...o });
  return {
    seek(t, ctx) {
      const cc = cam(t);
      K.begin(ctx, t, cc);
      K.world(ctx, t, cam, (g, t) => {
        // 1: traffic, nobody buys
        K.bigWord(g, t, 'traffic', 0.1, 1.5, { y: -380, size: 150 });
        text(g, t, 0, -470, { key: ['traffic', 'Nobody'], out: L[1].start - .2 });
        K.card(g, t, { x: 0, y: 160, w: 900, h: 760, t0: w(0, 'traffic'), t1: L[1].start - .3 }, (g, t, b) =>
          K.ui.dashboard(g, t, b, { title: 'Landing page · last 30 days', kpis: [{ label: 'Visitors', value: 12480, up: true }, { label: 'Sales', value: 3, up: false, hi: true }],
            line: [3, 5, 4, 8, 9, 13, 12, 18], at: [w(0, 'traffic'), w(0, 'Nobody')], lineAt: w(0, 'traffic') + .3 }));
        // 2-3: eight seconds, the headline
        text(g, t, 1, Y[1] - 470, { key: ['eight'], out: L[2].start - .1 });
        text(g, t, 2, Y[1] - 470, { key: ['headline'], out: L[3].start - .3 });
        K.card(g, t, { x: 0, y: Y[1] + 170, w: 900, h: 700, t0: w(1, 'decide'), t1: L[3].start - .3, from: 'right' }, (g, t, b) =>
          K.ui.table(g, t, b, { title: 'What visitors read', sub: 'in the first 8 seconds', cols: ['Part', 'Read by'],
            rows: [['Headline', '80%'], ['Subheading', '22%'], ['Features', '9%'], ['Price', '4%']], hi: 0, at: [w(2, 'headline'), w(2, 'Nothing'), w(2, 'Nothing') + .15, w(2, 'Nothing') + .3] }));
        // 4: vague loses them
        text(g, t, 3, Y[2] - 470, { key: ['vague'], out: L[4].start - .3 });
        K.card(g, t, { x: 0, y: Y[2] + 170, w: 920, h: 640, t0: w(3, 'vague'), t1: L[4].start - .3, from: 'left' }, (g, t, b) =>
          K.ui.compare(g, t, b, { left: { title: 'Vague', items: ['All-in-one platform', 'Built for growth', 'Next-gen tools'] },
            right: { title: 'Clear', items: ['Payroll for', 'teams of 5–50', 'in ten minutes'] }, at: [w(3, 'vague'), w(3, 'price')] }));
        // 5-6: one clear thing: who it's for
        text(g, t, 4, Y[3] - 470, { key: ['clear'], out: L[5].start - .1 });
        text(g, t, 5, Y[3] - 470, { key: ['for'], out: L[6].start - .3 });
        K.card(g, t, { x: 0, y: Y[3] + 170, w: 900, h: 520, t0: w(4, 'one'), t1: L[6].start - .3 }, (g, t, b) =>
          K.ui.profile(g, t, b, { name: 'Small agencies', role: 'The one audience on the page', tags: ['5–50 people', 'Payroll', 'No accountant'], stats: [['Problem', '1'], ['Offer', '1']], t0: w(5, 'Who'), at: [w(5, 'Who'), w(5, 'changes'), w(5, 'them')] }));
        // 7: more sales
        text(g, t, 6, Y[4] - 470, { key: ['sales'], out: L[7].start - .3 });
        K.card(g, t, { x: 0, y: Y[4] + 170, w: 900, h: 700, t0: w(6, 'Same'), t1: L[7].start - .3, from: 'bottom', tint: 1 }, (g, t, b) =>
          K.ui.dashboard(g, t, b, { title: 'After the new headline', kpis: [{ label: 'Visitors', value: 12510 }, { label: 'Sales', value: 41, up: true, hi: true }],
            bars: [3, 4, 3, 9, 14, 22, 31, 41], at: [w(6, 'Same'), w(6, 'sales')], barsAt: w(6, 'Clearer') }));
        // 8: punch + end card
        text(g, t, 7, Y[5] - 120, { key: ['headline'], size: 80 });
        K.endCard(g, t, L[7].end + .2, O.handle, { y: Y[5] + 180 });
      });
      K.finish(ctx, t, { fade: K.seg(t, 0, .3) });
    },
    cues: K.sounds([
      ...L.map(l => ({ t: l.start, type: 'type', d: Math.min(1.4, l.end - l.start), v: .7 })),
      { t: L[1].start - .1, type: 'whip' }, { t: L[3].start - .1, type: 'whip' }, { t: L[4].start - .1, type: 'whip' }, { t: L[6].start - .1, type: 'whip' }, { t: L[7].start - .1, type: 'whip' },
      { t: w(0, 'traffic'), type: 'slide' }, { t: w(0, 'traffic') + .1, type: 'count', d: .9 }, { t: w(1, 'decide'), type: 'slide' }, { t: w(2, 'headline'), type: 'tick' },
      { t: w(3, 'vague'), type: 'slide' }, { t: w(3, 'price'), type: 'pop' }, { t: w(4, 'one'), type: 'slide' }, { t: w(6, 'Same'), type: 'slide' }, { t: w(6, 'sales'), type: 'count', d: .9 },
      { t: L[7].start - 1.2, type: 'riser', d: 1.2 }, { t: w(7, 'first'), type: 'hit' }, { t: L[7].end + .2, type: 'tick' }]),
    sfx: {},
  };
}
```
