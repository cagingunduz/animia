"""
Block Horror pipeline: 40-50 s night-town horror Shorts with blocky characters, no GPU anywhere.

  pitches  (sync)  Claude pitches 3 rules + twists
  script   (sync)  Claude writes ~22 narration lines + the monster's line; the user edits and approves them
  job              Kokoro narration (am_onyx, pauses by role) + the monster's line pitched down with a room echo
                   -> Whisper word timings -> Claude writes build(BK, W) on the block kit -> load check, fixes,
                   a look at stills -> chunked CPU render, captions burned in (Montserrat ExtraBold) -> the score:
                   horror bed that steps up on "Run!", a drone, hits on words, dead silence in the blackout
"""

import asyncio
import json
import math
import os
import re
import subprocess
import tempfile
import traceback

import numpy as np

import motion_sound
import yard_voice
from block_prompts import PITCH_SYSTEM, PITCH_TOOL, REVIEW_SYSTEM, SCENE_SYSTEM, SCRIPT_SYSTEM, SCRIPT_TOOL
from jobs import job_store
from motion_pipeline import BillingError, _apply_edits, _render_call
from storybook_pipeline import upload_bytes_to_r2
from tts import get_word_timestamps
from yard_pipeline import (EDIT_TOOL, FIX_NOTE, MAX_FIXES, OUT_H, OUT_W, _ass_time, _assign_words, _claude,
                           _extract_code, _load, _render, _static_problems, _wav_to_mp3)

VOICE = os.environ.get("BLOCK_VOICE", "am_onyx")
SPEED = float(os.environ.get("BLOCK_VOICE_SPEED", "1.2"))
SR = 48000
STEPS = 7
RESERVED = {"end", "line", "lines", "t"}


def _job(job_id: str) -> dict:
    return job_store[job_id]


def _stage(job_id: str, stage: str, step: int, message: str):
    _job(job_id).update(status="processing", stage=stage, step=step, total_steps=STEPS, message=message)
    print(f"[block {job_id[:8]}] {step}/{STEPS} {message}")


def _scratch() -> str:
    jid = "b-" + os.urandom(6).hex()
    job_store[jid] = {"kind": "scratch", "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}}
    return jid


def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


# ─────────────────────────── sync: pitches and the script ───────────────────────────

async def pitches() -> list[dict]:
    jid = _scratch()
    try:
        r = await _claude(jid, PITCH_SYSTEM, "Pitch 3 stories.", 1500, "pitch", tool=PITCH_TOOL)
        return [{"title": _clean(p.get("title"))[:60], "rule": _clean(p.get("rule"))[:200], "twist": _clean(p.get("twist"))[:240]}
                for p in (r.get("pitches") or [])[:3]]
    finally:
        job_store.pop(jid, None)


def clean_script(s: dict) -> dict:
    lines, seen = [], set()
    for i, ln in enumerate(s.get("lines") or []):
        text = _clean(ln.get("text"))
        if not text:
            continue
        lid = re.sub(r"[^a-z0-9_]", "_", str(ln.get("id") or f"l{i}").lower()).strip("_") or f"l{i}"
        if lid[0].isdigit() or lid in RESERVED or lid == "monster":
            lid = "l_" + lid
        while lid in seen:
            lid += "_b"
        seen.add(lid)
        role = ln.get("role") if ln.get("role") in ("narration", "run", "blackout", "twist") else "narration"
        lines.append({"id": lid, "text": text[:200], "role": role})
    return {"title": _clean(s.get("title"))[:80] or "Block Horror", "hero": _clean(s.get("hero"))[:40],
            "loved_one": _clean(s.get("loved_one"))[:60], "lines": lines[:30],
            "monster_line": _clean(s.get("monster_line"))[:40] or "Welcome home.",
            "keywords": [_clean(k).lower() for k in (s.get("keywords") or []) if _clean(k)][:12]}


async def write_script(story: str, length: int = 45) -> dict:
    jid = _scratch()
    try:
        ask = f"Story (rule and twist): {story.strip()}\nTarget length: {length} seconds.\n\nWrite the script and submit it."
        s = clean_script(await _claude(jid, SCRIPT_SYSTEM, ask, 3000, "writer", tool=SCRIPT_TOOL))
        if len(s["lines"]) < 10:
            raise ValueError("the script came back too short")
        return {"script": s, "cost_usd": job_store[jid]["usage"]["cost_usd"]}
    finally:
        job_store.pop(jid, None)


# ─────────────────────────── voice ───────────────────────────

def _decode(path: str) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def _write_wav(path: str, a: np.ndarray, sr: int = SR):
    import soundfile as sf
    sf.write(path, a.astype(np.float32), sr)


async def _voice(job_id: str, script: dict, tmp: str) -> tuple[str, dict]:
    import soundfile as sf
    lines = [dict(l) for l in script["lines"]]
    # pauses: 0.06 s between lines plus 0.10 (0.30 before the twist, a long held breath after the blackout line)
    for i, l in enumerate(lines):
        nxt = lines[i + 1]["role"] if i + 1 < len(lines) else None
        l["pause"] = 2.4 if l["role"] == "blackout" else 0.30 if nxt == "twist" else 0.10
    audio, spans = await yard_voice.narrate(lines, speed=SPEED, gap=0.06, voice=VOICE, max_pause=0.11)
    total = len(audio) / yard_voice.SR
    if total > 50:                                        # too long: speak faster, never past 1.35
        audio, spans = await yard_voice.narrate(lines, speed=min(1.35, SPEED * total / 47), gap=0.06, voice=VOICE, max_pause=0.11)
    nar = os.path.join(tmp, "narration.wav")
    sf.write(nar, audio, yard_voice.SR)
    # the monster: 5 semitones down, slowed to 0.92x, a short room echo, lowpassed, 0.22 s after the narration
    m = await yard_voice.say(script["monster_line"], voice=VOICE, speed=1.0)
    mraw, mout = os.path.join(tmp, "mon_raw.wav"), os.path.join(tmp, "mon.wav")
    sf.write(mraw, m, yard_voice.SR)
    k = 2 ** (-5 / 12)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mraw, "-af",
                    f"asetrate={yard_voice.SR}*{k:.5f},aresample={yard_voice.SR},atempo={0.92 / k:.4f},"
                    "aecho=0.8:0.55:55|110:0.35|0.22,lowpass=f=6500,volume=1.5", mout], check=True)
    mon = _decode(mout)
    voice = _decode(nar)
    m_start = len(voice) / SR + 0.22
    full = np.zeros(int((m_start + len(mon) / SR + 1.6) * SR), np.float32)
    full[:len(voice)] += voice
    full[int(m_start * SR): int(m_start * SR) + len(mon)] += mon
    wav, mp3 = os.path.join(tmp, "voice.wav"), os.path.join(tmp, "voice.mp3")
    _write_wav(wav, full)
    _wav_to_mp3(wav, mp3)
    spans.append({"id": "monster", "text": script["monster_line"], "start": round(m_start, 3), "end": round(m_start + len(mon) / SR, 3)})
    try:
        words = await get_word_timestamps(open(mp3, "rb").read())
    except Exception as e:
        print(f"[block] whisper failed, spreading words: {e!r}")
        words = []
    timed = _assign_words(spans, words)
    roles = {l["id"]: l["role"] for l in lines}
    timing = {"end": round(len(full) / SR, 3),
              "lines": [{"id": t["id"], "text": t["text"], "role": roles.get(t["id"], "monster"), "start": t["start"], "end": t["end"],
                         "words": t["words"]} for t in timed]}
    _job(job_id)["voice"] = {"seconds": round(len(full) / SR, 2)}
    return wav, timing


# ─────────────────────────── captions ───────────────────────────

def _captions(timing: dict, keywords: list[str]) -> list[list]:
    """[start, Word, end, isKey]: Title Case, no punctuation, 0.03 s early, until the next word; the last held 0.25 s"""
    keys = {re.sub(r"[^a-z0-9']", "", k) for kw in keywords for k in kw.split()}
    words = [w for ln in timing["lines"] for w in ln["words"]]
    out = []
    for i, w in enumerate(words):
        word = re.sub(r"[^\w'-]", "", w["w"])
        if not word:
            continue
        low = word.lower()
        key = low in keys or low.rstrip("s") in keys
        nxt = words[i + 1]["start"] - 0.03 if i + 1 < len(words) else w["end"] + 0.25
        out.append([round(max(0, w["start"] - 0.03), 3), word[:1].upper() + word[1:], round(nxt, 3), key])
    return out


def _captions_ass(captions: list, path: str):
    """Montserrat ExtraBold 104 px, white with a 13 px black outline and a black shadow 4 px right, 7 px down at
    60 %; key nouns red #EC1C24; centred at 64 % of the height."""
    y = round(OUT_H * 0.64)
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {OUT_W}\nPlayResY: {OUT_H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,Montserrat ExtraBold,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H66000000,0,0,0,0,100,100,0,0,1,13,0,5,40,40,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rows = []
    for start, word, end, key in captions:
        text = word.replace("{", "").replace("}", "").replace("\\", "")
        colour = "\\c&H241CEC&" if key else ""
        rows.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{{\\an5\\pos({OUT_W // 2},{y})\\xshad4\\yshad7{colour}}}{text}")
    open(path, "w", encoding="utf-8").write(head + "\n".join(rows) + "\n")


# ─────────────────────────── composition ───────────────────────────

def compose(code: str, timing: dict, captions: list, w: int, h: int, start: float = 0.0,
            duration: float | None = None, probe: bool = False) -> str:
    dur = round(duration if duration is not None else timing["end"], 4)
    cap_px = round(h * 104 / 1920)
    probe_js = ""
    if probe:
        times = [round(x * 0.5, 2) for x in range(int(timing["end"] * 2) + 1)]
        probe_js = f"for (const m of BK.probe({json.dumps(times)})) window.__kCues.push({{ t: 0, kind: 'error', msg: m }});"
    return f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="lib/kit.css">
<style>
@font-face{{font-family:Montserrat;src:url(block/Montserrat.ttf);font-weight:100 900}}
#root{{width:{w}px;height:{h}px;background:#000;position:relative;overflow:hidden}}
#c{{position:absolute;inset:0;width:{w}px;height:{h}px}}
#cap{{position:absolute;left:50%;top:64%;transform:translate(-50%,-50%);font:800 {cap_px}px/1 Montserrat,sans-serif;color:#fff;
 white-space:nowrap;-webkit-text-stroke:{round(cap_px * 0.25)}px #000;paint-order:stroke fill;text-shadow:{round(cap_px * 0.04)}px {round(cap_px * 0.07)}px 0 rgba(0,0,0,.6);opacity:0}}
</style></head><body>
<div id="root" data-composition-id="block" data-no-timeline data-start="0" data-duration="{dur}" data-width="{w}" data-height="{h}">
<canvas id="c" width="{w}" height="{h}"></canvas><div id="cap"></div></div>
<script src="lib/anime.umd.min.js"></script><script src="lib/kit.js"></script>
<script src="block/three.min.js"></script><script src="block/blockkit.js"></script>
<script>const TIMING = {json.dumps(timing)}; const CAPTIONS = {json.dumps(captions)};</script>
<script>
{code}
</script>
<script>
(function () {{
  const tl = K.timeline(), OFFSET = {round(start * 1000, 3)};
  window.__kCues = window.__kCues || [];
  BK.init({{ canvas: document.getElementById('c'), width: {w}, height: {h}, caption: document.getElementById('cap') }});
  const W = BK.timing(TIMING);
  let shots = [];
  try {{
    if (typeof build !== 'function') throw new Error('build(BK, W) is not defined');
    shots = build(BK, W);
    if (!Array.isArray(shots) || !shots.flat().length) throw new Error('build() must return a non-empty list of shots (BK.shot)');
    shots = shots.flat();
  }} catch (e) {{ window.__kCues.push({{ t: 0, kind: 'error', msg: String((e && e.stack) || e).slice(0, 900) }}); shots = []; }}
  BK.shots(shots); BK.captions(CAPTIONS);
  {probe_js}
  tl._kHooks.push(ms => BK.renderAt(ms + OFFSET));
  tl.add({{ k: 0 }}, {{ k: 1, duration: {round(dur * 1000)}, ease: 'linear' }}, 0);
  BK.renderAt(OFFSET);
}})();
</script></body></html>"""


def _script_block(script: dict, timing: dict) -> str:
    rows = "\n".join(f'{l["id"]:>10} [{l["role"]}] {l["start"]:6.2f}-{l["end"]:6.2f}  {l["text"]}' for l in timing["lines"])
    return (f'TITLE: {script["title"]}\nHERO: {script["hero"]}   GOES BACK FOR: {script.get("loved_one") or "-"}\n\n'
            f'LINES (id, role, start-end seconds, text) — the last one is the monster\'s:\n{rows}\n\nW.end = {timing["end"]}')


def _fix_ctx(script, timing, code, issue):
    return f"{_script_block(script, timing)}\n\nYOUR CODE:\n```js\n{code}\n```\n\nERRORS:\n{issue}\n\n{FIX_NOTE}"


async def _build_scene(job_id: str, script: dict, timing: dict, captions: list) -> tuple[str, list[dict]]:
    text = await _claude(job_id, SCENE_SYSTEM, _script_block(script, timing) + "\n\nWrite build(BK, W) for this video.", 20000, "scene")
    code = _extract_code(text)
    for attempt in range(MAX_FIXES + 1):
        problems = [p.replace("YK", "BK") for p in _static_problems(code)]
        errors, cues = ([], [])
        if not problems:
            errors, cues = await _load(code, timing, captions, compose)
        if not problems and not errors:
            return code, cues
        if attempt == MAX_FIXES:
            break
        _job(job_id)["message"] = f"Fixing the scene ({attempt + 1})"
        res = await _claude(job_id, SCENE_SYSTEM, _fix_ctx(script, timing, code, "\n".join(problems + errors)[:3000]), 3000, "fixer", tool=EDIT_TOOL)
        code, n = _apply_edits(code, res.get("edits") or [])
        if not n:
            break
    raise ValueError("the scene kept failing to load")


async def _review(job_id: str, script: dict, timing: dict, captions: list, code: str):
    lines = [l for l in timing["lines"]]
    picks = sorted({min(len(lines) - 1, round(i * (len(lines) - 1) / 11)) for i in range(12)})
    at = [round((lines[i]["start"] + lines[i]["end"]) / 2, 2) for i in picks]
    r = await _render_call("/snapshot", {"files": {"index.html": compose(code, timing, captions, 540, 960)}, "at": at}, timeout=600)
    if r.status_code != 200:
        return code, None
    content = []
    for f, i in zip(r.json().get("frames", []), picks):
        content.append({"type": "text", "text": f'{f["at"]:.1f} s, line "{lines[i]["id"]}": {lines[i]["text"]}'})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": f["png"]}})
    content.append({"type": "text", "text": f"{_script_block(script, timing)}\n\nTHE CODE:\n```js\n{code}\n```"})
    res = await _claude(job_id, REVIEW_SYSTEM, content, 5000, "review", tool=EDIT_TOOL)
    _job(job_id)["review"] = str(res.get("problems") or "")[:500]
    new, n = _apply_edits(code, res.get("edits") or [])
    if not n or _static_problems(new):
        return code, None
    errors, cues = await _load(new, timing, captions, compose)
    return (new, cues) if not errors else (code, None)


# ─────────────────────────── the score ───────────────────────────

SFX_GAIN = {"impact": -15, "subdrop": -15.5, "shutter": -19, "doorslam": -19, "knock": -21, "click": -21, "riser": -21,
            "boom": -15, "bigboom": -11, "braam": -15, "creak": -18, "trailer": -11, "sting": -19}


def _db(x: float) -> float:
    return 10 ** (x / 20)


def _fit(a: np.ndarray, n: int) -> np.ndarray:
    if len(a) == 0:
        return np.zeros(n, np.float32)
    reps = int(math.ceil(n / len(a)))
    return np.tile(a, reps)[:n]


def _rms_to(a: np.ndarray, target_db: float) -> np.ndarray:
    rms = math.sqrt(float(np.mean(a ** 2))) if len(a) else 0
    return a * (_db(target_db) / rms) if rms > 1e-6 else a


async def _score(video: str, voice_wav: str, timing: dict, cues: list[dict], tmp: str) -> str:
    total = timing["end"]; n = int(total * SR)
    kinds = {c["kind"] for c in cues if c.get("kind") in SFX_GAIN} | {"horror_bed", "chase_bed", "drone"}
    try:
        lib = await motion_sound.fetch_library(kinds, tmp)
    except Exception as e:
        print(f"[block] sound library unavailable: {e!r}")
        lib = {}
    voice = _decode(voice_wav)[:n]
    voice = np.pad(voice, (0, n - len(voice)))
    v_rms = math.sqrt(float(np.mean(voice[np.abs(voice) > 0.01] ** 2))) if np.any(np.abs(voice) > 0.01) else 1
    voice *= _db(-15) / max(1e-6, v_rms)                                    # speech at about -15 dB
    t = np.arange(n) / SR
    lines = timing["lines"]
    run = next((l for l in lines if l["role"] == "run"), None)
    blk = next((l for l in lines if l["role"] == "blackout"), None)
    mon = next((l for l in lines if l["id"] == "monster"), lines[-1])
    t_run = run["start"] if run else total * 0.45
    t_dark = (blk["words"][-1]["start"] + 0.06) if blk and blk["words"] else (blk["end"] if blk else total * 0.7)
    after = [l for l in lines if l["start"] > t_dark + 0.1]
    t_back = after[0]["start"] if after else t_dark + 2.5
    # ducking: -4 dB under every word, fast attack, ~0.25 s release
    talk = np.zeros(n, np.float32)
    for l in lines:
        for w in l["words"]:
            talk[int(w["start"] * SR): int(w["end"] * SR)] = 1
    duck = np.zeros(n, np.float32); g = 0.0; rel = math.exp(-1 / (0.25 * SR))
    for i in range(0, n, 48):                                                 # 1 ms steps
        g = 1.0 if talk[i] else g * (rel ** 48)
        duck[i:i + 48] = g
    duck_gain = 1 - (1 - _db(-4)) * duck
    music = np.zeros(n, np.float32)
    bed = _rms_to(_decode(lib["horror_bed"]), -21) if "horror_bed" in lib else None
    chase = _rms_to(_decode(lib["chase_bed"]), -19) if "chase_bed" in lib else bed
    if bed is not None:
        fade = np.clip((t - t_run) / 0.08, 0, 1)
        music += _fit(bed, n) * (1 - fade) + _fit(chase, n) * fade
        # dead in the blackout; back quiet with the lights; gone 0.5 s before the monster speaks
        quiet = np.where(t >= t_back, _db(-6), 1.0)
        out = np.clip((mon["start"] - 0.5 - t) / 0.6, 0, 1)
        music *= np.where((t >= t_dark) & (t < t_back), 0, 1) * quiet * np.where(t >= t_back, out, 1) * duck_gain
    if "drone" in lib:
        dr = _rms_to(_decode(lib["drone"]), -34)
        music += _fit(dr, n) * np.where(t < t_dark, 1, 0) * np.clip(t / 1.5, 0, 1)
    fx = np.zeros(n, np.float32)
    for c in cues:
        k = c.get("kind")
        if k not in SFX_GAIN or k not in lib:
            continue
        a = _decode(lib[k])
        if not len(a):
            continue
        a = a / max(1e-6, float(np.max(np.abs(a)))) * _db(SFX_GAIN[k])         # peak at its level
        peak = int(np.argmax(np.abs(a)))                                        # the loudest point lands on the word
        s0 = int(c["t"] / 1000 * SR) - peak
        a0 = max(0, -s0); s0 = max(0, s0)
        seg = a[a0: a0 + n - s0]
        fx[s0: s0 + len(seg)] += seg
    mix = voice + music + fx
    pre = os.path.join(tmp, "premaster.wav")
    _write_wav(pre, mix)
    i, _tp = motion_sound.loudness(pre)
    gain = 0.0 if i is None else (-13 - i)
    mix = mix * _db(gain)
    mix = 0.75 * np.tanh(mix / 0.75)                                            # soft clip so AAC lands near -14 LUFS
    _write_wav(pre, mix)
    out = os.path.join(tmp, "final.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", pre, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "256k", "-ac", "2", "-shortest", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("audio mux failed: " + r.stderr[-300:])
    return out


# ─────────────────────────── the job ───────────────────────────

async def run_block_pipeline(job_id: str, p: dict):
    tmp = tempfile.mkdtemp(prefix="block-")
    try:
        script = clean_script(p["script"])
        if len(script["lines"]) < 10:
            raise ValueError("the script is too short")
        _job(job_id).update(title=script["title"])

        _stage(job_id, "voice", 1, "Recording the narrator")
        voice_wav, timing = await _voice(job_id, script, tmp)
        captions = _captions(timing, script["keywords"])
        _job(job_id)["duration"] = timing["end"]

        _stage(job_id, "scene", 2, "Building the town")
        code, cues = await _build_scene(job_id, script, timing, captions)

        _stage(job_id, "check", 3, "Checking the shots")
        try:
            code2, cues2 = await _review(job_id, script, timing, captions, code)
            if cues2 is not None:
                code, cues = code2, cues2
        except BillingError:
            raise
        except Exception as e:
            print(f"[block] review skipped: {e!r}")
        _job(job_id)["scene_code"] = code

        _stage(job_id, "render", 4, "Rendering")
        video = await _render(job_id, code, timing, captions, tmp, compose_fn=compose, ass_fn=_captions_ass)

        _stage(job_id, "sound", 5, "Scoring")
        final = await _score(video, voice_wav, timing, cues, tmp)

        _stage(job_id, "upload", 6, "Uploading")
        url = await asyncio.to_thread(upload_bytes_to_r2, open(final, "rb").read(), "block", "mp4", "video/mp4")
        thumb, thumb_url = os.path.join(tmp, "thumb.jpg"), None
        if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.8", "-i", final, "-frames:v", "1", "-q:v", "3", thumb]).returncode == 0:
            thumb_url = await asyncio.to_thread(upload_bytes_to_r2, open(thumb, "rb").read(), "block", "jpg", "image/jpeg")
        _job(job_id).update(status="completed", stage="done", step=STEPS, message="Done", final_video_url=url, thumbnail_url=thumb_url)
    except Exception as e:
        traceback.print_exc()
        _job(job_id).update(status="failed", stage="failed",
                            error=("Anthropic API credit is too low" if isinstance(e, BillingError) else str(e))[:500],
                            traceback=traceback.format_exc()[-3000:])
    finally:
        subprocess.run(["rm", "-rf", tmp])
