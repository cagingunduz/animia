"""Style Studio prompts, shared by every style. The style's own rules come from studio_styles/<key>/
(STYLE.md: the look, KIT.md: the kit's API, WRITER.md: the script structure)."""

from yard_prompts import EDIT_TOOL  # same find/replace tool


def writer_system(st: dict) -> str:
    return f"""You write the narration script for a vertical (9:16) reel in the {st['name']} style. The picture is drawn
entirely in code by an animator who reads your lines and notes; every line must be something they can show.

{st['writer_md']}

THE STYLE (for your shots; the animator follows it):
{st['style_md']}

THE LINES
- One line per beat. `text` is the caption form; `say` is the spoken form, only when they differ (digits, symbols,
  abbreviations: "1.5 km" -> "one and a half kilometres").
- `pause`: silence after the line, 0.1 to 0.8 s.
- Plain spoken English, contractions, no filler. Only true claims; drop anything you are unsure of.
- visual_notes: one line per voice line, what we see (the picture, where on the board / in the frame, what moves)."""


SCRIPT_TOOL = {
    "name": "submit_script",
    "description": "Submit the finished script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "a short title, 2 to 6 words"},
            "lines": {"type": "array", "items": {"type": "object", "properties": {
                "text": {"type": "string"}, "say": {"type": "string"}, "pause": {"type": "number"},
                "who": {"type": "string", "description": "dialogue styles only: the speaker, one of the cast names"},
                "caption": {"type": "string", "description": "footage styles only: the on-screen caption, chunks split by |, one {keyword}"},
                "media": {"type": "object", "description": "footage styles only: the footage under this line",
                          "properties": {"upload": {"type": "integer"}, "search": {"type": "string"},
                                         "kind": {"type": "string", "enum": ["video", "image"]}, "card": {"type": "boolean"},
                                         "at": {"type": "number"}, "mode": {"type": "string", "enum": ["play", "slow", "rewind", "freeze"]},
                                         "freeze_at": {"type": "number"}, "cx": {"type": "number"}}}},
                "required": ["text"]}},
            "visual_notes": {"type": "string"},
            "post": {"type": "string", "description": "a short post caption with 3 to 5 hashtags"},
        },
        "required": ["title", "lines", "visual_notes"],
    },
}


def film_system(st: dict) -> str:
    return f"""You animate one vertical (1080 x 1920) reel in the {st['name']} style, in JavaScript, on the style's kit.
Write ONE function:

    function film(K, T, c) {{
      // build everything once, here (K is the kit, T the narration timing, c the 2D canvas context)
      return {{ seek(t, ctx) {{ /* draw frame t */ }}, cues: [...], sfx: {{}} }};
    }}

Reply with only that function in a ```js code block. No imports, no HTML, no other top-level code.

THE PAGE calls film() once, then seek(t, ctx) for every frame, t in seconds from 0 to T.end, in any order.
- seek(t) MUST be a pure function of t: no Date, no Math.random (use K.mulberry(seed) at build time), no timers, no
  animation loops, no fetch, no DOM, no async code.
- The canvas is 1080 x 1920. Draw every frame completely (the kit's render does this for you).

TIMING (T): T.lines[i] = {{ text, start, end, words: [{{ w, s, e }}] }} for each 0-based voice line i; T.end = the end of
the video; T.w(i, 'word', nth = 1) = when that word is spoken in line i. Key every drawing, move and cut to the word
that names it: a term appears exactly when the narrator says it.

{st['kit_md']}

THE STYLE (follow all of it):
{st['style_md']}"""


FIX_NOTE = """The film failed to load, threw while seeking, or has the layout problems listed. Fix the cause with the smallest edits to your film() function.
Each edit replaces one exact snippet ('find', copied verbatim from the code, unique) with 'replace'."""


def review_system(st: dict) -> str:
    return f"""You review stills from a vertical reel in the {st['name']} style against its script and fix the film code.
Each still is labelled with its time and the line being spoken.

Look for, in order of importance:
1. What the narrator talks about is not on screen, is cut off by the frame edge, or is too small to read on a phone.
2. Text over text, or a drawing under the subtitle band at the bottom.
3. An empty or nearly empty frame while a line is spoken.
4. Anything that breaks the style's rules (below).
Only fix real, visible problems with small edits (a camera key, a position, a size, a time). If the stills look right,
return no edits. Each edit replaces one exact snippet ('find', copied verbatim from the code, unique) with 'replace'.

THE STYLE:
{st['style_md']}"""


__all__ = ["writer_system", "SCRIPT_TOOL", "film_system", "FIX_NOTE", "review_system", "EDIT_TOOL"]
