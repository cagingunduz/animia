import traceback
from jobs import job_store
from prompt_generator import generate_scene_prompts
from image_gen import generate_character_image, generate_scene_image
from video_gen import animate_scene, calculate_duration
from tts import generate_speech, get_audio_duration
from lipsync import apply_lipsync
from concat import concat_clips
from storage import upload_final_video


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


async def process_scene(job_id: str, scene_data: dict, character_defs: dict, scene_index: int, step_offset: int, total_steps: int) -> str:
    """
    Process a single scene and return its final video URL.
    character_defs: {char_id: {description, style, photo_url, char_url}}
    """

    scene_text = scene_data["scene_text"]
    aspect_ratio = scene_data.get("aspect_ratio", "16:9")
    pre_action = scene_data.get("pre_dialogue_action")
    scene_chars = scene_data["characters"]

    speaking_chars = [c for c in scene_chars if c["role"] == "speaking"]
    silent_chars = [c for c in scene_chars if c["role"] == "silent"]

    step = step_offset

    # --- Build character list for prompt generator ---
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

    # --- Step: Generate prompts ---
    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: Promptlar olusturuluyor...")
    prompts = await generate_scene_prompts(
        scene_text=scene_text,
        characters=chars_for_prompt,
        aspect_ratio=aspect_ratio,
        pre_dialogue_action=pre_action
    )
    movement_duration = prompts["movement_duration"]

    # --- Step: Generate scene image ---
    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: Sahne gorseli uretiliyor...")
    char_urls_ordered = [character_defs[sc["character_id"]]["char_url"] for sc in scene_chars if sc["character_id"] in character_defs]
    scene_image_url = await generate_scene_image(
        scene_prompt=prompts["scene_prompt"],
        character_urls=char_urls_ordered,
        aspect_ratio=aspect_ratio
    )

    set_scene_status(job_id, scene_index, "processing", character_urls={
        cid: character_defs[cid]["char_url"] for cid in character_defs
    })

    # --- No speaking characters: just animate ---
    if not speaking_chars:
        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Animasyon uretiliyor (sessiz sahne)...")
        video_url = await animate_scene(scene_image_url, scene_text, duration=max(3, movement_duration + 2))
        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Video yukleniyor...")
        final_url = await upload_final_video(video_url)
        set_scene_status(job_id, scene_index, "completed", video_url=final_url)
        return final_url

    # --- One speaking character ---
    if len(speaking_chars) == 1:
        sc = speaking_chars[0]
        cid = sc["character_id"]

        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Ses uretiliyor ({cid})...")
        audio_bytes = await generate_speech(sc["dialogue"], sc["voice_id"])
        audio_duration = get_audio_duration(audio_bytes)

        duration = calculate_duration(movement_duration, audio_duration)

        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Animasyon uretiliyor ({duration}sn)...")
        silent_video_url = await animate_scene(scene_image_url, scene_text, duration=duration)

        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Lip sync uygulanıyor...")
        lipsynced_url = await apply_lipsync(silent_video_url, audio_bytes)

        step += 1
        log(job_id, step, total_steps, f"Sahne {scene_index}: Video yukleniyor...")
        final_url = await upload_final_video(lipsynced_url)
        set_scene_status(job_id, scene_index, "completed", video_url=final_url)
        return final_url

    # --- Two speaking characters ---
    sc1 = speaking_chars[0]
    sc2 = speaking_chars[1]

    # Character 1
    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: K1 ses uretiliyor...")
    audio1_bytes = await generate_speech(sc1["dialogue"], sc1["voice_id"])
    audio1_duration = get_audio_duration(audio1_bytes)
    duration1 = calculate_duration(movement_duration, audio1_duration)

    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: K1 animasyon uretiliyor ({duration1}sn)...")
    silent_video1 = await animate_scene(scene_image_url, scene_text, duration=duration1)

    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: K1 lip sync uygulanıyor...")
    clip1_url = await apply_lipsync(silent_video1, audio1_bytes)

    # Character 2
    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: K2 ses uretiliyor...")
    audio2_bytes = await generate_speech(sc2["dialogue"], sc2["voice_id"])
    audio2_duration = get_audio_duration(audio2_bytes)
    duration2 = calculate_duration(0, audio2_duration)  # No movement for K2 turn

    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: K2 animasyon uretiliyor ({duration2}sn)...")
    silent_video2 = await animate_scene(scene_image_url, scene_text, duration=duration2)

    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: K2 lip sync uygulanıyor...")
    clip2_url = await apply_lipsync(silent_video2, audio2_bytes)

    # Merge clips
    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}: Klipler birlestiriliyor (FFmpeg)...")
    merged_url = await concat_clips([clip1_url, clip2_url], output_folder="scenes")

    set_scene_status(job_id, scene_index, "completed", video_url=merged_url)
    return merged_url


async def run_pipeline(job_id: str, payload: dict):
    try:
        characters_list = payload["characters"]
        scenes_list = payload["scenes"]

        # Build character def map
        character_defs = {c["id"]: c for c in characters_list}

        # Calculate total steps (rough estimate)
        # Per scene: 1 prompt + 1 scene_img + (1-3 audio + 1-3 video + 1-3 lipsync) + 1 upload
        # Global: 1 char img per unique char + 1 final concat if multi-scene
        n_chars = len(characters_list)
        n_scenes = len(scenes_list)
        total_steps = n_chars + (n_scenes * 7) + (1 if n_scenes > 1 else 0)

        job_store[job_id]["total_steps"] = total_steps
        step = 0

        # --- Generate all character images first ---
        for char in characters_list:
            cid = char["id"]
            step += 1
            log(job_id, step, total_steps, f"Karakter gorseli uretiliyor: {cid}...")

            char_prompt = f"{char['description']}, full body, clean white background, high quality digital illustration"
            char_url = await generate_character_image(
                character_prompt=char_prompt,
                photo_url=char.get("photo_url")
            )
            character_defs[cid]["char_url"] = char_url

        # --- Process each scene ---
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
                total_steps=total_steps
            )
            scene_video_urls.append(scene_url)
            step = job_store[job_id]["step"]

        # --- Merge all scenes if multiple ---
        if len(scene_video_urls) == 1:
            final_url = scene_video_urls[0]
        else:
            step += 1
            log(job_id, step, total_steps, "Tum sahneler birlestiriliyor (FFmpeg)...")
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
