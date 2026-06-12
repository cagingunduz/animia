import base64
import asyncio
import json
import os
import tempfile
import time
import traceback
import uuid

import anthropic
import httpx

from jobs import job_store
from image_gen import generate_fruit_drama_image
from storybook_pipeline import (
    concat_video_files,
    download_file,
    log,
    set_scene_status,
    upload_bytes_to_r2,
)


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
VEO_MODEL = os.environ.get("VEO_MODEL", "veo-3.1-lite-generate-preview")
VEO_DEFAULT_DURATION = int(os.environ.get("VEO_DEFAULT_DURATION", "8"))
VEO_DEFAULT_RESOLUTION = os.environ.get("VEO_DEFAULT_RESOLUTION", "720p")
VEO_DEFAULT_ASPECT_RATIO = os.environ.get("VEO_DEFAULT_ASPECT_RATIO", "9:16")


def _valid_aspect_ratio(value: str | None) -> str:
    return value if value in ("9:16", "16:9") else VEO_DEFAULT_ASPECT_RATIO


def _valid_resolution(value: str | None) -> str:
    return value if value in ("720p", "1080p") else VEO_DEFAULT_RESOLUTION


def _valid_duration(value) -> int:
    try:
        seconds = int(value)
    except Exception:
        seconds = VEO_DEFAULT_DURATION
    return seconds if seconds in (4, 6, 8) else 8


def _extract_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.strip().startswith("json"):
            text = text.strip()[4:]
    return json.loads(text.strip())


def _raise_for_veo_error(response: httpx.Response, context: str):
    if response.is_success:
        return
    body = response.text[:2000]
    raise RuntimeError(f"Veo {context} failed ({response.status_code}): {body}")


def _character_reference_prompt(character: dict, aspect_ratio: str) -> str:
    orientation = "vertical" if aspect_ratio == "9:16" else "horizontal"
    return f"""{orientation.capitalize()} {aspect_ratio} full-body character reference image.
Create a young adult anthropomorphic fruit character in premium Pixar-quality stylized 3D animated film design.

Character:
- Name: {character.get("name")}
- Fruit identity: {character.get("fruit")}
- Gender/style: {character.get("gender")}
- Role: {character.get("role")}
- Personality: {character.get("personality")}
- Outfit: {character.get("outfit")}
- Visual identity: {character.get("visual_description")}

Requirements:
Full body, centered composition, clean white studio background, soft shadow under feet.
Realistic fruit texture, expressive human-like eyes, clean brows, soft lips integrated naturally into the fruit surface.
Human-like animated body proportions, polished family-friendly 3D render, no props, no text, no watermark, no extra characters."""


def _scene_image_prompt(scene: dict, characters: list[dict], aspect_ratio: str) -> str:
    orientation = "vertical" if aspect_ratio == "9:16" else "horizontal"
    char_lines = []
    for c in characters:
        char_lines.append(
            f"{c.get('name')}: young adult anthropomorphic {c.get('fruit')} character, "
            f"{c.get('visual_description')}, {c.get('gender')} styling, {c.get('outfit')}, "
            f"personality: {c.get('personality')}. Preserve exact fruit identity, face design, body proportions, outfit colors, and texture."
        )
    return f"""Use the provided character reference images. Preserve the exact character identities and outfits.

{orientation.capitalize()} {aspect_ratio} ultra-detailed Pixar-style 3D cinematic render for a viral AI Fruit Drama short.

Characters in this scene:
{chr(10).join(char_lines)}

Scene:
- Title: {scene.get("title")}
- Location: {scene.get("location")}
- Action: {scene.get("action")}
- Emotion: {scene.get("emotion")}

Environment and camera:
{scene.get("image_direction")}

Composition must match a dramatic soap-opera short: cinematic lighting, shallow depth of field, expressive faces, rich fruit texture, smooth high-end 3D animation look. No text, no subtitles, no watermark."""


def _video_prompt(scene: dict, aspect_ratio: str) -> str:
    orientation = "vertical" if aspect_ratio == "9:16" else "horizontal"
    dialogue = scene.get("dialogue") or []
    dialogue_lines = "\n".join([f'{d.get("speaker")}: "{d.get("line")}"' for d in dialogue if d.get("line")])
    return f"""Animate this image as a {orientation} {aspect_ratio} AI Fruit Drama scene with native audio.

Motion:
{scene.get("video_motion")}

Drama direction:
Emotional soap-opera tension, subtle facial expressions, small body movements, smooth Pixar-style 3D character animation, cinematic lighting, no subtitles, no text, no watermark.

Dialogue with natural character voices:
{dialogue_lines}

Ambient sound should match the location: {scene.get("location")}."""


async def generate_fruit_drama_plan(
    title: str,
    main_fruit: str,
    main_gender: str,
    second_fruit: str,
    second_gender: str,
    scene_count: int,
) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=7000,
        messages=[{
            "role": "user",
            "content": f"""You are a viral short-form AI Fruit Drama director.

Create a family-safe, emotional, funny-but-serious fruit drama plan.

Story idea: {title}
Main character fruit/gender: {main_fruit} / {main_gender}
Second character fruit/gender: {second_fruit} / {second_gender}
Total scenes: {scene_count}

Return JSON ONLY with this exact shape:
{{
  "characters": [
    {{
      "id": "main",
      "name": "...",
      "fruit": "...",
      "gender": "...",
      "role": "...",
      "personality": "...",
      "outfit": "...",
      "visual_description": "full fruit texture, face, body and style description"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "title": "...",
      "location": "...",
      "characters": ["main", "second"],
      "action": "clear visible action",
      "emotion": "betrayal / jealousy / shock / relief / etc.",
      "image_direction": "cinematic image composition, camera, lighting, background",
      "video_motion": "short motion direction for image-to-video",
      "dialogue": [
        {{"speaker": "Character Name", "line": "short viral line"}},
        {{"speaker": "Character Name", "line": "short reply"}}
      ]
    }}
  ]
}}

Rules:
- Use only family-safe drama, no explicit/sexual content.
- Keep dialogue short, punchy, and viral.
- Every scene should work as an 8-second clip.
- Keep character outfits consistent across scenes unless the story explicitly requires a change.
- Use premium Pixar-style 3D animated fruit character design."""
        }]
    )
    return _extract_json(message.content[0].text)


async def generate_veo_video_from_image(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    out_path: str,
    aspect_ratio: str,
    resolution: str,
    duration_seconds: int,
) -> bool:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY is not configured")

    base_url = "https://generativelanguage.googleapis.com/v1beta"
    model = VEO_MODEL
    payload = {
        "instances": [{
            "prompt": prompt,
            "image": {
                "bytesBase64Encoded": base64.b64encode(image_bytes).decode("ascii"),
                "mimeType": mime_type,
            },
        }],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "durationSeconds": duration_seconds,
            "resolution": resolution,
            "personGeneration": "allow_adult",
        },
    }

    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        start = await client.post(
            f"{base_url}/models/{model}:predictLongRunning",
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json=payload,
        )
        _raise_for_veo_error(start, "start")
        operation_name = start.json().get("name")
        if not operation_name:
            raise RuntimeError(f"Veo did not return operation name: {start.text}")

        deadline = time.time() + 12 * 60
        status = {}
        while time.time() < deadline:
            await asyncio.sleep(10)
            poll = await client.get(
                f"{base_url}/{operation_name}",
                headers={"x-goog-api-key": GEMINI_API_KEY},
            )
            _raise_for_veo_error(poll, "poll")
            status = poll.json()
            if status.get("done"):
                break
        else:
            raise TimeoutError(f"Veo generation timed out: {operation_name}")

        if status.get("error"):
            raise RuntimeError(f"Veo generation failed: {status['error']}")

        samples = (
            status.get("response", {})
            .get("generateVideoResponse", {})
            .get("generatedSamples", [])
        )
        if not samples:
            raise RuntimeError(f"Veo completed without generated samples: {status}")
        video_uri = samples[0].get("video", {}).get("uri")
        if not video_uri:
            raise RuntimeError(f"Veo completed without video uri: {status}")

        video_resp = await client.get(video_uri, headers={"x-goog-api-key": GEMINI_API_KEY})
        video_resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(video_resp.content)
        return True


async def run_fruit_drama_pipeline(job_id: str, payload: dict):
    try:
        title = payload["title"]
        scene_count = max(1, min(10, int(payload.get("scene_count") or 5)))
        aspect_ratio = _valid_aspect_ratio(payload.get("aspect_ratio"))
        resolution = _valid_resolution(payload.get("resolution"))
        duration_seconds = _valid_duration(payload.get("duration_seconds_per_scene"))
        if resolution == "1080p":
            duration_seconds = 8

        total_steps = 2 + scene_count * 2 + (1 if scene_count > 1 else 0)
        job_store[job_id]["total_steps"] = total_steps
        job_store[job_id]["scenes"] = [
            {"scene_index": i + 1, "status": "queued", "video_url": None, "image_url": None}
            for i in range(scene_count)
        ]

        log(job_id, 1, total_steps, "Fruit drama senaryosu ve karakterleri yazılıyor...")
        plan = await generate_fruit_drama_plan(
            title=title,
            main_fruit=payload.get("main_fruit", "peach"),
            main_gender=payload.get("main_gender", "girl"),
            second_fruit=payload.get("second_fruit", "banana"),
            second_gender=payload.get("second_gender", "boy"),
            scene_count=scene_count,
        )
        characters = plan.get("characters", [])[:3]
        scenes = plan.get("scenes", [])[:scene_count]
        if not characters or not scenes:
            raise RuntimeError("Fruit drama plan did not include characters/scenes")

        log(job_id, 2, total_steps, "Karakter referansları oluşturuluyor...")
        character_urls = {}
        for character in characters:
            prompt = _character_reference_prompt(character, aspect_ratio)
            character_urls[character["id"]] = await generate_fruit_drama_image(
                prompt, aspect_ratio=aspect_ratio, folder="fruit-drama-characters"
            )
        job_store[job_id]["characters"] = [
            {**c, "image_url": character_urls.get(c["id"])} for c in characters
        ]

        tmp = tempfile.mkdtemp()
        clip_urls = []
        for i, scene in enumerate(scenes):
            idx = i + 1
            set_scene_status(job_id, idx, "processing")
            log(job_id, 2 + (idx - 1) * 2 + 1, total_steps, f"Sahne {idx}/{scene_count}: görsel oluşturuluyor...")
            scene_chars = [c for c in characters if c["id"] in scene.get("characters", [])] or characters
            refs = [character_urls.get(c["id"]) for c in scene_chars if character_urls.get(c["id"])]
            image_prompt = _scene_image_prompt(scene, scene_chars, aspect_ratio)
            image_url = await generate_fruit_drama_image(
                image_prompt,
                aspect_ratio=aspect_ratio,
                reference_urls=refs,
                folder="fruit-drama-scenes",
            )
            for s in job_store[job_id]["scenes"]:
                if s["scene_index"] == idx:
                    s["image_url"] = image_url
                    break

            log(job_id, 2 + (idx - 1) * 2 + 2, total_steps, f"Sahne {idx}/{scene_count}: Veo ile animate ediliyor...")
            image_bytes = await download_file(image_url)
            mime = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
            out_path = f"{tmp}/fruit_scene_{idx}_{uuid.uuid4().hex[:8]}.mp4"
            await generate_veo_video_from_image(
                image_bytes=image_bytes,
                mime_type=mime,
                prompt=_video_prompt(scene, aspect_ratio),
                out_path=out_path,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                duration_seconds=duration_seconds,
            )
            with open(out_path, "rb") as f:
                video_url = upload_bytes_to_r2(f.read(), "fruit-drama-scenes", "mp4", "video/mp4")
            set_scene_status(job_id, idx, "completed", video_url=video_url)
            clip_urls.append(video_url)

        if len(clip_urls) == 1:
            final_url = clip_urls[0]
        else:
            log(job_id, total_steps, total_steps, "Fruit drama sahneleri birleştiriliyor...")
            local_paths = []
            for i, url in enumerate(clip_urls):
                data = await download_file(url)
                p = f"{tmp}/clip_{i}_{uuid.uuid4().hex[:8]}.mp4"
                with open(p, "wb") as f:
                    f.write(data)
                local_paths.append(p)
            final_path = f"{tmp}/fruit_final_{uuid.uuid4().hex[:8]}.mp4"
            if not concat_video_files(local_paths, final_path):
                raise RuntimeError("Fruit drama concat failed")
            with open(final_path, "rb") as f:
                final_url = upload_bytes_to_r2(f.read(), "fruit-drama-final", "mp4", "video/mp4")

        job_store[job_id]["status"] = "completed"
        job_store[job_id]["message"] = "Tamamlandı!"
        job_store[job_id]["final_video_url"] = final_url

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{job_id}] Fruit drama pipeline hatası: {repr(e)}\n{tb}")
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = repr(e)
        job_store[job_id]["traceback"] = tb
