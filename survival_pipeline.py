"""
Survival Story pipeline: 60-90 s vertical second-person survival thrillers with flat 2D stickmen in real 3D low-poly
sets (three.js), a HUD, rule stickers, captions and a two-choice end card. No GPU and no AI images anywhere.
The format and the stage follow the MIT-licensed github.com/Theoxmotion/story-video-studio (v7).

  1. Writer (Claude)        pitches, picks, beat sheet, the script (text / say / voice / key / pause)
  2. Narrator (Kokoro)      am_michael + character voices on our own CPU, word times from Whisper
  3. Film builder (Claude)  one film(SV, T, stage) function on the stage kit (render_service/survival)
  4. Checks                 load + seek every half second (errors -> find/replace fixes), then a look at 6 stills
  5. Render                 the render service draws it in parallel chunks (3D at 960 tall, overlay at 1080x1920)
  6. Sound                  voice + a dark music bed made in code + room tone + effects, -14 LUFS
"""

import asyncio
import json
import math
import os
import re
import subprocess
import tempfile
import traceback

import anthropic

import motion_sound
import survival_sound
import survival_voice
from jobs import job_store
from motion_pipeline import BillingError, THINK_ROOM, _anthropic, _apply_edits, _record_usage, _render_call
from storybook_pipeline import upload_bytes_to_r2
from survival_compose import END_CARD, compose
from survival_prompts import EDIT_TOOL, FIX_NOTE, REVIEW_SYSTEM, SCENE_SYSTEM, SCRIPT_SYSTEM, SCRIPT_TOOL

MODEL = os.environ.get("SURVIVAL_MODEL", os.environ.get("PROMPT_MODEL", "claude-sonnet-5-5"))
EFFORT = os.environ.get("SURVIVAL_EFFORT", "medium")
OUT_W, OUT_H = 1080, 1920
DRAW_H = int(os.environ.get("SURVIVAL_DRAW_HEIGHT", "960"))   # the 3D draws this tall; the overlay is always full size
FPS = 30
CHUNKS = int(os.environ.get("SURVIVAL_RENDER_CHUNKS", "6"))
VOICE_SPEED = float(os.environ.get("SURVIVAL_VOICE_SPEED", "1.1"))
MAX_FIXES = 3
STEPS = 7
_FORBIDDEN = [
    (r"Math\.random\s*\(", "Math.random(): use SV.rng(seed) at build time"),
    (r"Date\.now|new Date\(|performance\.now", "reading the clock: everything must depend on t only"),
    (r"requestAnimationFrame|set(Timeout|Interval)\s*\(", "timers / requestAnimationFrame: the page owns the clock"),
    (r"\bfetch\s*\(|XMLHttpRequest|import\s*\(", "network or imports: build everything from SV"),
    (r"\bdocument\.(?!createElement)", "the DOM: only SV, stage and your own canvases"),
    (r"\.filter\s*=", "ctx.filter blur crashes long renders"),
]

_voice_sem = asyncio.Semaphore(1)       # Kokoro uses the whole CPU; one narration at a time


def _job(job_id: str) -> dict:
    return job_store[job_id]


def _stage(job_id: str, stage: str, step: int, message: str):
    j = _job(job_id)
    j.update(status="processing", stage=stage, step=step, total_steps=STEPS, message=message)
    print(f"[survival {job_id[:8]}] {step}/{STEPS} {message}")


async def _claude(job_id: str, system: str, content, max_tokens: int, role: str, tool: dict | None = None):
    """One Claude call; returns the text, or with `tool` the tool's input dict."""
    if tool:
        ask = {"type": "text", "text": f"Answer by calling the `{tool['name']}` tool."}
        content = [{"type": "text", "text": content}, ask] if isinstance(content, str) else [*content, ask]
    messages = [{"role": "user", "content": content}]
    kw = {"tools": [tool], "tool_choice": {"type": "auto"}} if tool else {}
    try:
        for _ in range(2 if tool else 1):
            async with _anthropic().messages.stream(
                model=MODEL, max_tokens=max_tokens + THINK_ROOM.get(EFFORT, 8000),
                output_config={"effort": EFFORT},
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages, **kw,
            ) as stream:
                msg = await stream.get_final_message()
            _record_usage(job_id, role, MODEL, msg.usage)
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


# ─────────────────────────── 1. story ───────────────────────────

def _clean_lines(lines: list) -> list[dict]:
    out = []
    for ln in lines or []:
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        o = {"text": text, "pause": max(0.1, min(1.0, float(ln.get("pause") or 0.25)))}
        say = str(ln.get("say") or "").strip()
        if say and say != text:
            o["say"] = say
        if ln.get("voice") in survival_voice.VOICES and ln.get("voice") != survival_voice.NARRATOR:
            o["voice"] = ln["voice"]
        if isinstance(ln.get("key"), dict) and ln["key"]:
            o["key"] = {str(k): str(v) for k, v in list(ln["key"].items())[:2]}
        out.append(o)
    return out


async def _write_story(job_id: str, p: dict) -> dict:
    ask = [f"The video idea: {p['idea'].strip()}" if (p.get("idea") or "").strip() else "The video idea: pitch 10 and pick the best."]
    if p.get("setting") and p["setting"] != "auto":
        ask.append(f"The setting: {p['setting']}.")
    ask.append(f"The length: about {int(p.get('seconds') or 70)} seconds.")
    ask.append(f"It is DAY {int(p.get('day') or 1)}.")
    s = await _claude(job_id, SCRIPT_SYSTEM, "\n".join(ask) + "\n\nWrite it, run the checklist, then submit the story.",
                      7000, "writer", tool=SCRIPT_TOOL)
    lines = _clean_lines(s.get("lines"))
    if len(lines) < 12:
        raise ValueError("the script came back too short")
    s["lines"] = lines
    return s


def _story_block(s: dict, timing: dict) -> str:
    rows = "\n".join(f'{i:>3}  {l["start"]:6.2f}-{l["end"]:6.2f}  {("[" + l["voice"] + "] ") if l.get("voice") else ""}{l["text"]}'
                     + (f'   key: {json.dumps(l["key"])}' if l.get("key") else "")
                     for i, l in enumerate(timing["lines"]))
    ch = s.get("choice") or {}
    return (f'TITLE: {s.get("title")}\nSETTING: {s.get("setting")}\nYOU: {s.get("hero")}\nCAST: {s.get("cast") or "-"}\n'
            f'DAY: {s.get("day")}\nCLOCK: {s.get("clock") or "-"}\nRULES: {json.dumps(s.get("rules"))}\nFACT: {s.get("fact") or "-"}\n'
            f'TWIST: {s.get("twist") or "-"}\nCHOICE: {ch.get("question")} / green: {ch.get("green")} / red: {ch.get("red")}\n\n'
            f'BEATS:\n{s.get("beats") or "-"}\n\nLINES (i, start-end seconds, text):\n{rows}\n\n'
            f'T.voice_end = {timing["voice_end"]}  (the end card runs {END_CARD} s after it)\n\n'
            f'SHOTS FROM THE WRITER:\n{s.get("visual_notes") or "-"}')


# ─────────────────────────── 3. the film ───────────────────────────

def _extract_code(text: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", text, re.S)
    code = (m.group(1) if m else text).strip()
    if "function film" not in code:
        raise ValueError("the film builder did not return a film() function")
    return code.replace("</script", "<\\/script")


def _static_problems(code: str) -> list[str]:
    return [why for pat, why in _FORBIDDEN if re.search(pat, code)]


async def _load(code: str, timing: dict) -> tuple[list[str], dict]:
    """Load the page once and seek every half second (no render): (errors, the film's sound spec)."""
    html = compose(code, timing, 270, 480, probe=True)
    r = await _render_call("/cues", {"files": {"index.html": html}}, timeout=300)
    if r.status_code != 200:
        return [f"page failed to load: {r.text[:600]}"], {}
    d = r.json()
    cues = d.get("cues", [])
    errors = [c.get("msg", "") for c in cues if c.get("kind") == "error"] + list(d.get("errors") or [])
    spec = next((c.get("spec") for c in cues if c.get("kind") == "spec"), None) or {}
    return errors, spec


async def _build_film(job_id: str, story: dict, timing: dict) -> tuple[str, dict]:
    text = await _claude(job_id, SCENE_SYSTEM, _story_block(story, timing) + "\n\nWrite film(SV, T, stage) for this video.",
                         28000, "film")
    code = _extract_code(text)
    for attempt in range(MAX_FIXES + 1):
        problems = _static_problems(code)
        errors, spec = ([], {})
        if not problems:
            errors, spec = await _load(code, timing)
        if not problems and not errors:
            return code, spec
        if attempt == MAX_FIXES:
            break
        _job(job_id)["message"] = f"Fixing the film ({attempt + 1})"
        issue = "\n".join(problems + errors)[:3000]
        res = await _claude(job_id, SCENE_SYSTEM,
                            f"{_story_block(story, timing)}\n\nYOUR CODE:\n```js\n{code}\n```\n\nERRORS:\n{issue}\n\n{FIX_NOTE}",
                            5000, "fixer", tool=EDIT_TOOL)
        code, n = _apply_edits(code, res.get("edits") or [])
        if not n:
            break
    raise ValueError("the film kept failing to load")


async def _review(job_id: str, story: dict, timing: dict, code: str) -> tuple[str, dict | None]:
    """One look at 6 stills: fix what is visibly wrong. Keeps the old code when the fix breaks anything."""
    lines = timing["lines"]
    picks = sorted({min(len(lines) - 1, round(i * (len(lines) - 1) / 4)) for i in range(5)})
    at = [0.05] + [round((lines[i]["start"] + lines[i]["end"]) / 2, 2) for i in picks[1:]] + [round(timing["voice_end"] + 1.5, 2)]
    labels = ["the first frame (the opener)"] + [f'line {i}: {lines[i]["text"]}' for i in picks[1:]] + ["the end card"]
    html = compose(code, timing, 540, 960, draw_h=720)
    r = await _render_call("/snapshot", {"files": {"index.html": html}, "at": at}, timeout=600)
    if r.status_code != 200:
        print(f"[survival] review skipped, snapshot failed: {r.text[:300]}")
        return code, None
    content = []
    for f, lab in zip(r.json().get("frames", []), labels):
        content.append({"type": "text", "text": f'{f["at"]:.1f} s, {lab}'})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": f["png"]}})
    content.append({"type": "text", "text": f"{_story_block(story, timing)}\n\nTHE CODE:\n```js\n{code}\n```"})
    res = await _claude(job_id, REVIEW_SYSTEM, content, 5000, "review", tool=EDIT_TOOL)
    _job(job_id)["review"] = str(res.get("problems") or "")[:500]
    new, n = _apply_edits(code, res.get("edits") or [])
    if not n:
        return code, None
    errors, spec = await _load(new, timing) if not _static_problems(new) else (["static"], {})
    return (new, spec) if not errors else (code, None)


# ─────────────────────────── 5. render ───────────────────────────

async def _render(job_id: str, code: str, timing: dict, tmp: str) -> str:
    """Draw the video in parallel chunks on the render service and join them (already 1080x1920)."""
    total_s = timing["voice_end"] + END_CARD
    total = int(round(total_s * FPS))
    per = math.ceil(total / CHUNKS / FPS) * FPS       # whole seconds per chunk, so the joins land on frames
    spans = [(k * per, min(per, total - k * per)) for k in range(CHUNKS) if total - k * per > 0]
    done = {"n": 0}

    async def one(k: int, f0: int, nf: int) -> str:
        html = compose(code, timing, OUT_W, OUT_H, start=f0 / FPS, duration=nf / FPS, draw_h=DRAW_H)
        for attempt in range(2):
            r = await _render_call("/render", {"files": {"index.html": html}, "quality": "standard", "fps": FPS, "timeout_ms": 1800000}, timeout=2400)
            if r.status_code == 200 and r.content:
                path = os.path.join(tmp, f"chunk{k}.mp4")
                open(path, "wb").write(r.content)
                done["n"] += 1
                _job(job_id)["message"] = f"Rendering the film ({done['n']}/{len(spans)})"
                return path
            print(f"[survival] chunk {k} attempt {attempt + 1} failed: {r.status_code} {r.text[:400]}")
        raise RuntimeError(f"render failed on chunk {k + 1}")

    paths = await asyncio.gather(*[one(k, f0, nf) for k, (f0, nf) in enumerate(spans)])
    lst = os.path.join(tmp, "chunks.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in paths))
    out = os.path.join(tmp, "video.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("joining the chunks failed: " + r.stderr[-600:])
    return out


# ─────────────────────────── 6. sound ───────────────────────────

async def _sound(job_id: str, video: str, voice_wav: str, timing: dict, spec: dict, tmp: str) -> str:
    total = timing["voice_end"] + END_CARD
    kinds = {str(c.get("type")) for c in (spec.get("sfx") or []) if str(c.get("type")) in survival_sound.LIBRARY_TYPES}
    if spec.get("roomtone", True):
        kinds.add("roomtone")
    try:
        lib = await motion_sound.fetch_library(kinds, tmp)
    except Exception as e:
        print(f"[survival] effects library unavailable, code-made sounds only: {e!r}")
        lib = {}
    mix_wav = os.path.join(tmp, "mix.wav")
    info = await asyncio.to_thread(survival_sound.mix, voice_wav, timing, spec, total, mix_wav, lib)
    _job(job_id)["sound"] = info
    out = os.path.join(tmp, "final.mp4")
    # the phone copy: H.264 + AAC, sized for Reels / Shorts / TikTok
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", mix_wav, "-map", "0:v", "-map", "1:a",
                        "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", "6M", "-bufsize", "12M",
                        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("encoding failed: " + r.stderr[-400:])
    return out


# ─────────────────────────── the job ───────────────────────────

async def run_survival_pipeline(job_id: str, p: dict):
    tmp = tempfile.mkdtemp(prefix="survival-")
    try:
        _stage(job_id, "script", 1, "Writing the story")
        story = await _write_story(job_id, p)
        _job(job_id).update(title=story.get("title"), script=story["lines"], rules=story.get("rules"),
                            choice=story.get("choice"), post=story.get("post"), pitches=story.get("top_pitches"))

        _stage(job_id, "voice", 2, "Recording the voices")
        voice_wav = os.path.join(tmp, "voice.wav")
        async with _voice_sem:
            timing = await survival_voice.narrate(story["lines"], voice_wav, speed=VOICE_SPEED)
        _job(job_id)["duration"] = round(timing["voice_end"] + END_CARD, 2)

        _stage(job_id, "scene", 3, "Building the sets and the shots")
        code, spec = await _build_film(job_id, story, timing)

        _stage(job_id, "check", 4, "Checking the key shots")
        try:
            code2, spec2 = await _review(job_id, story, timing, code)
            if spec2 is not None:
                code, spec = code2, spec2
        except BillingError:
            raise
        except Exception as e:
            print(f"[survival] review skipped: {e!r}")
        _job(job_id)["scene_code"] = code

        _stage(job_id, "render", 5, "Rendering the film")
        video = await _render(job_id, code, timing, tmp)

        _stage(job_id, "sound", 6, "Mixing the sound")
        final = await _sound(job_id, video, voice_wav, timing, spec, tmp)

        _stage(job_id, "upload", 7, "Uploading")
        url = await asyncio.to_thread(upload_bytes_to_r2, open(final, "rb").read(), "survival", "mp4", "video/mp4")
        thumb = os.path.join(tmp, "thumb.jpg")
        thumb_url = None
        if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.0", "-i", final, "-frames:v", "1", "-q:v", "3", thumb]).returncode == 0:
            thumb_url = await asyncio.to_thread(upload_bytes_to_r2, open(thumb, "rb").read(), "survival", "jpg", "image/jpeg")
        _job(job_id).update(status="completed", stage="done", step=STEPS, message="Done",
                            final_video_url=url, thumbnail_url=thumb_url)
    except Exception as e:
        traceback.print_exc()
        j = _job(job_id)
        j.update(status="failed", stage="failed", error=("Anthropic API credit is too low" if isinstance(e, BillingError) else str(e))[:500],
                 traceback=traceback.format_exc()[-3000:])
    finally:
        subprocess.run(["rm", "-rf", tmp])
