import asyncio
import replicate
import os

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
MAX_DURATION = 11
MIN_DURATION = 3

RESOLUTION_MAP = {
    "480p": "480p",
    "720p": "720p",
    "1080p": "1080p"
}


def _extract_url(output) -> str:
    if output is None:
        raise ValueError("Replicate returned None output")
    if isinstance(output, list):
        output = output[0]
    if hasattr(output, 'url'):
        return str(output.url)
    return str(output)


import time


def _run_with_retry(client, model: str, input_params: dict, max_retries: int = 6):
    """Replicate client.run with backoff on 429 (rate-limit) errors."""
    delays = [3, 6, 10, 10, 12, 15]
    for attempt in range(max_retries):
        try:
            return client.run(model, input=input_params)
        except Exception as e:
            if getattr(e, "status", None) == 429 and attempt < max_retries - 1:
                time.sleep(delays[min(attempt, len(delays) - 1)])
                continue
            raise


def calculate_duration(movement_duration: int, audio_duration: float) -> int:
    total = movement_duration + audio_duration + 0.5
    return max(MIN_DURATION, min(MAX_DURATION, round(total)))


async def animate_scene(
    scene_image_url: str,
    scene_description: str,
    duration: int = 5,
    resolution: str = "720p",
    speaking_duration: float = None
) -> str:
    # ── Self-hosted LTX-2.3 on RunPod (set VIDEO_BACKEND=runpod to enable) ──
    if os.environ.get("VIDEO_BACKEND") == "runpod":
        from runpod_client import animate_scene_runpod
        return await animate_scene_runpod(
            scene_image_url=scene_image_url,
            scene_description=scene_description,
            duration=duration,
            resolution=resolution,
            speaking_duration=speaking_duration,
        )

    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    if speaking_duration and speaking_duration > 0:
        speak_secs = round(speaking_duration, 1)
        prompt = (
            f"2D cartoon animation, {scene_description}, "
            f"character speaking naturally for {speak_secs} seconds, "
            f"mouth moving while talking, expressive hand gestures, "
            f"head nodding slightly, eyes blinking, smooth motion, natural body sway"
        )
    else:
        prompt = (
            f"2D cartoon animation, {scene_description}, "
            f"characters standing naturally, subtle breathing motion, "
            f"slight head movement, eyes blinking, smooth motion"
        )

    res = RESOLUTION_MAP.get(resolution, "720p")

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(None, lambda: client.run(
        "bytedance/seedance-1-lite",
        input={
            "image": scene_image_url,
            "prompt": prompt,
            "duration": duration,
            "resolution": res,
            "aspect_ratio": "16:9"
        }
    ))
    return _extract_url(output)


async def animate_scene_pvideo(
    scene_image_url: str,
    scene_description: str,
    duration: int = 5,
    resolution: str = "1080p",
    aspect_ratio: str = "16:9",
) -> str:
    """Animate a scene image with Replicate prunaai/p-video (image-to-video).
    Used by Animated Storytelling. p-video maxes at 1080p (2k -> 1080p)."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    res = "1080p" if resolution in ("1080p", "2k") else "720p"
    dur = max(1, min(10, int(duration)))
    prompt = (
        f"Animate this image. {scene_description}. "
        f"Keep the character EXACTLY as shown in the image — same face, hair, outfit, "
        f"colors and identity; do not redraw, rename or replace the character. "
        f"Dynamic expressive movement, lively natural motion, smooth fluid animation."
    )
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(None, lambda: _run_with_retry(
        client, "prunaai/p-video",
        {
            "image": scene_image_url,
            "prompt": prompt,
            "duration": dur,
            "resolution": res,
            "aspect_ratio": aspect_ratio,
        }
    ))
    return _extract_url(output)
