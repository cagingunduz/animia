import asyncio
import replicate
import os

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
MAX_DURATION = 11
MIN_DURATION = 3


def _extract_url(output) -> str:
    if output is None:
        raise ValueError("Replicate returned None output")
    if isinstance(output, list):
        output = output[0]
    if hasattr(output, 'url'):
        return str(output.url)
    return str(output)


def calculate_duration(movement_duration: int, audio_duration: float) -> int:
    """Calculate Seedance duration: movement + audio + 1s buffer, clamped to 3-11s."""
    total = movement_duration + audio_duration + 1.0
    return max(MIN_DURATION, min(MAX_DURATION, round(total)))


async def animate_scene(
    scene_image_url: str,
    scene_description: str,
    duration: int = 5
) -> str:
    """Generate silent animation from scene image."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(None, lambda: client.run(
        "bytedance/seedance-1-lite",
        input={
            "image": scene_image_url,
            "prompt": f"2D cartoon animation, {scene_description}, character talking and gesturing naturally, smooth motion, expressive",
            "duration": duration,
            "resolution": "1080p",
            "aspect_ratio": "16:9"
        }
    ))
    return _extract_url(output)
