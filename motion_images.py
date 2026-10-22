"""
Stills for image-based Motion Graphics looks ("cinematic3d"): one pre-rendered 3D-style image
per beat, generated with FAL Gemini Flash Image. The first still is made from text; the rest
use it as a reference image so the recurring character stays the same. The stills are then
animated in code (camera moves, scans, blinks, overlays) like any other composition.
"""

import asyncio
import base64
import os

import httpx

from image_gen import generate_scene_image

IMAGE_COST = float(os.environ.get("MOTION_IMAGE_COST_USD", "0.039"))  # per still, for usage reporting
_SEM = asyncio.Semaphore(int(os.environ.get("MOTION_IMAGE_CONCURRENCY", "3")))

LOOK_3D = ("Stylized semi-realistic 3D render, clean smooth CG, Blender Cycles look, soft cinematic lighting, "
           "shallow depth of field, rich but natural colours, medical-visualization aesthetic. "
           "No text, no letters, no numbers, no watermark. ")
FRAMING = {"9:16": "Vertical 9:16 composition, subject centred with room above and below. ",
           "16:9": "Wide 16:9 composition. ", "1:1": "Square composition. "}


async def _still(prompt: str, aspect: str, refs: list[str]) -> str:
    async with _SEM:
        return await generate_scene_image(scene_prompt=prompt, character_urls=refs, aspect_ratio=aspect)


def _jpeg_b64(data: bytes, max_side: int = 1920) -> str:
    """Re-encode as a ~1080p JPEG so compositions stay small to ship to the render service."""
    import cv2
    import numpy as np
    im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        return base64.b64encode(data).decode()
    h, w = im.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        im = cv2.resize(im, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return base64.b64encode(buf.tobytes() if ok else data).decode()


async def generate_stills(plan: dict, aspect: str, tmp: str) -> list[tuple[str, str | None]]:
    """Returns [(asset path, base64 jpeg or None)] aligned with plan['shots']."""
    anchor = (plan.get("character_anchor") or "").strip()
    shots = plan["shots"]
    prompts = [LOOK_3D + FRAMING.get(aspect, "") + (f"Recurring character, identical in every image: {anchor} " if anchor else "")
               + (s.get("still_prompt") or s.get("visual") or "") for s in shots]
    keys = [f"assets/beat{s['n']}.jpg" for s in shots]

    async def fetch(url: str) -> bytes:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.content

    out: list[tuple[str, str | None]] = [(k, None) for k in keys]
    try:
        first_url = await _still(prompts[0], aspect, [])
        out[0] = (keys[0], _jpeg_b64(await fetch(first_url)))
    except Exception as e:
        print(f"[motion images] first still failed: {e!r}")
        first_url = None
    refs = [first_url] if (first_url and anchor) else []

    async def one(i: int):
        try:
            url = await _still(prompts[i], aspect, refs)
            out[i] = (keys[i], _jpeg_b64(await fetch(url)))
        except Exception as e:
            print(f"[motion images] still {i + 1} failed: {e!r}")
    await asyncio.gather(*[one(i) for i in range(1, len(shots))])
    return out
