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
import studio_collage
import studio_footage
import studio_plate
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

# how each mood is performed by Kokoro (which has no emotion control): pace, extra silence after the line, loudness
MOODS = {
    "neutral":  {"speed": 1.0,  "pause": 0.0},
    "deadpan":  {"speed": 0.9,  "pause": 0.25},
    "excited":  {"speed": 1.12, "pause": -0.05, "bang": True},
    "panic":    {"speed": 1.2,  "pause": -0.1},
    "whisper":  {"speed": 0.9,  "pause": 0.1, "gain": 0.5},
    "confused": {"speed": 0.95, "pause": 0.2},
    "sad":      {"speed": 0.86, "pause": 0.3, "gain": 0.8},
    "angry":    {"speed": 1.08, "pause": 0.0, "gain": 1.15, "bang": True},
    "warm":     {"speed": 0.95, "pause": 0.1},
}


def _clean_lines(lines: list, st: dict) -> list[dict]:
    cast = {k.upper(): v for k, v in (st.get("cast") or {}).items()}
    out = []
    for ln in lines or []:
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        o = {"text": text, "voice": st["voice"], "pause": max(0.1, min(1.0, float(ln.get("pause") or 0.25)))}
        mood = str(ln.get("mood") or "neutral").lower()
        mood = mood if mood in MOODS else "neutral"
        o["mood"] = mood
        if cast:                                  # dialogue styles: each line is spoken by one of the cast
            who = str(ln.get("who") or "").strip().upper()
            who = who if who in cast else next(iter(cast))
            o.update(who=who, voice=cast[who]["voice"], speed=cast[who].get("speed", st.get("speed", 1.0)))
        say = str(ln.get("say") or "").strip()
        if say and say != text:
            o["say"] = say
        # the mood: pace, the silence after the line, loudness; excited / angry end on '!' in the spoken form
        m = MOODS[mood]
        o["speed"] = round(float(o.get("speed") or st.get("speed", 1.0)) * m["speed"], 3)
        o["pause"] = round(max(0.08, min(1.4, o["pause"] + m["pause"])), 3)
        if m.get("gain", 1) != 1:
            o["gain"] = m["gain"]
        if m.get("bang") and not re.search(r"[!?]$", (o.get("say") or text)):
            o["say"] = re.sub(r"[.…]*$", "", o.get("say") or text) + "!"
        if st.get("media") and ln.get("caption"):
            o["caption"] = str(ln["caption"])[:160]
        if st.get("media") and isinstance(ln.get("media"), dict):
            o["media"] = ln["media"]
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


def _options(st: dict, raw) -> dict:
    """The user's per-style choices, cleaned: accent (#rrggbb), handle (end card), voice (one of the style's), audience."""
    raw = raw if isinstance(raw, dict) else {}
    allowed, out = st.get("options") or [], {}
    if "accent" in allowed and re.fullmatch(r"#[0-9a-fA-F]{6}", str(raw.get("accent") or "")):
        out["accent"] = str(raw["accent"])
    if "handle" in allowed and str(raw.get("handle") or "").strip():
        out["handle"] = re.sub(r"[^\w@.\- ]", "", str(raw["handle"]).strip())[:40]
    if "voice" in allowed and raw.get("voice") in (st.get("voices") or []):
        out["voice"] = raw["voice"]
    if "audience" in allowed and str(raw.get("audience") or "").strip():
        out["audience"] = str(raw["audience"]).strip()[:160]
    return out


async def _write(job_id: str, st: dict, p: dict, media: dict | None = None) -> dict:
    lo, hi = st["seconds"]
    secs = max(lo, min(hi, int(p.get("seconds") or (lo + hi) // 2)))
    ask = [f"The topic: {p['topic'].strip()}" if (p.get("topic") or "").strip() else "No topic given: pick the best one for this style yourself."]
    ask.append(f"The length: about {secs} seconds of narration (about {round(secs * 2.4)} words).")
    if (p.get("_opts") or {}).get("audience"):
        ask.append(f"The audience: {p['_opts']['audience']}")
    content = "\n".join(ask) + "\n\nWrite it, then submit the script."
    if st.get("media"):
        content = [{"type": "text", "text": "\n".join(ask)}]
        ups = (media or {}).get("uploads") or []
        if ups:
            content.append({"type": "text", "text": f"THE USER'S UPLOADS ({len(ups)}), use them first (media.upload = the number):"})
            for i, u in enumerate(ups):
                content.append({"type": "text", "text": f"upload {i}: {u['kind']}" + (f", {u['duration']:.1f} s (sheet: one frame per {u['every']:g} s, time in the corner)" if u['kind'] == 'video' else "")})
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": u["sheet"]}})
        else:
            content.append({"type": "text", "text": "No uploads: every footage line gets a media.search (archive footage is found for it)."})
        content.append({"type": "text", "text": "Write it, then submit the script."})
    s = await _claude(job_id, writer_system(st), content, 5000, "writer", tool=SCRIPT_TOOL)
    if st.get("fact_check"):
        s = await _fact_check(job_id, st, s)
    s["lines"] = _clean_lines(s.get("lines"), st)
    if len(s["lines"]) < 5:
        raise ValueError("the script came back too short")
    return s


async def _fact_check(job_id: str, st: dict, s: dict) -> dict:
    """True stories (Collage Documentary): every line is checked before anything is recorded; doubtful claims are
    softened or cut ("could barely hear" rather than "was completely deaf" when sources disagree)."""
    _job(job_id)["message"] = "Checking the facts"
    draft = json.dumps({k: s.get(k) for k in ("title", "lines", "visual_notes", "post")}, ensure_ascii=False)
    ask = (f"THE DRAFT SCRIPT:\n{draft}\n\nFact-check it line by line before it is recorded. For every claim (names, dates, "
           "numbers, quotes, causes, 'first' / 'only' / 'never'): keep it only if it is well established. If sources disagree, "
           "say it the careful way; if it is a legend or a misattributed quote, cut it or call it a legend. Keep the length, the "
           "structure, the moods and the punch; only change what is wrong or doubtful. Then submit the full corrected script, "
           "with a `fact_notes` line in visual_notes' first line listing what you changed (or 'no changes').")
    try:
        fixed = await _claude(job_id, writer_system(st), ask, 5000, "fact_check", tool=SCRIPT_TOOL)
        if fixed.get("lines") and len(fixed["lines"]) >= 5:
            _job(job_id)["fact_notes"] = str(fixed.get("visual_notes") or "").split("\n", 1)[0][:400]
            return fixed
    except BillingError:
        raise
    except Exception as e:
        print(f"[studio] fact check skipped: {e!r}")
    return s


def _block(s: dict, timing: dict) -> str:
    rows = "\n".join(f'{i:>3}  {l["start"]:6.2f}-{l["end"]:6.2f}  {(l["who"] + ": ") if l.get("who") else ""}{l["text"]}' for i, l in enumerate(timing["lines"]))
    opts = f'\n\nT.options = {json.dumps(timing["options"])}' if timing.get("options") else ""
    return (f'TITLE: {s.get("title")}\n\nLINES (i, start-end seconds, text):\n{rows}\n\nT.end = {timing["end"]}{opts}\n\n'
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


async def _load(st: dict, code: str, timing: dict, bins: dict | None = None) -> tuple[list[str], dict, list]:
    payload = {"files": {"index.html": compose(st, code, timing, probe=True)}}
    if bins:
        payload["binary_files"] = bins
    r = await _render_call("/cues", payload, timeout=300)
    if r.status_code != 200:
        return [f"page failed to load: {r.text[:600]}"], {}, []
    d = r.json(); cues = d.get("cues", [])
    errors = [c.get("msg", "") for c in cues if c.get("kind") == "error"] + list(d.get("errors") or [])
    spec = next((c.get("spec") for c in cues if c.get("kind") == "spec"), None) or {}
    foley = next((c.get("events") for c in cues if c.get("kind") == "foley"), None) or []
    return errors, spec, foley


def _offscreen(st: dict, foley: list) -> list[str]:
    """Whiteboard: strokes drawn while the camera looks elsewhere (the kit marks each stroke on / off screen)."""
    if st.get("foley") != "marker":
        return []
    out = []
    lay = next((e for e in foley if isinstance(e, dict) and e.get("type") == "layout"), None)
    if lay and lay.get("overlaps"):
        rows = "\n".join(f"- '{o['a']['label']}' (drawn at {o['a']['t']}s, box {o['a']['box']}) overlaps '{o['b']['label']}' "
                         f"(drawn at {o['b']['t']}s, box {o['b']['box']})" for o in lay["overlaps"][:12])
        out.append("LAYOUT: drawings run into each other (boxes are [x0, y0, x1, y1] on the board; K.text(...).width "
                   f"tells you how wide a line of writing is):\n{rows}\nMove one of each pair so they don't touch (a gap of "
                   "40+ units), or shrink the text; keep labels beside or under a drawing, not across it.")
    strokes = [e for e in foley if isinstance(e, dict) and e.get("type") in ("stroke", "write") and e.get("x") is not None]
    off = [e for e in strokes if e.get("on") == 0]
    if strokes and len(off) >= max(3, 0.08 * len(strokes)):
        rows = ", ".join(f"t={e['t']:.1f}s at ({e['x']:.0f}, {e['y']:.0f})" for e in off[:12])
        out.append(f"LAYOUT: {len(off)} of {len(strokes)} strokes are drawn OFF SCREEN (the camera is not looking at them when "
                   f"they are drawn): {rows}. The screen is 1080 x 1920: at zoom z it shows x = camX ± 540/z, y = camY ± 960/z. "
                   "Move those drawings into the column the camera shows, or add / move a camera key so it looks at them while "
                   "they are drawn.")
    return out


async def _film(job_id: str, st: dict, s: dict, timing: dict, stills: list | None = None, bins: dict | None = None,
                sheets: list | None = None) -> tuple[str, dict, list]:
    system = film_system(st)
    content = _block(s, timing) + "\n\nWrite film(K, T, c) for this reel."
    if timing.get("shots"):
        content = _block(s, timing) + "\n\nT.shots (the footage plate under your canvas):\n" + json.dumps(timing["shots"]) + "\n\nWrite film(K, T, c) for this reel."
    if stills:
        content = [{"type": "text", "text": content.rsplit("\n\n", 1)[0]}]
        for f in stills:
            content.append({"type": "text", "text": f"FREEZE {f['freeze']:.2f}-{f['t1']:.2f} s: the frozen picture as it is on screen (grid = SCREEN pixels, x across, y down; draw at these coordinates):"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": f["jpeg"]}})
        content.append({"type": "text", "text": "Write film(K, T, c) for this reel."})
    if sheets:
        rows = "\n".join(f'- T.img.{im["id"]}: {im["kind"]}, {im["w"]}x{im["h"]} px' + (f' — {im["use"]}' if im.get("use") else "")
                         + (f' (credit on screen: "{im["credit"]}")' if im.get("credit") else "") for im in timing["images"])
        content = [{"type": "text", "text": _block(s, timing) + f"\n\nTHE PICTURES (T.img[id], already loaded; cut-outs have transparent backgrounds):\n{rows}"}]
        for k, jpg in enumerate(sheets):
            content.append({"type": "text", "text": f"Contact sheet {k + 1} (checkerboard = transparent):"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpg}})
        content.append({"type": "text", "text": "Write film(K, T, c) for this reel."})
    text = await _claude(job_id, system, content, 24000, "film", model=FILM_MODEL)
    code = _extract(text)
    for attempt in range(MAX_FIXES + 1):
        problems = _static(code)
        errors, spec, foley = ([], {}, [])
        if not problems:
            errors, spec, foley = await _load(st, code, timing, bins)
            if not errors and attempt < 2:
                errors = _offscreen(st, foley)
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


async def _review(job_id: str, st: dict, s: dict, timing: dict, code: str, plate: str | None = None, bins: dict | None = None):
    lines = timing["lines"]
    picks = sorted({min(len(lines) - 1, round(i * (len(lines) - 1) / 5)) for i in range(6)})
    at = [round((lines[i]["start"] + lines[i]["end"]) / 2, 2) for i in picks]
    payload = {"files": {"index.html": compose(st, code, timing, plate="plate.mp4" if plate else None)}, "at": at}
    if plate:
        payload["binary_files"] = {"plate.mp4": base64.b64encode(open(plate, "rb").read()).decode()}
    if bins:
        payload["binary_files"] = {**payload.get("binary_files", {}), **bins}
    r = await _render_call("/snapshot", payload, timeout=900)
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
    errors, spec, foley = await _load(st, new, timing, bins)
    return (new, (spec, foley)) if not errors else (code, None)


# ─────────────────────────── 5. render ───────────────────────────

async def _render(job_id: str, st: dict, code: str, timing: dict, tmp: str, plate: str | None = None, bins: dict | None = None) -> str:
    total = int(round(timing["end"] * FPS))
    per = math.ceil(total / CHUNKS / FPS) * FPS
    spans = [(k * per, min(per, total - k * per)) for k in range(CHUNKS) if total - k * per > 0]
    done = {"n": 0}

    async def one(k: int, f0: int, nf: int) -> str:
        html = compose(st, code, timing, start=f0 / FPS, duration=nf / FPS, plate="plate.mp4" if plate else None)
        payload = {"files": {"index.html": html}, "quality": "standard", "fps": FPS, "timeout_ms": 1800000}
        if plate:   # this chunk's frames of the footage plate, starting at the chunk's first frame
            part = await asyncio.to_thread(studio_plate.cut, plate, f0 / FPS, nf / FPS, os.path.join(tmp, f"plate{k}.mp4"))
            payload["binary_files"] = {"plate.mp4": base64.b64encode(open(part, "rb").read()).decode()}
        if bins:
            payload["binary_files"] = {**payload.get("binary_files", {}), **bins}
        for attempt in range(2):
            r = await _render_call("/render", payload, timeout=2400)
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
        opts = _options(st, p.get("options"))
        p = {**p, "_opts": opts}
        if opts.get("voice"):
            st["voice"] = opts["voice"]
        media = None
        if st.get("media"):
            _stage(job_id, "script", 1, "Looking at your footage")
            media = {"uploads": await studio_footage.uploads(p.get("uploads") or [], tmp)}
        _stage(job_id, "script", 1, "Writing the script")
        s = await _write(job_id, st, p, media)
        _job(job_id).update(title=s.get("title"), script=s["lines"], post=s.get("post"))

        art = None
        if st.get("art"):              # the pictures are cast and made while the narrator records
            pics_state = {"n": 0, "of": 0}
            def pic_progress(n, of):
                pics_state.update(n=n, of=of)
                if _job(job_id).get("stage") == "pictures":
                    _job(job_id)["message"] = f"Making the pictures ({n}/{of})"
            tool = lambda system, content, mt, role, tl: _claude(job_id, system, content, mt, role, tool=tl)
            async def look(content):
                return await _claude(job_id, "You pick pictures. Answer with a number only.", content, 50, "art_pick")
            art = asyncio.create_task(studio_collage.make(job_id, tool, look, st, s, tmp, progress=pic_progress))

        _stage(job_id, "voice", 2, "Recording the narrator")
        voice_wav = os.path.join(tmp, "voice.wav")
        def said(stage, i, n):
            _job(job_id)["message"] = {"model": "Loading the voice model (first reel after a restart)",
                                       "line": f"Recording the narrator ({i}/{n})", "align": "Lining up the words"}[stage]
        if _voice_sem.locked():
            _job(job_id)["message"] = "Waiting for the narrator (another reel is recording)"
        async with _voice_sem:
            timing = await survival_voice.narrate(s["lines"], voice_wav, speed=st.get("speed", 1.05), progress=said)
        timing["end"] = round(timing["voice_end"] + st.get("tail", TAIL), 3)
        if opts:
            timing["options"] = {k: v for k, v in opts.items() if k in ("accent", "handle")}
        if st.get("cast"):
            timing["lips"] = await asyncio.to_thread(_lips, voice_wav, timing)
        _job(job_id)["duration"] = timing["end"]

        bins = sheets = None
        if art is not None:
            _stage(job_id, "pictures", 2, f"Making the pictures ({pics_state['n']}/{pics_state['of'] or '…'})")
            got = await art
            timing["images"] = studio_collage.public(got["pictures"])
            bins = studio_collage.binaries(got["pictures"])
            sheets = await asyncio.to_thread(studio_collage.sheet, got["pictures"])
            _job(job_id)["sources"] = studio_collage.sources(got["pictures"])
            _job(job_id)["pictures"] = len(got["pictures"])

        plate = proxy = None
        stills = []
        if st.get("media"):
            _stage(job_id, "voice", 2, "Finding the footage")
            ask = lambda system, content, mt, role, tool: _claude(job_id, system, content, mt, role, tool=tool)
            fit = "tele" if st["media"] == "clip" else "band"
            shots = await studio_footage.shots(job_id, ask, s["lines"], timing, media["uploads"], tmp, fit=fit)
            timing["shots"] = studio_footage.public(shots)
            _job(job_id)["sources"] = studio_footage.sources(shots)
            plate = await asyncio.to_thread(studio_plate.build, shots, timing["end"], os.path.join(tmp, "plate.mp4"), tmp)
            proxy = await asyncio.to_thread(studio_plate.proxy, plate, os.path.join(tmp, "proxy.mp4"))
            if fit == "tele":
                stills = await asyncio.to_thread(studio_footage.freeze_stills, plate, timing["shots"], tmp, studio_plate.TELE[0], studio_plate.TELE[1])

        _stage(job_id, "scene", 3, "Animating")
        code, spec, foley = await _film(job_id, st, s, timing, stills, bins, sheets)

        _stage(job_id, "check", 4, "Checking the key frames")
        try:
            code2, extra = await _review(job_id, st, s, timing, code, proxy, bins)
            if extra is not None:
                code, (spec, foley) = code2, extra
        except BillingError:
            raise
        except Exception as e:
            print(f"[studio] review skipped: {e!r}")
        _job(job_id)["scene_code"] = code

        _stage(job_id, "render", 5, "Rendering")
        video = await _render(job_id, st, code, timing, tmp, plate, bins)

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
