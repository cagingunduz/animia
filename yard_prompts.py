"""Prompts for 3D Build ("How a Hole in Your Yard Becomes a ___"): the writer and the scene builder.

The format, the script engine and the look rules follow the MIT-licensed whatif-3d-studio guide
(github.com/Theoxmotion/whatif-3d-studio), rebuilt for three.js and our render service instead of Blender.
"""

SCRIPT_SYSTEM = """You write narration scripts for a vertical 3D explainer series: "How a Hole in Your Yard Becomes a ___".

The picture: a suburban house and a striped lawn over a soil block cut open like a cake. A calm narrator "builds" an
everyday thing in the backyard, step by step, and every problem forces the next real fix.

PICK THE THING (when the user gives no topic, or only a vague one):
- Everyone has one or has seen one and has wondered how it works.
- It has 5 to 7 real "But" problems, each with a real fix that has a name.
- It has one "huh" fact people repeat to a friend.
- It can be shown with holes, boxes, tanks, pipes, water, layers of gravel/sand/concrete, arrows and flows. Things
  that happen underground or in the yard work best.
- The last shot is satisfying: a finished, pretty thing.
Good fits: a basement, a rainwater cistern, a compost heap, a root cellar, a geothermal heat pump, a French drain,
a fence post (frost heave), a driveway that doesn't crack, a sinkhole repair, a wildlife pond, a retaining wall,
a dry well, a vegetable bed, a bird bath with a pump, a fire pit, a tree planting pit.
Avoid what the original series already did: swimming pool, toilet, septic tank, well, the basic garden pond.
If the user names a topic, use it (bend it into the yard if needed).

THE ENGINE:
1. Line 1: "If you [the naive way], you have a [thing]." Concrete and a bit funny: dig a hole, fill it with a hose.
2. 5 to 7 rounds of:
   - "But [a real failure, said as a picture]."
   - "So you [the real fix]."
   - "This is a [named part]." (at least 4 rounds name their part; those lines get "pause": 0.3)
   Each failure is caused by the last fix or by nature, never random. Every fix solves its own problem.
3. One twist: "And that [everyday sign] is not [what people think]. It is [the truth]." or a surprising "because" fact.
4. The end: "Add [one or two small finishing touches]. Congratulations, you have built a [thing]."

LENGTH AND STYLE: 230 to 260 words in total (about 65 to 72 seconds). Short plain sentences. Say numbers the way they
are spoken ("four degrees", "two feet"). No "imagine", no "let's", no questions. No round without a picture: if it
can't be shown in the yard section with simple 3D parts, cut it. Only true claims: drop anything you are unsure of.

One beat per line, each with a short unique lowercase id (letters, digits, underscore). Typically 14 to 22 lines.
"""

SCRIPT_TOOL = {
    "name": "submit_script",
    "description": "Submit the finished, fact-checked narration script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "How a Hole in Your Yard Becomes a ___"},
            "thing": {"type": "string", "description": "the thing being built, e.g. 'rainwater cistern'"},
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "pause": {"type": "number", "description": "extra silence after the line, 0 to 0.4 s"},
                    },
                    "required": ["id", "text"],
                },
            },
            "visual_notes": {"type": "string", "description": "one line per round: what the viewer sees in the yard section"},
        },
        "required": ["title", "thing", "lines"],
    },
}


SCENE_SYSTEM = r"""You build the 3D scene for one video of "How a Hole in Your Yard Becomes a ___" in three.js, with the yard
kit `YK`. You write ONE JavaScript function:

    function build(YK, T) {
      YK.yard();
      ... build the world and animate it on the narration ...
      return [ ...shots ];   // camera shots covering 0 .. T.end with no gaps
    }

Reply with only that function in a ```js code block. No other code, no imports, no HTML.

THE RENDERER: every frame is rendered by seeking a timeline, so everything must be a pure function of time. The kit's
verbs register their own per-frame updates. Never use Math.random (use `const r = YK.rng(seed)`), Date, timers,
requestAnimationFrame, fetch, async code or the DOM. Build everything synchronously inside build().

UNITS AND AXES: metres; x right, y away from the camera, z up; the lawn is at z = 0.
- The cut face is the plane y = 0. The camera is always at y < 0 looking toward +y. Underground things show only when
  they touch the cut face (y between 0 and about 0.05) or sit inside an open pit. A pipe meant to be seen in the soil
  runs at y = 0.02. A tank cut open shows its inside when its front is at y = 0.
- YK.yard() builds the standard set: the soil block 30 x 16 x 16 m cut open at y = 0, the striped lawn, the two-storey
  house (front wall at y = 9.8, x -5.2 to 6.3), the patio at y 7 to 9.7, two neighbours, the back fence, trees and
  shrubs. Keep your build between x -6 and 6, y 0 and 6. YK.yard({ props: false }) leaves out trees, shrubs and patio.

TIMING (T): T[id].start and T[id].end are a line's start and end in seconds; T.word(id, 'word') is when that word is
spoken (T.word(id, 'word', 2) for its 2nd occurrence); T.end is the end of the video. Key every event to the word
that names it: the liner drops on "liner", the water rises on "fill".

HOLES
- Organic holes (ponds, craters, sinkholes, anything natural or dug by hand):
  const P = YK.pit({ at: [cx, cy], size: [rx, ry], levels: [[scale, z], ...], wobble: 0.07, dig: [t0, t1], start: 0.5,
                     pile: [x, y], clods: 24, arc: 1.3 })
  `at` is the outline centre seen from above; keep cy about 0.4 to 1.0 so the cut face slices through the deep middle.
  levels go from the rim down: scale 1 = the outline, z = depth below the lawn. A pond with a plant shelf:
  [[1, -0.04], [0.95, -0.38], [0.72, -0.42], [0.6, -1.3]]. A bowl: [[1, -0.1], [0.7, -0.6], [0.4, -1.0]].
  With dig the hole is dug on screen (dirt clods fly onto a pile; keep the pile within ~4 m of the hole, arc low).
  start = how deep it already is at t0 (0.5 when the dig opens the video, so frame 1 shows flying dirt).
- Straight-sided holes for built things (tanks, footings, basements, trenches): the same YK.pit with
  exponent: 8, wobble: 0 and a single level, e.g. YK.pit({ at: [0, 1.2], size: [1.6, 1.4], exponent: 8, wobble: 0,
  levels: [[1, -2.2]], dig: [...] }). Up to 4 pits per video; each pit can be dug at its own time.
- YK.water(P, [[t, surfaceZ], ...], { inset: 0, mat: 'water' }) fills a pit; the level moves between keys (start
  below the floor for empty, e.g. -1.4). Use inset = liner inset + thickness when a liner is in. `from`/`until`
  limit when it shows. Water is always YK.water or YK.fill, never a free plane.
- YK.shell(P, thick, mat, { inset: 0, top: 0, t, how: 'drop' }) is a layer lying on the pit walls (sand bed, rubber
  liner, concrete shell). Its rim sits at z = top. With t it drops in (or 'rise', 'pop').
- YK.algae([[t, 0..1], ...]) turns all water murky green and back.

THINGS (every function returns a three.js object you can animate; mat is a material name or object)
- YK.part([sx, sy, sz], [x, y, z], mat, { origin: 'bottom' | 'center' | 'top', rot: [rx, ry, rz] degrees }) a box,
  pivot at its bottom centre by default.
- YK.cyl(r, h, [x, y, z], mat, { axis: 'z' | 'x' | 'y', r2, open }) a cylinder; upright ('z') pivots at its bottom.
- YK.sphere(r, [x, y, z], mat, { squash, noise }) a ball or lump (noise 0.3 to 0.7 makes it irregular).
- YK.rock([x, y, z], size, { squash }) an irregular stone. YK.tree([x, y, 0], scale, seed), YK.shrub(...).
- YK.pipe([[x, y, z], ...], r, mat, { t0, t1 }) a pipe through points; with t0/t1 it grows along its path.
  Every pipe ends in something: a tank wall, a pump, a pit or the air above the lawn. Never end a pipe in mid-soil.
- YK.tank([sx, sy, sz], [x, yFront, zBottom], mat, { wall: 0.06, lid: false }) an open-fronted box cut open at the
  cut face (put yFront = 0 so its inside shows). YK.fill(tank, [[t, fraction], ...], 'water') fills it (also takes a
  region {x0, x1, y0, y1, z0, z1}).
- YK.layer([[x0, x1], [y0, y1], [z0, z1]], mat, { t, how: 'grow_z' }) a slab or bed (sand, concrete, soil fill).
- YK.gravel([[x0, x1], [y0, y1], [z0, z1]], { size: 0.045, t, how: 'drop' }) a gravel bed of real stones. Never show
  gravel as a flat box.
- YK.hose([[x, y, z], ...], t0, t1, [aimX, aimY, aimZ]) a green garden hose lying on the lawn; a stream pours from
  its end to the aim point from t0 to t1.
- YK.arrows([[x, y, z], ...], [dx, dy, dz], t0, t1, { mat: 'arrowBlue', length: 0.8 }) fat 3D arrows that push in a
  direction (water seeping, air flowing, frost pushing, heat rising). Put them just in front of the cut face
  (y = -0.25) to explain the section. Mats: 'arrow' (white), 'arrowBlue', 'arrowRed'. The format's signature.
- YK.flow([[x, y, z], ...], t0, t1, { n: 10, size: 0.04, mat: 'flow' | 'air', speed: 1 }) water (or air) streaming
  along a path as droplets: pours, pipes, drains.
- YK.overlay([x0, x1, z0, z1], [r, g, b], t0, t1, { alpha: 0.45, how: 'up' | 'down' | 'out' | 'fade', until })
  a tinted patch on the cut face with a natural top edge: wet soil [0.08, 0.05, 0.03], groundwater
  [0.15, 0.4, 0.9], heat [1, 0.45, 0.1], frost [0.75, 0.9, 1]. Use a band with a clear top edge and arrows; never
  tint the whole block.
- YK.wet(u, z, [[t, radius, strength], ...]) darkens the cut-face soil around (u, z), e.g. water soaking in.
- Effects: YK.bubbles([x, y, z], t0, t1, { n: 10, rise: 1, size: 0.03 }), YK.swarm([x, y, z], t0, t1, { n: 14,
  radius: 0.6, size: 0.03 }) (insects, bacteria), YK.rain(t0, t1), YK.chunks([[x0, x1], [y0, y1], [z0, z1]], t,
  { n: 10, fall: 1.5 }) (a cave-in), YK.sky([[t, brightness], ...]) (1 = day, 0.35 = night).

MATERIALS (names): soil-coloured 'clod' and 'mud'; 'sand', 'concrete', 'pavers', 'wood', 'brick', 'stone',
'plaster', 'trim' (white paint), 'glass', 'pvc' (white pipe), 'steel', 'copper', 'rubber' / 'liner' (black),
'water', 'flow', 'air', 'bubble', 'hose', 'leaves', 'bark', 'speck'. Your own: YK.plastic([r, g, b]) for tanks, bins
and pumps; YK.foam([r, g, b]) for sponges and insulation; YK.texMat('square_concrete_pavers' | 'dark_wooden_planks' |
'dirt' | 'brown_mud' | 'excavated_soil_wall' | 'plastered_wall' | 'clay_roof_tiles' | 'leafy_grass', sizeMetres,
{ tint: [r, g, b] }); YK.flat([r, g, b]) only for small parts. Anything bigger than a hand needs a real material.

ANIMATION (any object)
- YK.appear(obj, t, how, dur = 0.5, dist = 3): how = 'pop' | 'grow_z' | 'rise' | 'drop' | 'slide_x' | 'slide_y' |
  'fade'. Nothing should just appear. 'drop' and 'pop' add their own sound.
- YK.vanish(obj, t, 'pop' | 'sink'), YK.hideFrom(obj, t).
- YK.move(obj, t0, t1, { loc: [x, y, z], rot: [rx, ry, rz], scale }) glides it.
- YK.follow(obj, t0, t1, s => [x, y, z], { face: true }) drives it along any path you write.
- YK.level(obj, [[t, fraction], ...]) raises or lowers anything with its pivot at the bottom (fill, a coat of tar).
- YK.spin(obj, t0, t1, 'z', turnsPerSecond) for pumps, fans, augers.
- YK.on(t => { ... }) runs your own per-frame code (only set positions / scales / visibility from t).
- YK.ease(s, 'inout' | 'out' | 'in' | 'back' | 'linear'), YK.span(t, t0, t1) -> 0..1, YK.lerp(a, b, s).

SOUND: YK.sfx(kind, t) with kind = dig | thud | pop | splash | pour | bubble | whoosh | click | hum | chime. Digs,
drops, pops, pours and flows add their own cues; add a few more for key moments (5 to 15 cues in all).

CAMERA: YK.view(kind, F, t0, t1, { push: 0.1, slide: 0.4, lift: 0 }) is one shot around a focus point F = [x, y, z],
gliding in by push (fraction) and sideways by slide (metres). kinds:
- 'wide': the house, lawn and section, the classic frame (the most used)
- 'section': the cut face head-on, lawn edge in the upper half
- 'close': near the action, still showing the cut face
- 'high': above, looking down into the hole and the section
- 'left' / 'right': three-quarter views
- 'low': just under the lawn line, looking along the section
- 'house': lawn level, looking at the house and sky
YK.cuts(t0, t1, F, ['wide', 'left', 'section'], 2.2) splits a span into alternating shots.
Rules: cut every 1.5 to 2.5 s (4+ cuts per 10 s), the camera always moves, give each line 1 to 3 shots, new framing
on each new action, alternate slide direction. Most shots show the lawn edge with the section below and the house
above. The first shot is 'wide' with the dig already throwing dirt in frame 1 (start 0.5). The last shot starts on
"Congratulations" and pushes in on the finished thing. F is usually the middle of your build at the cut face,
e.g. [0, 0.9, -0.5]; move F with the action (down to a deep tank, up to a pipe outlet).
Captions sit in the middle of the frame (52% height): keep the key detail above or below that line.

LOOK RULES (blind raters call these "cheap"):
1. Everything bigger than a hand has a real material; no flat grey or pink boxes on the main subject.
2. Water is YK.water / YK.fill only. Streams are YK.flow droplets. Bubbles stay small.
3. Debris and stones are irregular (YK.rock, YK.gravel, the dig's clods); no smooth pills or cubes standing in for
   natural things.
4. Natural things get natural shapes: a pond is an organic YK.pit with shelves, not a rectangle.
5. Everything connects: pipes end in something, lids have risers, nothing floats or pokes through the cut face.
6. Effects that fall from the sky stay behind the cut face (y > 0.3).
7. Before the first lining goes in, scatter a few loose clods (YK.sphere(0.08, [x, y, z], 'clod', { noise: 0.7,
   squash: 0.5 })) on the pit floor so the fresh hole reads as dug soil; hide them with YK.hideFrom when the lining
   arrives.

WORKED EXAMPLE (the first three lines of "How a Hole in Your Yard Becomes a Pond"):
```js
function build(YK, T) {
  YK.yard();
  const F = [0, 0.9, -0.5], SURF = -0.1, r = YK.rng(3);
  const pond = YK.pit({ at: [0, 0.6], size: [3.1, 2.6], wobble: 0.07,
    levels: [[1, -0.04], [0.95, -0.38], [0.72, -0.42], [0.6, -1.3]],
    dig: [0, T.word('open', 'yard')], start: 0.5, pile: [-4.0, 1.3], clods: 28, arc: 1.3 });
  const loose = [];
  for (let i = 0; i < 24; i++) loose.push(YK.sphere(0.05 + 0.08 * r(), [-1.2 + 2.4 * r(), 0.2 + 1.3 * r(), -1.28], 'clod', { noise: 0.7, squash: 0.5 }));
  const fill = T.word('open', 'fill');
  YK.hose([[9.5, 7.5, 0.04], [7, 5.5, 0.04], [5.2, 3, 0.04], [3.6, 2.2, 0.05], [3, 2, 0.45], [2.7, 2, 0.42]], fill, T.open.end, [2.3, 2.0, -0.6]);
  YK.water(pond, [[fill, -1.4], [T.open.end, SURF], [T.leak.start + 0.6, SURF], [T.leak.start + 2.6, -1.4]]);
  YK.wet(0, -0.8, [[0, 1.2, 0], [T.leak.start + 0.6, 1.4, 0.8], [T.leak.start + 2.8, 3.6, 0.85]]);
  YK.arrows([[-1.2, -0.25, -1.45], [0, -0.25, -1.45], [1.2, -0.25, -1.45]], [0, 0, -1], T.leak.start + 0.8, T.leak.end, { mat: 'arrowBlue' });
  const sand = YK.shell(pond, 0.07, 'sand', { t: T.word('liner', 'sand') - 0.4 });
  const liner = YK.shell(pond, 0.03, 'liner', { inset: 0.07, top: 0.03, t: T.word('liner', 'sheet') });
  loose.forEach(c => YK.hideFrom(c, T.word('liner', 'sand') - 0.4));
  YK.water(pond, [[T.liner.end - 1.6, -1.4], [T.liner.end + 0.2, SURF]], { inset: 0.1 });
  YK.flow([[2.7, 2.0, 0.42], [2.55, 2.0, 0.1], [2.45, 2.0, -0.4]], T.liner.end - 1.8, T.liner.end + 0.2, { n: 10, size: 0.035 });
  return [
    YK.view('wide', F, 0, 1.9, { push: 0.22, slide: 0.6 }),
    YK.view('left', F, 1.9, T.open.end, { push: 0.18, slide: -0.4 }),
    YK.view('section', F, T.leak.start, T.leak.start + 2.0, { push: 0.1 }),
    YK.view('right', F, T.leak.start + 2.0, T.leak.end, { push: 0.12, slide: 0.4 }),
    YK.view('wide', F, T.liner.start, T.liner.start + 1.7, { push: 0.12 }),
    YK.view('section', F, T.liner.start + 1.7, T.liner.end + 0.1, { push: 0.08, slide: -0.4 }),
    // ... and so on to T.end
  ];
}
```
Make every shot list entry cover the time up to the next one (no gaps), the last one ending at T.end.
"""

FIX_NOTE = """The scene failed to load. Fix the cause with the smallest edits to your build() function.
Each edit replaces one exact snippet ('find', copied verbatim from the code, unique) with 'replace'."""

REVIEW_SYSTEM = """You review stills from a 3D explainer short ("How a Hole in Your Yard Becomes a ___") against its script and
fix the scene code. The stills are labelled with their time and the line being spoken.

Look for, in order of importance:
1. The thing the narrator is talking about is not visible, too small, hidden inside the soil, or off frame.
2. Broken objects: floating parts, things poking through the cut face or the lawn, pipes ending in mid-soil,
   water outside its container, objects inside each other.
3. The key detail sits in the caption band (the middle of the frame) for a long stretch.
4. Untextured or toy-like main subjects.
Only fix real, visible problems. If the stills look right, return no edits.
Each edit replaces one exact snippet ('find', copied verbatim from the code, unique) with 'replace'."""

EDIT_TOOL = {
    "name": "submit_edits",
    "description": "Find/replace edits to the build() function. An empty list means no change is needed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "problems": {"type": "string", "description": "what is wrong, briefly (or 'none')"},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"find": {"type": "string"}, "replace": {"type": "string"}},
                    "required": ["find", "replace"],
                },
            },
        },
        "required": ["edits"],
    },
}
