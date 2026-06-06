"""
Animated Storytelling pipeline.

Flow: character(s) created up front  ->  Claude writes a character-driven cartoon
script  ->  per scene: character-consistent image (Gemini) animated by LTX-2.3
(RunPod), optional narrator (TTS) merged in + optional word-level captions  ->
concat into one video.

Narrator/captions are toggleable (like the Storytelling section). When narrator
is off the clip is a snappy 4s silent animation; when on, the clip length tracks
the narration so audio and video stay in sync.
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
from tts import generate_speech, get_audio_duration, get_word_timestamps
from storybook_pipeline import (
    concat_video_files,
    download_file,
    upload_bytes_to_r2,
    merge_video_audio,
    build_ass,
    burn_ass_subtitles,
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
    given characters and carries a `motion` hint plus a short `narrator_text`."""
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
- Total scenes: {scene_count} (each becomes ~4-5 seconds of animation)

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
- "narrator_text": one SHORT narration line, MAX 14 words (~4 seconds spoken).
  Punchy, present tense, advances the story. This is the voice-over for the scene.

RULES
- Keep the characters consistent (same appearance, outfit, colors) in every scene.
- Every scene visually distinct (different location / angle / action).
- Clear narrative arc: hook -> development -> climax -> resolution.
- Do NOT give characters small handheld props (magnifying glass, phone, papers,
  tiny tools) — they animate badly and duplicate. Favor full-body poses,
  expressions, hand gestures, walking/turning, and rich environments.
- narrator_text MUST stay <= 14 words so it fits the short clip.

Respond with a valid JSON array ONLY, no other text:
[{{"scene_number":1,"title":"...","scene_description":"...","motion":"...","narrator_text":"..."}}]"""
        }]
    )

    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


async def generate_single_animated_scene(
    scene: dict,
    char_urls: list,
    style: str,
    aspect_ratio: str,
    resolution: str,
    narrator_voice_id: str,
    include_narrator: bool,
    include_subtitles: bool,
) -> dict:
    """One scene: character-consistent image -> LTX animation -> (narrator + captions)."""
    tmp = tempfile.mkdtemp()
    run_id = uuid.uuid4().hex[:8]
    style_prompt = get_style_prompt(style)
    desc = scene.get("scene_description", "")
    motion = scene.get("motion", "")
    narrator_text = scene.get("narrator_text", "")

    # 1) Scene image (character-consistent)
    scene_prompt = f"{desc}. Style: {style_prompt}. High detail, clean composition, sharp focus."
    img_url = await generate_scene_image(scene_prompt, char_urls, aspect_ratio)

    # 2) Narrator TTS (optional) — drives the clip length so A/V stay in sync
    _valid_voice = narrator_voice_id and str(narrator_voice_id).strip().lower() != "none"
    do_narrator = include_narrator and narrator_text and _valid_voice
    audio_bytes = None
    audio_path = None
    clip_duration = 4
    if do_narrator:
        try:
            audio_bytes = await generate_speech(narrator_text, narrator_voice_id)
            audio_dur = get_audio_duration(audio_bytes)
            clip_duration = max(4, min(8, int(round(audio_dur)) + 1))  # keep video >= narration
            audio_path = f"{tmp}/audio_{run_id}.mp3"
            with open(audio_path, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            print(f"[WARN] narrator TTS failed: {repr(e)}")
            audio_bytes = None

    # 3) LTX animation (silent — narrator is the audio)
    ltx_desc = f"{motion}. {desc}" if motion else desc
    clip_url = await animate_scene_runpod(
        scene_image_url=img_url,
        scene_description=ltx_desc,
        duration=clip_duration,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        audio=False,
    )
    clip_bytes = await download_file(clip_url)
    video_path = f"{tmp}/video_{run_id}.mp4"
    with open(video_path, "wb") as f:
        f.write(clip_bytes)
    final_path = video_path

    # 4) Merge narrator audio
    if audio_bytes and audio_path:
        merged = f"{tmp}/merged_{run_id}.mp4"
        if merge_video_audio(video_path, audio_path, merged):
            final_path = merged

    # 5) Captions (CapCut-style, word-level from Whisper)
    if include_subtitles and audio_bytes:
        try:
            word_ts = await get_word_timestamps(audio_bytes)
            if word_ts:
                ass = build_ass(word_ts, aspect_ratio=aspect_ratio)
                ass_path = f"{tmp}/subs_{run_id}.ass"
                with open(ass_path, "w", encoding="utf-8") as f:
                    f.write(ass)
                subbed = f"{tmp}/subbed_{run_id}.mp4"
                if burn_ass_subtitles(final_path, ass_path, subbed):
                    final_path = subbed
        except Exception as e:
            print(f"[WARN] captions failed: {repr(e)}")

    # 6) Upload
    with open(final_path, "rb") as f:
        out_url = upload_bytes_to_r2(f.read(), "animated-story-scenes", "mp4", "video/mp4")
    for p in {video_path, final_path}:
        try:
            os.remove(p)
        except OSError:
            pass

    return {"image_url": img_url, "video_url": out_url}


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
        narrator_voice_id = payload.get("narrator_voice_id")
        include_narrator = bool(payload.get("include_narrator", False))
        include_subtitles = bool(payload.get("include_subtitles", False))

        char_urls = [c["char_url"] for c in characters if c.get("char_url")]

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

        # 2) Per scene
        clip_urls = []
        for i, scene in enumerate(scenes):
            idx = i + 1
            set_scene_status(job_id, idx, "processing")
            log(job_id, idx, total_steps, f"Sahne {idx}/{total}: görsel + animasyon...")

            res = await generate_single_animated_scene(
                scene=scene,
                char_urls=char_urls,
                style=style,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                narrator_voice_id=narrator_voice_id,
                include_narrator=include_narrator,
                include_subtitles=include_subtitles,
            )

            for s in job_store[job_id]["scenes"]:
                if s["scene_index"] == idx:
                    s["image_url"] = res["image_url"]
                    break
            set_scene_status(job_id, idx, "completed", video_url=res["video_url"])
            clip_urls.append(res["video_url"])

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
