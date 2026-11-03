"""Kyutai Pocket TTS (github.com/kyutai-labs/pocket-tts: code MIT, model and voices CC BY 4.0, credit "Voice: Kyutai
Pocket TTS"): a small English TTS that runs faster than real time on our CPU and sounds more natural than Kokoro.

Voices are the package's built-in ones, addressed as "pt_<name>" (pt_george, pt_michael, pt_alba...). The model (about
250 MB) is downloaded once from Hugging Face into the model volume (HF_HOME under KOKORO_DIR when that is set).
"""

import os
import subprocess
import tempfile
import threading

import numpy as np

if os.environ.get("KOKORO_DIR") and not os.environ.get("HF_HOME"):
    os.environ["HF_HOME"] = os.path.join(os.environ["KOKORO_DIR"], "hf")

SR = 24000
VOICES = {"george", "michael", "charles", "paul", "marius", "javert", "jean", "alba", "anna", "vera", "fantine", "eponine",
          "azelma", "mary", "jane", "eve", "cosette"}
_lock = threading.Lock()
_model = None
_states: dict = {}


def is_pocket(voice: str | None) -> bool:
    return bool(voice) and voice.startswith("pt_") and voice[3:] in VOICES


def loaded() -> bool:
    return _model is not None


def _load():
    global _model
    with _lock:
        if _model is None:
            import torch
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 2)))
            from pocket_tts import TTSModel
            _model = TTSModel.load_model()
        return _model


def _tempo(a: np.ndarray, factor: float) -> np.ndarray:
    """Pace change without pitch change (ffmpeg atempo), for moods."""
    if abs(factor - 1) < 0.02:
        return a
    import soundfile as sf
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "i.wav"), os.path.join(d, "o.wav")
        sf.write(i, a, SR)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", i, "-filter:a", f"atempo={max(.5, min(2.0, factor)):.3f}", o], check=True)
        b, _ = sf.read(o, dtype="float32")
    return b


def say(text: str, voice: str, tempo: float = 1.0) -> np.ndarray:
    """One line -> mono float32 at 24 kHz (blocking: call it in a thread)."""
    m = _load()
    name = voice[3:] if voice.startswith("pt_") else voice
    with _lock:
        if name not in _states:
            _states[name] = m.get_state_for_audio_prompt(name)
        st = _states[name]
    a = m.generate_audio(st, text).numpy().astype(np.float32)
    if m.sample_rate != SR:
        import scipy.signal as ss
        a = ss.resample_poly(a, SR, m.sample_rate).astype(np.float32)
    return _tempo(a, tempo)
