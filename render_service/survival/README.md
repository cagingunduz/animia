# survival/: the Survival Story stage

Loaded by Survival Story compositions (`survival_compose.compose`). The render service copies `stage.three.js` and
`fonts/` into any project whose index.html references `survival/stage.three.js` (the name has "three" in it so the
HyperFrames lint sees that three.js is loaded: it is bundled inside).

- `stage.three.js`: the built bundle (one classic script, `window.SV`): `src/stage.js` + three.js 0.160 (MIT,
  `THREE_LICENSE`) with its EffectComposer, UnrealBloom and Output passes, and cannon-es 0.20 (MIT, `CANNON_LICENSE`).
- `src/stage.js`: `engine/stage.js` from github.com/Theoxmotion/story-video-studio (MIT, `LICENSE_story-video-studio`),
  with npm imports, a smaller 3D draw size scaled onto a full-size overlay canvas, and `wordTime()`.
- `fonts/`: Oswald 700 and JetBrains Mono 700 (SIL OFL 1.1, from @fontsource), so renders never need the network.

The API is documented for the model in `survival_prompts.SCENE_SYSTEM`; keep the two in sync.

## Build

    cd render_service/survival
    npm ci
    npm run build       # writes stage.three.js (commit it: the render service image does not build it)

## Render cost

HyperFrames `/render`, 4 vCPU, a 2 s chunk (60 frames, ~8 s of it chunk start-up), one apartment set with a shadowed
practical, an accent spot and bloom: overlay at 1080x1920 with the 3D at 960 tall: 29 s; at 736 tall: 25 s.
`SURVIVAL_DRAW_HEIGHT` (default 960) sets the 3D size; the captions, HUD and cards are always drawn at full size.
