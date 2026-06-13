import traceback
import asyncio
import uuid
import httpx
import boto3
from botocore.config import Config
from jobs import job_store
from prompt_generator import generate_2d_animation_plan, generate_scene_prompts
from image_gen import generate_character_image, generate_scene_image
from video_gen import animate_scene, calculate_duration
from tts import generate_speech, get_audio_duration
from lipsync import apply_lipsync
from concat import concat_clips
from storage import upload_final_video

R2_ACCOUNT_ID = __import__('os').environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY = __import__('os').environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = __import__('os').environ.get("R2_SECRET_KEY")
R2_BUCKET = __import__('os').environ.get("R2_BUCKET", "animai-videos")
R2_PUBLIC_BASE = "https://assets.animave.com"


def log(job_id: str, step: int, total: int, message: str, status: str = "processing"):
    job_store[job_id]["status"] = status
    job_store[job_id]["step"] = step
    job_store[job_id]["total_steps"] = total
    job_store[job_id]["message"] = message
    print(f"[{job_id}] Step {step}/{total}: {message}")


def set_scene_status(job_id: str, scene_index: int, status: str, video_url: str = None, character_urls: dict = None):
    scenes = job_store[job_id]["scenes"]
    for s in scenes:
        if s["scene_index"] == scene_index:
            s["status"] = status
            if video_url:
                s["video_url"] = video_url
            if character_urls:
                s["character_urls"] = character_urls
            break


def update_scene_metadata(job_id: str, scene_index: int, **fields):
    scenes = job_store[job_id]["scenes"]
    for s in scenes:
        if s["scene_index"] == scene_index:
            s.update(fields)
            break


def _planned_scene_to_pipeline_scene(scene: dict, character_defs: dict, aspect_ratio: str, scene_duration: int) -> dict:
    valid_ids = set(character_defs.keys())
    scene_char_ids = [cid for cid in (scene.get("characters") or []) if cid in valid_ids] or list(valid_ids)
    dialogue_by_id = {
        item.get("speaker_id"): item.get("line")
        for item in (scene.get("dialogue") or [])
        if item.get("speaker_id") in valid_ids and item.get("line")
    }
    scene_text = (
        f"Title: {scene.get('title') or 'Scene'}. "
        f"Location: {scene.get('location') or 'unspecified'}. "
        f"Action: {scene.get('action') or ''}. "
        f"Emotion: {scene.get('emotion') or ''}. "
        f"Image direction: {scene.get('image_direction') or ''}. "
        f"Video motion: {scene.get('video_motion') or ''}. "
        "Keep the same approved character identities and outfits. No on-screen text, captions, logos, watermark or subtitles."
    )
    return {
        "scene_text": scene_text,
        "aspect_ratio": aspect_ratio,
        "scene_duration": scene_duration,
        "characters": [
            {
                "character_id": cid,
                "role": "speaking" if dialogue_by_id.get(cid) else "silent",
                "dialogue": dialogue_by_id.get(cid),
                "voice_id": None,
                "framing": "full_body",
            }
            for cid in scene_char_ids
        ],
        "plan": scene,
    }


def upload_audio_bytes_to_r2(audio_bytes: bytes) -> str:
    """Upload audio to R2 and return public URL."""
    import os
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )
    key = f"audio/{uuid.uuid4()}.mp3"
    s3.put_object(Bucket=R2_BUCKET, Key=key, Body=audio_bytes, ContentType="audio/mpeg")
    return f"{R2_PUBLIC_BASE}/{key}"


async def merge_audio_video(video_url: str, audio_bytes: bytes) -> str:
    """Merge audio onto video using FFmpeg without lipsync."""
    import subprocess, os, tempfile
    tmp = tempfile.mkdtemp()
    run_id = uuid.uuid4().hex[:8]

    # Download video
    video_path = f"{tmp}/video_{run_id}.mp4"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(video_url)
        resp.raise_for_status()
        with open(video_path, "wb") as f:
            f.write(resp.content)

    # Write audio
    audio_path = f"{tmp}/audio_{run_id}.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    # Merge with FFmpeg
    output_path = f"{tmp}/merged_{run_id}.mp4"
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")

    # Upload merged video to R2
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )
    key = f"scenes/{uuid.uuid4()}.mp4"
    with open(output_path, "rb") as f:
        s3.put_object(Bucket=R2_BUCKET, Key=key, Body=f, ContentType="video/mp4")

    # Cleanup
    for p in [video_path, audio_path, output_path]:
        try: os.remove(p)
        except: pass

    return f"{R2_PUBLIC_BASE}/{key}"


async def process_scene(job_id: str, scene_data: dict, character_defs: dict, scene_index: int, step_offset: int, total_steps: int, resolution: str = "720p", lipsync_enabled: bool = False) -> str:
    scene_text = scene_data["scene_text"]
    aspect_ratio = scene_data.get("aspect_ratio", "16:9")
    pre_action = scene_data.get("pre_dialogue_action")
    scene_dur = scene_data.get("scene_duration")  # 4/6/8s from the 2D setup (Veo clamps)
    scene_chars = scene_data["characters"]
    speaking_chars = [c for c in scene_chars if c["role"] == "speaking"]
    step = step_offset

    # Build character list for prompt generator
    chars_for_prompt = []
    for sc in scene_chars:
        cid = sc["character_id"]
        cdef = character_defs.get(cid, {})
        chars_for_prompt.append({
            "id": cid,
            "description": cdef.get("description", ""),
            "style": cdef.get("style", "western_cartoon"),
            "role": sc["role"],
            "framing": sc.get("framing", "full_body")
        })

    # Generate prompts
    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: Promptlar olusturuluyor...")
    prompts = await generate_scene_prompts(
        scene_text=scene_text,
        characters=chars_for_prompt,
        aspect_ratio=aspect_ratio,
        pre_dialogue_action=pre_action,
        blur_faces=scene_data.get("blur_faces", False)
    )
    movement_duration = prompts["movement_duration"]

    # Generate scene image
    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: Sahne gorseli uretiliyor...")
    char_urls_ordered = [character_defs[sc["character_id"]]["char_url"] for sc in scene_chars if sc["character_id"] in character_defs]
    scene_image_url = await generate_scene_image(
        scene_prompt=prompts["scene_prompt"],
        character_urls=char_urls_ordered,
        aspect_ratio=aspect_ratio
    )

    update_scene_metadata(
        job_id,
        scene_index,
        status="processing",
        image_url=scene_image_url,
        character_urls={cid: character_defs[cid]["char_url"] for cid in character_defs},
    )

    # No speaking characters: just animate
    if not speaking_chars:
        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Animasyon uretiliyor (sessiz sahne)...")
        video_url = await animate_scene(
            scene_image_url, scene_text,
            duration=scene_dur or max(3, movement_duration + 2),
            resolution=resolution,
            aspect_ratio=aspect_ratio
        )
        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Video yukleniyor...")
        final_url = await upload_final_video(video_url)
        set_scene_status(job_id, scene_index, "completed", video_url=final_url)
        return final_url

    # Speaking characters → Veo 3.1 voices the dialogue natively (no separate TTS/merge).
    # We feed the dialogue into the prompt and let Veo generate the audio with the video.
    dialogue_text = " ".join(
        f'A character says: "{sc["dialogue"]}"'
        for sc in speaking_chars if sc.get("dialogue")
    )
    words = sum(len((sc.get("dialogue") or "").split()) for sc in speaking_chars)
    spoken_secs = max(2.0, words / 2.3)  # ~2.3 words/sec
    duration = scene_dur or calculate_duration(movement_duration, spoken_secs)

    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: Animasyon + ses (Veo) uretiliyor ({duration}sn)...")
    video_url = await animate_scene(
        scene_image_url,
        f"{scene_text}. {dialogue_text}".strip(),
        duration=duration,
        resolution=resolution,
        speaking_duration=spoken_secs,  # drives the "speaking" prompt for lip movement
        aspect_ratio=aspect_ratio,
    )

    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: Video yukleniyor...")
    final_url = await upload_final_video(video_url)
    set_scene_status(job_id, scene_index, "completed", video_url=final_url)
    return final_url


async def run_pipeline(job_id: str, payload: dict):
    try:
        characters_list = payload["characters"]
        scenes_list = payload["scenes"]
        resolution = payload.get("resolution", "720p")
        lipsync_enabled = payload.get("lipsync", False)

        character_defs = {c["id"]: c for c in characters_list}
        auto_plan = bool(payload.get("auto_plan"))
        scene_count = max(1, min(8, int(payload.get("scene_count") or len(scenes_list) or 1)))
        aspect_ratio = payload.get("aspect_ratio") or "16:9"
        scene_duration = 8 if resolution == "1080p" else int(payload.get("scene_duration") or 8)
        scene_duration = scene_duration if scene_duration in (4, 6, 8) else 8

        n_chars = len(characters_list)
        n_scenes = scene_count if auto_plan else len(scenes_list)
        total_steps = n_chars + (1 if auto_plan else 0) + (n_scenes * 4) + (1 if n_scenes > 1 else 0)

        job_store[job_id]["total_steps"] = total_steps
        step = 0

        # Generate all character images first
        for char in characters_list:
            cid = char["id"]
            existing_url = char.get("char_url") or char.get("image_url")
            if existing_url:
                step += 1
                log(job_id, step, total_steps, f"Karakter referansi hazirlaniyor: {cid}...")
                char_url = existing_url
            else:
                step += 1
                log(job_id, step, total_steps, f"Karakter gorseli uretiliyor: {cid}...")
                char_prompt = f"{char['description']}, full body, clean white background, high quality digital illustration"
                char_url = await generate_character_image(
                    character_prompt=char_prompt,
                    photo_url=char.get("photo_url")
                )
            character_defs[cid]["char_url"] = char_url

        if auto_plan:
            step += 1
            log(job_id, step, total_steps, "Mave sahneleri planliyor...")
            plan = await generate_2d_animation_plan(
                project_prompt=payload.get("project_prompt") or "",
                user_direction=payload.get("user_direction") or "",
                characters=characters_list,
                scene_count=scene_count,
                aspect_ratio=aspect_ratio,
                style=payload.get("style") or characters_list[0].get("style", "anime"),
                scene_duration=scene_duration,
            )
            planned_scenes = plan.get("scenes", [])[:scene_count]
            if not planned_scenes:
                raise RuntimeError("2D scene planner did not return scenes")
            scenes_list = [
                _planned_scene_to_pipeline_scene(scene, character_defs, aspect_ratio, scene_duration)
                for scene in planned_scenes
            ]
            job_store[job_id]["scenes"] = [
                {
                    "scene_index": i + 1,
                    "status": "queued",
                    "title": scene.get("title") or f"Scene {i + 1}",
                    "emotion": scene.get("emotion"),
                    "dialogue": [
                        {"speaker": item.get("speaker_id"), "line": item.get("line")}
                        for item in (scene.get("dialogue") or [])
                    ],
                    "duration_seconds": scene_duration,
                    "video_url": None,
                    "image_url": None,
                    "character_urls": {},
                }
                for i, scene in enumerate(planned_scenes)
            ]
            job_store[job_id]["plan"] = plan

        # Process each scene
        scene_video_urls = []
        for i, scene in enumerate(scenes_list):
            scene_index = i + 1
            set_scene_status(job_id, scene_index, "processing")

            scene_url = await process_scene(
                job_id=job_id,
                scene_data=scene,
                character_defs=character_defs,
                scene_index=scene_index,
                step_offset=step,
                total_steps=total_steps,
                resolution=resolution,
                lipsync_enabled=lipsync_enabled
            )
            scene_video_urls.append(scene_url)
            step = job_store[job_id]["step"]

        # Merge all scenes
        if len(scene_video_urls) == 1:
            final_url = scene_video_urls[0]
        else:
            step += 1
            log(job_id, step, total_steps, "Tum sahneler birlestiriliyor...")
            final_url = await concat_clips(scene_video_urls, output_folder="final")

        job_store[job_id]["status"] = "completed"
        job_store[job_id]["message"] = "Tamamlandi!"
        job_store[job_id]["final_video_url"] = final_url
        print(f"[{job_id}] Pipeline tamamlandi: {final_url}")

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{job_id}] Pipeline hatasi: {repr(e)}\n{tb}")
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = repr(e)
        job_store[job_id]["traceback"] = tb
