"""Collage Documentary: the pictures. After the script, an art director (Claude) casts every picture the reel needs,
then they are found or made in parallel. Two sources:

ARCHIVE (the default): every picture is a real, openly licensed
photo from Wikimedia Commons / NASA (public domain, CC0 or CC BY; credited). Claude picks the best of a few candidates
by thumbnail; cut-outs get their background removed on our CPU (IS-Net, the rembg "isnet-general-use" model); all of
them get one shared archival grade so the reel looks like one piece.

GENERATED (STUDIO_COLLAGE_SOURCE=generate, with GEMINI_API_KEY):

  plate     a full-bleed background: an EMPTY room, street, landscape, sky (Gemini image, 9:16)
  cutout    a person (from behind / far away / a silhouette), a hand or an arm, an animal, an object: generated on a
            flat chroma-key green and keyed to a transparent PNG here (green, not white: white gives messy edges)
  document  a letter, a ticket, a newspaper, a score, a map: flat, from above (Gemini image)
  portrait  the REAL face of a real person: a historical portrait from Wikimedia Commons (public domain / CC BY, credited),
            never generated. Everyone else is shown from behind, so no one's likeness is invented.

Every generated prompt starts with the same look line (one era, one palette, one light direction), so the pieces match.
The method follows Naomi Metzger's (@naometzger) guide to documentary-style reels, rebuilt for our pipeline.
"""

import asyncio
import base64
import io
import os
import re

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import studio_media

GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
IMAGE_MODEL = os.environ.get("STUDIO_IMAGE_MODEL", "gemini-3.1-flash-image")
IMAGE_FALLBACK = os.environ.get("STUDIO_IMAGE_FALLBACK", "gemini-2.5-flash-image")
MAX_PICTURES = 16
# archive photos by default; STUDIO_COLLAGE_SOURCE=generate (with GEMINI_API_KEY) makes them with Gemini instead
SOURCE = "generate" if GEMINI_KEY and os.environ.get("STUDIO_COLLAGE_SOURCE", "archive") == "generate" else "archive"
MODEL_DIR = os.environ.get("STUDIO_MODEL_DIR") or os.environ.get("KOKORO_DIR") or "/tmp/models"
ISNET_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
_archive_sem = asyncio.Semaphore(3)            # Commons rate limits: a few searches at a time
_sem = asyncio.Semaphore(int(os.environ.get("STUDIO_IMAGE_PARALLEL", "5")))

KINDS = ("plate", "cutout", "document", "portrait")
ASPECTS = ("9:16", "3:4", "1:1", "4:3", "2:3", "3:2")
GREEN = (" Isolated on a solid flat pure chroma-key green background (#00FF00), evenly lit, no shadow on the background,"
         " no floor, no other objects, the whole subject inside the frame with a margin.")
PLATE = " A single full-bleed photograph filling the whole frame: no border, no inset pictures, no collage, no text, no people."
DOC = " Seen flat from directly above, filling the frame, on nothing. No hands, no other objects."

ART_TOOL = {
    "name": "cast_pictures",
    "description": "Submit the pictures the reel needs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "look": {"type": "string", "description": "ONE line every generated picture starts with: medium, era, palette, light direction, grain"},
            "pictures": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "short snake_case name, e.g. man_back, hall_empty, letter, arm_left"},
                "kind": {"type": "string", "enum": list(KINDS)},
                "prompt": {"type": "string", "description": "plate / cutout / document: what to generate (the subject only; the look line and the background rules are added for you)"},
                "search": {"type": "string", "description": "portrait only: a Wikimedia Commons search for a real historical portrait (name + 'portrait' + painter or year if known)"},
                "aspect": {"type": "string", "enum": list(ASPECTS)},
                "alts": {"type": "array", "items": {"type": "string"}, "description": "archive only: 1-2 other searches for the same subject, tried if the first finds nothing that fits"},
                "lines": {"type": "array", "items": {"type": "integer"}, "description": "the 0-based voice lines it is used in"},
                "use": {"type": "string", "description": "how the animator should use it (one short sentence)"},
            }, "required": ["id", "kind", "aspect"]}},
            "scenes": {"type": "array", "description": "the picture track, in order: one entry per thing the narrator names, starting on the word that names it (every line has at least one entry)",
                       "items": {"type": "object", "properties": {
                           "line": {"type": "integer"},
                           "at": {"type": "string", "description": "the word in that line that names what is shown (the picture appears when it is spoken); empty = the line's start"},
                           "show": {"type": "array", "items": {"type": "string"}, "description": "picture ids on screen (1-3), each one showing what THIS line says"},
                           "words": {"type": "string", "description": "the big word(s) set on screen (1-4 words from the line)"},
                           "ring": {"type": "string", "description": "the ONE word from `words` (or a picture id) that gets a hand-drawn ring, or empty for no ring"},
                       }, "required": ["line", "show"]}},
        },
        "required": ["look", "pictures", "scenes"],
    },
}


ARCHIVE_RULES = f"""THE PICTURES COME FROM PHOTO ARCHIVES (Wikimedia Commons and NASA), not from a generator. For every picture
give a `search`: 2 to 5 plain English words that an archive photo would be titled with, e.g. "New York street 1905",
"Hotel New Yorker", "feral pigeon", "incandescent light bulb", "Wardenclyffe Tower", "concert hall interior", "old
letter handwriting", "Nikola Tesla portrait". Prefer subjects that were really photographed (places, buildings, objects,
animals, the person's own photos and paintings); avoid scenes nobody photographed.
- plate: a place or a texture to fill the frame (a street, a room, a building, a sky, a landscape, a sea).
- cutout: ONLY a simple, solid subject that archives photograph alone on a plain background (a hat, a sword, a
  statue, a bust, a medal, a coin, a bottle, a book, a telephone, a bird, a single figure). Every cut-out is checked;
  a fragment is replaced by the whole photo. Anything big or in context (a ship, a cannon in a battle, a building, a
  crowd, a machine in a room) is a `document` (a photo print taped on the collage), not a cut-out.
- document: a letter, a newspaper page, a patent drawing, a map, a ticket, a manuscript page.
- portrait: the real person (a photograph or a painting of them).
- Real photographs of real people are fine here (they are not invented). No modern stock-photo subjects.
- Give each picture 1-2 `alts` (other ways the archive may title the same subject).
- 6 to {MAX_PICTURES} pictures. One clear idea per scene: don't cast pictures nobody needs.
- Leave `prompt` empty; set `aspect` to what you expect (it is only a hint).
""" + "{SCENE_RULES}"


SCENE_RULES = """THE PICTURE TRACK (`scenes`, binding for the animator): the pictures follow the voice word by word.
- WHAT IS SAID IS WHAT IS SHOWN. Go through the script word by word: every time the narrator names something a viewer
  can see (a place, a person, an object, an event, a document, a number on a document), that thing comes on screen at
  that word (`at`). A line that names two things gets two entries: "He took Toulon, and Paris made him a general" ->
  {at: "Toulon", show: the port of Toulon} then {at: "general", show: him in a general's uniform}.
- Literally that thing: the line names a lab -> that lab; a ship -> the ship; a letter -> the letter; the person -> their
  portrait or them from behind. Never a loosely related, generic or decorative picture. A picture comes back later only
  when the narrator talks about that thing again.
- Every line has at least one entry; a picture stays until the next entry.
- words: 1-4 words from the line that carry it (a name, a number, a date, the key noun).
- ring: at most one ring every two or three lines, only around a word or an object the line points at (a number, a
  date, a name, a phrase on a document). Leave it empty otherwise. Never ring decoration."""


def art_system(st: dict) -> str:
    if SOURCE == "archive":
        return f"""You are the art director of a vertical documentary collage reel. Read the script and its shot notes and cast
EVERY picture the animator will need, then call the tool (`look` = one line describing the shared look, e.g. "sepia
archival photographs"). The animator places them like paper cut-outs on photo plates and paper, with big words and
hand-drawn white rings; they can reuse a picture in several scenes, flip it, scale it.

{ARCHIVE_RULES.replace("{SCENE_RULES}", SCENE_RULES)}

THE STYLE:
{st['style_md']}"""
    return f"""You are the art director of a vertical documentary collage reel. Read the script and its shot notes and cast
EVERY picture the animator will need, then call the tool. The animator places them like paper cut-outs on photo plates and
paper, with big words and hand-drawn white rings; they can reuse a picture in several scenes, flip it, scale it.

THE RULES (they save most of the time):
- ONE look line for everything generated: the same medium, era, palette and the same light direction (e.g. "Black and
  white archival documentary photograph, 1820s Vienna, soft window light from the upper left, gentle film grain, muted
  silver tones, realistic"). Match the era of the story; modern stories can be colour, but keep one palette.
- Keep rooms EMPTY. A plate is a place with nobody in it (a hall, a street, a study, a sky, a sea). People and objects are
  separate cut-outs, so they can be placed, moved and reused.
- Cut-outs: one subject each, whole (a full body, a hand and forearm, a chair, a piano, a dog, a ship). Arms / hands that
  must move get their own cut-out (an arm with its sleeve, entering from one edge) so the animator can swing them.
- A REAL person's face only ever comes from a real portrait: give it kind 'portrait' and a `search` (e.g. "Ludwig van
  Beethoven portrait Stieler 1820"). Every generated image of a real person shows them from BEHIND, far away or as a
  silhouette, never their face. Fictional or anonymous people can face the camera.
- Documents: letters, tickets, newspapers, scores, maps, diaries, flat from above.
- No text inside generated pictures except old handwriting / print on documents. No logos, no brands, no famous artworks.
- 6 to {MAX_PICTURES} pictures. One clear idea per scene: don't cast pictures nobody needs.
{SCENE_RULES}
- Aspect: plates 9:16; standing people 3:4 or 2:3; hands / arms 3:4; wide objects 4:3 or 1:1; documents 3:4.

THE STYLE:
{st['style_md']}"""


def _brief(s: dict) -> str:
    rows = "\n".join(f"{i:>3}  {l['text']}" for i, l in enumerate(s["lines"]))
    return f"TITLE: {s.get('title')}\n\nLINES:\n{rows}\n\nSHOT NOTES:\n{s.get('visual_notes') or '-'}"


def _clean(res: dict) -> tuple[str, list[dict]]:
    look = str(res.get("look") or "").strip()[:400] or "Black and white archival documentary photograph, soft light from the upper left, gentle film grain."
    out, seen = [], set()
    for p in res.get("pictures") or []:
        pid = re.sub(r"[^a-z0-9_]", "_", str(p.get("id") or "").lower()).strip("_")[:32]
        kind = p.get("kind") if p.get("kind") in KINDS else None
        if not pid or pid in seen or not kind:
            continue
        if (kind == "portrait" or SOURCE == "archive") and not str(p.get("search") or "").strip():
            continue
        if kind != "portrait" and SOURCE != "archive" and not str(p.get("prompt") or "").strip():
            continue
        seen.add(pid)
        out.append({"id": pid, "kind": kind, "prompt": str(p.get("prompt") or "").strip()[:900], "search": str(p.get("search") or "").strip()[:160],
                    "aspect": p.get("aspect") if p.get("aspect") in ASPECTS else ("9:16" if kind == "plate" else "3:4"),
                    "alts": [str(a).strip()[:160] for a in (p.get("alts") or []) if str(a).strip()][:2],
                    "lines": [int(x) for x in (p.get("lines") or []) if isinstance(x, (int, float))][:12], "use": str(p.get("use") or "")[:200]})
    return look, out[:MAX_PICTURES]


def _scenes(res: dict, n_lines: int) -> list[dict]:
    out = {}
    for sc in res.get("scenes") or []:
        try:
            i = int(sc.get("line"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < n_lines:
            out.setdefault(i, []).append({"line": i, "at": str(sc.get("at") or "").strip()[:40],
                      "show": [re.sub(r"[^a-z0-9_]", "_", str(x).lower()).strip("_") for x in (sc.get("show") or [])][:3],
                      "words": str(sc.get("words") or "").strip()[:60], "ring": str(sc.get("ring") or "").strip()[:40]})
    return [b for i in sorted(out) for b in out[i][:4]]


# ─────────────────────────── making them ───────────────────────────

async def _gemini(prompt: str, aspect: str) -> bytes:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured (Collage Documentary makes its pictures with Gemini)")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    last = None
    for model in (IMAGE_MODEL, IMAGE_FALLBACK):
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=180) as c:
                    r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                     headers={"x-goog-api-key": GEMINI_KEY}, json=body)
                if r.status_code == 200:
                    for cand in r.json().get("candidates") or []:
                        for part in (cand.get("content") or {}).get("parts") or []:
                            if "inlineData" in part:
                                return base64.b64decode(part["inlineData"]["data"])
                    last = f"{model}: no image ({str(r.json())[:200]})"
                    break                      # refused / blocked: a retry won't help, try the other model
                last = f"{model}: {r.status_code} {r.text[:200]}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            except httpx.HTTPError as e:
                last = f"{model}: {e!r}"
            await asyncio.sleep(3 * (attempt + 1))
    raise RuntimeError(last or "image generation failed")


def key_green(raw: bytes) -> Image.Image:
    """A picture on a green screen -> RGBA with the green gone (despilled), cropped to the subject."""
    im = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB")).astype(np.float32)
    h, w, _ = im.shape
    border = np.concatenate([im[:8].reshape(-1, 3), im[-8:].reshape(-1, 3), im[:, :8].reshape(-1, 3), im[:, -8:].reshape(-1, 3)])
    bg = np.median(border, 0)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    green = g - np.maximum(r, b)
    gbg = max(30.0, bg[1] - max(bg[0], bg[2]))
    dist = np.sqrt(((im - bg) ** 2).sum(-1))
    a = np.maximum(np.clip((gbg * .85 - green) / (gbg * .5), 0, 1), np.clip((dist - 40) / 60, 0, 1) * (green < gbg * .6))
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(3))).astype(np.float32)
    m = max(4, int(min(w, h) * .012))        # generators often draw a thin frame line at the very edge: drop it
    a[:m], a[-m:], a[:, :m], a[:, -m:] = 0, 0, 0, 0
    rgb = np.stack([r, np.minimum(g, np.maximum(r, b) + 6), b], -1)
    img = Image.fromarray(np.concatenate([rgb, a[..., None]], -1).clip(0, 255).astype(np.uint8), "RGBA")
    # keep the biggest solid part only (specks and stray frame bits go)
    mask = img.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    bb = mask.getbbox()
    if not bb:
        raise ValueError("the cut-out came back empty")
    pad = 6
    return img.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(w, bb[2] + pad), min(h, bb[3] + pad)))


def _fit(img: Image.Image, long_side: int) -> Image.Image:
    s = long_side / max(img.size)
    return img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS) if s < 1 else img


async def _portrait(p: dict, claude) -> dict | None:
    cands = await studio_media.search_commons(p["search"], kind="image", n=6)
    if not cands:
        return None
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        thumbs = await asyncio.gather(*[studio_media.thumb(c, x) for x in cands])
    pairs = [(x, th) for x, th in zip(cands, thumbs) if th]
    if not pairs:
        return None
    pick = 0
    if claude and len(pairs) > 1:
        content = [{"type": "text", "text": f"Which picture is the best portrait for: {p['search']}? It must be a painting, drawing or photograph "
                                            "OF that person (their face clearly visible), not a statue, a building, a document or someone else. "
                                            "Answer with the number only, or -1 if none fits."}]
        for i, (x, th) in enumerate(pairs):
            content += [{"type": "text", "text": f"{i}: {x['title'][:80]}"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(_jpeg(th, 320)).decode()}}]
        try:
            m = re.search(r"-?\d+", await claude(content))
            pick = int(m.group()) if m else 0
        except Exception as e:
            print(f"[collage] portrait pick failed: {e!r}")
        if pick < 0 or pick >= len(pairs):
            return None
    src = pairs[pick][0]
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
        r = await c.get(src["url"], headers={"User-Agent": studio_media.UA})
        r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)); img = ImageOps.exif_transpose(img).convert("RGB")
    return {"img": img, "credit": src.get("credit"), "page": src.get("page"), "title": src.get("title"), "licence": src.get("licence")}


def _jpeg(raw: bytes, w: int) -> bytes:
    im = Image.open(io.BytesIO(raw)).convert("RGB"); im.thumbnail((w, w * 2)); b = io.BytesIO(); im.save(b, "JPEG", quality=80); return b.getvalue()


# ─────────────────────────── archive photos ───────────────────────────

_isnet = None
import threading
_isnet_lock = threading.Lock()


def _isnet_session():
    global _isnet
    with _isnet_lock:
        return _load_isnet()


def _load_isnet():
    global _isnet
    if _isnet is None:
        import onnxruntime as ort
        path = os.path.join(MODEL_DIR, "isnet-general-use.onnx")
        if not os.path.exists(path) or os.path.getsize(path) < 100_000_000:
            os.makedirs(MODEL_DIR, exist_ok=True)
            print("[collage] downloading the background-removal model (once)")
            with httpx.stream("GET", ISNET_URL, follow_redirects=True, timeout=600) as r:
                r.raise_for_status()
                with open(path + ".part", "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            os.replace(path + ".part", path)
        opts = ort.SessionOptions(); opts.intra_op_num_threads = 2
        _isnet = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
    return _isnet


def cut_out(img: Image.Image) -> Image.Image:
    """A photo -> RGBA with only the main subject (IS-Net salient object mask), cropped to it."""
    rgb = img.convert("RGB")
    x = np.asarray(rgb.resize((1024, 1024), Image.BILINEAR)).astype(np.float32) / 255.0
    x = ((x - .5) / 1.0).transpose(2, 0, 1)[None]
    sess = _isnet_session()
    pred = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    pred = (pred - pred.min()) / (pred.max() - pred.min() + 1e-8)
    mask = Image.fromarray((pred * 255).astype(np.uint8)).resize(rgb.size, Image.BILINEAR)
    m = np.asarray(mask).astype(np.float32)
    m = np.clip((m - 40) / 170, 0, 1) * 255                     # firm the edges a little
    out = rgb.convert("RGBA"); out.putalpha(Image.fromarray(m.astype(np.uint8)))
    bb = Image.fromarray(m.astype(np.uint8)).point(lambda v: 255 if v > 60 else 0).getbbox()
    if not bb or (bb[2] - bb[0]) * (bb[3] - bb[1]) < .02 * rgb.width * rgb.height:
        raise ValueError("no clear subject to cut out")
    pad = 6
    return out.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(rgb.width, bb[2] + pad), min(rgb.height, bb[3] + pad)))


def grade(img: Image.Image, keep_colour: float = 0.0) -> Image.Image:
    """One archival look for pictures from many sources: monochrome with a warm silver tone, levels evened out.
    keep_colour 0..1 keeps some of the original colour (portraits)."""
    from PIL import ImageEnhance
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    rgb = img.convert("RGB")
    g = ImageOps.autocontrast(rgb.convert("L"), cutoff=1)
    toned = ImageOps.colorize(g, black=(22, 18, 14), white=(244, 236, 220), mid=(128, 118, 104))
    if keep_colour > 0:
        col = ImageEnhance.Color(ImageOps.autocontrast(rgb, cutoff=1)).enhance(.75)
        toned = Image.blend(toned, col, keep_colour)
    if alpha is not None:
        toned = toned.convert("RGBA"); toned.putalpha(alpha)
    return toned


def _big(c: dict, w: int = 1280) -> str:
    """A larger rendition of a candidate. Commons serves only standard thumbnail widths (w.wiki/GHai: 500, 960, 1280,
    1920...), so ask for 1280 when the original is bigger, else the original."""
    t = c.get("thumb") or ""
    if c.get("source") == "commons" and re.search(r"/\d+px-", t) and (c.get("w") or 0) > w:
        return re.sub(r"/\d+px-", f"/{w}px-", t)
    return c.get("url") or t


async def _archive(p: dict, claude, said: str = "") -> dict | None:
    """Try the search and its alternatives in turn; the first candidate that really shows the subject wins."""
    for q in [p["search"], *p.get("alts", [])]:
        got = await _archive_one(p, q, claude, said)
        if got:
            return got
    return None


async def _archive_one(p: dict, q: str, claude, said: str) -> dict | None:
    async with _archive_sem:
        cands = await studio_media.search(q, kind="image", n=8)
    cands = [c for c in cands if (c.get("w") or 1000) >= 500]
    if not cands:
        return None
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        thumbs = await asyncio.gather(*[studio_media.thumb(c, x) for x in cands])
    pairs = [(x, th) for x, th in zip(cands, thumbs) if th] or [(x, None) for x in cands[:1]]   # no thumbnails: take the top hit
    pick, shows = 0, ""
    if claude and pairs[0][1] is not None:
        want = {"plate": "a full-frame background (a place, no big text, no modern things, sharp)",
                "cutout": "ONE clear subject, big and whole in the frame, easy to cut out of its background",
                "document": "a flat document filling the frame", "portrait": "the person's face clearly visible"}[p["kind"]]
        content = [{"type": "text", "text": f"A documentary reel needs a picture of: {p['search']} ({p.get('use') or p['kind']}).\n"
                                            + (f"While it is on screen the narrator says: {said}\n" if said else "")
                                            + f"It must be {want}; no watermark, no collage, no screenshot, no modern look for a historical story.\n"
                                            "Pick the candidate that CLEARLY shows exactly that subject, so a viewer sees what the narrator says. "
                                            "If none does, answer -1 (better no picture than a wrong one).\n"
                                            "Answer on one line: the number | what that picture actually shows (under 15 words)."}]
        for i, (x, th) in enumerate(pairs):
            content += [{"type": "text", "text": f"{i}: {x['title'][:80]}"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(_jpeg(th, 320)).decode()}}]
        try:
            ans = await claude(content)
            m = re.search(r"-?\d+", ans)
            pick = int(m.group()) if m else -1
            shows = ans.split("|", 1)[1].strip()[:120] if "|" in ans else ""
        except Exception as e:
            print(f"[collage] archive pick failed: {e!r}")
        if pick < 0 or pick >= len(pairs):
            return None
    src = pairs[pick][0]
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
        r = await studio_media._get(c, _big(src))                 # our User-Agent, waits and retries on 429
        if r.status_code != 200 and src.get("url") and _big(src) != src["url"]:
            r = await studio_media._get(c, src["url"])
        r.raise_for_status()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(r.content))).convert("RGB")
    return {"img": img, "credit": src.get("credit"), "page": src.get("page"), "title": src.get("title"), "licence": src.get("licence"),
            "shows": shows or src.get("title", "")[:120]}


async def _cut_ok(cut: Image.Image, p: dict, claude) -> bool:
    """Is the cut-out the WHOLE subject, recognisable on its own (not a fragment such as one wheel of a cannon)?"""
    if not claude:
        return True
    im = cut.copy(); im.thumbnail((420, 420))
    bg = Image.new("RGBA", im.size, (235, 230, 220, 255)); bg.alpha_composite(im)
    b = io.BytesIO(); bg.convert("RGB").save(b, "JPEG", quality=80)
    content = [{"type": "text", "text": f"This was cut out of an archive photo to show: {p['search']} ({p.get('use') or ''}). Is it the WHOLE "
                                        "subject, clean and recognisable on its own by a viewer, not a fragment (e.g. one wheel of a "
                                        "cannon, half a person, a piece of a building) and not a messy blob? Answer yes or no."},
               {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}]
    try:
        return (await claude(content)).strip().lower().startswith("y")
    except Exception as e:
        print(f"[collage] cut-out check failed: {e!r}")
        return False


async def _one(p: dict, look: str, tmp: str, claude, said: str = "") -> dict | None:
    async with _sem:
        try:
            if SOURCE == "archive":
                got = await _archive(p, claude, said)
                if not got:
                    print(f"[collage] nothing in the archives for {p['search']!r}")
                    return None
                img = _fit(got["img"], 1400 if p["kind"] == "plate" else 1100)
                if p["kind"] == "cutout":
                    try:
                        cut = await asyncio.to_thread(cut_out, img)
                        ok = await _cut_ok(cut, p, claude)
                    except ValueError:
                        cut, ok = None, False
                    if ok:
                        img = cut
                    else:            # a fragment (a wheel instead of the cannon): show the whole photo as a taped print instead
                        print(f"[collage] cut-out of {p['id']} is not clean: using the photo as a print")
                        p = {**p, "kind": "document", "use": (p.get("use") or "") + " (shown as a whole photo print: tape it on the paper or a plate, do not treat it as a cut-out)"}
                img = grade(img, .55 if p["kind"] == "portrait" else 0)
                meta = {"credit": got["credit"], "page": got["page"], "source_title": got["title"], "licence": got["licence"], "shows": got["shows"]}
            elif p["kind"] == "portrait":
                got = await _portrait(p, claude)
                if not got:
                    print(f"[collage] no portrait found for {p['search']!r}")
                    return None
                img = _fit(got["img"], 1100)
                from PIL import ImageEnhance
                img = ImageEnhance.Color(img).enhance(.8)            # an old print: slightly faded colour
                meta = {"credit": got["credit"], "page": got["page"], "source_title": got["title"], "licence": got["licence"]}
            else:
                extra = GREEN if p["kind"] == "cutout" else PLATE if p["kind"] == "plate" else DOC
                raw = await _gemini(f"{look.rstrip('.')}. {p['prompt'].rstrip('.')}.{extra}", p["aspect"])
                img = key_green(raw) if p["kind"] == "cutout" else Image.open(io.BytesIO(raw)).convert("RGB")
                img = _fit(img, 1400 if p["kind"] == "plate" else 1100)
                meta = {}
            path = os.path.join(tmp, f"img_{p['id']}.webp")
            img.save(path, "WEBP", quality=86, method=4)
            return {**p, **meta, "path": path, "file": f"img/{p['id']}.webp", "w": img.width, "h": img.height}
        except Exception as e:
            print(f"[collage] picture {p['id']} failed: {e!r}")
            return None


async def make(job_id: str, claude_tool, claude_text, st: dict, s: dict, tmp: str, progress=None) -> dict:
    """claude_tool(system, content, max_tokens, role, tool) -> dict; claude_text(content) -> str (a short vision answer)."""
    res = await claude_tool(art_system(st), _brief(s) + "\n\nCast the pictures.", 4000, "art", ART_TOOL)
    look, plan = _clean(res)
    if not plan:
        raise ValueError("the art director cast no pictures")
    scenes = _scenes(res, len(s["lines"]))
    done = {"n": 0}

    def said(p):       # what the narrator says while this picture is on screen (the picker checks it shows that)
        idx = sorted({sc["line"] for sc in scenes if p["id"] in sc["show"]} | set(p.get("lines") or []))
        return " / ".join(s["lines"][i]["text"] for i in idx if 0 <= i < len(s["lines"]))[:400]

    async def run(p):
        r = await _one(p, look, tmp, claude_text, said(p))
        done["n"] += 1
        if progress:
            progress(done["n"], len(plan))
        return r
    pics = [p for p in await asyncio.gather(*[run(p) for p in plan]) if p]
    if len(pics) < max(3, len(plan) // 3):
        raise RuntimeError("most of the pictures could not be found or made")
    return {"look": look, "pictures": pics, "source": SOURCE, "scenes": scenes}


def scene_plan(scenes: list[dict], pics: list[dict], lines: list[dict]) -> str:
    """The binding plan for the animator: per line, the pictures that were really found (with what they show), the
    big words and the ring. A line whose pictures were not found gets paper + words, never a stand-in picture."""
    have = {p["id"]: p for p in pics}
    norm = lambda w: re.sub(r"[^a-z0-9]", "", str(w).lower())
    rows = []
    for i, ln in enumerate(lines):
        beats = [b for b in scenes if b["line"] == i] or [{"at": "", "show": [], "words": "", "ring": ""}]
        rows.append(f'line {i} ({ln.get("start", 0):.2f}-{ln.get("end", 0):.2f} s) "{ln["text"]}":')
        for b in beats:
            when, word = ln.get("start", 0), ""
            if b.get("at"):           # the time the naming word is spoken
                hit = next((w for w in ln.get("words") or [] if norm(w["w"]) == norm(b["at"].split()[0])), None)
                if hit:
                    when, word = hit["s"], hit["w"]
            show = [f'{x} ({have[x].get("shows") or have[x].get("use") or have[x]["kind"]})' for x in b["show"] if x in have]
            rows.append(f'   at {when:.2f} s' + (f' ("{word}")' if word else " (line start)") + ": "
                        + (", ".join(show) if show else "NO PICTURE FOUND: keep the previous picture (dimmed) or paper, with the big words")
                        + (f' | words: {b["words"]}' if b.get("words") else "") + f' | ring: {b.get("ring") or "none"}')
    return "\n".join(rows)


def public(pics: list[dict]) -> list[dict]:
    """What goes into T.images (the page): id, file, size, kind, use, what it shows."""
    return [{"id": p["id"], "file": p["file"], "w": p["w"], "h": p["h"], "kind": p["kind"], "use": p.get("use", ""),
             **({"shows": p["shows"]} if p.get("shows") else {}), **({"credit": p["credit"]} if p.get("credit") else {})} for p in pics]


def binaries(pics: list[dict]) -> dict:
    return {p["file"]: base64.b64encode(open(p["path"], "rb").read()).decode() for p in pics}


def sources(pics: list[dict]) -> list[dict]:
    return [{"title": p.get("source_title"), "page": p.get("page"), "licence": p.get("licence"), "credit": p.get("credit")}
            for p in pics if p.get("page")]


def sheet(pics: list[dict]) -> list[dict]:
    """Contact sheets for the animator: each picture on a checkerboard (so cut-outs show their edges), labelled."""
    out, cell, cols = [], 300, 4
    for k in range(0, len(pics), 8):
        group = pics[k:k + 8]; rows = (len(group) + cols - 1) // cols
        S = Image.new("RGB", (cols * cell, rows * (cell + 34)), (40, 40, 40)); d = ImageDraw.Draw(S)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 18)
        except OSError:
            font = ImageFont.load_default()
        for i, p in enumerate(group):
            x, y = (i % cols) * cell, (i // cols) * (cell + 34)
            im = Image.open(p["path"]).convert("RGBA"); im.thumbnail((cell - 12, cell - 12))
            bg = Image.new("RGBA", im.size, (200, 200, 200, 255)); cb = ImageDraw.Draw(bg)
            for yy in range(0, im.height, 16):
                for xx in range(0, im.width, 16):
                    if (xx // 16 + yy // 16) % 2:
                        cb.rectangle([xx, yy, xx + 15, yy + 15], fill=(160, 160, 160, 255))
            bg.alpha_composite(im)
            S.paste(bg.convert("RGB"), (x + (cell - im.width) // 2, y + 6 + (cell - 12 - im.height) // 2))
            d.text((x + 8, y + cell + 6), f"{p['id']} ({p['kind']}, {p['w']}x{p['h']})"[:34], fill=(240, 240, 240), font=font)
        b = io.BytesIO(); S.save(b, "JPEG", quality=82); out.append(base64.b64encode(b.getvalue()).decode())
    return out
