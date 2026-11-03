# Flat Explainer — Style Prompt (long video, 16:9)

> A 1920 x 1080 flat vector explainer in the style of the big infographic animation genre: every scene is a full
> illustrated place (a lab, a street, a classroom, a stage) with characters acting the line out.

## 1. Look
- Flat colour shapes, no outlines, one slightly darker flat shade for form; a muted palette (dusty blue-grey, slate teal,
  warm beige, navy, soft purple); salmon-pink skin, big heads, dot eyes. The plates and characters already look like
  this: never draw art in code except signs, marks, icons and cards from the kit.
- A new shot every 2-5 s and a hard cut on every sentence that changes the idea. A white splat wipe (K.splat) only
  between big parts. The camera always drifts 2-4 % or pans (K.cam): never a still frame longer than 1 s, never a
  character who doesn't move (they breathe, talk, turn, jump, walk).

## 2. Text lives only on things in the world
- On the plate's own blank surfaces (measured boxes: K.write), or on a kit sign on a post / a hanging board / a
  chalkboard / a screen (K.sign) that stands IN the scene. Typed in Montserrat 800 at 26-34 letters a second.
- Ink #2b2d42 on white boards. A red X (K.redX) goes over every wrong idea. Every date gets the date card (K.dateCard).
- Headlines: white caps on a flat colour card (K.headline: orange with puffs, or purple with gears), full frame, short.
- Banned: outlines, motion-design UI floating over the art (code editors, glass cards, checklists), emoji, burned-in
  subtitles, any channel's logo, text floating over the art without a surface.

## 3. Motion
- Things arrive with a spring, a squash, a pop or a white puff (K.puff), never a fade.
- Characters act the line: the one speaking talks (talk: [t0, t1]); reactions jump / turn / get a "!" (K.bang);
  walkers walk across (walk: [[t, x], ...]).
- Every cut, sign, gesture, icon and mark starts on a real word (T.w).

## 4. Sound
- One clear, lively narrator (~190 words a minute). A light curious documentary bed 10-11 dB under the voice. Effects:
  a typewriter tick on typed signs, a whoosh on wipes and drops, a pop on signs, icons and arrivals, a hit on the red X,
  a ding on ticks and counters.
