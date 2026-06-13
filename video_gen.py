import asyncio
import replicate
import os

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
FAL_KEY = os.environ.get("FAL_KEY")
MAX_DURATION = 11
MIN_DURATION = 3

RESOLUTION_MAP = {
    "480p": "480p",
    "720p": "720p",
    "1080p": "1080p"
}

GROK_TEXT_TO_VIDEO_MODEL = "xai/grok-imagine-video/text-to-video"
GROK_ASPECT_RATIOS = {"16:9", "4:3", "3:2", "1:1", "2:3", "3:4", "9:16"}


def _fal_video_model() -> str:
    return os.environ.get("FAL_2D_VIDEO_MODEL") or GROK_TEXT_TO_VIDEO_MODEL


def _is_text_to_video_model(model: str) -> bool:
    return "text-to-video" in (model or "")


def uses_text_to_video() -> bool:
    return bool(FAL_KEY and _is_text_to_video_model(_fal_video_model()))


def _grok_duration(value: int) -> int:
    return max(2, min(10, int(round(value or 6))))


def _grok_resolution(value: str) -> str:
    return "480p" if value == "480p" else "720p"


def _grok_aspect(value: str) -> str:
    return value if value in GROK_ASPECT_RATIOS else "16:9"


def _extract_url(output) -> str:
    if output is None:
        raise ValueError("Replicate returned None output")
    if isinstance(output, list):
        output = output[0]
    if hasattr(output, 'url'):
        return str(output.url)
    return str(output)


def _extract_fal_video_url(output: dict) -> str:
    video = (output or {}).get("video") or {}
    if isinstance(video, dict) and video.get("url"):
        return video["url"]
    raise ValueError(f"fal video output did not include a video URL: {output}")


def _veo_duration(value: int, resolution: str) -> str:
    if resolution == "1080p":
        return "8s"
    target = max(4, min(8, int(round(value or 8))))
    allowed = (4, 6, 8)
    return f"{min(allowed, key=lambda current: abs(current - target))}s"


def _veo_aspect(value: str) -> str:
    return value if value in ("16:9", "9:16") else "auto"


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
    speaking_duration: float = None,
    aspect_ratio: str = "16:9",
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

    if speaking_duration and speaking_duration > 0:
        speak_secs = round(speaking_duration, 1)
        prompt = (
            f"2D cartoon animation, {scene_description}, "
            f"character speaking naturally for {speak_secs} seconds, "
            f"speak normal words fluently, never spell words letter by letter, "
            f"mouth moving while talking, expressive hand gestures, "
            f"head nodding slightly, eyes blinking, smooth motion, natural body sway"
        )
    else:
        prompt = (
            f"2D cartoon animation, {scene_description}, "
            f"characters standing naturally, subtle breathing motion, "
            f"slight head movement, eyes blinking, smooth motion"
        )

    if FAL_KEY:
        import fal_client

        model = _fal_video_model()
        if _is_text_to_video_model(model):
            output = await fal_client.subscribe_async(
                model,
                arguments={
                    "prompt": prompt,
                    "duration": _grok_duration(duration),
                    "resolution": _grok_resolution(resolution),
                    "aspect_ratio": _grok_aspect(aspect_ratio),
                },
                with_logs=True,
                client_timeout=1200,
            )
            return _extract_fal_video_url(output)

        res = "1080p" if resolution == "1080p" else "720p"
        output = await fal_client.subscribe_async(
            model,
            arguments={
                "image_url": scene_image_url,
                "prompt": prompt,
                "duration": _veo_duration(duration, res),
                "resolution": res,
                "aspect_ratio": _veo_aspect(aspect_ratio),
                "generate_audio": bool(speaking_duration and speaking_duration > 0),
                "safety_tolerance": "4",
            },
            with_logs=True,
            client_timeout=1200,
        )
        return _extract_fal_video_url(output)

    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

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
        f"Animate this image into a subtle living photo (cinemagraph). {scene_description}. "
        f"Keep the character EXACTLY as shown — same face, hair, outfit, colors and identity; "
        f"do not redraw, rename or replace the character. The character stays mostly still, "
        f"with only very subtle motion (gentle breathing, a slight head movement, blinking). "
        f"Animate the ENVIRONMENT instead — wind, water, waves, drifting clouds, blowing "
        f"fabric and hair, leaves, dust, flickering light and small background movements. "
        f"Subtle, smooth, natural, atmospheric motion — just enough to feel alive."
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
            "fps": 48,  # smoother "living photo" feel for subtle/ambient motion
        }
    ))
    return _extract_url(output)
