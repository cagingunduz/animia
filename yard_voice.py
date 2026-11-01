"""Kokoro-82M narration for 3D Build / 3D Health (am_michael) and Explainer (a voice the user picks):
free, runs on the backend's CPU.

The ONNX model and voices (~350 MB, Apache-2.0) are downloaded on first use and kept for the container's life.
"""

import asyncio
import os

import numpy as np

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
CACHE = os.environ.get("KOKORO_DIR", "/tmp/kokoro")
VOICE = os.environ.get("YARD_VOICE", "am_michael")
SR = 24000

_kokoro = None
_lock = asyncio.Lock()


async def _fetch(url: str, path: str):
    import httpx
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return
    tmp = path + ".part"
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    f.write(chunk)
    os.replace(tmp, path)


async def _model():
    global _kokoro
    async with _lock:
        if _kokoro is None:
            os.makedirs(CACHE, exist_ok=True)
            model, voices = os.path.join(CACHE, "kokoro-v1.0.onnx"), os.path.join(CACHE, "voices-v1.0.bin")
            await asyncio.gather(_fetch(MODEL_URL, model), _fetch(VOICES_URL, voices))

            def load():
                import espeakng_loader
                from kokoro_onnx import Kokoro
                from kokoro_onnx.config import EspeakConfig
                # espeak-ng wants the folder that CONTAINS espeak-ng-data
                data = os.environ.get("KOKORO_ESPEAK_DIR") or os.path.dirname(espeakng_loader.get_data_path())
                return Kokoro(model, voices, espeak_config=EspeakConfig(data_path=data))
            _kokoro = await asyncio.to_thread(load)
    return _kokoro


def _trim(a: np.ndarray) -> np.ndarray:
    idx = np.where(np.abs(a) > 0.01)[0]
    if not len(idx):
        return a
    return a[max(0, idx[0] - int(0.02 * SR)): idx[-1] + int(0.06 * SR)]


VOICES = {"am_michael": "Michael (US, calm)", "af_heart": "Heart (US, warm)", "bm_george": "George (UK)", "bf_emma": "Emma (UK)"}


def tighten(a: np.ndarray, max_pause: float = 0.24) -> np.ndarray:
    """Cut every truly silent stretch (30 ms windows under -45 dB) longer than max_pause down to max_pause."""
    win = int(0.03 * SR)
    if len(a) < win * 3:
        return a
    n = len(a) // win
    db = 20 * np.log10(np.sqrt(np.mean(a[: n * win].reshape(n, win) ** 2, axis=1)) + 1e-9)
    keep, run = [], 0
    for i in range(n):
        run = run + 1 if db[i] < -45 else 0
        if run * win / SR <= max_pause:
            keep.append(a[i * win:(i + 1) * win])
    keep.append(a[n * win:])
    return np.concatenate(keep)


async def say(text: str, voice: str = VOICE, speed: float = 1.1) -> np.ndarray:
    k = await _model()
    a, _ = await asyncio.to_thread(k.create, text, voice=voice, speed=speed, lang="en-us")
    return _trim(np.asarray(a, dtype=np.float32))


async def narrate(lines: list[dict], speed: float = 1.15, gap: float = 0.22, voice: str = VOICE,
                  max_pause: float | None = None) -> tuple[np.ndarray, list[dict]]:
    """lines [{id, text, pause?}] -> (mono float32 audio at 24 kHz, [{id, text, start, end}]).
    Lines are spoken one by one and joined with a short gap (+ the line's own pause); with max_pause, the
    silences inside a line are cut down to it as well."""
    k = await _model()
    out, spans, t = [], [], 0.0
    lead = np.zeros(int(0.12 * SR), dtype=np.float32)
    out.append(lead); t += len(lead) / SR
    for ln in lines:
        a, sr = await asyncio.to_thread(k.create, ln["text"], voice=voice, speed=speed, lang="en-us")
        a = _trim(np.asarray(a, dtype=np.float32))
        if max_pause:
            a = tighten(a, max_pause)
        spans.append({"id": ln["id"], "text": ln["text"], "start": round(t, 3), "end": round(t + len(a) / SR, 3)})
        out.append(a); t += len(a) / SR
        pause = np.zeros(int((gap + float(ln.get("pause") or 0)) * SR), dtype=np.float32)
        out.append(pause); t += len(pause) / SR
    return np.concatenate(out), spans
