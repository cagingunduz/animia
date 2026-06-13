import os
import io

import httpx


ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
# Current high-quality multilingual model. Railway can still override this with
# ELEVENLABS_MODEL if a project needs v2 compatibility.
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_v3")

# Fallback list shown if the ElevenLabs API can't be reached (premade voice ids).
_FALLBACK_VOICES = [
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George",  "preview_url": "", "labels": {"gender": "male",   "descriptive": "warm, mature narrator"}},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah",   "preview_url": "", "labels": {"gender": "female", "descriptive": "soft, engaging"}},
    {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel",  "preview_url": "", "labels": {"gender": "male",   "descriptive": "deep, authoritative"}},
    {"voice_id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte","preview_url": "", "labels": {"gender": "female", "descriptive": "expressive, youthful"}},
]


def _headers() -> dict:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY environment variable is not set")
    return {"xi-api-key": api_key}


# Per-tone voice settings. Lower stability + higher style = more emotional,
# human, expressive delivery (less robotic/monotone). Tuned per scene mood.
TONE_SETTINGS = {
    "emotional":  {"stability": 0.30, "style": 0.55},
    "closing":    {"stability": 0.32, "style": 0.50},
    "tense":      {"stability": 0.34, "style": 0.55},
    "exciting":   {"stability": 0.30, "style": 0.62},
    "triumphant": {"stability": 0.33, "style": 0.58},
    "mysterious": {"stability": 0.45, "style": 0.38},
    "calm":       {"stability": 0.50, "style": 0.28},
}
# Default (no tone given): warm, lively human baseline — NOT the flat 0.5/0.0.
DEFAULT_TONE = {"stability": 0.40, "style": 0.42}


async def generate_speech(text: str, voice_id: str, tone: str = None) -> bytes:
    """Generate narration audio (MP3 bytes) with ElevenLabs TTS.
    `tone` shapes the emotional delivery (see TONE_SETTINGS)."""
    ts = TONE_SETTINGS.get((tone or "").strip().lower(), DEFAULT_TONE)
    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": ts["stability"],
            "similarity_boost": 0.75,
            "style": ts["style"],
            "use_speaker_boost": True,
        },
    }
    headers = {**_headers(), "Content-Type": "application/json", "Accept": "audio/mpeg"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            url, json=payload, headers=headers,
            params={"output_format": "mp3_44100_128"},
        )
        resp.raise_for_status()
        return resp.content


def get_audio_duration(audio_bytes: bytes) -> float:
    """Get MP3 duration in seconds using mutagen."""
    try:
        from mutagen.mp3 import MP3
        audio_file = MP3(io.BytesIO(audio_bytes))
        return audio_file.info.length
    except Exception:
        return len(audio_bytes) / 16000.0


async def get_word_timestamps(audio_bytes: bytes) -> list:
    """Use OpenAI Whisper to get word-level timestamps from audio (for captions).
    Independent of the TTS engine — works on any MP3."""
    import asyncio
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return []

    def _sync():
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.mp3"
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )
        return [{"word": w.word, "start": w.start, "end": w.end} for w in (transcript.words or [])]

    return await asyncio.to_thread(_sync)


def _map_voice(v: dict) -> dict:
    labels = v.get("labels") or {}
    return {
        "voice_id": v.get("voice_id"),
        "name": v.get("name", "Voice"),
        "preview_url": v.get("preview_url", ""),
        "labels": {
            "gender": labels.get("gender", ""),
            "accent": labels.get("accent", ""),
            "age": labels.get("age", ""),
            "use_case": labels.get("use_case", ""),
            # ElevenLabs uses "description"; our UI reads "descriptive"
            "descriptive": labels.get("description") or labels.get("descriptive") or labels.get("use_case", ""),
        },
    }


async def get_voices() -> list:
    """List narrator voices from the ElevenLabs account (premade + custom).
    Each carries a preview_url so the UI can play a sample instantly."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{ELEVENLABS_BASE}/voices", headers=_headers())
            resp.raise_for_status()
            data = resp.json()
        voices = [_map_voice(v) for v in data.get("voices", []) if v.get("voice_id")]
        return voices or _FALLBACK_VOICES
    except Exception as e:
        print(f"[WARN] ElevenLabs get_voices failed: {repr(e)}")
        return _FALLBACK_VOICES
