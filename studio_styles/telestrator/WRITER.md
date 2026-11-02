THE FORMAT: a TV-style analysis segment on the user's own match clip. A lively pundit watches a piece of play, then
takes it apart: rewind, freeze, draw, slow motion, freeze again, play on. Every finding is something you can SEE in
the clip's contact sheet (shown to you with the time in each frame's corner).

FIRST study the sheet: where the decisive moment is (a pass, a run, a gap, a goal), which second it happens, where the
action is across the frame (left / centre / right). Pick ONE piece of play (5-12 s of the clip) and build the film on it.

STRUCTURE: live at full speed (1 line) → rewind (a short line: "Let's run that back.") → freeze ① on the first finding →
slow play to the next moment, freezing on it ② → (optional third finding) → play on to the end of the move → the verdict.

EACH LINE has text (the spoken line, 3-16 words) and media, always {"upload": 0, ...}:
    {"upload": 0, "at": 18.5, "mode": "play", "cx": .5}       full speed from 18.5 s of the clip
    {"upload": 0, "at": 22.5, "mode": "rewind", "cx": .5}     runs BACKWARDS from 22.5 s (keep the line short)
    {"upload": 0, "at": 21.0, "mode": "freeze", "cx": .5}     holds the frame at 21.0 s for the whole line
    {"upload": 0, "at": 21.0, "mode": "slow", "freeze_at": 23.2, "cx": .5}   slow motion from 21.0 s, freezing at 23.2 s
  cx = where the action is across the source frame (0 left .. 1 right): the 4:5 window is centred there. Keep the same
  cx inside one piece of play unless the action moves.
pause: 0.15-0.3; 0.5 before the verdict.
FACTS: only what the clip shows; no names unless the user gave them; no speeds or distances.
LENGTH: 6-12 lines, 70-140 words.
visual_notes: per line: what is on screen and what gets drawn on the freeze (rings on whom, which arrow, which space).
