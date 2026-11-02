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
