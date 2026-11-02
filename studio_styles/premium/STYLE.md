# Premium Faceless Reel — Style Prompt

> A premium, faceless short-form reel for a brand or a creator: no camera, no presenter. The script is the picture:
> each line types on letter by letter, and every line has one detailed, live UI diagram that proves it. White ground,
> one accent colour, glossy cards with depth, a camera that never parks, techy sound on every action.
> After the "premium faceless Reels with Claude" workflow published by @aygramm.ai (look and rules only).

## 1. Essence
- **The words are the hero.** Every spoken line appears as kinetic type: letters arrive grey and blurred and sharpen
  into ink, synced to the voice. The key word of each line is set in the accent colour, in a serif italic.
- **One diagram per line, never flat icons.** A mini interface with real-looking data: a pricing / comparison table,
  search results that re-sort, a dashboard with rolling counters and a chart, a market map with dots, a profile card,
  a network with pulses, a chat, a checklist, a notification stack, a before / after comparison. Each part appears on
  the word that names it.
- **One continuous camera.** No hard cuts: the camera travels from one block to the next (whip, zoom-through, drift)
  with motion blur, and never stops (a slow drift and rotation is always on). The opening is one huge blurred word
  that resolves, then the camera pulls back to reveal the line.
- **Depth and light.** Cards have a soft gradient fill, a glossy top highlight, 3-4 layered soft shadows tinted with
  the accent, and a 3D tilt as they enter. Behind: a far layer of big blurred accent shapes, a near layer of bokeh,
  subtle grain and vignette.
- **End card**: the user's handle as a wordmark that flickers in.

## 2. Colour and type
- White ground, near-black ink, ONE accent (the user's; default deep purple #5B21B6) on the key word of every line and
  on the hero shapes of each diagram (the highlighted row, the last bar, the hub, the winning column). Nothing else is
  saturated.
- Inter (regular / medium) for type, 70-80 px, centred; key words in Playfair Display italic. Diagram text 22-40 px
  inside cards (scaled up for phones by the kit).

## 3. Motion
- Type: letter by letter, grey + blurred -> sharp ink, each word over its spoken span.
- Transitions: zoom-through, whip-rotate (a few degrees), slide-out, pull-away; motion blur on every move.
- Cards enter from a side with a tilt that settles; they leave by fading and sliding.
- Counters roll, charts draw, rows re-sort, dots pop with a ring: something moves in every second.

## 4. Sound
- One clean, confident voice. Music ~14 dB under the voice (minimal tech pulse). Custom techy effects on every visible
  action: typing ticks, UI ticks, panel slides, glitch whips on camera moves, counters, pops, a riser into the last
  line and one big hit on the last word.

## 5. Mistakes to avoid
- Flat icons instead of mini interfaces with data. Full sentences parked on screen (type them on). Text over text.
  A diagram that does not match its line. Numbers that are not true or not clearly illustrative.

## 6. Our reels: vertical 9:16
- The frame is 1080 x 1920. Lay the film out as a column of blocks, one per beat (one or two lines), each block:
  the line's type at the top (y = blockY - 470), its card below (centre y = blockY + 170, about 900 wide and 520-760
  tall). Blocks 1500 units apart; the camera key for a block points at (0, blockY), zoom 1.
- The script follows hook -> problem -> cost -> reframe -> proof -> punch (8-10 lines, ~65 words, 20-35 s).
