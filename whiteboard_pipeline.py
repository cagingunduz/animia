"""
Whiteboard Animation pipeline.

Flow: prompt -> Claude writes a whiteboard explainer script -> per scene: a clean
black line-art drawing on white (Grok) is "drawn" with a left-to-right reveal
(ffmpeg xfade, no hand), narration (ElevenLabs) merged in + optional word-level
captions -> concat into one explainer video.
"""

import os
import json
import uuid
import tempfile
import traceback
import subprocess

import anthropic

from jobs import job_store
from image_gen import generate_whiteboard_image
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

# Whiteboard explainers use fewer, longer scenes than the animated mode.
WHITEBOARD_SCENE_MAP = {1: 5, 2: 9, 3: 13, 5: 20, 10: 38}


def whiteboard_scene_count(duration_minutes: int) -> int:
    closest = min(WHITEBOARD_SCENE_MAP.keys(), key=lambda x: abs(x - duration_minutes))
    return WHITEBOARD_SCENE_MAP[closest]


def _dims(aspect_ratio: str, resolution: str) -> tuple:
    tall = resolution in ("1080p", "2k")
    if aspect_ratio == "9:16":
        return (1080, 1920) if tall else (720, 1280)
    if aspect_ratio == "1:1":
        return (1080, 1080) if tall else (720, 720)
    return (1920, 1080) if tall else (1280, 720)  # 16:9 default


def _whiteboard_draw(image_path: str, out_path: str, total_dur: float,
                     aspect_ratio: str, resolution: str) -> bool:
    """Real whiteboard 'being drawn' effect (no hand): trace the line-art contours
    and progressively reveal the ink ALONG the strokes, so lines appear following
    their own shape (not a slide/wipe). Then hold the finished drawing."""
    import math
    import numpy as np
    import cv2

    w, h = _dims(aspect_ratio, resolution)
    fps = 30
    total = max(3.0, float(total_dur))
    draw = max(2.0, total - 0.8)

    src = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if src is None:
        return False
    # Fit the drawing onto a white w×h canvas
    ih, iw = src.shape[:2]
    scale = min(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    interp = cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA  # sharper upscaling
    resized = cv2.resize(src, (nw, nh), interpolation=interp)
    canvas_img = np.full((h, w, 3), 255, np.uint8)
    ox, oy = (w - nw) // 2, (h - nh) // 2
    canvas_img[oy:oy + nh, ox:ox + nw] = resized

    gray = cv2.cvtColor(canvas_img, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)  # ink = white(255)
    # SIMPLE keeps only corner points (bounded memory); we draw line segments between them.
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    # Natural drawing order: roughly top→bottom, then left→right by contour position
    band = max(20, h // 20)
    contours = sorted(contours, key=lambda c: (cv2.boundingRect(c)[1] // band, cv2.boundingRect(c)[0]))
    segs = []  # (x1,y1,x2,y2) stroke segments in draw order
    for c in contours:
        p = c[:, 0, :]
        for k in range(len(p) - 1):
            segs.append((int(p[k][0]), int(p[k][1]), int(p[k + 1][0]), int(p[k + 1][1])))
        if len(p) > 2:
            segs.append((int(p[-1][0]), int(p[-1][1]), int(p[0][0]), int(p[0][1])))
    MAX_SEG = 120000  # cap for memory/time safety on busy images
    if len(segs) > MAX_SEG:
        segs = segs[:: math.ceil(len(segs) / MAX_SEG)]
    n = len(segs)

    draw_frames = max(1, int(draw * fps))
    hold_frames = max(1, int((total - draw) * fps))
    brush = max(2, int(round(h / 220)))

    # Stream raw frames straight to ffmpeg (no lossy MJPG step) → crisp libx264.
    proc = subprocess.Popen(
        [
            "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", out_path,
        ],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    def emit(fr) -> bool:
        try:
            proc.stdin.write(fr.tobytes())
            return True
        except (BrokenPipeError, ValueError):
            return False

    if n == 0:
        for _ in range(draw_frames + hold_frames):
            if not emit(canvas_img):
                break
    else:
        frame = np.full((h, w, 3), 255, np.uint8)  # persistent, drawn incrementally
        per = max(1, math.ceil(n / draw_frames))
        idx = 0
        for _f in range(draw_frames):
            target = min(n, idx + per)
            if target > idx:
                newmask = np.zeros((h, w), np.uint8)
                for j in range(idx, target):
                    x1, y1, x2, y2 = segs[j]
                    cv2.line(newmask, (x1, y1), (x2, y2), 255, brush, lineType=cv2.LINE_AA)
                m = newmask > 0
                frame[m] = canvas_img[m]
                idx = target
            if not emit(frame):
                break
        for _ in range(hold_frames):  # hold the complete drawing
            if not emit(canvas_img):
                break

    try:
        proc.stdin.close()
    except (BrokenPipeError, ValueError):
        pass
    proc.wait()
    if proc.returncode != 0:
        print(f"[WARN] whiteboard draw encode rc={proc.returncode}")
    return proc.returncode == 0


async def generate_whiteboard_script(title: str, duration_minutes: int,
                                     scene_count: int | None = None) -> list:
    """Claude writes a whiteboard explainer: each scene is one clear thing to draw
    plus the narration that explains it."""
    if scene_count is None:
        scene_count = whiteboard_scene_count(duration_minutes)

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": f"""You are a whiteboard explainer-video director. Write a clear, engaging
whiteboard animation script.

TOPIC: {title}
TOTAL SCENES: {scene_count} (each is one drawing + one narration beat, ~10-12s)

For each scene produce:
- "title": short scene title
- "visual_concept": ONE simple thing to draw as a black-ink line doodle on a white
  board (10-20 words). A single clear object / icon / simple diagram / metaphor that
  illustrates this beat. Simple silhouettes draw well; avoid busy scenes, photos,
  text labels, or fine detail.
- "narrator_text": the spoken explanation for this beat (1-2 sentences, <= 28 words).
  Clear, friendly, informative — like a teacher explaining. Builds on the previous beat.
- "tone": one of "calm", "informative", "exciting", "emotional", "closing".

RULES
- Logical flow: hook -> explanation -> build-up -> takeaway. The FINAL scene is the
  CLOSING (a clear takeaway / call to action), tone "closing".
- Each visual_concept is a DISTINCT, simple drawable doodle.
- Keep it concrete and visual — prefer icons/metaphors over abstract words.

Respond with a valid JSON array ONLY, no other text:
[{{"scene_number":1,"title":"...","visual_concept":"...","narrator_text":"...","tone":"..."}}]"""
        }]
    )
    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


async def generate_single_whiteboard_scene(
    scene: dict,
    aspect_ratio: str,
    resolution: str,
    narrator_voice_id: str,
    include_narrator: bool,
    include_subtitles: bool,
    narrator_speed: float = 1.0,
) -> dict:
    tmp = tempfile.mkdtemp()
    run_id = uuid.uuid4().hex[:8]
    concept = scene.get("visual_concept", "") or scene.get("title", "")
    narrator_text = scene.get("narrator_text", "")
    tone = scene.get("tone", "informative")

    # 1) Line-art drawing on white
    img_url = await generate_whiteboard_image(concept, aspect_ratio)
    img_bytes = await download_file(img_url)
    img_path = f"{tmp}/draw_{run_id}.jpg"
    with open(img_path, "wb") as f:
        f.write(img_bytes)

    # 2) Narration (optional) — drives the clip length
    _valid_voice = narrator_voice_id and str(narrator_voice_id).strip().lower() != "none"
    do_narrator = include_narrator and narrator_text and _valid_voice
    audio_bytes = None
    audio_path = None
    clip_dur = 6.0
    if do_narrator:
        try:
            from animated_story_pipeline import _speed_audio
            audio_bytes = await generate_speech(narrator_text, narrator_voice_id, tone=tone)
            audio_bytes = _speed_audio(audio_bytes, narrator_speed, tmp, run_id)
            audio_dur = get_audio_duration(audio_bytes)
            clip_dur = max(4.0, audio_dur + 0.6)
            audio_path = f"{tmp}/audio_{run_id}.mp3"
            with open(audio_path, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            print(f"[WARN] whiteboard narration failed: {repr(e)}")
            audio_bytes = None

    # 3) Whiteboard "being drawn" animation
    reveal_path = f"{tmp}/reveal_{run_id}.mp4"
    if not _whiteboard_draw(img_path, reveal_path, clip_dur, aspect_ratio, resolution):
        raise RuntimeError("Whiteboard draw render failed")
    final_path = reveal_path

    # 4) Merge narration (xfade output is silent already)
    if audio_bytes and audio_path:
        merged = f"{tmp}/merged_{run_id}.mp4"
        if merge_video_audio(reveal_path, audio_path, merged):
            final_path = merged

    # 5) Captions
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
            print(f"[WARN] whiteboard captions failed: {repr(e)}")

    # 6) Upload
    with open(final_path, "rb") as f:
        out_url = upload_bytes_to_r2(f.read(), "whiteboard-scenes", "mp4", "video/mp4")
    return {"image_url": img_url, "video_url": out_url}


async def run_whiteboard_pipeline(job_id: str, payload: dict):
    try:
        title = payload["title"]
        duration_minutes = payload.get("duration_minutes", 1)
        aspect_ratio = payload.get("aspect_ratio", "16:9")
        resolution = payload.get("resolution", "1080p")
        scene_count = payload.get("scene_count")
        narrator_voice_id = payload.get("narrator_voice_id")
        narrator_speed = payload.get("narrator_speed", 1.0) or 1.0
        include_narrator = bool(payload.get("include_narrator", False))
        include_subtitles = bool(payload.get("include_subtitles", False))

        # 1) Script
        log(job_id, 1, 1, "Senaryo yazılıyor...")
        scenes = await generate_whiteboard_script(title, duration_minutes, scene_count)

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
            log(job_id, idx, total_steps, f"Sahne {idx}/{total}: çizim + animasyon...")
            res = await generate_single_whiteboard_scene(
                scene=scene,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                narrator_voice_id=narrator_voice_id,
                include_narrator=include_narrator,
                include_subtitles=include_subtitles,
                narrator_speed=narrator_speed,
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
                final_url = upload_bytes_to_r2(f.read(), "whiteboard-final", "mp4", "video/mp4")

        job_store[job_id]["status"] = "completed"
        job_store[job_id]["message"] = "Tamamlandı!"
        job_store[job_id]["final_video_url"] = final_url

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{job_id}] Whiteboard pipeline hatası: {repr(e)}\n{tb}")
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = repr(e)
        job_store[job_id]["traceback"] = tb
