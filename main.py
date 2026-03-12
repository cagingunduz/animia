import uuid
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from jobs import job_store
from pipeline import run_pipeline
from tts import get_voices, generate_speech
from lipsync import upload_audio_to_r2

app = FastAPI(title="AnimAI API v3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Models ---

class CharacterDef(BaseModel):
    id: str                                    # Unique ID (user defined, e.g. "char_1")
    description: str                           # "60 year old male politician, navy suit"
    style: Optional[str] = "western_cartoon"  # western_cartoon | anime | pixar | comic | chibi | retro | custom
    photo_url: Optional[str] = None           # User uploaded reference photo (optional)


class SceneCharacter(BaseModel):
    character_id: str                          # References CharacterDef.id
    role: str = "silent"                       # "speaking" | "silent"
    dialogue: Optional[str] = None            # Only if role=speaking
    voice_id: Optional[str] = None            # Only if role=speaking
    framing: Optional[str] = "full_body"      # full_body | half_body | close_up


class Scene(BaseModel):
    scene_text: str                            # "A politician gives a speech at a podium"
    characters: List[SceneCharacter]           # Max 14, max 2 speaking
    aspect_ratio: Optional[str] = "16:9"      # 16:9 | 9:16 | 1:1
    pre_dialogue_action: Optional[str] = None # "Character slams fist on table, stands up"


class GenerateRequest(BaseModel):
    characters: List[CharacterDef]            # Global character definitions
    scenes: List[Scene]                       # One or more scenes


class TTSTestRequest(BaseModel):
    text: str
    voice_id: str


# --- Endpoints ---

@app.get("/")
async def root():
    return {
        "status": "AnimAI v3 online",
        "pipeline": "Claude -> Gemini -> Gemini -> ElevenLabs -> Seedance -> LipSync -> FFmpeg -> R2"
    }


@app.post("/generate")
async def generate(req: GenerateRequest):
    # Validate max 2 speaking per scene
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
        "traceback": None
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
