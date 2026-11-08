"""Gemini TTS narrators (Google Gemini API, GEMINI_API_KEY): voices the creator picked by ear, each with its own
delivery prompt and pace. Voice ids start with "gm_" so they sit in the same picker as the ElevenLabs voices.

gm_zephyr_tr: Turkish, Zephyr, friendly ad-voiceover delivery (approved 2026-11-08). The first beat (the hook) plays
1.18x, every other beat 1.12x, sped up with ffmpeg atempo (pitch kept). Word timings come from Whisper, like every
other engine without native alignment.
"""

import asyncio
import base64
import os
import subprocess
import tempfile

import httpx

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

VOICES = {
    "gm_zephyr_tr": {
        "name": "Zephyr - Samimi Türkçe (Gemini)",
        "voice": "Zephyr",
        "model": os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
        "language": "tr",
        "prompt": ("Reklam filmi seslendirmeni kalitesinde ama acele etmeden, rahat ve sakin bir tempoda oku; cümleler arasında "
                   "kısa nefesler bırak. Ton samimi ve içten olsun, yakın bir arkadaşına tavsiye veriyormuş gibi; vurgular doğal "
                   "ve abartısız, gülmeden: "),
        "hook_tempo": 1.18,
        "tempo": 1.12,
        "labels": {"gender": "female", "accent": "Turkish", "age": "young", "use_case": "social_media",
                   "descriptive": "warm, friendly, like advice from a friend"},
        "preview_url": "/voices/zephyr-tr.mp3",
    },
}


class GeminiTTSError(RuntimeError):
    """Gemini TTS refused or failed (most often the daily free-tier quota)."""


def is_gemini(voice_id: str | None) -> bool:
    return bool(voice_id) and voice_id in VOICES


def voice_list() -> list[dict]:
    """Entries in the /voices shape (the app's picker)."""
    return [{"voice_id": k, "name": v["name"], "preview_url": v["preview_url"], "labels": v["labels"]} for k, v in VOICES.items()]


def tempo(voice_id: str, hook: bool) -> float:
    v = VOICES[voice_id]
    return v["hook_tempo"] if hook else v["tempo"]


async def _pcm(text: str, v: dict) -> tuple[bytes, int]:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise GeminiTTSError("GEMINI_API_KEY is not set")
    body = {"contents": [{"parts": [{"text": v["prompt"] + " ".join(text.split())}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v["voice"]}}}}}
    last = ""
    for attempt in range(4):
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(URL.format(model=v["model"]), json=body, headers={"x-goog-api-key": key})
        if r.status_code == 200:
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            mime = part.get("mimeType", "")
            rate = next((int(x.split("=")[1]) for x in mime.split(";") if x.strip().startswith("rate=")), 24000)
            return base64.b64decode(part["data"]), rate
        last = f"{r.status_code} {r.text[:300]}"
        if r.status_code == 429 and "PerDay" in r.text:
            break                                   # the day's quota is gone: retrying won't help
        if r.status_code not in (429, 500, 502, 503):
            break
        await asyncio.sleep(3 * (attempt + 1))
    if "429" in last[:3]:
        raise GeminiTTSError("Gemini TTS quota exceeded (enable billing for the Gemini API key): " + last)
    raise GeminiTTSError("Gemini TTS failed: " + last)


def _to_mp3(raw: bytes, rate: int, factor: float) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "in"), os.path.join(d, "out.mp3")
        open(src, "wb").write(raw)
        fmt = [] if raw[:4] == b"RIFF" else ["-f", "s16le", "-ar", str(rate), "-ac", "1"]
        af = f"atempo={max(0.5, min(2.0, factor)):.3f}" if abs(factor - 1) > 0.005 else "anull"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *fmt, "-i", src, "-af", af, "-ar", "44100", "-ac", "1",
                        "-c:a", "libmp3lame", "-b:a", "128k", out], check=True)
        return open(out, "rb").read()


def _seconds(raw: bytes, rate: int) -> float:
    """Length of 16-bit mono audio (raw PCM, or a WAV with its 44-byte header)."""
    return max(0, len(raw) - (44 if raw[:4] == b"RIFF" else 0)) / (2 * rate)


# Gemini TTS sometimes drops part of a line. Natural Turkish speech at 1.0x is ~11-15 characters a second; a take
# faster than this was cut short and is recorded again (the longest take wins).
MAX_CPS = 20.0


async def speech(text: str, voice_id: str, factor: float | None = None, hook: bool = False) -> bytes:
    """One line -> MP3 bytes at the voice's pace (the hook pace for the first beat)."""
    v = VOICES[voice_id]
    chars = len("".join(text.split()))
    best = None
    for attempt in range(3):
        raw, rate = await _pcm(text, v)
        secs = _seconds(raw, rate)
        if best is None or secs > best[2]:
            best = (raw, rate, secs)
        if secs > 0 and chars / secs <= MAX_CPS:
            break
        print(f"[gemini voice] take {attempt + 1} looks cut short ({secs:.2f} s for {chars} characters): recording again")
    raw, rate, _ = best
    return await asyncio.to_thread(_to_mp3, raw, rate, factor if factor else tempo(voice_id, hook))


async def speech_timed(text: str, voice_id: str, factor: float | None = None, hook: bool = False) -> tuple[bytes, list]:
    """One line -> (MP3 bytes, [{word, start, end}]) with Whisper word timings on the sped-up audio."""
    from tts import get_word_timestamps
    audio = await speech(text, voice_id, factor, hook)
    return audio, await get_word_timestamps(audio, language=VOICES[voice_id].get("language"))
