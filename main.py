import os
import uuid
import asyncio
import tempfile
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Literal

from jobs import job_store
from pipeline import run_pipeline
from tts import get_voices, generate_speech
from lipsync import upload_audio_to_r2
from image_gen import generate_character_image, generate_scene_image
from prompt_generator import get_style_prompt, generate_scene_prompts, generate_story_script
from storybook_pipeline import run_storybook_pipeline, generate_single_scene, download_file, concat_video_files, upload_bytes_to_r2
from animated_story_pipeline import run_animated_story_pipeline

app = FastAPI(title="Animave API v3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
 

class CharacterDef(BaseModel):
    id: str
    description: str
    style: Optional[str] = "western_cartoon"
    photo_url: Optional[str] = None


class SceneCharacter(BaseModel):
    character_id: str
    role: str = "silent"
    dialogue: Optional[str] = None
    voice_id: Optional[str] = None
    framing: Optional[str] = "full_body"


class Scene(BaseModel):
    scene_text: str
    characters: List[SceneCharacter]
    aspect_ratio: Optional[str] = "16:9"
    pre_dialogue_action: Optional[str] = None


class GenerateRequest(BaseModel):
    characters: List[CharacterDef]
    scenes: List[Scene]
    resolution: Optional[Literal["480p", "720p", "1080p"]] = "720p"
    lipsync: Optional[bool] = False


class TTSTestRequest(BaseModel):
    text: str
    voice_id: str


class GenerateCharacterRequest(BaseModel):
    description: str
    style: Optional[str] = "western_cartoon"
    photo_url: Optional[str] = None


class GenerateSceneImageRequest(BaseModel):
    scene_text: str
    aspect_ratio: Optional[str] = "16:9"
    characters: List[dict]


class GenerateSceneVideoRequest(BaseModel):
    scene_image_url: str
    scene_text: str
    duration: Optional[int] = 5
    resolution: Optional[Literal["480p", "720p", "1080p"]] = "720p"
    characters: Optional[List[dict]] = []
    lipsync: Optional[bool] = False


class GenerateStoryRequest(BaseModel):
    title: str
    genre: str
    style: Optional[str] = "western_cartoon"
    theme: Optional[str] = "true_crime"
    duration_minutes: Optional[int] = 2
    narrator_voice_id: Optional[str] = None
    blur_faces: Optional[bool] = False


@app.get("/")
async def root():
    return {
        "status": "Animave API v3 online",
        "features": {
            "resolutions": ["480p", "720p", "1080p"],
            "lipsync": "optional premium feature",
            "max_characters_per_scene": 14,
            "max_speaking_per_scene": 2
        }
    }


@app.post("/generate-character")
async def generate_character(req: GenerateCharacterRequest):
    try:
        style_prompt = get_style_prompt(req.style or "western_cartoon")
        if req.photo_url:
            full_prompt = (
                f"Keep this exact character's appearance, outfit, colors, and art style. "
                f"Only make this specific change: {req.description}. "
                f"Full body, clean white background, {style_prompt}"
            )
        else:
            full_prompt = (
                f"{req.description}, full body, clean white background, "
                f"{style_prompt}, high quality digital illustration"
            )
        char_url = await generate_character_image(
            character_prompt=full_prompt,
            photo_url=req.photo_url
        )
        return {
            "success": True,
            "character_image_url": char_url,
            "character_id": f"char-{uuid.uuid4().hex[:8]}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


@app.post("/generate-scene-image")
async def generate_scene_image_endpoint(req: GenerateSceneImageRequest):
    try:
        chars_for_prompt = [
            {
                "id": c.get("id"),
                "description": c.get("description", ""),
                "style": c.get("style", "western_cartoon"),
                "role": c.get("role", "silent"),
                "framing": c.get("framing", "full_body")
            }
            for c in req.characters
        ]

        prompts = await generate_scene_prompts(
            scene_text=req.scene_text,
            characters=chars_for_prompt,
            aspect_ratio=req.aspect_ratio or "16:9",
            blur_faces=req.blur_faces or False
        )

        char_urls = [c.get("char_url") for c in req.characters if c.get("char_url")]

        scene_image_url = await generate_scene_image(
            scene_prompt=prompts["scene_prompt"],
            character_urls=char_urls,
            aspect_ratio=req.aspect_ratio or "16:9"
        )

        return {
            "success": True,
            "scene_image_url": scene_image_url,
            "scene_prompt": prompts["scene_prompt"],
            "movement_duration": prompts.get("movement_duration", 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


@app.post("/generate-scene-video")
async def generate_scene_video_endpoint(req: GenerateSceneVideoRequest):
    try:
        from video_gen import animate_scene
        from tts import generate_speech, get_audio_duration
        from pipeline import merge_audio_video
        from storage import upload_final_video

        speaking_chars = [c for c in (req.characters or []) if c.get("role") == "speaking"]
        speaking_duration = None
        audio_bytes = None

        if speaking_chars:
            sc = speaking_chars[0]
            if sc.get("dialogue") and sc.get("voice_id"):
                audio_bytes = await generate_speech(sc["dialogue"], sc["voice_id"])
                audio_duration = get_audio_duration(audio_bytes)
                speaking_duration = audio_duration

        video_url = await animate_scene(
            scene_image_url=req.scene_image_url,
            scene_description=req.scene_text,
            duration=req.duration or 5,
            resolution=req.resolution or "720p",
            speaking_duration=speaking_duration
        )

        if audio_bytes:
            video_url = await merge_audio_video(video_url, audio_bytes)

        final_url = await upload_final_video(video_url)

        return {"success": True, "video_url": final_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


@app.post("/generate-story")
async def generate_story(req: GenerateStoryRequest):
    """Generate a full story script using Claude."""
    try:
        scenes = await generate_story_script(
            title=req.title,
            genre=req.genre,
            style=req.style or "western_cartoon",
            theme=req.theme or "true_crime",
            duration_minutes=req.duration_minutes or 2,
            narrator_voice_id=req.narrator_voice_id,
            blur_faces=req.blur_faces or False,
        )
        return {"success": True, "scenes": scenes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


@app.post("/generate")
async def generate(req: GenerateRequest):
    for i, scene in enumerate(req.scenes):
        speaking = [c for c in scene.characters if c.role == "speaking"]
        if len(speaking) > 2:
            raise HTTPException(
                status_code=400,
                detail=f"Scene {i+1}: max 2 speaking characters allowed, got {len(speaking)}"
            )

    job_id = str(uuid.uuid4())
    scenes_status = [
        {"scene_index": i + 1, "status": "queued", "video_url": None, "character_urls": {}}
        for i in range(len(req.scenes))
    ]

    job_store[job_id] = {
        "status": "queued",
        "step": 0,
        "total_steps": 0,
        "message": "Kuyrukta bekleniyor...",
        "scenes": scenes_status,
        "final_video_url": None,
        "error": None,
        "traceback": None,
        "resolution": req.resolution,
        "lipsync": req.lipsync
    }

    asyncio.create_task(run_pipeline(job_id, req.model_dump()))
    return {"job_id": job_id, "status": "queued"}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job bulunamadi")
    job = job_store[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "step": job["step"],
        "total_steps": job["total_steps"],
        "message": job["message"],
        "scenes": job.get("scenes", []),
        "final_video_url": job.get("final_video_url"),
        "resolution": job.get("resolution"),
        "lipsync": job.get("lipsync"),
        "error": job.get("error"),
        "traceback": job.get("traceback")
    }


@app.get("/voices")
async def voices():
    try:
        result = await get_voices()
        return {"voices": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


@app.post("/tts-test")
async def tts_test(req: TTSTestRequest):
    try:
        audio_bytes = await generate_speech(req.text, req.voice_id)
        audio_url = upload_audio_to_r2(audio_bytes)
        return {"audio_url": audio_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


class GenerateStorybookRequest(BaseModel):
    scenes: List[dict]
    narrator_voice_id: str
    aspect_ratio: Optional[str] = "9:16"
    scene_duration: Optional[int] = 8


class GenerateSingleSceneRequest(BaseModel):
    scene_description: str
    narrator_text: Optional[str] = ""
    narrator_voice_id: Optional[str] = None
    aspect_ratio: Optional[str] = "9:16"
    scene_duration: Optional[int] = 8
    ken_burns: Optional[bool] = True
    include_narrator: Optional[bool] = True
    include_subtitles: Optional[bool] = False


@app.post("/generate-storybook")
async def generate_storybook(req: GenerateStorybookRequest):
    job_id = str(uuid.uuid4())
    scenes_status = [
        {"scene_index": i + 1, "status": "queued", "video_url": None, "image_url": None}
        for i in range(len(req.scenes))
    ]
    job_store[job_id] = {
        "status": "queued", "step": 0, "total_steps": 0,
        "message": "Kuyrukta bekleniyor...", "scenes": scenes_status,
        "final_video_url": None, "error": None, "traceback": None,
        "aspect_ratio": req.aspect_ratio, "lipsync": False
    }
    asyncio.create_task(run_storybook_pipeline(job_id, req.model_dump()))
    return {"job_id": job_id, "status": "queued"}


# ─── Animated Storytelling: character-driven script → scene images → LTX ───
class GenerateAnimatedStoryRequest(BaseModel):
    title: str
    theme: Optional[str] = ""
    style: Optional[str] = "western_cartoon"
    duration_minutes: Optional[int] = 1
    aspect_ratio: Optional[str] = "16:9"
    resolution: Optional[Literal["480p", "720p", "1080p", "2k"]] = "1080p"
    characters: List[dict]              # [{id, description, char_url, style}]
    scene_count: Optional[int] = None   # override for cheap testing
    narrator_voice_id: Optional[str] = None
    narrator_speed: Optional[float] = 1.0   # 1.0 / 1.5 / 2.0 narration playback speed
    include_narrator: Optional[bool] = False
    include_subtitles: Optional[bool] = False


@app.post("/generate-animated-story")
async def generate_animated_story(req: GenerateAnimatedStoryRequest):
    job_id = str(uuid.uuid4())
    job_store[job_id] = {
        "status": "queued", "step": 0, "total_steps": 0,
        "message": "Kuyrukta bekleniyor...", "scenes": [],
        "final_video_url": None, "error": None, "traceback": None,
        "aspect_ratio": req.aspect_ratio,
    }
    asyncio.create_task(run_animated_story_pipeline(job_id, req.model_dump()))
    return {"job_id": job_id, "status": "queued"}


@app.post("/generate-single-scene")
async def generate_single_scene_endpoint(req: GenerateSingleSceneRequest):
    """
    Generate a single storybook scene: Grok image + Ken Burns/Static + Narrator.
    Used for auto-generating scene previews in the timeline editor.
    """
    try:
        result = await generate_single_scene(
            scene_description=req.scene_description,
            narrator_text=req.narrator_text,
            narrator_voice_id=req.narrator_voice_id,
            aspect_ratio=req.aspect_ratio or "9:16",
            scene_duration=req.scene_duration or 8,
            ken_burns=req.ken_burns if req.ken_burns is not None else True,
            include_narrator=req.include_narrator if req.include_narrator is not None else True,
            include_subtitles=req.include_subtitles if req.include_subtitles is not None else False,
        )
        return {"success": True, "image_url": result["image_url"], "video_url": result["video_url"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


class MergeVideosRequest(BaseModel):
    video_urls: List[str]

@app.post("/merge-videos")
async def merge_videos_endpoint(req: MergeVideosRequest):
    """Merge already-generated scene videos into a final video."""
    try:
        if not req.video_urls:
            raise HTTPException(status_code=400, detail="No video URLs provided")
        if len(req.video_urls) == 1:
            return {"success": True, "final_video_url": req.video_urls[0]}

        tmp = tempfile.mkdtemp()
        run_id = uuid.uuid4().hex[:8]
        local_paths = []

        for idx, url in enumerate(req.video_urls):
            video_bytes = await download_file(url)
            path = f"{tmp}/scene_{idx}_{run_id}.mp4"
            with open(path, "wb") as f:
                f.write(video_bytes)
            local_paths.append(path)

        final_path = f"{tmp}/final_{run_id}.mp4"
        if not concat_video_files(local_paths, final_path):
            raise RuntimeError("Merge failed")

        with open(final_path, "rb") as f:
            final_data = f.read()

        final_url = upload_bytes_to_r2(final_data, "storybook-final", "mp4", "video/mp4")

        for p in local_paths + [final_path]:
            try: os.remove(p)
            except: pass

        return {"success": True, "final_video_url": final_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


@app.get("/check-ffmpeg")
async def check_ffmpeg():
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    return {"available": result.returncode == 0, "version": result.stdout[:100]}

@app.get("/check-env")
async def check_env():
    keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "REPLICATE_API_TOKEN",
            "R2_ACCOUNT_ID", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_BUCKET"]
    return {k: bool(os.environ.get(k)) for k in keys}


@app.get("/download")
async def download(url: str, filename: str = "video.mp4"):
    """Stream a (public R2) video back with an attachment disposition so browsers
    download it. No size limit (unlike a Vercel proxy) and no CORS needed."""
    import httpx
    from fastapi.responses import StreamingResponse

    safe_name = "".join(c for c in filename if c.isalnum() or c in " ._-").strip() or "video.mp4"
    if not safe_name.lower().endswith(".mp4"):
        safe_name += ".mp4"

    async def stream():
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes(chunk_size=1 << 16):
                    yield chunk

    return StreamingResponse(
        stream(),
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@app.get("/recent-final-videos")
async def recent_final_videos(hours: int = 24, prefix: str = "animated-story-final/"):
    """List final video objects in R2 under `prefix`, newest first, within the
    last `hours`. NOT user-scoped (the bucket mixes all users) — admin use only;
    the Next.js proxy gates this on is_admin."""
    from datetime import datetime, timezone, timedelta
    from storybook_pipeline import get_r2_client, R2_BUCKET, R2_PUBLIC_BASE

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    s3 = get_r2_client()
    items = []
    token = None
    while True:
        kwargs = {"Bucket": R2_BUCKET, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith(".mp4"):
                continue
            lm = obj["LastModified"]
            if lm < cutoff:
                continue
            items.append({
                "url": f"{R2_PUBLIC_BASE}/{key}",
                "key": key,
                "last_modified": lm.isoformat(),
            })
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    items.sort(key=lambda x: x["last_modified"], reverse=True)
    return {"videos": items}

class GenerateStorybookSceneRequest(BaseModel):
    scene_text: str
    aspect_ratio: Optional[str] = "9:16"
    characters: Optional[List[dict]] = []

@app.post("/generate-storybook-scene-image")
async def generate_storybook_scene_image_endpoint(req: GenerateStorybookSceneRequest):
    try:
        from image_gen import generate_storybook_scene_image
        image_url = await generate_storybook_scene_image(
            scene_prompt=req.scene_text,
            aspect_ratio=req.aspect_ratio or "9:16"
        )
        return {"success": True, "scene_image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))
