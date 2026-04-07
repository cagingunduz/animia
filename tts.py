import os
import io


OPENAI_VOICES = [
    {"voice_id": "onyx",    "name": "Onyx",    "preview_url": "", "labels": {"gender": "male",   "accent": "american", "age": "middle_aged", "use_case": "narrator", "descriptive": "deep, authoritative"}},
    {"voice_id": "echo",    "name": "Echo",    "preview_url": "", "labels": {"gender": "male",   "accent": "american", "age": "young",       "use_case": "narrator", "descriptive": "clear, confident"}},
    {"voice_id": "fable",   "name": "Fable",   "preview_url": "", "labels": {"gender": "male",   "accent": "british",  "age": "middle_aged", "use_case": "narrator", "descriptive": "warm, storytelling"}},
    {"voice_id": "alloy",   "name": "Alloy",   "preview_url": "", "labels": {"gender": "male",   "accent": "american", "age": "middle_aged", "use_case": "narrator", "descriptive": "neutral, balanced"}},
    {"voice_id": "nova",    "name": "Nova",    "preview_url": "", "labels": {"gender": "female", "accent": "american", "age": "young",       "use_case": "narrator", "descriptive": "warm, engaging"}},
    {"voice_id": "shimmer", "name": "Shimmer", "preview_url": "", "labels": {"gender": "female", "accent": "american", "age": "young",       "use_case": "narrator", "descriptive": "clear, expressive"}},
]


async def generate_speech(text: str, voice_id: str) -> bytes:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice=voice_id,
        input=text,
    )
    return response.content


def get_audio_duration(audio_bytes: bytes) -> float:
    """Get MP3 duration in seconds using mutagen."""
    try:
        from mutagen.mp3 import MP3
        audio_file = MP3(io.BytesIO(audio_bytes))
        return audio_file.info.length
    except Exception:
        return len(audio_bytes) / 16000.0


async def get_word_timestamps(audio_bytes: bytes) -> list:
    """Use OpenAI Whisper to get word-level timestamps from audio."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return []
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


async def get_voices() -> list:
    return OPENAI_VOICES
