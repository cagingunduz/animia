"""Style Studio: the styles. Each one is a kit (render_service/studio/kits/<file>, a global), its fonts, its rules for
the writer and for the film builder (studio_styles/<key>/STYLE.md + KIT.md), a narrator, a music bed and its foley.

The looks follow styles from the MIT-licensed github.com/lemomo-ai/lemo-opuscar, adapted to vertical 9:16 reels.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(key: str, name: str) -> str:
    try:
        return open(os.path.join(HERE, "studio_styles", key, name), encoding="utf-8").read()
    except FileNotFoundError:
        return ""


STYLES: dict[str, dict] = {
    "whiteboard": {
        "name": "Whiteboard Explainer",
        "kit_file": "whiteboard.js", "kit_global": "WB",
        "fonts": [{"family": "AD", "file": "ArchitectsDaughter-400.woff2"}],
        "background": "#fbfbf9",
        "voice": "bm_george", "speed": 1.05,
        "seconds": (45, 90),
        "bed": "studio_bed_whiteboard",     # motion_sound.SFX_LIBRARY entry (generated once, cached)
        "foley": "marker",                  # survival-style code-made foley from the kit's stroke events
        "inputs": [],
    },
    "scifi-toon": {
        "name": "Sci-Fi Sitcom Toon",
        "kit_file": "scifi-toon.js", "kit_global": "TOON",
        "fonts": [{"family": '"Baloo 2"', "file": "Baloo2-800.woff2", "weight": 800},
                  {"family": "Bungee", "file": "Bungee-400.woff2"},
                  {"family": "VT323", "file": "VT323-400.woff2"},
                  {"family": '"Titan One"', "file": "TitanOne-400.woff2"}],
        "background": "#000",
        "voice": "am_santa", "speed": 1.0,
        "cast": {"VASK": {"voice": "am_santa", "speed": 0.92}, "GARY": {"voice": "am_puck", "speed": 1.1},
                 "DECAF": {"voice": "af_sky", "speed": 1.05}},
        "seconds": (35, 75),
        "tail": 1.6,
        "bed": "studio_bed_toon", "bed_db": -16.0,
        "foley": "toon",
        "inputs": [],
    },
    "paper-lantern": {
        "name": "Paper-cut Lightbox",
        "kit_file": "paper-lantern.js", "kit_global": "LB",
        "fonts": [{"family": "Cormorant", "file": "Cormorant-600.woff2", "weight": 600}],
        "background": "#000",
        "voice": "bm_george", "speed": 0.95,
        "seconds": (40, 90),
        "tail": 2.0,
        "bed": "studio_bed_lantern", "bed_db": -15.0,
        "foley": "paper",
        "inputs": [],
    },
    "teardown": {
        "name": "Exploded Teardown",
        "kit_file": "teardown.three.js", "kit_global": "TD",
        "fonts": [{"family": "Inter", "file": "Inter-500.woff2", "weight": 500},
                  {"family": "Inter", "file": "Inter-700.woff2", "weight": 700},
                  {"family": "JetBrainsMono", "file": "JetBrainsMono-500.woff2", "weight": 500}],
        "background": "#0d0e10",
        "voice": "am_michael", "speed": 1.0,
        "seconds": (35, 75),
        "bed": "studio_bed_teardown", "bed_db": -16.0,
        "foley": "teardown",
        "inputs": [],
    },
    "caption-news": {
        "name": "Caption News",
        "kit_file": "caption-news.js", "kit_global": "CN",
        "fonts": [{"family": "Inter", "file": f"Inter-{w}.woff2", "weight": w} for w in (500, 600, 700, 800, 900)],
        "background": "#000",
        "voice": "am_michael", "speed": 1.12,
        "seconds": (30, 75),
        "tail": 1.0,
        "bed": "studio_bed_news", "bed_db": -15.0,
        "foley": "news",
        "media": "footage",                 # uploads first, else open archives (studio_footage / studio_plate)
        "inputs": ["uploads"],
    },
    "telestrator": {
        "name": "Sports Telestrator",
        "kit_file": "telestrator.js", "kit_global": "TL",
        "fonts": [{"family": "BarlowCondensed", "file": "BarlowCondensed-600.woff2", "weight": 600},
                  {"family": "BarlowCondensed", "file": "BarlowCondensed-800.woff2", "weight": 800},
                  {"family": "BarlowCondensed", "file": "BarlowCondensed-800i.woff2", "weight": 800, "style": "italic"},
                  {"family": "IBMPlexMono", "file": "IBMPlexMono-500.woff2", "weight": 500}],
        "background": "#000",
        "voice": "bm_george", "speed": 1.08,
        "seconds": (30, 75),
        "tail": 1.0,
        "bed": "studio_bed_tele", "bed_db": -16.0,
        "foley": "tele",
        "media": "clip",                    # the user's match clip: played / slowed / rewound / frozen by the script
        "requires_upload": True,
        "inputs": ["uploads"],
    },
    "premium": {
        "name": "Premium Faceless Reel",
        "kit_file": "premium.js", "kit_global": "PR",
        "fonts": [{"family": "Inter", "file": f"Inter-{w}.woff2", "weight": w} for w in (500, 600, 700)]
                 + [{"family": "PlayfairDisplay", "file": "PlayfairDisplay-600i.woff2", "weight": 600, "style": "italic"}],
        "background": "#ffffff",
        "voice": "am_michael", "speed": 1.05,
        "voices": ["am_michael", "am_adam", "bm_george", "af_heart", "af_bella", "bf_emma"],
        "seconds": (20, 45),
        "tail": 1.6,
        "bed": "studio_bed_premium", "bed_db": -14.0,
        "foley": "tech",
        "options": ["accent", "handle", "voice", "audience"],
        "inputs": [],
    },
    "collage-doc": {
        "name": "Collage Documentary",
        "kit_file": "collage-doc.js", "kit_global": "CD",
        "fonts": [{"family": "PlayfairDisplay", "file": "PlayfairDisplay-600i.woff2", "weight": 600, "style": "italic"},
                  {"family": "Cormorant", "file": "Cormorant-500i.woff2", "weight": 500, "style": "italic"},
                  {"family": "Cormorant", "file": "Cormorant-600.woff2", "weight": 600}],
        "background": "#e9e4d8",
        "voice": "pt_michael", "speed": 1.1,    # Kyutai Pocket TTS (pocket_voice), sped up 10% (pitch kept)
        "voices": ["pt_michael", "pt_george", "pt_charles", "pt_paul", "pt_alba", "am_michael", "af_heart"],
        "mood_pace": 0.4,
        "wps": 2.7,                         # words per second at this narrator's pace (sizes the script to the length)                   # moods change the pace only a little (a documentary keeps moving)
        "seconds": (25, 60),
        "tail": 1.8,
        "bed": "studio_bed_doc", "bed_db": -15.0,
        "foley": "collage",
        "art": True,                        # pictures cast by an art director and made per reel (studio_collage)
        "fact_check": True,                 # true stories: every line is checked before it is recorded
        "options": ["voice", "audience"],
        "inputs": [],
    },
    # long videos (16:9), made by long_pipeline: a plan you approve, then parts made one by one, resumable
    "flat-explainer": {
        "name": "Flat Explainer",
        "kit_file": "flat-explainer.js", "kit_global": "FX",
        "size": (1920, 1080),
        "fonts": [{"family": "Montserrat", "file": "Montserrat-800.woff2", "weight": 800}],
        "background": "#e8dcc5",
        "voice": "pt_michael", "speed": 1.12,
        "voices": ["pt_michael", "pt_george", "pt_charles", "pt_paul", "pt_alba", "am_michael", "af_heart"],
        "wps": 3.1,
        "tail": 0.6,
        "bed": "studio_bed_flat", "bed_db": -10.5,
        "foley": "flat",
        "long": True,
        "minutes": (2, 12),
        "inputs": [],
    },
    "collage-doc-long": {
        "name": "Collage Documentary",
        "kit_file": "collage-doc.js", "kit_global": "CD",
        "size": (1920, 1080),
        "fonts": [{"family": "PlayfairDisplay", "file": "PlayfairDisplay-600i.woff2", "weight": 600, "style": "italic"},
                  {"family": "Cormorant", "file": "Cormorant-500i.woff2", "weight": 500, "style": "italic"},
                  {"family": "Cormorant", "file": "Cormorant-600.woff2", "weight": 600}],
        "background": "#e9e4d8",
        "voice": "pt_michael", "speed": 1.08,
        "voices": ["pt_michael", "pt_george", "pt_charles", "pt_paul", "pt_alba", "am_michael", "af_heart"],
        "mood_pace": 0.4,
        "wps": 2.7,
        "tail": 1.0,
        "bed": "studio_bed_doc", "bed_db": -15.0,
        "foley": "collage",
        "long": True,
        "art_source": "archive",            # every picture from open archives (studio_collage), credited
        "minutes": (3, 15),
        "inputs": [],
    },
}


def style(key: str) -> dict:
    if key not in STYLES:
        raise ValueError(f"unknown style {key!r}")
    s = dict(STYLES[key])
    s["key"] = key
    s["style_md"] = _read(key, "STYLE.md")
    s["kit_md"] = _read(key, "KIT.md")
    s["writer_md"] = _read(key, "WRITER.md")
    s["plan_md"] = _read(key, "PLAN.md")
    return s
