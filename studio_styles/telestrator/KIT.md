THE KIT (K = window.TL): the analysis desk's graphics over the user's match clip. The CLIP is not yours to draw: the
server plays it (played, slowed, rewound, frozen exactly as the script says) as a video plate under your transparent
canvas, in a 4:5 window at y 250..1600 of the 1080 x 1920 frame. Draw in SCREEN pixels. Above the window (y 0..250)
and below it (y 1600..1920) are dark decks for the bug and the subtitles.

T.shots = [{ t0, t1, mode: 'play' | 'slow' | 'rewind' | 'freeze', src (clip seconds at t0), speed, reverse, freeze (the film
second where the picture stops, held until t1), box }]: one per line. A freeze still of every frozen picture is shown
to you with a grid in screen pixels: place every drawing with it.

EVERY FRAME (seek(t, ctx)), in this order:
    K.begin(ctx, t, T.shots);     // clear, decks, the automatic flash on each freeze and the rewind look
    ...drawings (only while their picture is frozen, or a static arrow during slow play)...
    K.wipe(ctx, t, cutTime);      // the yellow packaging wipe, centred on a cut between segments (optional)
    K.bug(ctx, t, T.shots, 'Show Name', { replay: false });   // always
    K.clock(ctx, t, T.shots);     // the source clock in analysis (always call; it hides itself in live play)
    subs.draw(ctx, t);            // last (subs = K.subtitles(T) built once in film())

DRAWINGS (each draws itself in from t0 and fades out at t1; pass t1 = the shot's t1 so nothing outlives its freeze):
- K.ring(ctx, t, t0, t1, [x, y], { r: 40-60, color }) a ring under a player's FEET (y = the feet, not the body).
- K.arrow(ctx, t, t0, t1, [[x, y], ...], { color, w: 9, dash: false, head: true, d: .5 }) a marker line drawn along its
  length in d seconds; 2 points curve slightly; dash: true for an intended pass or a run.
- K.link(ctx, t, t0, t1, [x, y], [x, y], { color, dash }) a thin line between two players (a passing lane, the gap
  between two defenders).
- K.space(ctx, t, t0, t1, [[x, y], ...]) the red patch for space nobody covers.
- K.spotlight(ctx, t, t0, t1, [cx, cy, rx, ry]) everything outside the ellipse darkens.
- K.label(ctx, t, t0, t1, [x, y], 'The finding', 'small line', { color, size: 54 }) a label card; put it on empty grass,
  never over the action; its left bar takes the colour of what it names.
- K.stopwatch(ctx, t, tStart, tStop, tEnd, [x, y], { label }) a stopwatch running from tStart, stopping yellow at tStop.
- K.stamp(ctx, t, t0, t1, 'Offside', [x, y]) a stamp card (once per film at most).
- K.board(ctx, t, t0, t1, 'Title', [[label, value, note], ...], { key }) a data card over the window (the summary).
- K.scoreBar(ctx, t, { home, away, score: [h, a], minute, goals: [[t, 'home' | 'away']] }) only if the score is known.
- Colours: K.C.us (yellow: the team we follow, the ball, main lines), K.C.them (cyan: opponents), K.C.space (red),
  K.C.chalk. Draw order inside a freeze: ring (who) -> area or link (what) -> label (the finding), 0.3-0.6 s apart,
  each on the word that names it (T.w(i, 'word')).
- K.at(T.shots, t) -> { mode, src, frozen } if you need the clip state yourself.

SOUND: cues: K.sounds([...K.freezeCues(T.shots), { t, type, v, d }, ...]) with type in squeak (a marker line; d), pop
(a ring), tick (a label), whoosh (a wipe: 0.17 s before its centre), stopwatch (ticks; d), stamp, hit, shutter, tape.
sfx: {}.

A WORKED EXAMPLE (shots: play, rewind, freeze, slow with a freeze, freeze, play):
```js
function film(K, T, c) {
  const L = T.lines, w = T.w, S = T.shots;
  const subs = K.subtitles(T);
  const F1 = S[2], F2 = S[4];
  return {
    seek(t, ctx) {
      K.begin(ctx, t, S);
      // freeze 1: three yellow attackers against two grey defenders
      K.spotlight(ctx, t, F1.freeze + .1, F1.t1, [600, 870, 340, 220]);
      K.ring(ctx, t, w(2, 'three'), F1.t1, [770, 800], { r: 44 });
      K.ring(ctx, t, w(2, 'three') + .15, F1.t1, [684, 955], { r: 44 });
      K.ring(ctx, t, w(2, 'three') + .3, F1.t1, [366, 860], { r: 44 });
      K.ring(ctx, t, w(2, 'two'), F1.t1, [646, 965], { r: 44, color: K.C.them });
      K.ring(ctx, t, w(2, 'two') + .15, F1.t1, [836, 920], { r: 44, color: K.C.them });
      K.label(ctx, t, w(2, 'defenders'), F1.t1, [90, 1180], '3 v 2', 'wide right', {});
      // slow play: the winger's run (drawn while the clip runs slowly, until the second freeze)
      K.arrow(ctx, t, w(3, 'width'), F2.t1, [[770, 790], [860, 860], [900, 960]], { dash: true, d: .8 });
      // freeze 2: the gap
      K.space(ctx, t, w(4, 'gap'), F2.t1, [[560, 1000], [800, 960], [860, 1160], [520, 1190]]);
      K.link(ctx, t, w(4, 'gap') - .2, F2.t1, [636, 955], [836, 900]);
      K.arrow(ctx, t, w(4, 'space'), F2.t1, [[682, 945], [700, 1090]], { d: .45 });
      K.label(ctx, t, w(4, 'space') + .2, F2.t1, [520, 1230], 'The gap', 'nobody steps in', { color: K.C.space });
      K.stopwatch(ctx, t, S[3].t0, S[3].freeze, F2.t1, [60, 1440], { label: 'SLOW MOTION' });
      K.wipe(ctx, t, S[5].t0);
      K.bug(ctx, t, S, 'The Board');
      K.clock(ctx, t, S);
      subs.draw(ctx, t);
    },
    cues: K.sounds([...K.freezeCues(S), { t: w(2, 'three'), type: 'pop' }, { t: w(2, 'two'), type: 'pop' }, { t: w(2, 'defenders'), type: 'tick' },
      { t: w(3, 'width'), type: 'squeak', d: .8 }, { t: w(4, 'gap'), type: 'squeak', d: .5 }, { t: w(4, 'space'), type: 'squeak', d: .45 },
      { t: w(4, 'space') + .2, type: 'tick' }, { t: S[5].t0 - .17, type: 'whoosh' }, { t: S[3].t0, type: 'stopwatch', d: S[3].freeze - S[3].t0 }]),
    sfx: {},
  };
}
```
