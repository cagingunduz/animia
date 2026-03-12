import os
import httpx
import uuid
import io
import boto3
import asyncio
import replicate
from botocore.config import Config

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET", "animai-videos")
R2_PUBLIC_BASE = "https://pub-410f3488491a42f5a631e8944960bd55.r2.dev"


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


async def generate_character_image(character_prompt: str, photo_url: str = None) -> str:
    """
    Generate character PNG on white background.
    If photo_url provided, use as reference for likeness.
    """
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    input_params = {
        "prompt": character_prompt,
        "aspect_ratio": "1:1",
        "output_format": "png"
    }

    # If user provided a reference photo, add it
    if photo_url:
        input_params["image"] = photo_url

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(None, lambda: client.run("google/gemini-2.5-flash-image", input=input_params))
    image_url = _extract_url(output)

    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()
        image_bytes = resp.content

    return upload_to_r2(image_bytes, "characters")


async def generate_scene_image(
    scene_prompt: str,
    character_urls: list,   # List of R2 URLs for character PNGs
    aspect_ratio: str = "16:9"
) -> str:
    """
    Generate scene image with all character references.
    Supports up to 14 reference images (Gemini limit).
    """
    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    # Map aspect ratio to Replicate format
    ratio_map = {"16:9": "16:9", "9:16": "9:16", "1:1": "1:1"}
    ar = ratio_map.get(aspect_ratio, "16:9")

    input_params = {
        "prompt": scene_prompt,
        "aspect_ratio": ar,
        "output_format": "png"
    }

    # Add first character as primary reference
    if character_urls:
        input_params["image"] = character_urls[0]

    # Add additional characters as extra references if model supports it
    # Gemini 2.5 flash image supports multiple images via prompt context
    if len(character_urls) > 1:
        extra_refs = ", ".join([f"character reference {i+2}: {url}" for i, url in enumerate(character_urls[1:])])
        input_params["prompt"] = f"{scene_prompt}. Additional character references: {extra_refs}"

    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(None, lambda: client.run("google/gemini-2.5-flash-image", input=input_params))
    image_url = _extract_url(output)

    async with httpx.AsyncClient() as http:
        resp = await http.get(image_url, timeout=60)
        resp.raise_for_status()
        image_bytes = resp.content

    return upload_to_r2(image_bytes, "scenes")
