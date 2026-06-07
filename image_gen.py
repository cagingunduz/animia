import os
import httpx
import uuid
import asyncio
import replicate
import boto3
from botocore.config import Config

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET", "animai-videos")
R2_PUBLIC_BASE = "https://assets.animave.com"

ASPECT_RATIO_MAP = {
    "16:9": "16:9",
    "9:16": "9:16",
    "1:1":  "1:1",
}


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )


def upload_to_r2(image_bytes: bytes, folder: str, ext: str = "png") -> str:
    s3 = get_r2_client()
    key = f"{folder}/{uuid.uuid4()}.{ext}"
    content_type = "image/png" if ext == "png" else "image/jpeg"
    s3.put_object(Bucket=R2_BUCKET, Key=key, Body=image_bytes, ContentType=content_type)
    return f"{R2_PUBLIC_BASE}/{key}"


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


# ─── GEMINI — 2D Animation (characters + scenes) ───

async def generate_character_image(character_prompt: str, photo_url: str = None) -> str:
    """Generate character PNG on white background using Gemini. Used for 2D Animation mode."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    input_params = {
        "prompt": character_prompt,
        "aspect_ratio": "3:4",
        "output_format": "png"
    }

    if photo_url:
        input_params["image"] = photo_url

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: _run_with_retry(client, "google/gemini-2.5-flash-image", input_params)
    )
    image_url = _extract_url(output)

    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()

    return upload_to_r2(resp.content, "characters")


async def generate_scene_image(
    scene_prompt: str,
    character_urls: list,
    aspect_ratio: str = "16:9"
) -> str:
    """Generate scene image with character references using Gemini. Used for 2D Animation mode."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    ar = ASPECT_RATIO_MAP.get(aspect_ratio, "16:9")

    input_params = {
        "prompt": scene_prompt,
        "aspect_ratio": ar,
        "output_format": "png"
    }

    if character_urls:
        input_params["image"] = character_urls[0]

    if len(character_urls) > 1:
        extra_refs = ", ".join([f"character reference {i+2}: {url}" for i, url in enumerate(character_urls[1:])])
        input_params["prompt"] = f"{scene_prompt}. Additional character references: {extra_refs}"

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: _run_with_retry(client, "google/gemini-2.5-flash-image", input_params)
    )
    image_url = _extract_url(output)

    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()

    return upload_to_r2(resp.content, "scenes")


# ─── GROK — 2.5D Animation (cinematic story scenes) ───

async def generate_storybook_scene_image(
    scene_prompt: str,
    aspect_ratio: str = "9:16"
) -> str:
    """
    Generate a cinematic scene image using Grok via Replicate.
    Used for 2.5D Animation / Storybook mode.
    """
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    ar = ASPECT_RATIO_MAP.get(aspect_ratio, "9:16")

    input_params = {
        "prompt": scene_prompt,
        "aspect_ratio": ar,
    }

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: _run_with_retry(client, "xai/grok-imagine-image", input_params)
    )
    image_url = _extract_url(output)

    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()

    return upload_to_r2(resp.content, "storybook", ext="jpg")


async def generate_scene_image_grok(
    scene_prompt: str,
    character_urls: list,
    aspect_ratio: str = "16:9"
) -> str:
    """Scene image via Grok (xai/grok-imagine-image), conditioned on the character
    reference image when available (image-editing) for consistency. Used for
    Animated Storytelling mode."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    ar = ASPECT_RATIO_MAP.get(aspect_ratio, "16:9")

    input_params = {"prompt": scene_prompt, "aspect_ratio": ar}
    if character_urls:
        input_params["image"] = character_urls[0]  # character reference for consistency

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: _run_with_retry(client, "xai/grok-imagine-image", input_params)
    )
    image_url = _extract_url(output)

    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()

    return upload_to_r2(resp.content, "scenes", ext="jpg")
