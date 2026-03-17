import uuid
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Literal

from jobs import job_store
from pipeline import run_pipeline
from tts import get_voices, generate_speech
from lipsync import upload_audio_to_r2
from image_gen import generate_character_image
from prompt_generator import get_style_prompt

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
    """Generate a single character image and return its URL."""
    try:
        style_prompt = get_style_prompt(req.style or "western_cartoon")
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
        {
            "scene_index": i + 1,
            "status": "queued",
            "video_url": None,
            "character_urls": {}
        }
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
