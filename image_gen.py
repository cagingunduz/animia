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
    """Replicate client.run with backoff on transient provider errors."""
    delays = [3, 6, 10, 10, 12, 15]
    for attempt in range(max_retries):
        try:
            return client.run(model, input=input_params)
        except Exception as e:
            if _is_retryable_replicate_error(e) and attempt < max_retries - 1:
                print(f"[WARN] {model} transient error, retry {attempt + 1}/{max_retries}: {repr(e)}")
                time.sleep(delays[min(attempt, len(delays) - 1)])
                continue
            raise


def _is_retryable_replicate_error(error: Exception) -> bool:
    status = getattr(error, "status", None)
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    msg = str(error).lower()
    transient_terms = (
        "internal",
        "try again later",
        "temporarily",
        "timeout",
        "timed out",
        "rate limit",
        "overloaded",
        "failed to generate image",
    )
    return any(term in msg for term in transient_terms)


def _run_with_fallback(
    client,
    primary_model: str,
    primary_input: dict,
    fallback_model: str,
    fallback_input: dict,
):
    try:
        return _run_with_retry(client, primary_model, primary_input)
    except Exception as primary_error:
        print(f"[WARN] {primary_model} failed, falling back to {fallback_model}: {repr(primary_error)}")
        try:
            return _run_with_retry(client, fallback_model, fallback_input)
        except Exception as fallback_error:
            raise RuntimeError(
                f"Image generation failed on primary {primary_model} and fallback {fallback_model}: "
                f"{repr(primary_error)} / {repr(fallback_error)}"
            ) from fallback_error


async def _download_and_upload_generated_image(image_url: str, folder: str, default_ext: str = "jpg") -> str:
    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "").lower()
    ext = "png" if "png" in content_type else default_ext
    return upload_to_r2(resp.content, folder, ext=ext)


# ─── GEMINI — 2D Animation (characters + scenes) ───

async def generate_character_image(character_prompt: str, photo_url: str = None) -> str:
    """Generate a character reference image using Grok (xai/grok-imagine-image).
    Keeps the whole image pipeline on Grok for stronger character consistency."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    input_params = {
        "prompt": character_prompt,
        "aspect_ratio": "9:16",
    }
    if photo_url:
        input_params["image"] = photo_url

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: _run_with_retry(client, "xai/grok-imagine-image", input_params)
    )
    image_url = _extract_url(output)

    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()

    return upload_to_r2(resp.content, "characters", ext="jpg")


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


async def generate_whiteboard_image(concept: str, aspect_ratio: str = "16:9") -> str:
    """Generate a clean black line-art illustration on a plain white background,
    for the Whiteboard Animation mode (revealed as if hand-drawn)."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    ar = ASPECT_RATIO_MAP.get(aspect_ratio, "16:9")

    prompt = (
        f"Black ink line drawing of: {concept}. "
        f"Simple hand-drawn marker sketch / doodle, clean bold black outlines on a "
        f"plain pure white background. Whiteboard explainer / doodle style. "
        f"Flat, no shading, no gradients, no color, no grey fills, minimal detail, "
        f"clear silhouette, lots of white space. No text, no watermark, no border."
    )
    input_params = {"prompt": prompt, "aspect_ratio": ar}
    fallback_input = {"prompt": prompt, "aspect_ratio": ar, "output_format": "png"}

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None,
        lambda: _run_with_fallback(
            client,
            "xai/grok-imagine-image",
            input_params,
            "google/gemini-2.5-flash-image",
            fallback_input,
        )
    )
    image_url = _extract_url(output)
    return await _download_and_upload_generated_image(image_url, "whiteboard")


async def generate_whiteboard_color_image(
    concept: str,
    aspect_ratio: str = "16:9",
    render_style: str = "classic",
) -> str:
    """Generate a COLORFUL flat illustration with bold black outlines on white, for the
    colored Whiteboard mode (outline is drawn, then the color washes in)."""
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    ar = ASPECT_RATIO_MAP.get(aspect_ratio, "16:9")

    if render_style == "illustrated":
        prompt = (
            f"Premium AI whiteboard explainer canvas illustration of: {concept}. "
            f"Create one rich educational scene, not a single icon: expressive hand-drawn "
            f"characters when useful, props, arrows, symbols, maps, coins, charts, or "
            f"cause-and-effect visual metaphors. Bold imperfect black ink outlines, warm "
            f"watercolor and colored-pencil fills, cross-hatching, sketch texture, and "
            f"editorial explainer composition on a pure white background. Arrange the "
            f"scene as 3 to 7 clear separated visual components so it can be revealed "
            f"piece by piece. Avoid tiny text; use simple symbols instead of words. "
            f"No photorealism, no 3D render, no glossy vector clipart, no watermark, "
            f"no border."
        )
    else:
        prompt = (
            f"Colorful flat vector illustration of: {concept}. "
            f"Bold clean BLACK outlines with simple flat color fills, cartoon / children's "
            f"book / explainer doodle style, on a plain pure white background. "
            f"Bright friendly colors, simple shapes, no shading, no gradients, no photo "
            f"realism, no text, no watermark, no border, lots of white space."
        )
    input_params = {"prompt": prompt, "aspect_ratio": ar}
    fallback_input = {"prompt": prompt, "aspect_ratio": ar, "output_format": "png"}

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None,
        lambda: _run_with_fallback(
            client,
            "xai/grok-imagine-image",
            input_params,
            "google/gemini-2.5-flash-image",
            fallback_input,
        )
    )
    image_url = _extract_url(output)
    return await _download_and_upload_generated_image(image_url, "whiteboard")


async def generate_fruit_drama_image(
    prompt: str,
    aspect_ratio: str = "9:16",
    reference_urls: list[str] | None = None,
    folder: str = "fruit-drama",
) -> str:
    """Generate Fruit Drama character/scene stills with Gemini Flash Image via Replicate.

    Replicate's Gemini image model is used for both clean character references and
    scene stills. When a reference is available, pass the first one as an image
    input and repeat all character details in the prompt for consistency.
    """
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)
    ar = ASPECT_RATIO_MAP.get(aspect_ratio, "9:16")
    input_params = {
        "prompt": prompt,
        "aspect_ratio": ar,
        "output_format": "png",
    }
    refs = [u for u in (reference_urls or []) if u]
    if refs:
        input_params["image"] = refs[0]
        if len(refs) > 1:
            input_params["prompt"] = (
                f"{prompt}\n\nAdditional character reference image URLs to preserve: "
                + ", ".join(refs[1:])
            )

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None, lambda: _run_with_retry(client, "google/gemini-2.5-flash-image", input_params)
    )
    image_url = _extract_url(output)
    return await _download_and_upload_generated_image(image_url, folder, default_ext="png")
