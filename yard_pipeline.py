"""
3D Build pipeline: "How a Hole in Your Yard Becomes a ___" vertical explainers, no GPU anywhere.

  1. Writer (Claude)        topic -> fact-checked narration script (If you... But... So you... This is a...)
  2. Narrator (Kokoro)      am_michael on our own CPU, word timings from Whisper
  3. Scene builder (Claude) one build(YK, T) function: the yard kit (render_service/yard/yardkit.js, three.js)
  4. Checks                 load + probe every second (errors -> find/replace fixes), then a look at stills
  5. Render                 the render service draws it with SwiftShader in parallel chunks, joined and upscaled
  6. Sound                  dig / pour / thud cues from the scene + a soft music bed, ducked under the voice
"""

import asyncio
import base64
import json
import math
import os
import re
import subprocess
import tempfile
import traceback

import anthropic
import numpy as np

import motion_sound
import yard_voice
from jobs import job_store
from motion_pipeline import BillingError, THINK_ROOM, _anthropic, _apply_edits, _record_usage, _render_call
from storybook_pipeline import upload_bytes_to_r2
from tts import get_word_timestamps
from yard_prompts import EDIT_TOOL, FIX_NOTE, REVIEW_SYSTEM, SCENE_SYSTEM, SCRIPT_SYSTEM, SCRIPT_TOOL

MODEL = os.environ.get("YARD_MODEL", os.environ.get("PROMPT_MODEL", "claude-sonnet-5-5"))
EFFORT = os.environ.get("YARD_EFFORT", "medium")
# The 3D is drawn at this size (CPU rendering) and upscaled to 1080x1920 at the end.
DRAW_H = int(os.environ.get("YARD_DRAW_HEIGHT", "1280"))
DRAW_W = DRAW_H * 9 // 16
OUT_W, OUT_H = 1080, 1920
FPS = 30
CHUNKS = int(os.environ.get("YARD_RENDER_CHUNKS", "4"))
VOICE_SPEED = float(os.environ.get("YARD_VOICE_SPEED", "1.15"))
MAX_FIXES = 3
TEXTURES = ["sky", "excavated_soil_wall", "leafy_grass", "plastered_wall", "clay_roof_tiles",
            "square_concrete_pavers", "dark_wooden_planks", "dirt", "brown_mud"]
RESERVED_IDS = {"end", "word", "list"}
STEPS = 7

_voice_sem = asyncio.Semaphore(1)       # Kokoro uses the whole CPU; one narration at a time


# ─────────────────────────── job helpers ───────────────────────────

def _job(job_id: str) -> dict:
    return job_store[job_id]


def _stage(job_id: str, stage: str, step: int, message: str):
    j = _job(job_id)
    j.update(status="processing", stage=stage, step=step, total_steps=STEPS, message=message)
    print(f"[yard {job_id[:8]}] {step}/{STEPS} {message}")


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


# ─────────────────────────── 1. script ───────────────────────────

def _clean_lines(lines: list) -> list[dict]:
    out, seen = [], set()
    for i, ln in enumerate(lines or []):
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        lid = re.sub(r"[^a-z0-9_]", "_", str(ln.get("id") or f"l{i}").lower()).strip("_") or f"l{i}"
        if lid[0].isdigit() or lid in RESERVED_IDS:
            lid = "l_" + lid
        while lid in seen:
            lid += "_b"
        seen.add(lid)
        pause = ln.get("pause") or 0
        out.append({"id": lid, "text": text, "pause": max(0.0, min(0.4, float(pause)))})
    return out


async def _write_script(job_id: str, topic: str | None) -> dict:
    ask = (f"Topic from the user: {topic.strip()}" if topic and topic.strip()
           else "No topic given: pick the best thing yourself.")
    s = await _claude(job_id, SCRIPT_SYSTEM, ask + "\n\nWrite the script, fact-check every claim, then submit it.",
                      3000, "writer", tool=SCRIPT_TOOL)
    lines = _clean_lines(s.get("lines"))
    if len(lines) < 6:
        raise ValueError("the script came back too short")
    return {"title": str(s.get("title") or "How a Hole in Your Yard Becomes Something").strip(),
            "thing": str(s.get("thing") or "").strip(), "lines": lines,
            "visual_notes": str(s.get("visual_notes") or "").strip()}


# ─────────────────────────── 2. voice + timing ───────────────────────────

def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def _assign_words(spans: list[dict], words: list[dict]) -> list[dict]:
    """Whisper words -> the line they were spoken in (by time); lines Whisper missed get spread words."""
    out = []
    for sp in spans:
        got = [{"w": w["word"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)}
               for w in words
               if sp["start"] - 0.2 <= (float(w["start"]) + float(w["end"])) / 2 <= sp["end"] + 0.2 and w["word"].strip()]
        if len(got) < max(1, len(sp["text"].split()) // 2):
            toks = sp["text"].split()
            total = sum(len(t) + 1 for t in toks)
            t, got = sp["start"], []
            for tok in toks:
                d = (sp["end"] - sp["start"]) * (len(tok) + 1) / total
                got.append({"w": tok, "start": round(t, 3), "end": round(t + d, 3)})
                t += d
        out.append({**sp, "words": got})
    return out


def _captions(lines: list[dict]) -> list[list]:
    words = [w for ln in lines for w in ln["words"]]
    caps = []
    for i, w in enumerate(words):
        word = re.sub(r"[^\w'%-]", "", w["w"])
        if not word:
            continue
        word = word[:1].upper() + word[1:]
        nxt = words[i + 1]["start"] if i + 1 < len(words) else w["end"] + 0.4
        caps.append([w["start"], word, round(min(nxt, w["end"] + 0.35), 3)])
    return caps


def _wav_to_mp3(wav: str, mp3: str):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "96k", mp3], check=True)


async def _voice(job_id: str, lines: list[dict], tmp: str) -> tuple[str, dict]:
    import soundfile as sf
    speed = VOICE_SPEED
    async with _voice_sem:
        audio, spans = await yard_voice.narrate(lines, speed=speed)
        total = len(audio) / yard_voice.SR
        if total > 76:                                     # too long: speak a little faster, never past 1.3
            speed = min(1.3, speed * total / 72)
            audio, spans = await yard_voice.narrate(lines, speed=speed)
    wav, mp3 = os.path.join(tmp, "voice.wav"), os.path.join(tmp, "voice.mp3")
    sf.write(wav, audio, yard_voice.SR)
    _wav_to_mp3(wav, mp3)
    try:
        words = await get_word_timestamps(open(mp3, "rb").read())
    except Exception as e:
        print(f"[yard] whisper failed, spreading words: {e!r}")
        words = []
    timed = _assign_words(spans, words)
    end = round(spans[-1]["end"] + 1.0, 3)
    timing = {"end": end, "lines": [{"id": l["id"], "text": l["text"], "start": l["start"], "end": l["end"], "words": l["words"]}
                                    for l in timed]}
    _job(job_id)["voice"] = {"seconds": round(len(audio) / yard_voice.SR, 2), "speed": round(speed, 3)}
    return wav, timing


# ─────────────────────────── 3. composition ───────────────────────────

def compose(code: str, timing: dict, captions: list, w: int, h: int, start: float = 0.0,
            duration: float | None = None, probe: bool = False) -> str:
    """The HyperFrames page for a scene: the canvas, captions, kit, textures and the timeline.
    start/duration render one chunk of the video (the scene still sees absolute time)."""
    dur = round(duration if duration is not None else timing["end"], 4)
    imgs = "".join(f'<img id="tx_{t}" src="yard/tex/{t}.jpg">' for t in TEXTURES)
    cap_px = round(h * 0.048)
    probe_js = ""
    if probe:
        times = [round(x * 0.5, 2) for x in range(int(timing["end"] * 2) + 1)]
        probe_js = f"for (const m of YK.probe({json.dumps(times)})) window.__kCues.push({{ t: 0, kind: 'error', msg: m }});"
    return f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="lib/kit.css">
<style>
@font-face{{font-family:Nunito;src:url(yard/Nunito.ttf);font-weight:200 1000}}
#root{{width:{w}px;height:{h}px;background:#000;position:relative;overflow:hidden}}
#c{{position:absolute;inset:0;width:{w}px;height:{h}px}}
#cap{{position:absolute;left:50%;top:52%;transform:translate(-50%,-50%);font:900 {cap_px}px/1 Nunito,sans-serif;color:#fff;
 white-space:nowrap;-webkit-text-stroke:{max(4, round(cap_px * 0.16))}px #12121a;paint-order:stroke fill;
 text-shadow:{round(cap_px * 0.05)}px {round(cap_px * 0.09)}px 0 rgba(0,0,0,.45);opacity:0}}
#tx{{position:absolute;left:-9999px;top:0;width:4px;height:4px;overflow:hidden}}
</style></head><body>
<div id="root" data-composition-id="yard" data-no-timeline data-start="0" data-duration="{dur}" data-width="{w}" data-height="{h}">
<canvas id="c" width="{w}" height="{h}"></canvas><div id="cap"></div>
<div id="tx">{imgs}</div></div>
<script src="lib/anime.umd.min.js"></script><script src="lib/kit.js"></script>
<script src="yard/three.min.js"></script><script src="yard/yardkit.js"></script>
<script>const TIMING = {json.dumps(timing)}; const CAPTIONS = {json.dumps(captions)};</script>
<script>
{code}
</script>
<script>
(function () {{
  const tl = K.timeline(), OFFSET = {round(start * 1000, 3)};
  window.__kCues = window.__kCues || [];
  YK.init({{ canvas: document.getElementById('c'), width: {w}, height: {h}, caption: document.getElementById('cap') }});
  const T = YK.timing(TIMING);
  let shots = [];
  try {{
    if (typeof build !== 'function') throw new Error('build(YK, T) is not defined');
    shots = build(YK, T);
    if (!Array.isArray(shots) || !shots.flat().length) throw new Error('build() must return a non-empty list of shots (YK.view / YK.cuts)');
    shots = shots.flat();
  }} catch (e) {{ window.__kCues.push({{ t: 0, kind: 'error', msg: String((e && e.stack) || e).slice(0, 900) }}); shots = []; }}
  YK.finish(); YK.shots(shots); YK.captions(CAPTIONS);
  {probe_js}
  tl._kHooks.push(ms => YK.renderAt(ms + OFFSET));
  tl.add({{ k: 0 }}, {{ k: 1, duration: {round(dur * 1000)}, ease: 'linear' }}, 0);
  YK.renderAt(OFFSET);
}})();
</script></body></html>"""


_FORBIDDEN = [
    (r"Math\.random\s*\(", "Math.random(): use YK.rng(seed)"),
    (r"Date\.now|new Date\(|performance\.now", "reading the clock: everything must depend on t only"),
    (r"requestAnimationFrame|set(Timeout|Interval)\s*\(", "timers / requestAnimationFrame: the renderer owns the clock"),
    (r"\bfetch\s*\(|XMLHttpRequest|import\s*\(", "network or imports: build everything from the kit"),
    (r"\bdocument\.|\bwindow\.", "the DOM: only use YK and T"),
]


def _extract_code(text: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", text, re.S)
    code = (m.group(1) if m else text).strip()
    if "function build" not in code:
        raise ValueError("the scene builder did not return a build() function")
    return code.replace("</script", "<\\/script")


def _static_problems(code: str) -> list[str]:
    return [why for pat, why in _FORBIDDEN if re.search(pat, code)]


async def _load(code: str, timing: dict, captions: list) -> tuple[list[str], list[dict]]:
    """Load the page once (no render): (errors, sound cues)."""
    html = compose(code, timing, captions, 360, 640, probe=True)
    r = await _render_call("/cues", {"files": {"index.html": html}}, timeout=180)
    if r.status_code != 200:
        return [f"page failed to load: {r.text[:600]}"], []
    d = r.json()
    cues = d.get("cues", [])
    errors = [c.get("msg", "") for c in cues if c.get("kind") == "error"] + list(d.get("errors") or [])
    return errors, [c for c in cues if c.get("kind") != "error"]


def _script_block(script: dict, timing: dict) -> str:
    rows = "\n".join(f'{l["id"]:>10}  {l["start"]:6.2f}-{l["end"]:6.2f}  {l["text"]}' for l in timing["lines"])
    return (f'TITLE: {script["title"]}\nTHING: {script["thing"]}\n\nLINES (id, start-end seconds, text):\n{rows}\n\n'
            f'T.end = {timing["end"]}\n\nVISUAL NOTES FROM THE WRITER:\n{script["visual_notes"] or "(none)"}')


async def _build_scene(job_id: str, script: dict, timing: dict, captions: list) -> tuple[str, list[dict]]:
    text = await _claude(job_id, SCENE_SYSTEM,
                         _script_block(script, timing) + "\n\nWrite build(YK, T) for this video.", 16000, "scene")
    code = _extract_code(text)
    for attempt in range(MAX_FIXES + 1):
        problems = _static_problems(code)
        errors, cues = ([], [])
        if not problems:
            errors, cues = await _load(code, timing, captions)
        if not problems and not errors:
            return code, cues
        if attempt == MAX_FIXES:
            break
        _job(job_id)["message"] = f"Fixing the scene ({attempt + 1})"
        issue = "\n".join(problems + errors)[:3000]
        res = await _claude(job_id, SCENE_SYSTEM,
                            f"{_script_block(script, timing)}\n\nYOUR CODE:\n```js\n{code}\n```\n\nERRORS:\n{issue}\n\n{FIX_NOTE}",
                            3000, "fixer", tool=EDIT_TOOL)
        code, n = _apply_edits(code, res.get("edits") or [])
        if not n:
            break
    raise ValueError("the 3D scene kept failing to load")


async def _review(job_id: str, script: dict, timing: dict, captions: list, code: str) -> tuple[str, list[dict] | None]:
    """One look at stills: fix what is visibly wrong. Keeps the old code when the fix breaks anything."""
    lines = timing["lines"]
    picks = sorted({min(len(lines) - 1, round(i * (len(lines) - 1) / 5)) for i in range(6)})
    at = [round((lines[i]["start"] + lines[i]["end"]) / 2, 2) for i in picks]
    html = compose(code, timing, captions, 540, 960)
    r = await _render_call("/snapshot", {"files": {"index.html": html}, "at": at}, timeout=600)
    if r.status_code != 200:
        print(f"[yard] review skipped, snapshot failed: {r.text[:300]}")
        return code, None
    content = []
    for f, i in zip(r.json().get("frames", []), picks):
        content.append({"type": "text", "text": f'{f["at"]:.1f} s, line "{lines[i]["id"]}": {lines[i]["text"]}'})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": f["png"]}})
    content.append({"type": "text", "text": f"{_script_block(script, timing)}\n\nTHE CODE:\n```js\n{code}\n```"})
    res = await _claude(job_id, REVIEW_SYSTEM, content, 3000, "review", tool=EDIT_TOOL)
    _job(job_id)["review"] = str(res.get("problems") or "")[:500]
    new, n = _apply_edits(code, res.get("edits") or [])
    if not n:
        return code, None
    errors, cues = await _load(new, timing, captions) if not _static_problems(new) else (["static"], [])
    return (new, cues) if not errors else (code, None)


# ─────────────────────────── 5. render ───────────────────────────

async def _render(job_id: str, code: str, timing: dict, captions: list, tmp: str) -> str:
    """Draw the video in parallel chunks on the render service, join them and upscale to 1080x1920."""
    total = int(round(timing["end"] * FPS))
    per = math.ceil(total / CHUNKS / FPS) * FPS       # whole seconds per chunk, so the joins land on frames
    spans = [(k * per, min(per, total - k * per)) for k in range(CHUNKS) if total - k * per > 0]
    done = {"n": 0}

    async def one(k: int, f0: int, nf: int) -> str:
        html = compose(code, timing, captions, DRAW_W, DRAW_H, start=f0 / FPS, duration=nf / FPS)
        for attempt in range(2):
            r = await _render_call("/render", {"files": {"index.html": html}, "quality": "standard", "fps": FPS}, timeout=1800)
            if r.status_code == 200 and r.content:
                path = os.path.join(tmp, f"chunk{k}.mp4")
                open(path, "wb").write(r.content)
                done["n"] += 1
                _job(job_id)["message"] = f"Rendering the 3D ({done['n']}/{len(spans)})"
                return path
            print(f"[yard] chunk {k} attempt {attempt + 1} failed: {r.status_code} {r.text[:400]}")
        raise RuntimeError(f"render failed on chunk {k + 1}")

    paths = await asyncio.gather(*[one(k, f0, nf) for k, (f0, nf) in enumerate(spans)])
    lst = os.path.join(tmp, "chunks.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in paths))
    out = os.path.join(tmp, "video.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-vf", f"scale={OUT_W}:{OUT_H}:flags=lanczos,format=yuv420p", "-r", str(FPS),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("joining the chunks failed: " + r.stderr[-600:])
    return out


# ─────────────────────────── 6. sound ───────────────────────────

async def _sound(video: str, voice_wav: str, cues: list[dict], total: float, tmp: str) -> str:
    out = os.path.join(tmp, "final.mp4")
    events = motion_sound.plan_events([c for c in cues if c.get("kind") in motion_sound.SFX_LIBRARY and c.get("kind") != "yard_bed"])
    kinds = {e["kind"] for e in events}
    try:
        lib = await motion_sound.fetch_library(kinds | {"yard_bed"}, tmp)
    except Exception as e:
        print(f"[yard] sound library unavailable: {e!r}")
        lib = {}
    music = lib.pop("yard_bed", None)
    ok = motion_sound.mix(video, out, total, events, lib, [{"path": voice_wav, "start": 0.0, "tempo": 1.0}], music)
    if ok:
        return out
    # last resort: voice only
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", voice_wav, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("audio mix failed: " + r.stderr[-400:])
    return out


# ─────────────────────────── the job ───────────────────────────

async def run_yard_pipeline(job_id: str, p: dict):
    tmp = tempfile.mkdtemp(prefix="yard-")
    try:
        _stage(job_id, "script", 1, "Writing the script")
        script = await _write_script(job_id, p.get("topic"))
        _job(job_id).update(title=script["title"], thing=script["thing"], script=script["lines"])

        _stage(job_id, "voice", 2, "Recording the narrator")
        voice_wav, timing = await _voice(job_id, script["lines"], tmp)
        captions = _captions(timing["lines"])
        _job(job_id)["duration"] = timing["end"]

        _stage(job_id, "scene", 3, "Building the 3D yard")
        code, cues = await _build_scene(job_id, script, timing, captions)

        _stage(job_id, "check", 4, "Checking the shots")
        try:
            code2, cues2 = await _review(job_id, script, timing, captions, code)
            if cues2 is not None:
                code, cues = code2, cues2
        except BillingError:
            raise
        except Exception as e:
            print(f"[yard] review skipped: {e!r}")
        _job(job_id)["scene_code"] = code

        _stage(job_id, "render", 5, "Rendering the 3D")
        video = await _render(job_id, code, timing, captions, tmp)

        _stage(job_id, "sound", 6, "Mixing the sound")
        final = await _sound(video, voice_wav, cues, timing["end"], tmp)

        _stage(job_id, "upload", 7, "Uploading")
        url = await asyncio.to_thread(upload_bytes_to_r2, open(final, "rb").read(), "yard", "mp4", "video/mp4")
        thumb = os.path.join(tmp, "thumb.jpg")
        thumb_url = None
        if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.8", "-i", final, "-frames:v", "1", "-q:v", "3", thumb]).returncode == 0:
            thumb_url = await asyncio.to_thread(upload_bytes_to_r2, open(thumb, "rb").read(), "yard", "jpg", "image/jpeg")
        _job(job_id).update(status="completed", stage="done", step=STEPS, message="Done",
                            final_video_url=url, thumbnail_url=thumb_url)
    except Exception as e:
        traceback.print_exc()
        j = _job(job_id)
        j.update(status="failed", stage="failed", error=("Anthropic API credit is too low" if isinstance(e, BillingError) else str(e))[:500],
                 traceback=traceback.format_exc()[-3000:])
    finally:
        subprocess.run(["rm", "-rf", tmp])
