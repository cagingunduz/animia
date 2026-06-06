"""
Animated Storytelling pipeline.

Flow: character(s) created up front  ->  Claude writes a character-driven
cartoon script  ->  per scene: character-consistent image (Gemini) animated by
LTX-2.3 (RunPod, audio included)  ->  concat into one video.

No narrator / captions / Ken Burns in v1 — LTX supplies the audio.
"""

import os
import json
import uuid
import tempfile
import traceback

import anthropic

from jobs import job_store
from image_gen import generate_scene_image
from runpod_client import animate_scene_runpod
from prompt_generator import get_style_prompt, get_scene_count
from storybook_pipeline import (
    concat_video_files,
    download_file,
    upload_bytes_to_r2,
    log,
    set_scene_status,
)


async def generate_animated_story_script(
    title: str,
    theme: str,
    style: str,
    characters: list,
    duration_minutes: int,
    scene_count: int | None = None,
) -> list:
    """Claude writes a cartoon, character-driven script. Each scene reuses the
    given characters and carries an explicit `motion` hint for the animation."""
    if scene_count is None:
        scene_count = get_scene_count(duration_minutes)
    style_prompt = get_style_prompt(style)
    char_lines = "\n".join(f"- {c.get('id', 'char')}: {c.get('description', '')}" for c in characters)

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": f"""You are a master animated-story director. Write a short animated story.

STORY
- Title/topic: {title}
- Theme/genre: {theme}
- Visual style: {style_prompt}
- Total scenes: {scene_count} (each becomes ~5 seconds of animation)

CHARACTERS — reuse these EXACT characters across every scene, keep them visually identical:
{char_lines}

For each of the {scene_count} scenes produce:
- "title": short scene title
- "scene_description": a detailed image-generation prompt (50-80 words). Place the
  character(s) in a clear environment doing a specific action that advances the story.
  Describe location, lighting, composition and the character's pose/expression. Apply
  the {style} cartoon style. No photorealism, no text/watermarks.
- "motion": one short sentence describing the MOVEMENT for the animation
  (e.g. "the detective slowly turns his head as rain falls and the camera pushes in").

RULES
- Keep the characters consistent (same appearance, outfit, colors) in every scene.
- Every scene visually distinct (different location / angle / action).
- Clear narrative arc: hook -> development -> climax -> resolution.
- Do NOT give characters small handheld props (magnifying glass, phone, papers,
  tiny tools) — they animate badly and duplicate. Favor full-body poses,
  expressions, hand gestures, walking/turning, and rich environments.

Respond with a valid JSON array ONLY, no other text:
[{{"scene_number":1,"title":"...","scene_description":"...","motion":"..."}}]"""
        }]
    )

    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


async def run_animated_story_pipeline(job_id: str, payload: dict):
    try:
        characters = payload["characters"]              # [{id, description, char_url, style}]
        title = payload["title"]
        theme = payload.get("theme", "")
        style = payload.get("style", "western_cartoon")
        duration_minutes = payload.get("duration_minutes", 1)
        aspect_ratio = payload.get("aspect_ratio", "16:9")
        resolution = payload.get("resolution", "1080p")
        scene_count = payload.get("scene_count")        # optional override (cheap testing)

        char_urls = [c["char_url"] for c in characters if c.get("char_url")]
        style_prompt = get_style_prompt(style)

        # 1) Script
        log(job_id, 1, 1, "Senaryo yazılıyor...")
        scenes = await generate_animated_story_script(
            title, theme, style, characters, duration_minutes, scene_count
        )

        total = len(scenes)
        total_steps = total + 1
        job_store[job_id]["total_steps"] = total_steps
        job_store[job_id]["scenes"] = [
            {"scene_index": i + 1, "status": "queued", "video_url": None, "image_url": None}
            for i in range(total)
        ]

        # 2) Per scene: character-consistent image -> LTX animation
        clip_urls = []
        for i, scene in enumerate(scenes):
            idx = i + 1
            set_scene_status(job_id, idx, "processing")
            log(job_id, idx, total_steps, f"Sahne {idx}/{total}: görsel + animasyon...")

            desc = scene.get("scene_description", "")
            motion = scene.get("motion", "")

            scene_prompt = f"{desc}. Style: {style_prompt}. High detail, clean composition, sharp focus."
            img_url = await generate_scene_image(scene_prompt, char_urls, aspect_ratio)

            ltx_desc = f"{motion}. {desc}" if motion else desc
            clip_url = await animate_scene_runpod(
                scene_image_url=img_url,
                scene_description=ltx_desc,
                duration=4,                 # tighter window = snappier motion
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                audio=False,                # v1: no LTX scene audio (narrator added later)
            )

            for s in job_store[job_id]["scenes"]:
                if s["scene_index"] == idx:
                    s["image_url"] = img_url
                    break
            set_scene_status(job_id, idx, "completed", video_url=clip_url)
            clip_urls.append(clip_url)

        # 3) Concat
        if len(clip_urls) == 1:
            final_url = clip_urls[0]
        else:
            log(job_id, total_steps, total_steps, "Sahneler birleştiriliyor...")
            tmp = tempfile.mkdtemp()
            run_id = uuid.uuid4().hex[:8]
            paths = []
            for j, url in enumerate(clip_urls):
                data = await download_file(url)
                p = f"{tmp}/clip_{j}_{run_id}.mp4"
                with open(p, "wb") as f:
                    f.write(data)
                paths.append(p)
            final_path = f"{tmp}/final_{run_id}.mp4"
            if not concat_video_files(paths, final_path):
                raise RuntimeError("Final concat failed")
            with open(final_path, "rb") as f:
                final_data = f.read()
            final_url = upload_bytes_to_r2(final_data, "animated-story-final", "mp4", "video/mp4")
            for p in paths + [final_path]:
                try:
                    os.remove(p)
                except OSError:
                    pass

        job_store[job_id]["status"] = "completed"
        job_store[job_id]["message"] = "Tamamlandı!"
        job_store[job_id]["final_video_url"] = final_url

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{job_id}] Animated story pipeline hatası: {repr(e)}\n{tb}")
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = repr(e)
        job_store[job_id]["traceback"] = tb
