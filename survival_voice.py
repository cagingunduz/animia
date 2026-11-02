"""Survival Story narration: Kokoro voices on our own CPU, word times from Whisper, mapped onto the caption words.

Each line has "text" (the caption form: "11:58 PM") and optionally "say" (the spoken form: "eleven fifty-eight P M"),
"voice" (a character: bm_george, af_bella, bf_emma, am_puck, am_fenrir; the narrator is am_michael) and "pause".
The text/say mapping follows engine/voice.py from github.com/Theoxmotion/story-video-studio (MIT).
"""

import asyncio
import difflib
import os
import re
import subprocess

import numpy as np

import yard_voice
from tts import get_word_timestamps

SR = yard_voice.SR                      # 24 kHz (Kokoro)
NARRATOR = os.environ.get("SURVIVAL_VOICE", "am_michael")
VOICES = {"am_michael", "bm_george", "af_bella", "bf_emma", "am_puck", "am_fenrir", "af_heart", "bm_lewis", "af_sarah",
          "am_onyx", "am_eric", "af_sky", "am_adam", "bm_fable"}
LEAD = 0.15


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(w).lower())


def _clean(w: str) -> str:
    return str(w).strip(".,!?;\"()[]").rstrip(".")


def _trim(a: np.ndarray) -> np.ndarray:
    idx = np.where(np.abs(a) > 0.01)[0]
    if not len(idx):
        return a
    return a[max(0, idx[0] - int(0.02 * SR)): idx[-1] + int(0.08 * SR)]


async def speak(lines: list[dict], speed: float) -> tuple[np.ndarray, list[dict]]:
    """lines -> (mono float32 audio at 24 kHz, spans [{i, start, end}]). Lines are spoken one by one with their pause."""
    k = await yard_voice._model()
    out, spans, t = [np.zeros(int(LEAD * SR), dtype=np.float32)], [], LEAD
    for i, ln in enumerate(lines):
        voice = ln.get("voice") if ln.get("voice") in VOICES else NARRATOR
        text = (ln.get("say") or ln["text"]).strip()
        a, _ = await asyncio.to_thread(k.create, text, voice=voice, speed=float(ln.get("speed") or speed), lang="en-us")
        a = _trim(np.asarray(a, dtype=np.float32))
        spans.append({"i": i, "start": round(t, 3), "end": round(t + len(a) / SR, 3)})
        out.append(a); t += len(a) / SR
        gap = np.zeros(int(max(0.0, min(1.2, float(ln.get("pause", 0.25)))) * SR), dtype=np.float32)
        out.append(gap); t += len(gap) / SR
    return np.concatenate(out), spans


def _spread(words: list[str], a: float, b: float) -> list[tuple[str, float, float]]:
    k = [len(w) + 2 for w in words]; tot = sum(k) or 1; out, t = [], a
    for w, n in zip(words, k):
        d = (b - a) * n / tot; out.append((w, t, t + d * 0.9)); t += d
    return out


def _spoken_times(spoken: list[str], heard: list[tuple[str, float, float]], a: float, b: float) -> list[tuple[str, float, float]]:
    """Whisper's words matched back to the spoken words of one line; gaps shared by word length."""
    if not heard:
        return _spread(spoken, a, b)
    times: list = [None] * len(spoken)
    sm = difflib.SequenceMatcher(a=[_norm(w) for w in spoken], b=[_norm(h[0]) for h in heard], autojunk=False)
    for i, j, n in sm.get_matching_blocks():
        for q in range(n):
            times[i + q] = (heard[j + q][1], heard[j + q][2])
    if not any(times):
        return _spread(spoken, a, b)
    i = 0
    while i < len(spoken):
        if times[i] is None:
            j = i
            while j < len(spoken) and times[j] is None:
                j += 1
            t0 = times[i - 1][1] if i > 0 else a
            t1 = times[j][0] if j < len(spoken) else b
            for m, (w, s, e) in zip(range(i, j), _spread(spoken[i:j], t0, max(t0 + 0.05, t1))):
                times[m] = (s, e)
            i = j
        else:
            i += 1
    return [(w, s, e) for w, (s, e) in zip(spoken, times)]


def _caption_words(text: str, say: str | None, spoken: list[tuple[str, float, float]]) -> list[dict]:
    """Times on the caption words ("11:58 PM") from the spoken words ("eleven fifty-eight P M")."""
    cw = text.split()
    if not say:
        return [{"w": _clean(w), "s": round(s, 3), "e": round(e, 3)} for (w, s, e), w in zip(spoken, cw)] if len(cw) == len(spoken) \
            else [{"w": _clean(w), "s": round(s, 3), "e": round(e, 3)} for w, s, e in _spread(cw, spoken[0][1], spoken[-1][2])]
    sw = [w for w, _, _ in spoken]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=[_norm(w) for w in cw], b=[_norm(w) for w in sw], autojunk=False).get_opcodes():
        if op == "equal":
            out += [{"w": _clean(cw[i1 + q]), "s": spoken[j1 + q][1], "e": spoken[j1 + q][2]} for q in range(i2 - i1)]
        elif i2 > i1:
            js, je = (j1, j2) if j2 > j1 else (max(0, j1 - 1), max(1, j1))
            st, en = spoken[js][1], spoken[je - 1][2]
            for q in range(i2 - i1):
                out.append({"w": _clean(cw[i1 + q]), "s": st + (en - st) * q / (i2 - i1), "e": st + (en - st) * (q + 1) / (i2 - i1)})
    return [{**w, "s": round(w["s"], 3), "e": round(w["e"], 3)} for w in out]


async def narrate(lines: list[dict], wav_path: str, speed: float = 1.1) -> dict:
    """lines -> wav_path (24 kHz mono) and the TIMING the film reads: {voice_end, lines: [{i, text, start, end, words, ...}]}."""
    import soundfile as sf
    audio, spans = await speak(lines, speed)
    sf.write(wav_path, audio, SR)
    mp3 = wav_path[:-4] + ".mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav_path, "-c:a", "libmp3lame", "-b:a", "96k", mp3], check=True)
    try:
        heard_all = await get_word_timestamps(open(mp3, "rb").read())
    except Exception as e:
        print(f"[survival] whisper failed, spreading words: {e!r}")
        heard_all = []
    out = []
    for ln, sp in zip(lines, spans):
        a, b = sp["start"], sp["end"]
        heard = [(str(w["word"]).strip(), float(w["start"]), float(w["end"])) for w in heard_all
                 if a - 0.2 <= (float(w["start"]) + float(w["end"])) / 2 <= b + 0.2 and str(w["word"]).strip()]
        spoken_words = (ln.get("say") or ln["text"]).split()
        spoken = _spoken_times(spoken_words, heard, a, b)
        words = _caption_words(ln["text"], ln.get("say"), spoken)
        extra = {k: v for k, v in ln.items() if k in ("key", "voice", "nocap", "who")}
        out.append({"i": sp["i"], "text": ln["text"].strip(), "start": a, "end": b, "words": words, **extra})
    return {"voice_end": round(spans[-1]["end"], 3), "lines": out, "seconds": round(len(audio) / SR, 2)}
