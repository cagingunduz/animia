"""
Style Studio pipeline: vertical reels in styles from the MIT-licensed github.com/lemomo-ai/lemo-opuscar, made by
Claude writing the script and the animation code on each style's kit, rendered on our CPU (no GPU, no AI images).

  1. Writer (Claude)        the script in the style's structure (text / say / pause) + shot notes
  2. Narrator (Kokoro)      the style's voice on our CPU, word times from Whisper
  3. Film (Claude)          one film(K, T, c) function on the style's kit (render_service/studio/kits/<style>.js)
  4. Checks                 load + seek every half second (errors -> find/replace fixes), then a look at 6 stills
  5. Render                 the render service draws 1080x1920 in parallel chunks, joined
  6. Sound                  voice + the style's foley from the kit's events + a music bed + effects, -14 LUFS
"""

import asyncio
import base64
import io
import json
import math
import os
import re
import subprocess
import tempfile
import traceback

import anthropic

import motion_sound
import studio_sound
import studio_styles
import survival_voice
from jobs import job_store
from motion_pipeline import BillingError, THINK_ROOM, _anthropic, _apply_edits, _record_usage, _render_call
from storybook_pipeline import upload_bytes_to_r2
from studio_compose import compose
from studio_prompts import EDIT_TOOL, FIX_NOTE, SCRIPT_TOOL, film_system, review_system, writer_system

MODEL = os.environ.get("STUDIO_MODEL", os.environ.get("PROMPT_MODEL", "claude-sonnet-5-5"))
FILM_MODEL = os.environ.get("STUDIO_FILM_MODEL", MODEL)       # the animation code; Opus is better, and dearer
EFFORT = os.environ.get("STUDIO_EFFORT", "medium")
FPS = 30
CHUNKS = int(os.environ.get("STUDIO_RENDER_CHUNKS", "6"))
TAIL = 1.2                                                    # seconds after the last word
MAX_FIXES = 3
STEPS = 7
_FORBIDDEN = [
    (r"Math\.random\s*\(", "Math.random(): use K.mulberry(seed) at build time"),
    (r"Date\.now|new Date\(|performance\.now", "reading the clock: everything must depend on t only"),
    (r"requestAnimationFrame|set(Timeout|Interval)\s*\(", "timers / requestAnimationFrame: the page owns the clock"),
    (r"\bfetch\s*\(|XMLHttpRequest|import\s*\(|\bawait\b|\basync\b", "network, imports or async code: build everything synchronously"),
    (r"\bdocument\.(?!createElement)", "the DOM: only K, T and your own canvases"),
]
_voice_sem = asyncio.Semaphore(1)


def _job(job_id: str) -> dict:
    return job_store[job_id]


def _stage(job_id: str, stage: str, step: int, message: str):
    j = _job(job_id)
    j.update(status="processing", stage=stage, step=step, total_steps=STEPS, message=message)
    print(f"[studio {job_id[:8]}] {step}/{STEPS} {message}")


async def _claude(job_id: str, system: str, content, max_tokens: int, role: str, tool: dict | None = None, model: str = MODEL):
    if tool:
        ask = {"type": "text", "text": f"Answer by calling the `{tool['name']}` tool."}
        content = [{"type": "text", "text": content}, ask] if isinstance(content, str) else [*content, ask]
    messages = [{"role": "user", "content": content}]
    kw = {"tools": [tool], "tool_choice": {"type": "auto"}} if tool else {}
    try:
        for _ in range(2 if tool else 1):
            async with _anthropic().messages.stream(
                model=model, max_tokens=max_tokens + THINK_ROOM.get(EFFORT, 8000), output_config={"effort": EFFORT},
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}], messages=messages, **kw,
            ) as stream:
                msg = await stream.get_final_message()
            _record_usage(job_id, role, model, msg.usage)
            if not tool:
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
                if not text.strip():
                    raise ValueError(f"{role}: empty answer ({msg.stop_reason})")
                return text
            for b in msg.content:
                if getattr(b, "type", "") == "tool_use":
                    return dict(b.input)
            if msg.stop_reason in ("max_tokens", "refusal"):
                break
            messages += [{"role": "assistant", "content": msg.content},
                         {"role": "user", "content": f"Call the `{tool['name']}` tool now with your answer."}]
        raise ValueError(f"{role}: no structured answer ({msg.stop_reason})")
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e).lower():
            raise BillingError("Anthropic API credit balance is too low") from e
        raise


# ─────────────────────────── 1. script ───────────────────────────

def _clean_lines(lines: list, st: dict) -> list[dict]:
    cast = {k.upper(): v for k, v in (st.get("cast") or {}).items()}
    out = []
    for ln in lines or []:
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        o = {"text": text, "voice": st["voice"], "pause": max(0.1, min(1.0, float(ln.get("pause") or 0.25)))}
        if cast:                                  # dialogue styles: each line is spoken by one of the cast
            who = str(ln.get("who") or "").strip().upper()
            who = who if who in cast else next(iter(cast))
            o.update(who=who, voice=cast[who]["voice"], speed=cast[who].get("speed", st.get("speed", 1.0)))
        say = str(ln.get("say") or "").strip()
        if say and say != text:
            o["say"] = say
        out.append(o)
    return out


def _lips(wav: str, timing: dict) -> list[float]:
    """Mouth openness 0..1 per 1/24 s of the voice track (RMS over 50 ms, normalised per line to its 95th percentile)."""
    import numpy as np
    import soundfile as sf
    y, sr = sf.read(wav)
    if y.ndim > 1:
        y = y.mean(1)
    hop, win = sr / 24, int(0.05 * sr)
    n = int(len(y) / hop) + 1
    rms = np.array([np.sqrt(np.mean(y[max(0, int(k * hop) - win // 2):int(k * hop) + win // 2] ** 2) + 1e-12) for k in range(n)])
    out = np.zeros(n)
    for L in timing["lines"]:
        a, b = int(L["start"] * 24), min(n, int(L["end"] * 24) + 2)
        if b <= a:
            continue
        p = np.percentile(rms[a:b], 95) + 1e-9
        out[a:b] = np.clip((rms[a:b] / p - 0.1) / 0.8, 0, 1)
    return [round(float(v), 2) for v in out]


async def _write(job_id: str, st: dict, p: dict) -> dict:
    lo, hi = st["seconds"]
    secs = max(lo, min(hi, int(p.get("seconds") or (lo + hi) // 2)))
    ask = [f"The topic: {p['topic'].strip()}" if (p.get("topic") or "").strip() else "No topic given: pick the best one for this style yourself."]
    ask.append(f"The length: about {secs} seconds of narration (about {round(secs * 2.4)} words).")
    s = await _claude(job_id, writer_system(st), "\n".join(ask) + "\n\nWrite it, then submit the script.", 5000, "writer", tool=SCRIPT_TOOL)
    s["lines"] = _clean_lines(s.get("lines"), st)
    if len(s["lines"]) < 5:
        raise ValueError("the script came back too short")
    return s


def _block(s: dict, timing: dict) -> str:
    rows = "\n".join(f'{i:>3}  {l["start"]:6.2f}-{l["end"]:6.2f}  {(l["who"] + ": ") if l.get("who") else ""}{l["text"]}' for i, l in enumerate(timing["lines"]))
    return (f'TITLE: {s.get("title")}\n\nLINES (i, start-end seconds, text):\n{rows}\n\nT.end = {timing["end"]}\n\n'
            f'SHOT NOTES FROM THE WRITER:\n{s.get("visual_notes") or "-"}')


# ─────────────────────────── 3. film ───────────────────────────

def _extract(text: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", text, re.S)
    code = (m.group(1) if m else text).strip()
    if "function film" not in code:
        raise ValueError("the animator did not return a film() function")
    return code.replace("</script", "<\\/script")


def _static(code: str) -> list[str]:
    return [why for pat, why in _FORBIDDEN if re.search(pat, code)]


async def _load(st: dict, code: str, timing: dict) -> tuple[list[str], dict, list]:
    r = await _render_call("/cues", {"files": {"index.html": compose(st, code, timing, probe=True)}}, timeout=300)
    if r.status_code != 200:
        return [f"page failed to load: {r.text[:600]}"], {}, []
    d = r.json(); cues = d.get("cues", [])
    errors = [c.get("msg", "") for c in cues if c.get("kind") == "error"] + list(d.get("errors") or [])
    spec = next((c.get("spec") for c in cues if c.get("kind") == "spec"), None) or {}
    foley = next((c.get("events") for c in cues if c.get("kind") == "foley"), None) or []
    return errors, spec, foley


async def _film(job_id: str, st: dict, s: dict, timing: dict) -> tuple[str, dict, list]:
    system = film_system(st)
    text = await _claude(job_id, system, _block(s, timing) + "\n\nWrite film(K, T, c) for this reel.", 24000, "film", model=FILM_MODEL)
    code = _extract(text)
    for attempt in range(MAX_FIXES + 1):
        problems = _static(code)
        errors, spec, foley = ([], {}, [])
        if not problems:
            errors, spec, foley = await _load(st, code, timing)
        if not problems and not errors:
            return code, spec, foley
        if attempt == MAX_FIXES:
            break
        _job(job_id)["message"] = f"Fixing the animation ({attempt + 1})"
        issue = "\n".join(problems + errors)[:3000]
        res = await _claude(job_id, system, f"{_block(s, timing)}\n\nYOUR CODE:\n```js\n{code}\n```\n\nERRORS:\n{issue}\n\n{FIX_NOTE}",
                            5000, "fixer", tool=EDIT_TOOL, model=FILM_MODEL)
        code, n = _apply_edits(code, res.get("edits") or [])
        if not n:
            break
    raise ValueError("the animation kept failing to load")


def _small_jpeg(png_b64: str) -> str:
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(png_b64))).convert("RGB")
    im.thumbnail((540, 960)); buf = io.BytesIO(); im.save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


async def _review(job_id: str, st: dict, s: dict, timing: dict, code: str):
    lines = timing["lines"]
    picks = sorted({min(len(lines) - 1, round(i * (len(lines) - 1) / 5)) for i in range(6)})
    at = [round((lines[i]["start"] + lines[i]["end"]) / 2, 2) for i in picks]
    r = await _render_call("/snapshot", {"files": {"index.html": compose(st, code, timing)}, "at": at}, timeout=900)
    if r.status_code != 200:
        print(f"[studio] review skipped, snapshot failed: {r.text[:300]}")
        return code, None
    content = []
    for f, i in zip(r.json().get("frames", []), picks):
        content.append({"type": "text", "text": f'{f["at"]:.1f} s, line {i}: {lines[i]["text"]}'})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _small_jpeg(f["png"])}})
    content.append({"type": "text", "text": f"{_block(s, timing)}\n\nTHE CODE:\n```js\n{code}\n```"})
    res = await _claude(job_id, review_system(st), content, 5000, "review", tool=EDIT_TOOL)
    _job(job_id)["review"] = str(res.get("problems") or "")[:500]
    new, n = _apply_edits(code, res.get("edits") or [])
    if not n:
        return code, None
    if _static(new):
        return code, None
    errors, spec, foley = await _load(st, new, timing)
    return (new, (spec, foley)) if not errors else (code, None)


# ─────────────────────────── 5. render ───────────────────────────

async def _render(job_id: str, st: dict, code: str, timing: dict, tmp: str) -> str:
    total = int(round(timing["end"] * FPS))
    per = math.ceil(total / CHUNKS / FPS) * FPS
    spans = [(k * per, min(per, total - k * per)) for k in range(CHUNKS) if total - k * per > 0]
    done = {"n": 0}

    async def one(k: int, f0: int, nf: int) -> str:
        html = compose(st, code, timing, start=f0 / FPS, duration=nf / FPS)
        for attempt in range(2):
            r = await _render_call("/render", {"files": {"index.html": html}, "quality": "standard", "fps": FPS, "timeout_ms": 1800000}, timeout=2400)
            if r.status_code == 200 and r.content:
                path = os.path.join(tmp, f"chunk{k}.mp4"); open(path, "wb").write(r.content)
                done["n"] += 1; _job(job_id)["message"] = f"Rendering ({done['n']}/{len(spans)})"
                return path
            print(f"[studio] chunk {k} attempt {attempt + 1} failed: {r.status_code} {r.text[:400]}")
        raise RuntimeError(f"render failed on chunk {k + 1}")

    paths = await asyncio.gather(*[one(k, f0, nf) for k, (f0, nf) in enumerate(spans)])
    lst = os.path.join(tmp, "chunks.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in paths))
    out = os.path.join(tmp, "video.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("joining the chunks failed: " + r.stderr[-600:])
    return out


# ─────────────────────────── 6. sound ───────────────────────────

async def _sound(job_id: str, st: dict, video: str, voice_wav: str, timing: dict, spec: dict, foley: list, tmp: str) -> str:
    kinds = {str(c.get("type")) for c in (spec.get("sfx") or []) if str(c.get("type")) in motion_sound.SFX_LIBRARY}
    if st.get("bed") in motion_sound.SFX_LIBRARY:
        kinds.add(st["bed"])
    try:
        lib = await motion_sound.fetch_library(kinds, tmp)
    except Exception as e:
        print(f"[studio] sound library unavailable: {e!r}")
        lib = {}
    mix_wav = os.path.join(tmp, "mix.wav")
    info = await asyncio.to_thread(studio_sound.mix, voice_wav, timing, timing["end"], mix_wav, foley_kind=st.get("foley", ""),
                                   foley_events=foley, bed=st.get("bed"), bed_db=st.get("bed_db", -14.0), spec=spec, lib=lib)
    _job(job_id)["sound"] = info
    out = os.path.join(tmp, "final.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", mix_wav, "-map", "0:v", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", "6M", "-bufsize", "12M", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("encoding failed: " + r.stderr[-400:])
    return out


# ─────────────────────────── the job ───────────────────────────

async def run_studio_pipeline(job_id: str, p: dict):
    tmp = tempfile.mkdtemp(prefix="studio-")
    try:
        st = studio_styles.style(p["style"])
        _stage(job_id, "script", 1, "Writing the script")
        s = await _write(job_id, st, p)
        _job(job_id).update(title=s.get("title"), script=s["lines"], post=s.get("post"))

        _stage(job_id, "voice", 2, "Recording the narrator")
        voice_wav = os.path.join(tmp, "voice.wav")
        async with _voice_sem:
            timing = await survival_voice.narrate(s["lines"], voice_wav, speed=st.get("speed", 1.05))
        timing["end"] = round(timing["voice_end"] + st.get("tail", TAIL), 3)
        if st.get("cast"):
            timing["lips"] = await asyncio.to_thread(_lips, voice_wav, timing)
        _job(job_id)["duration"] = timing["end"]

        _stage(job_id, "scene", 3, "Animating")
        code, spec, foley = await _film(job_id, st, s, timing)

        _stage(job_id, "check", 4, "Checking the key frames")
        try:
            code2, extra = await _review(job_id, st, s, timing, code)
            if extra is not None:
                code, (spec, foley) = code2, extra
        except BillingError:
            raise
        except Exception as e:
            print(f"[studio] review skipped: {e!r}")
        _job(job_id)["scene_code"] = code

        _stage(job_id, "render", 5, "Rendering")
        video = await _render(job_id, st, code, timing, tmp)

        _stage(job_id, "sound", 6, "Mixing the sound")
        final = await _sound(job_id, st, video, voice_wav, timing, spec, foley, tmp)

        _stage(job_id, "upload", 7, "Uploading")
        url = await asyncio.to_thread(upload_bytes_to_r2, open(final, "rb").read(), "studio", "mp4", "video/mp4")
        thumb = os.path.join(tmp, "thumb.jpg"); thumb_url = None
        if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.0", "-i", final, "-frames:v", "1", "-q:v", "3", thumb]).returncode == 0:
            thumb_url = await asyncio.to_thread(upload_bytes_to_r2, open(thumb, "rb").read(), "studio", "jpg", "image/jpeg")
        _job(job_id).update(status="completed", stage="done", step=STEPS, message="Done", final_video_url=url, thumbnail_url=thumb_url)
    except Exception as e:
        traceback.print_exc()
        j = _job(job_id)
        j.update(status="failed", stage="failed", error=("Anthropic API credit is too low" if isinstance(e, BillingError) else str(e))[:500],
                 traceback=traceback.format_exc()[-3000:])
    finally:
        subprocess.run(["rm", "-rf", tmp])
