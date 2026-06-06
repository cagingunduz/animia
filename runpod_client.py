"""
Client for the self-hosted LTX-2.3 RunPod serverless endpoint.

Drop-in replacement for video_gen.animate_scene (same return: a video URL).
Submits an async job to RunPod, polls until done, returns the R2 video URL
that the worker produced.

Env:
  RUNPOD_API_KEY          RunPod API key
  RUNPOD_LTX_ENDPOINT_ID  serverless endpoint id
"""

import os
import time
import asyncio

import httpx

RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_LTX_ENDPOINT_ID")
BASE = "https://api.runpod.ai/v2"
MAX_WAIT_S = int(os.environ.get("RUNPOD_MAX_WAIT_S", "900"))  # 15 min safety deadline

NEGATIVE = (
    "distorted face, morphing facial features, warping, melting, extra limbs, "
    "deformed hands, inconsistent character, jittery motion, blurry, low quality, "
    "text artifacts, watermark, floating objects, duplicate objects, duplicated props, "
    "extra props, magnifying glass, morphing artifacts, distorted shapes, glitch, "
    "ghosting, deformed geometry, spurious objects"
)


def _build_prompt(scene_description: str, speaking_duration: float | None) -> str:
    # scene_description already carries the scene's motion hint from the script.
    base = (
        f"2D cartoon animation. {scene_description}. "
        f"Dynamic expressive character movement, lively energetic motion, "
        f"smooth fluid animation, cinematic camera movement."
    )
    if speaking_duration and speaking_duration > 0:
        base += " The character speaks naturally, mouth moving in sync."
    return base


async def animate_scene_runpod(
    scene_image_url: str,
    scene_description: str,
    duration: int = 5,
    resolution: str = "1080p",
    speaking_duration: float = None,
    aspect_ratio: str = "16:9",
    audio: bool = False,
) -> str:
    if not (RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID):
        raise RuntimeError("RUNPOD_API_KEY / RUNPOD_LTX_ENDPOINT_ID not set")

    payload = {
        "input": {
            "image_url": scene_image_url,
            "prompt": _build_prompt(scene_description, speaking_duration),
            "negative_prompt": NEGATIVE,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "audio": audio,
        }
    }
    headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{BASE}/{RUNPOD_ENDPOINT_ID}/run", json=payload, headers=headers)
        r.raise_for_status()
        job_id = r.json()["id"]

        deadline = time.monotonic() + MAX_WAIT_S
        while True:
            if time.monotonic() > deadline:
                raise RuntimeError(f"RunPod job {job_id} timed out after {MAX_WAIT_S}s")
            await asyncio.sleep(3)
            s = await c.get(f"{BASE}/{RUNPOD_ENDPOINT_ID}/status/{job_id}", headers=headers)
            s.raise_for_status()
            data = s.json()
            status = data.get("status")
            if status == "COMPLETED":
                out = data.get("output") or {}
                if out.get("error"):
                    raise RuntimeError(f"LTX worker error: {out['error']}")
                return out["video_url"]
            if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                raise RuntimeError(f"RunPod job {status}: {data}")
            # else IN_QUEUE / IN_PROGRESS -> keep polling
