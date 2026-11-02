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
        "voice": "am_onyx", "speed": 1.0,
        "cast": {"VASK": {"voice": "am_onyx", "speed": 0.92}, "GARY": {"voice": "am_eric", "speed": 1.1},
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
}


def style(key: str) -> dict:
    if key not in STYLES:
        raise ValueError(f"unknown style {key!r}")
    s = dict(STYLES[key])
    s["key"] = key
    s["style_md"] = _read(key, "STYLE.md")
    s["kit_md"] = _read(key, "KIT.md")
    s["writer_md"] = _read(key, "WRITER.md")
    return s
