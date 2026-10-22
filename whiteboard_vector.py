"""
Whiteboard scene animation, vector edition.

A scene image (black line art, or black outlines + colour) is turned into ordered ink strokes:
the image's own ink is revealed along those strokes on an empty board, like a pen moving across
the page; fine hatching settles in, colour blooms from the middle (colour mode), and — unless it
is the last scene — the board is wiped clean at the end (K.erase). Rendered by the render
service (HyperFrames), so lines stay crisp at any resolution. No AI calls: cost is render time.
"""

import base64
import json

import cv2
import numpy as np

BOARD = "#FFFFFF"


def _fit(img: np.ndarray, box_w: int, box_h: int) -> np.ndarray:
    h, w = img.shape[:2]
    s = min(box_w / w, box_h / h)
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)


def vectorize(image_path: str, box_w: int, box_h: int, groups_n: int = 120) -> dict:
    """Image -> {w, h, ink_png (b64), color_jpg (b64), groups: [{d, len}]} in pen order."""
    im = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if im is None:
        raise ValueError("unreadable scene image")
    im = _fit(im, box_w, box_h)
    h, w = im.shape[:2]
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)[..., 1]

    # ink = dark, not strongly coloured (colour fills are lighter / saturated)
    ink = ((gray < 120) & (sat < 120)).astype(np.uint8) * 255
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    # the ink layer: dark lines, alpha from darkness (keeps the artist's line weight and hatching)
    alpha = np.clip((200 - gray.astype(np.float32)) / 140.0, 0, 1)
    alpha[sat >= 120] *= 0.25
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = 35
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    ok1, ink_png = cv2.imencode(".png", rgba)
    ok2, color_jpg = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 90])

    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    strokes = []
    for c in contours:
        if cv2.arcLength(c, False) < 10:
            continue
        c = cv2.approxPolyDP(c, 0.9, False).reshape(-1, 2)
        if len(c) >= 2:
            strokes.append(c)
    if not strokes:
        raise ValueError("no ink found in the scene image")

    # pen order: greedy nearest neighbour from the top-left
    starts = np.array([s[0] for s in strokes], float)
    used = np.zeros(len(strokes), bool)
    cur = np.array([0.0, 0.0])
    ordered = []
    for _ in range(len(strokes)):
        d = np.linalg.norm(starts - cur, axis=1) + used * 1e12
        i = int(np.argmin(d))
        used[i] = True
        ordered.append(strokes[i])
        cur = strokes[i][-1].astype(float)

    lengths = [float(np.sum(np.linalg.norm(np.diff(s, axis=0), axis=1))) for s in ordered]
    budget = sum(lengths) / groups_n
    groups, cur_d, cur_len = [], [], 0.0
    for s, L in zip(ordered, lengths):
        cur_d.append("M" + " L".join(f"{x:.0f} {y:.0f}" for x, y in s))
        cur_len += L
        if cur_len >= budget:
            groups.append({"d": "".join(cur_d), "len": round(cur_len, 1)})
            cur_d, cur_len = [], 0.0
    if cur_d:
        groups.append({"d": "".join(cur_d), "len": round(cur_len, 1)})

    return {
        "w": w, "h": h, "groups": groups,
        "ink_png": base64.b64encode(ink_png.tobytes()).decode() if ok1 else None,
        "color_jpg": base64.b64encode(color_jpg.tobytes()).decode() if ok2 else None,
    }


def timing(dur: float, colored: bool, erase: bool) -> dict:
    """Split a scene of `dur` seconds into draw / settle / colour / hold / erase (ms)."""
    erase_ms = 0 if not erase else (1400 if dur >= 5 else 1000)
    settle_ms, color_ms = 450, (1500 if colored else 0)   # colour: fade + bloom from the middle
    start = 300
    hold_min = 600                                        # the finished picture stays this long
    draw_ms = dur * 1000 - start - settle_ms - color_ms - hold_min - erase_ms - 100
    draw_ms = int(max(1200, min(8000, draw_ms)))
    t_settle = start + draw_ms
    t_color = t_settle + 300
    t_erase = int(dur * 1000 - erase_ms - 80) if erase else None
    return {"start": start, "draw": draw_ms, "settle": t_settle, "color": t_color, "erase": t_erase,
            "erase_ms": erase_ms}


def scene_html(vec: dict, canvas: tuple, dur: float, colored: bool, erase: bool) -> str:
    W, H = canvas
    w, h = vec["w"], vec["h"]
    left, top = (W - w) // 2, (H - h) // 2
    tm = timing(dur, colored, erase)
    total = sum(g["len"] for g in vec["groups"]) or 1.0
    plan, paths, t = [], [], tm["start"]
    for i, g in enumerate(vec["groups"]):
        d = max(25, int(tm["draw"] * g["len"] / total))
        paths.append(f'<path id="g{i}" d="{g["d"]}"/>')
        plan.append([i, t, d])
        t += d
    stroke_w = max(6, round(min(w, h) / 105))
    colour_js = (f"tl.add('#color', {{opacity: [0, 1], duration: 300}}, {tm['color']})"
                 f".add('#color', {{'--r': ['0%', '80%'], duration: 1500, ease: 'outCubic'}}, {tm['color']});"
                 if colored else "")
    erase_js = (f"K.erase(tl, {tm['erase']}, {{duration: {tm['erase_ms']}, clear: '#art', tool: false, board: '{BOARD}'}});"
                if erase else "")
    return f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="lib/kit.css">
<style>
#root{{width:{W}px;height:{H}px;background:{BOARD}}}
#art{{position:absolute;left:{left}px;top:{top}px;width:{w}px;height:{h}px}}
#art svg, #art img{{position:absolute;inset:0;width:{w}px;height:{h}px}}
#mk path{{fill:none;stroke:#fff;stroke-width:{stroke_w};stroke-linecap:round;stroke-linejoin:round}}
#color{{opacity:0;--r:0%;-webkit-mask-image:radial-gradient(circle at 50% 55%, #000 var(--r), transparent calc(var(--r) + 22%));mask-image:radial-gradient(circle at 50% 55%, #000 var(--r), transparent calc(var(--r) + 22%))}}
#inkfull{{opacity:0}}
</style></head><body>
<div id="root" data-composition-id="shot" data-no-timeline data-start="0" data-duration="{dur:.2f}" data-width="{W}" data-height="{H}">
 <div id="art">
  {'<img id="color" src="assets/color.jpg">' if colored else ''}
  <svg viewBox="0 0 {w} {h}">
   <defs><mask id="reveal" maskUnits="userSpaceOnUse" x="0" y="0" width="{w}" height="{h}"><g id="mk">{''.join(paths)}</g></mask></defs>
   <image href="assets/ink.png" width="{w}" height="{h}" mask="url(#reveal)"/>
  </svg>
  <img id="inkfull" src="assets/ink.png">
 </div>
</div>
<script src="lib/anime.umd.min.js"></script><script src="lib/kit.js"></script>
<script>
const tl = K.timeline();
{json.dumps(plan)}.forEach(([i, t, d]) => {{
  const [p] = anime.svg.createDrawable('#g' + i);
  K.set(p, {{draw: '0 0'}});
  tl.add(p, {{draw: ['0 0', '0 1'], duration: d, ease: 'linear'}}, t);
}});
K.cue({tm['start']}, 'draw', {tm['draw']}, 1);
tl.add('#inkfull', {{opacity: [0, 1], duration: 450, ease: 'inOutSine'}}, {tm['settle']});
{colour_js}
{erase_js}
tl.add({{k: 0}}, {{k: 1, duration: 1}}, {int(dur * 1000) - 1});
</script></body></html>"""


def scene_project(vec: dict, canvas: tuple, dur: float, colored: bool, erase: bool) -> dict:
    assets = {"assets/ink.png": vec["ink_png"]}
    if colored and vec.get("color_jpg"):
        assets["assets/color.jpg"] = vec["color_jpg"]
    return {"files": {"index.html": scene_html(vec, canvas, dur, colored, erase)}, "binary_files": assets}
