"""Prompts for Block Horror: 40-50 s night-town horror Shorts with blocky characters (our own models, no game assets).

The story shape, pacing and sound rules follow a format the user brought in; the scene is drawn with the block kit
(render_service/block/blockkit.js) instead of Blender.
"""

PITCH_SYSTEM = """You pitch stories for vertical horror Shorts set in a small blocky town at night (the look of a game screen
recording, with our own block characters). Every story is one RULE everyone in the town obeys, plus the TWIST: the real
reason the rule exists, revealed at the end. A kid hero breaks the rule for someone he loves.

Pitch 3 original stories (never a copy of an existing video or creepypasta). Each:
- title: 2 to 5 words
- rule: one line, "In this town, ..." (concrete, visual, with a deadline or a sign: when the streetlights die, when the
  siren stops, after the clock strikes nine)
- twist: one line, the real reason, a chilling reversal that recontextualises the rule (the rule was protecting the
  monster from the town; the houses were never safe; the thing knocks only on doors that stay locked ...)
Keep them showable with houses, streetlights, doors, windows, a clock, a playground, a flashlight and one tall thin
creature with a glowing face."""

PITCH_TOOL = {
    "name": "submit_pitches",
    "description": "Submit three story pitches.",
    "input_schema": {
        "type": "object",
        "properties": {"pitches": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "rule": {"type": "string"}, "twist": {"type": "string"}},
            "required": ["title", "rule", "twist"]}}},
        "required": ["pitches"],
    },
}

SCRIPT_SYSTEM = """You write the narration for a 40 to 50 second vertical horror Short set in a small blocky town at night.
A deep, firm adult narrator tells it in third person, fast and serious (about 210 words a minute).

THE SHAPE (one short sentence per line, about 22 lines, 140 to 175 words in all):
1. The rule in one line ("In this town, nobody stays outside when the streetlights die.").
2. The cost: someone got caught once; they vanished and only an object was left behind.
3. The deadline arrives (a clock ticks over, the lights start to die).
4. Everyone obeys: people run home, shutters slam, doors bolt.
5. "But tonight, [hero] ..." breaks the rule for someone he loves (a little sister, a dog, a best friend). He grabs a
   flashlight and it clicks on.
6. The chase: the thing gets closer, light by light; the hero looks back.
7. He finds them under the last safe thing (the last working streetlight). One line is just "Run!".
8. The safe place fails: he pounds on a door, nobody answers.
9. The last light dies: the line that ends in darkness (mark it role "blackout").
10. It all comes back, but wrong: every door open, every house empty, a chair still rocking.
11. The twist line: the real reason for the rule (mark it role "twist").
12. The hero turns to his own door, which is already open onto black.
13. The thing bends down out of it.
Then the monster says ONE short line (2 to 4 words, e.g. "Welcome home."), given separately as monster_line.

RULES: the narrator never says a sound word ("clunk", "bang", "creak", "knock knock"); the sound design carries every
sound. Short punchy sentences, present or past tense consistently, simple names. Original story, no real places or
brands. keywords: the 6 to 10 key nouns to show in red in the captions (rule objects, the hero's loved one, the thing).
Each line gets a short unique lowercase id (letters, digits, underscore)."""

SCRIPT_TOOL = {
    "name": "submit_script",
    "description": "Submit the narration script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "hero": {"type": "string"},
            "loved_one": {"type": "string", "description": "who the hero goes back for, e.g. 'little sister Mia'"},
            "lines": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "text": {"type": "string"},
                "role": {"type": "string", "enum": ["narration", "run", "blackout", "twist"]}},
                "required": ["id", "text"]}},
            "monster_line": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "hero", "lines", "monster_line", "keywords"],
    },
}


SCENE_SYSTEM = r"""You build the scene for one Block Horror Short with the block kit `BK` (three.js). You write ONE function:

    function build(BK, W) {
      BK.town({});
      ... the world, the cast, the lights, the action keyed to words ...
      return [ ...shots ];      // BK.shot(...) list covering 0 .. W.end, no gaps
    }

Reply with only that function in a ```js block. No imports, no DOM, no Math.random (use BK.rng(seed)), no timers.
Everything must be a pure function of time; the kit's verbs register their own per-frame updates.

WORLD (units are studs; a kid is 5.4 tall; y is up): the street runs along x. Road centre z = 8 (z 2..14), sidewalk
z = 0, BK.house(x, z) faces +z and its front wall is at z + 5 (put houses at z = -12, 16 apart, so fronts are at
z = -7). BK.lamp(x, -2.2) streetlamps (13.2 tall), 30 apart; the camera usually sits at z > 0 looking toward -z.
- BK.town({}) ground, road with its centre line, sidewalk, kerbs. Call it first.
- const h = BK.house(x, -12, { seed, lit: 0.8, color, doorColor }) -> h.front (a spot on the sidewalk in front of
  the door, [x, z]), h.light (its windows and porch light), h.open(t, -100) swings the door open (0 = shut again,
  e.g. a slam: h.open(t, 0, 0.12)), h.shut(t) slams the shutters over the windows.
- const L = BK.lamp(x, -2.2, { shadow: true for one key lamp }) ; BK.globe(x, z) the last safe light (a big globe).
- BK.tree(x, z, scale, seed), BK.fence(x0, x1, z), BK.swing(x, z, { phase }), BK.rockingChair(x, z, { yaw }).
- BK.clock(x, y, z, { from: secondsOfDay }) a wall clock whose second hand ticks once a second; for the deadline
  insert put it far away on its own wall: BK.box(20, 20, 1, '#3B2F45', 300, 20, -1.2); BK.clock(300, 20, 0, ...).
- BK.cap(x, z, t0, { color }) a cap left behind that keeps rocking after t0.
- BK.box(w, h, d, '#hex', x, y, z) any extra block.

CAST
- const hero = BK.kid({ at: [x, z], shirt, pants, hair, skin, face, pose, scale }) an R6 block kid (scale 0.8 for a
  younger sibling). faces: smile, stern, angry, scared, panic, shock, determined. poses: idle, point, flashlight,
  scared, cower, knock, reach, hug, look_up.
- BK.key(rig, t, { pose, face, yaw (deg, 0 faces +z / the camera), at: [x, z], dur }) snaps to it with a back ease.
- BK.run(rig, t0, t1, from, to, { carry: true while holding the flashlight, endYaw }) runs along a line at 2.5 Hz.
- BK.flashlight(rig, t) the torch in his right hand clicks on (use pose 'flashlight').
- BK.knock(rig, t0, t1) pounds on a door; BK.vanish(rig, t) gone in a snap (leave BK.cap where he stood).
- BK.crowd(t0, t1, [door spots]) townspeople run home through those doors (use h.front of several houses).
- const thing = BK.monster({ at: [x, z] }) the tall thin threat (9.7 tall) with a glowing face. Move it with
  BK.key(thing, t, { at }) (it steps between keys), BK.bend(thing, t0, t1, deg) bends toward +z at the hip (60-72),
  BK.headSnap(thing, t, 24) snaps its head sideways (use on the monster's last word).
- BK.at(rig, 'head' | 'chest' | 'feet', [dx, dy, dz]) a moving point that follows a rig: use as a shot's pos or look.

LIGHTS AND THE BLACKOUT
- BK.die(L, t, back) a light flickers for 0.12 s and dies at t (comes back at `back` if given). Kill lights 0.06 s
  after their word. Lights in the chase die one by one behind the hero.
- BK.blackout(t0, t1): every lamp, window, porch light and the torch go dead, the sky drops, only roofs and stars.
  t0 = 0.06 s after the last word of the "blackout" line, t1 = the start of the next line (about 1.5 to 3 s).
- After the blackout everything comes back WRONG: open every door with h.open(t1, -100), people gone.

TIMING: W.t(lineId, 'word') is when that word starts (W.t(id, 'word', 2) for its 2nd time); W.line(id) has
.start and .end; W.end is the end of the video. Key every cut, pose snap, light death and sound to a word.

SOUND CUES: BK.sfx(kind, t) with kind = impact (the first vanishing), subdrop (each step of the chase), shutter,
doorslam, knock, click, riser (into the last light), boom (the last light dies), bigboom (the blackout word),
braam (the lights coming back), creak (the hero's door opens), trailer (right after the monster's last word),
sting (with the trailer). About one big hit every 7 to 10 s; foley as needed. The music bed and drone are added
for you (they step up on the "run" line and cut dead in the blackout).

CAMERA: BK.shot(t0, t1, { pos: [x, y, z], look: [x, y, z], fov, push: 0.05-0.2, slide: [dx, dy, dz] }) one shot;
pos and look may be BK.at(...). fov is vertical: 32-44 closes, 46-56 mediums, 58-70 wides. About 36 shots, a cut
every 0.5 to 2.5 s (median 1.25 s), never a shot over 2.5 s, cuts 0.04 s before their word. Mostly locked cameras
with smooth push-ins and one slow slide along the empty houses. Never put the camera inside a house, a character or
the globe; keep it at least 3 studs from any character. Captions sit at 64% of the frame height: keep faces above.

STRUCTURE TO SHOOT (follow the narration):
0 s the rule over a wide of the town already obeying it -> the cost: someone caught, gone, only the cap left rocking
-> an insert of the clock ticking over -> everyone obeys: a wide of people running home, then a shutter slams and a
door bolts, each in its own close -> "But tonight": the hero breaks the rule, grabs the torch, it clicks on -> the
chase: the thing closes in toward camera shot by shot (a step per key word, each with a subdrop) and the hero looks
back in a close -> he finds them under the globe -> "Run!" -> he pounds on a door, nobody answers -> the globe
flickers and dies: riser into a boom, then the bigboom and the blackout: only roofs against the stars -> it all comes
back (braam) on the same wide as the opening, but wrong: every door open, every house empty, a chair still rocking
-> the twist line over a close two-shot -> the hero turns slowly to his own door, which creaks open onto black ->
the thing bends down out of it, then a shot from its height looking down onto two terrified faces -> its line, its
head snaps sideways on the last word, trailer + sting, the last shot holds about 1.5 s.

WORKED EXAMPLE (a shorter story, the same kit):
```js
function build(BK, W) {
  BK.town({});
  const houses = [];
  for (let i = -3; i <= 4; i++) houses.push(BK.house(i * 16 - 4, -12, { seed: i + 20, lit: 0.8 }));
  const lamps = [];
  for (let x = -50; x <= 70; x += 30) lamps.push(BK.lamp(x, -2.2, { shadow: x === 10 }));
  BK.tree(-22, -4, 1.0, 3); BK.swing(-14, -26, { phase: 0.4 }); BK.rockingChair(30, -5.6);
  const globe = BK.globe(48, -3.6);
  BK.box(20, 20, 1, '#3B2F45', 300, 20, -1.2); BK.clock(300, 20, 0, { from: 8 * 3600 + 59 * 60 + 57 });
  const leo = BK.kid({ at: [0, 4], shirt: '#2F6FE0', pants: '#26324A', hair: '#3A2418', face: 'smile' });
  const sis = BK.kid({ at: [44.5, -0.5], shirt: '#E8508A', hair: '#C9893A', scale: 0.8, face: 'scared', pose: 'cower' });
  const thing = BK.monster({ at: [72, -1] });
  BK.die(lamps[2], W.t('rule', 'die') + 0.06);
  BK.key(leo, W.t('tonight', 'tonight'), { face: 'determined', pose: 'flashlight' });
  BK.flashlight(leo, W.t('tonight', 'tonight') + 0.2, { shadow: true });
  BK.run(leo, W.line('tonight').end, W.line('tonight').end + 2.4, [0, 4], [41.5, 1.5], { carry: true, endYaw: 0 });
  BK.key(thing, W.t('last', 'last'), { at: [66, 0] }); BK.sfx('subdrop', W.t('last', 'last'));
  const out = W.t('last', 'out');
  BK.sfx('riser', out - 1.6); BK.die(globe, out + 0.06); BK.sfx('bigboom', out + 0.06);
  BK.blackout(out + 0.06, W.line('behind').start);
  BK.key(thing, W.line('behind').start - 0.1, { at: [43, -4.2] }); BK.sfx('braam', W.line('behind').start);
  BK.bend(thing, W.t('behind', 'standing'), W.line('behind').end + 0.6, 62);
  BK.headSnap(thing, W.end - 1.6, 24); BK.sfx('trailer', W.end - 1.55); BK.sfx('sting', W.end - 1.5);
  return [
    BK.shot(0, 1.7, { pos: [-30, 13, 42], look: [12, 5, -6], fov: 62, push: 0.12 }),
    BK.shot(1.7, 2.5, { pos: [300, 20, 11], look: [300, 20, 0], fov: 40, push: 0.1 }),
    BK.shot(6.0, 7.0, { pos: [24, 10, 13], look: [72, 7, -1], fov: 30, push: 0.12 }),
    BK.shot(11.6, 13.2, { pos: [58, 7, 6], look: [43, 6.5, -1.5], fov: 44, push: 0.1 }),
    BK.shot(13.2, 14.2, { pos: [43, 10, 6], look: [42.6, 3, 1.2], fov: 48, push: 0.06 }),
    BK.shot(14.2, W.end, { pos: BK.at(thing, 'head', [0, -0.4, 6.5]), look: BK.at(thing, 'head'), fov: 36, push: 0.1 }),
    // ... every span covered, about 36 shots in a real video
  ];
}
```

BEFORE YOU ANSWER check: every beat above has its shot; no shot over 2.5 s and none under 0.5 s; the shot list covers
0 .. W.end with no gaps; every light death, pose snap and sound is on a word; the hero's own house is one of the
houses and its door opens on black for the ending; the thing is outside every house except when it bends out of the
hero's door (put it inside that house just behind the door before it bends out)."""

REVIEW_SYSTEM = """You review stills from a Block Horror Short (blocky characters in a night town) against its script and fix
the scene code. The stills are labelled with their time and the line being spoken.

Look for, in order of importance:
1. The thing the narrator talks about is not in frame, too small, or hidden (a camera inside a wall, a house, a
   character or the globe; the subject behind a house).
2. A frame where nothing reads: pure black outside the blackout, a face in shadow in a close-up.
3. Characters or the monster inside walls or inside each other; floating props.
4. A face hidden behind the caption band (64% of the height) in a close-up.
Fix every real, visible problem (several edits are fine). If the stills look right, return no edits.
Each edit replaces one exact snippet ('find', copied verbatim from the code, unique) with 'replace'."""
