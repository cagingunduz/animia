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
