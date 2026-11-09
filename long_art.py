"""Long videos: the art. Flat vector plates (empty places) and characters on a chroma green, all matched to ONE style
master picture (the first plate is made first, then every other picture is made with it as the reference).

Image model: Gemini 2.5 / 3.x image ("nano banana") through whichever key the backend has, in this order:
GEMINI_API_KEY (Google directly), FAL_KEY (fal.ai), REPLICATE_API_TOKEN (Replicate). All take a reference image.
"""

import asyncio
import base64
import io
import os
import re

import httpx

GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
FAL_KEY = os.environ.get("FAL_KEY")
REPLICATE_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
GEMINI_MODEL = os.environ.get("LONG_IMAGE_MODEL", "gemini-3.1-flash-image")
_sem = asyncio.Semaphore(int(os.environ.get("LONG_IMAGE_PARALLEL", "4")))

STYLE = ("Flat vector illustration for an animated explainer video. Flat colour shapes with NO outlines at all; each "
         "shape has one slightly darker flat shade for form. Muted palette: dusty blue-grey, slate teal, warm beige, navy, "
         "soft purple, with small warm accents. Characters have salmon-pink skin, big round heads and simple dot eyes. "
         "Clean, simple, friendly 2D, no gradients, no texture, no text, no letters, no numbers, no logos, no watermark.")
PLATE = (" An EMPTY place with nobody in it, seen straight-on as a wide stage-like view, an open floor across the lower "
         "third where characters can stand, every sign, board and screen in it blank.")
GREEN = (" Full body, the whole figure inside the frame with a margin, standing on nothing, isolated on a solid flat chroma "
         "green background (#00B140) with nothing else in the frame, no shadow on the background, nothing green on the character.")
OBJECT = " A single object, whole, isolated on a solid flat chroma green background (#00B140), nothing green on the object."


# Remakes pin Nano Banana (Gemini 2.5 Flash Image, ~$0.039/image; Google lists 2027-03-15 as its earliest shutdown) on
# every provider, whatever the LONG_/FAL_/REPLICATE_ model overrides say. Successor when it retires:
# gemini-3.1-flash-lite-image (set REMAKE_GEMINI_IMAGE_MODEL etc.).
NANO = {"gemini": os.environ.get("REMAKE_GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        "fal": os.environ.get("REMAKE_FAL_IMAGE_MODEL", "fal-ai/gemini-25-flash-image"),
        "replicate": os.environ.get("REMAKE_REPLICATE_IMAGE_MODEL", "google/nano-banana")}
REMAKE_REF = ("Use the reference picture ONLY for its art style (medium, line work, texture, palette, light, and exactly how "
              "the characters' heads, faces and bodies are drawn). Do NOT copy its layout, objects or composition: draw "
              "something completely different, exactly as described: ")

REF = ("Use the reference picture ONLY for its art style (flat shapes, palette, shading, how faces look). Do NOT copy its "
       "layout, furniture, objects or composition: draw something completely different, exactly as described: ")


ORDER = [x.strip() for x in os.environ.get("LONG_IMAGE_PROVIDERS", "replicate,fal,gemini").split(",") if x.strip()]
_dead: dict[str, float] = {}          # provider -> time it last failed hard (no credit, bad key): skipped for 10 minutes


def providers() -> list[str]:
    have = {"replicate": bool(REPLICATE_TOKEN), "fal": bool(FAL_KEY), "gemini": bool(GEMINI_KEY)}
    import time
    return [p for p in ORDER if have.get(p) and time.time() - _dead.get(p, 0) > 600]


def provider() -> str:
    ps = providers()
    return ps[0] if ps else ""


async def _gemini(prompt: str, aspect: str, ref: bytes | None, model: str | None = None, ref_text: str = REF) -> bytes:
    parts = [{"text": prompt}]
    if ref:
        parts = [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(ref).decode()}},
                 {"text": ref_text + prompt}]
    body = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model or GEMINI_MODEL}:generateContent",
                         headers={"x-goog-api-key": GEMINI_KEY}, json=body)
    r.raise_for_status()
    for cand in r.json().get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            if "inlineData" in part:
                return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError(f"no image: {str(r.json())[:200]}")


async def _fal(prompt: str, aspect: str, ref_url: str | None, model: str | None = None, ref_text: str = REF) -> bytes:
    import fal_client
    model = model or os.environ.get("FAL_IMAGE_MODEL", "fal-ai/gemini-25-flash-image")
    args = {"prompt": prompt, "aspect_ratio": aspect, "output_format": "png", "num_images": 1}
    if ref_url:
        model = model if model.endswith("/edit") else model + "/edit"
        args = {"prompt": ref_text + prompt, "image_urls": [ref_url], "output_format": "png", "num_images": 1, "aspect_ratio": aspect}
    out = await fal_client.run_async(model, arguments=args)
    url = (out.get("images") or [{}])[0].get("url")
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url); r.raise_for_status(); return r.content


async def _replicate(prompt: str, aspect: str, ref_url: str | None, model: str | None = None, ref_text: str = REF) -> bytes:
    import replicate
    cl = replicate.Client(api_token=REPLICATE_TOKEN)
    inp = {"prompt": (ref_text if ref_url else "") + prompt, "aspect_ratio": aspect, "output_format": "png"}
    if ref_url:
        inp["image_input"] = [ref_url]
    out = await asyncio.to_thread(cl.run, model or os.environ.get("REPLICATE_IMAGE_MODEL", "google/nano-banana"), input=inp)
    out = out[0] if isinstance(out, list) else out
    url = str(getattr(out, "url", out))
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url); r.raise_for_status(); return r.content


async def make(prompt: str, aspect: str, ref: bytes | None = None, ref_url: str | None = None, nano: bool = False) -> bytes:
    """One picture: Replicate first, then fal, then Gemini (LONG_IMAGE_PROVIDERS), whichever works right now. A provider
    that fails hard (no credit, bad key) is skipped for 10 minutes; transient errors are retried.
    nano=True (remakes): Nano Banana on every provider (NANO), the reference read with REMAKE_REF."""
    rt = REMAKE_REF if nano else REF
    import time
    ps = providers()
    if not ps:
        raise RuntimeError("No image model is configured (REPLICATE_API_TOKEN, FAL_KEY or GEMINI_API_KEY)")
    last = None
    async with _sem:
        for p in ps:
            for attempt in range(2):
                try:
                    m = NANO[p] if nano else None
                    if p == "gemini":
                        return await _gemini(prompt, aspect, ref, m, rt)
                    if p == "fal":
                        return await _fal(prompt, aspect, ref_url, m, rt)
                    return await _replicate(prompt, aspect, ref_url, m, rt)
                except Exception as e:
                    last = e
                    msg = str(e).lower()
                    if any(k in msg for k in ("credit", "balance", "billing", "payment", "insufficient", "unauthor", "401", "402", "403", "invalid api", "exhausted")):
                        _dead[p] = time.time(); print(f"[long_art] {p} unavailable ({e!r}), trying the next provider"); break
                    await asyncio.sleep(3 * (attempt + 1))
    raise RuntimeError(f"image generation failed on {', '.join(ps)}: {last!r}")


def plate_prompt(desc: str) -> str:
    return f"{STYLE} {desc.rstrip('.')}.{PLATE}"


def char_prompt(desc: str, pose: str) -> str:
    return f"{STYLE} {desc.rstrip('.')}, {pose.rstrip('.')}.{GREEN}"


def object_prompt(desc: str) -> str:
    return f"{STYLE} {desc.rstrip('.')}.{OBJECT}"


def key(raw: bytes):
    """Chroma green -> RGBA (border-connected green, so dark clothes never leak), soft 2 px edge, despilled."""
    import numpy as np
    from PIL import Image, ImageFilter
    from scipy import ndimage
    im = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB")).astype(np.float32)
    h, w, _ = im.shape
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    border = np.concatenate([im[:6].reshape(-1, 3), im[-6:].reshape(-1, 3), im[:, :6].reshape(-1, 3), im[:, -6:].reshape(-1, 3)])
    bg = np.median(border, 0)
    cand = ((g - np.maximum(r, b)) > 40) & (np.sqrt(((im - bg) ** 2).sum(-1)) < 110)
    lab, _ = ndimage.label(cand)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bgmask = np.isin(lab, list(edge))
    alpha = (~bgmask).astype(np.float32)
    alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))).astype(np.float32) / 255
    band = (alpha > 0.02) & (alpha < 0.98)
    g2 = np.where(band | (alpha > 0), np.minimum(g, np.maximum(r, b) + 6), g)
    out = Image.fromarray(np.dstack([r, g2, b, alpha * 255]).clip(0, 255).astype(np.uint8), "RGBA")
    bb = out.getchannel("A").point(lambda v: 255 if v > 30 else 0).getbbox()
    if not bb:
        raise ValueError("empty cut-out")
    return out.crop((max(0, bb[0] - 4), max(0, bb[1] - 4), min(w, bb[2] + 4), min(h, bb[3] + 4)))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", str(s).lower()).strip("_")[:32] or "x"


def boards(raw: bytes, out_w: int = 1920, out_h: int = 1080) -> list[dict]:
    """Blank surfaces to write on, measured on the plate (whiteboards, signs, panels: near-white; screens: near-black
    and flat): [{x, y, w, h, kind}] in frame pixels (the plate is drawn to cover out_w x out_h), biggest first."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    s = max(out_w / im.width, out_h / im.height); ox, oy = (out_w - im.width * s) / 2, (out_h - im.height * s) / 2
    a = np.asarray(im.resize((im.width // 2, im.height // 2))).astype(np.int16)
    found = []
    for kind, mask in (("board", (a.min(-1) > 232) & ((a.max(-1) - a.min(-1)) < 18)),
                       ("screen", (a.max(-1) < 70) & ((a.max(-1) - a.min(-1)) < 22))):
        mask = ndimage.binary_opening(mask, iterations=2)
        lab, n = ndimage.label(mask)
        for sl in ndimage.find_objects(lab):
            if sl is None:
                continue
            y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
            bw, bh = x1 - x0, y1 - y0
            region = mask[y0:y1, x0:x1].mean()
            if bw * bh < 0.008 * mask.size or region < 0.88 or bw < 40 or bh < 25 or bw / bh > 6 or bh / bw > 3:
                continue
            k = 2 * s
            found.append({"kind": kind, "x": round(ox + x0 * k), "y": round(oy + y0 * k), "w": round(bw * k), "h": round(bh * k)})
    return sorted(found, key=lambda b: -b["w"] * b["h"])[:4]
