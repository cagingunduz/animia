"""Collage Documentary: the pictures. After the script, an art director (Claude) casts every picture the reel needs,
then they are made in parallel:

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
MAX_PICTURES = 14
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
                "lines": {"type": "array", "items": {"type": "integer"}, "description": "the 0-based voice lines it is used in"},
                "use": {"type": "string", "description": "how the animator should use it (one short sentence)"},
            }, "required": ["id", "kind", "aspect"]}},
        },
        "required": ["look", "pictures"],
    },
}


def art_system(st: dict) -> str:
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
        if kind == "portrait" and not str(p.get("search") or "").strip():
            continue
        if kind != "portrait" and not str(p.get("prompt") or "").strip():
            continue
        seen.add(pid)
        out.append({"id": pid, "kind": kind, "prompt": str(p.get("prompt") or "").strip()[:900], "search": str(p.get("search") or "").strip()[:160],
                    "aspect": p.get("aspect") if p.get("aspect") in ASPECTS else ("9:16" if kind == "plate" else "3:4"),
                    "lines": [int(x) for x in (p.get("lines") or []) if isinstance(x, (int, float))][:12], "use": str(p.get("use") or "")[:200]})
    return look, out[:MAX_PICTURES]


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


async def _one(p: dict, look: str, tmp: str, claude) -> dict | None:
    async with _sem:
        try:
            if p["kind"] == "portrait":
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
    done = {"n": 0}

    async def run(p):
        r = await _one(p, look, tmp, claude_text)
        done["n"] += 1
        if progress:
            progress(done["n"], len(plan))
        return r
    pics = [p for p in await asyncio.gather(*[run(p) for p in plan]) if p]
    if len([p for p in pics if p["kind"] != "portrait"]) < max(3, len([p for p in plan if p["kind"] != "portrait"]) // 2):
        raise RuntimeError("most of the pictures failed to generate")
    return {"look": look, "pictures": pics}


def public(pics: list[dict]) -> list[dict]:
    """What goes into T.images (the page): id, file, size, kind, use."""
    return [{"id": p["id"], "file": p["file"], "w": p["w"], "h": p["h"], "kind": p["kind"], "use": p.get("use", ""),
             **({"credit": p["credit"]} if p.get("credit") else {})} for p in pics]


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
