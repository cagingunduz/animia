"""Prompts for Explainer: a 30-60 s vertical explainer reel on cream paper with a cartoon presenter.

Claude writes the script (the user approves it), then plans the visuals as data; the explainer kit
(render_service/explainer) draws everything, so the look stays the same in every video.
"""

SCRIPT_SYSTEM = """You write scripts for 30 to 60 second vertical explainer reels. A friendly cartoon presenter talks to camera while
cards, titles, counters and small demos act out each point. Viewers are curious people who want to learn something
useful fast.

THE SHAPE:
1. Hook, two lines.
   - Line 1 states the problem in under 6 words ("You forget what you read").
   - Line 2 promises the payoff ("Three tricks make it stick, and the first one is free").
2. 3 to 7 points. Each point has:
   - a short point line that names it ("First, close the book and recall"),
   - one or two explanation lines with something concrete: a number, a comparison, an example, a quick how-to.
3. One closing line that pays off the hook in a few words and could lead straight back into line 1, so the video
   loops ("Read less, recall more").

LENGTH: 85 to 150 words in total (30 to 60 seconds at a brisk pace). Use 3 points for short topics, up to 5 for
rich ones; only go to 7 when every point is one short line.

STYLE: plain, specific, confident. Short sentences. Numbers as words ("fifty percent"). No "imagine", no "let's",
no questions to the viewer, no filler ("in this video"). Only true claims; when a number comes from research, keep it
modest and well known.

MUST MENTION: if the user gives something the video must mention (a product, a tool, a link, a name), weave it into
one point or the closing naturally, as a genuinely useful part of the advice. It must not sound like an ad.
"""

SCRIPT_TOOL = {
    "name": "submit_script",
    "description": "Submit the explainer script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "a short title for the video"},
            "hook": {"type": "array", "items": {"type": "string"}, "description": "exactly two lines"},
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "1 or 2 lowercase words naming the point, e.g. 'recall'"},
                        "line": {"type": "string", "description": "the point line"},
                        "explain": {"type": "array", "items": {"type": "string"}, "description": "1 or 2 explanation lines"},
                    },
                    "required": ["name", "line", "explain"],
                },
            },
            "close": {"type": "string", "description": "the closing line"},
        },
        "required": ["title", "hook", "points", "close"],
    },
}


PLAN_SYSTEM = """You plan the visuals of a vertical explainer reel. The renderer has a fixed design (cream paper, ink and red,
cards with halftone shadows, a cartoon presenter bottom right, word-by-word captions top left); you only choose the
content of each element, as data. Every word you name for timing must be copied exactly from its line.

THE ELEMENTS:
- hook.problem: a UI card shown at 0 s that pictures the problem, struck through in red at the end of line 1.
  label (a small mono line, e.g. "your brain, 24 hours later"), title (2 or 3 words), lines (two short grey lines).
- hook.payoff_cards: 2 or 3 one-word cards that pop in on line 2 (usually the point names); ring = the index of the
  card circled in red.
- hook.stat / point.stat: the small stat at the top right: num (short, e.g. "70%", "3x", "#1") and text (2-4 words).
- keywords: for every line id, the one word that matters most (two for lines over 8 words). They show in red italic.
- points: one per point, in order:
  - title: two words; the first shows in ink, the second in red ("Recall", "First"). title_word: the word of the
    POINT line on which the title slams in.
  - card: the main card that rises under the title and stays through the point line and the FIRST explanation
    line, so show what those lines say: a number that counts up (value, prefix, suffix, caption: a short line under
    it) or big: 1-3 words in large red text with a caption.
  - terminal: one line that types itself in a terminal (kind "terminal") or a search bar (kind "search"): a command,
    a query or a tiny rule of thumb, under 40 characters.
  - demo: the animation that acts out the LAST explanation line of the point (the only one when there is one),
    exactly what the voice says. kinds:
    "bars"      items [[label, number], ...] 2-4 rows, highlight = index of the red row, suffix/prefix
    "compare"   items [["Without", "what goes wrong"], ["With", "what goes right"]]
    "checklist" items ["short step", ...] 2-5 steps ticked one by one
    "chat"      items ["a message", "a reply", ...] 2-4 bubbles, alternating sides
    "flow"      items ["Step", "Step", "Step"] 2-4 boxes joined by arrows
    "search"    query "...", items ["result", "result", "result"]
    "number"    value, prefix, suffix, caption: one giant number
  - stamp: a 1-2 word red stamp (e.g. "PROVEN", "FREE", "2 MIN") that lands on stamp_word, a word of the point's
    explanation lines.
- close: label (small mono line), words (2-4 words, alternating ink and red, usually the closing line itself),
  stamp (1-2 words), stamp_word (a word of the closing line).

On-screen text has no full stops, no emoji. Keep every text short enough for a phone.
"""

PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the visual plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "hook": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "stat": {"type": "object", "properties": {"num": {"type": "string"}, "text": {"type": "string"}}},
                    "problem": {"type": "object", "properties": {"label": {"type": "string"}, "title": {"type": "string"},
                                                                 "lines": {"type": "array", "items": {"type": "string"}}}},
                    "payoff_cards": {"type": "array", "items": {"type": "string"}},
                    "ring": {"type": "integer"},
                },
            },
            "keywords": {"type": "object", "description": "line id -> [word, ...]"},
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "stat": {"type": "object", "properties": {"num": {"type": "string"}, "text": {"type": "string"}}},
                        "title": {"type": "array", "items": {"type": "string"}},
                        "title_word": {"type": "string"},
                        "card": {"type": "object"},
                        "terminal": {"type": "object", "properties": {"kind": {"type": "string"}, "text": {"type": "string"}}},
                        "demo": {"type": "object"},
                        "stamp": {"type": "object", "properties": {"text": {"type": "string"}, "stamp_word": {"type": "string"}}},
                    },
                    "required": ["title", "title_word", "card", "demo"],
                },
            },
            "close": {"type": "object", "properties": {"label": {"type": "string"}, "words": {"type": "array", "items": {"type": "string"}},
                                                       "stamp": {"type": "string"}, "stamp_word": {"type": "string"}}},
        },
        "required": ["hook", "keywords", "points", "close"],
    },
}


PRESENTER_SYSTEM = """You design the presenter for an explainer video: a flat cartoon host drawn from fixed parts. Pick the option for
each part that best matches what you are given (a description, or a photo or drawing of a person or character).
Match what is visible: skin tone, hair style and colour, glasses, facial hair, clothing and its colour, a cap,
headphones or earrings. When something is not given, choose what fits the overall description. Never refuse: every
input maps to some combination of parts."""


def presenter_tool(options: dict) -> dict:
    return {
        "name": "submit_presenter",
        "description": "Submit the presenter's parts.",
        "input_schema": {
            "type": "object",
            "properties": {k: {"type": "string", "enum": v} for k, v in options.items()},
            "required": list(options.keys()),
        },
    }


PRESENTER_OPTIONS = {
    "skin": ["light", "fair", "medium", "tan", "brown", "deep"],
    "hair": ["short", "curly", "long", "bun", "buzz", "bald", "side", "afro"],
    "hairColor": ["black", "brown", "auburn", "blonde", "grey", "white", "pink", "blue"],
    "glasses": ["none", "round", "square"],
    "top": ["hoodie", "tee", "shirt", "blazer"],
    "topColor": ["red", "ink", "navy", "green", "mustard", "grey", "cream", "blue", "purple"],
    "beard": ["none", "stubble", "full", "moustache"],
    "accessory": ["none", "cap", "earrings", "headphones"],
}
