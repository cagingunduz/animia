"""Recipe reels: a 9:16 recipe from an empty glass (or pan) to the finished drink (or dish), every ingredient going in
with its measurement on screen.

  sync:  write_recipe -> the plan (steps, amounts, shapes, colours, narration); the user edits it
  job:   voice (Kokoro, one line per step) -> plan timed to the voice -> render (render_service/recipe kit, DOM/SVG,
         full 1080x1920) -> sound (recipe effects from the library, quietly under the voice) -> upload

The kit draws everything from the plan, so there is no scene code and no review pass: one Claude call per recipe."""
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
from jobs import job_store
from motion_pipeline import BillingError, _render_call
from recipe_prompts import RECIPE_SYSTEM, RECIPE_TOOL
from storybook_pipeline import upload_bytes_to_r2
from tts import get_word_timestamps
from yard_pipeline import _assign_words, _claude, _wav_to_mp3

SPEED = float(os.environ.get("RECIPE_VOICE_SPEED", "1.2"))
VOICES = {"af_heart": "Heart (US, warm)", "am_michael": "Michael (US, calm)", "bf_emma": "Emma (UK)", "bm_george": "George (UK)"}
SR = 48000
FPS = 30
STEPS = 5

DRINK_KINDS = {"add", "muddle", "pour", "ice", "top", "stir", "shake", "garnish"}
DISH_KINDS = {"pour", "add", "sprinkle", "crack", "stir", "whisk", "cook", "garnish"}
DRINK_ADD = {"mint", "lime", "berries", "sugar"}
DRINK_GARNISH = {"mint", "lime_wheel", "orange_peel", "cherry", "olive", "umbrella"}
SHAPES = {"dice", "slice", "ring", "round", "strip", "leaf", "mince", "crumble", "grain", "chunk"}
# seconds a step needs on screen for its animation, whatever the narrator says
MIN_STEP = {"add": 2.5, "muddle": 2.8, "pour": 2.7, "top": 2.5, "ice": 2.4, "stir": 2.2, "shake": 3.0, "garnish": 3.0,
            "sprinkle": 2.4, "whisk": 2.4, "cook": 2.4}
GARNISH_HOLD = 2.4     # the garnish, then the closing card with every ingredient
OUTRO = 2.8
VOICE_DB = -20.3       # speech level the effect gains in motion_sound were set against
EFFECT_DB = -16.0      # every effect's active level before its library gain


def _job(job_id: str) -> dict:
    return job_store[job_id]


def _stage(job_id: str, stage: str, step: int, message: str):
    _job(job_id).update(status="processing", stage=stage, step=step, total_steps=STEPS, message=message)
    print(f"[recipe {job_id[:8]}] {step}/{STEPS} {message}")


def _clean(s, n: int = 200) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def _hex(c, default: str) -> str:
    c = str(c or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
        return c.upper()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:]).upper()
    return default


def _num(x, lo: float, hi: float, default: float | None = None):
    try:
        return min(hi, max(lo, float(x)))
    except (TypeError, ValueError):
        return default


# ─────────────────────────── sync: the recipe ───────────────────────────

def clean_recipe(r: dict) -> dict:
    """Whatever Claude (or the edit form) sent -> a plan the kit can draw: known kinds only, real hex colours,
    fills that fit the glass, short on-screen text."""
    mode = "dish" if r.get("mode") == "dish" or (r.get("vessel") and not r.get("glass")) else "drink"
    kinds = DISH_KINDS if mode == "dish" else DRINK_KINDS
    bg = r.get("bg") if isinstance(r.get("bg"), list) else []
    out = {"name": _clean(r.get("name"), 24) or "Recipe", "mode": mode,
           "tagline": _clean(r.get("tagline"), 30) or "30-second recipe",
           "bg": [_hex(bg[0] if len(bg) > 0 else None, "#1F5A55" if mode == "drink" else "#4A2E22"),
                  _hex(bg[1] if len(bg) > 1 else None, "#0A2422" if mode == "drink" else "#170D09")],
           "accent": _hex(r.get("accent"), "#F2C14E"), "final": _hex(r.get("final"), "#E8C27A"),
           "intro": _clean(r.get("intro"), 120) or f"Here's how to make {_clean(r.get('name'), 24) or 'it'} in thirty seconds.",
           "voice": r.get("voice") if r.get("voice") in VOICES else "af_heart"}
    if mode == "drink":
        out["glass"] = r.get("glass") if r.get("glass") in ("highball", "rocks", "coupe", "martini") else "highball"
    else:
        out["vessel"] = r.get("vessel") if r.get("vessel") in ("pan", "pot", "bowl") else "pan"
    steps = []
    for s in (r.get("steps") or [])[:12]:
        k = s.get("kind")
        line = _clean(s.get("line"), 140)
        if k not in kinds or not line:
            continue
        st = {"kind": k, "line": line, "title": _clean(s.get("title"), 22) or k.capitalize(),
              "amount": _clean(s.get("amount"), 10), "unit": _clean(s.get("unit"), 10), "name": _clean(s.get("name"), 24),
              "color": _hex(s.get("color"), "#E9C46A")}
        if st["unit"].lower() in ("piece", "pieces", "pcs", "pc", "whole"):
            st["unit"] = ""
        if s.get("ml") not in (None, "") and _num(s.get("ml"), 1, 2000):
            st["ml"] = int(_num(s.get("ml"), 1, 2000))
        if k in ("pour", "top") or (k == "add" and mode == "dish"):
            st["fill"] = _num(s.get("fill"), 0.0, 0.5, 0.25 if k != "add" else 0.04)
        if k in ("pour", "top"):
            st["opacity"] = _num(s.get("opacity"), 0.2, 1.0, 0.9)
            st["bottle"] = _hex(s.get("bottle"), "#DCE3E8")
            if s.get("spread") is not None:
                st["spread"] = _num(s.get("spread"), 0.3, 1.0, 1.0)
            if mode == "dish":
                st["container"] = "bowl" if s.get("container") == "bowl" else "bottle"
                st["pourDur"] = 1.6 if st["container"] == "bowl" else 1.2
            else:
                st["pourDur"] = 1.2 if k == "top" else 1.6
        if k == "ice":
            st["style"] = "crushed" if s.get("style") == "crushed" else "cubes"
        if k == "crack":
            st["count"] = int(_num(s.get("count"), 1, 6, 2))
        if k == "cook":
            st["brown"] = _num(s.get("brown"), 0, 0.8, 0.2)
            if s.get("lid"):
                st["lid"] = True
            if s.get("bubbles") is False:
                st["bubbles"] = False
            if s.get("color"):
                st["color"] = _hex(s.get("color"), "#A5261A")
            else:
                st.pop("color")
        if k in ("stir", "whisk") and s.get("blend"):
            st["blend"] = True
        if s.get("heat") and mode == "dish":
            st["heat"] = True
        if s.get("spoon") and mode == "dish" and k == "add":
            st["spoon"] = True
        items = s.get("items") if isinstance(s.get("items"), list) else []
        if mode == "drink" and k in ("add", "garnish"):
            allowed = DRINK_ADD if k == "add" else DRINK_GARNISH
            st["items"] = [i for i in items if isinstance(i, str) and i in allowed][:3] or (["mint"] if k == "garnish" else ["lime"])
        if mode == "dish" and k in ("add", "garnish"):
            got = []
            for i in items[:3]:
                if isinstance(i, dict) and i.get("shape") in SHAPES:
                    cap = 60 if i["shape"] == "grain" else 24
                    got.append({"shape": i["shape"], "color": _hex(i.get("color"), st["color"]),
                                "count": int(_num(i.get("count"), 4, cap, 14))})
            st["items"] = got or [{"shape": "leaf" if k == "garnish" else "chunk", "color": st["color"], "count": 12}]
        steps.append(st)
    # everything that raises the contents fits in the vessel
    raise_ = [s for s in steps if "fill" in s]
    total = sum(s["fill"] for s in raise_)
    if total > 0.9:
        for s in raise_:
            s["fill"] = round(s["fill"] * 0.9 / total, 3)
    out["steps"] = steps
    return out


async def write_recipe(dish: str, length: int = 30) -> dict:
    jid = "r-" + os.urandom(6).hex()
    job_store[jid] = {"kind": "scratch", "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}}
    try:
        ask = (f"Dish or drink (a name, or the user's own recipe):\n{dish.strip()}\n\nTarget length: {length} seconds."
               "\n\nPlan the reel and submit it.")
        r = clean_recipe(await _claude(jid, RECIPE_SYSTEM, ask, 4000, "recipe", tool=RECIPE_TOOL))
        if len(r["steps"]) < 4:
            raise ValueError("the recipe came back too short")
        return {"recipe": r, "cost_usd": job_store[jid]["usage"]["cost_usd"]}
    finally:
        job_store.pop(jid, None)


# ─────────────────────────── voice and timing ───────────────────────────

def _min_step(s: dict) -> float:
    if s["kind"] == "crack":
        return 1.4 + 0.45 * s.get("count", 2)
    if s["kind"] == "pour":
        return 1.3 + s.get("pourDur", 1.4)
    return MIN_STEP.get(s["kind"], 2.4)


async def _voice(job_id: str, r: dict, tmp: str, speed: float) -> tuple[str, list[dict], float]:
    """Each line spoken on its own, followed by enough silence for its step's animation."""
    import soundfile as sf
    lines = [{"id": "intro", "text": r["intro"], "min": 2.4}] + \
            [{"id": f"s{i}", "text": s["line"], "min": _min_step(s)} for i, s in enumerate(r["steps"])]
    vs = yard_voice.SR
    out, spans, t = [np.zeros(int(0.3 * vs), np.float32)], [], 0.3
    for ln in lines:
        a = await yard_voice.say(ln["text"], voice=r["voice"], speed=speed)
        d = len(a) / vs
        spans.append({"id": ln["id"], "text": ln["text"], "start": round(t, 3), "end": round(t + d, 3)})
        g = max(0.3, ln["min"] - d)
        out += [a, np.zeros(int(g * vs), np.float32)]
        t += d + g
    audio = np.concatenate(out)
    wav = os.path.join(tmp, "voice.wav")
    sf.write(wav, audio, vs)
    return wav, spans, t


def _plan(r: dict, spans: list[dict], words: list[dict], spoken_end: float) -> dict:
    by = {s["id"]: s for s in spans}
    steps = []
    for i, s in enumerate(r["steps"]):
        st = {k: v for k, v in s.items() if k != "line"}
        st["at"] = by[f"s{i}"]["start"]
        last = i == len(r["steps"]) - 1
        st["end"] = st["at"] + GARNISH_HOLD if last and s["kind"] == "garnish" else \
            (by[f"s{i + 1}"]["start"] if not last else spoken_end)
        steps.append(st)
    duration = round(max(spoken_end, steps[-1]["end"] + OUTRO), 2)
    # captions: up to four words at a time, timed by Whisper (or spread over the line when it missed)
    caps = []
    for ln in _assign_words(spans, words):
        ws = ln["words"]
        for j in range(0, len(ws), 4):
            c = ws[j:j + 4]
            caps.append([round(c[0]["start"], 2), " ".join(w["w"] for w in c), round(c[-1]["end"] + 0.15, 2)])
    # short lines: hold each caption up to 0.8 s longer, never past the next one
    for i, c in enumerate(caps):
        nxt = caps[i + 1][0] if i + 1 < len(caps) else c[2] + 0.8
        c[2] = round(max(c[2], min(nxt - 0.02, c[2] + 0.8)), 2)
    plan = {"duration": duration, "name": r["name"], "tagline": r["tagline"], "bg": r["bg"], "accent": r["accent"],
            "final": r["final"], "steps": steps, "captions": caps}
    plan["vessel" if r["mode"] == "dish" else "glass"] = r.get("vessel") or r.get("glass")
    return plan


def compose(plan: dict) -> str:
    d = plan["duration"]
    data = json.dumps(plan, ensure_ascii=False).replace("</", "<\\/")   # outside the f-string: Python 3.11
    return f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="lib/kit.css">
<style>#root{{width:1080px;height:1920px;position:relative;overflow:hidden}}</style></head><body>
<div id="root" data-composition-id="recipe" data-no-timeline data-start="0" data-duration="{d}" data-width="1080" data-height="1920"></div>
<script src="lib/anime.umd.min.js"></script><script src="lib/kit.js"></script><script src="recipe/recipe.js"></script>
<script>
const PLAN = {data};
const tl = K.timeline();
const draw = RC.run(document.getElementById('root'), PLAN);
tl._kHooks.push(ms => draw(ms / 1000));
tl.add({{ k: 0 }}, {{ k: 1, duration: {int(d * 1000)}, ease: 'linear' }}, 0);
draw(0);
</script></body></html>"""


# ─────────────────────────── sound: effects quietly under the voice ───────────────────────────

def _decode(path: str) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def _active_to(a: np.ndarray, target_db: float) -> np.ndarray:
    """Level by the loud part only (frames over 3% of the peak), so sparse clicks and dense fizz sit alike."""
    hop = SR // 50
    if len(a) < hop * 2:
        return a
    r = np.sqrt(np.mean(a[: len(a) // hop * hop].reshape(-1, hop) ** 2, axis=1))
    act = r[r > r.max() * 0.03]
    db = 20 * math.log10(math.sqrt(float(np.mean(act ** 2))) + 1e-9) if len(act) else -90
    return a * 10 ** ((target_db - db) / 20)


def _cues(plan: dict) -> list[tuple]:
    """(kind, t, extra dB, max seconds) for every effect in the reel."""
    dish, hot, cues = bool(plan.get("vessel")), False, []
    if not dish:
        cues.append(("bar_set", 0.35, 0, None))
    for s in plan["steps"]:
        k, a = s["kind"], s["at"]
        pd = s.get("pourDur", 1.4)
        hot = hot or bool(s.get("heat")) or k == "cook"
        if k in ("pour", "top"):
            if s.get("container") == "bowl":
                cues.append(("food_glop", a + 0.6, 0, None))
                if hot:
                    cues.append(("food_simmer", a + 1.4, -6, 1.4))
            else:
                cues.append(("bar_pour", a + 0.5, -3 if k == "top" else 0, pd + 0.35))
            if k == "top":
                cues.append(("bar_fizz", a + 0.9, 0, None))
        elif k == "add":
            if dish:
                cues.append(("food_sizzle" if hot else "food_drop", a + 0.5, 0, max(1.2, s["end"] - a - 0.6)))
            else:
                cues += [("bar_leaves", a + 0.55, 0, None), ("bar_leaves", a + 1.0, -3, None)]
        elif k == "sprinkle":
            cues.append(("food_sprinkle", a + 0.5, 0, None))
        elif k == "whisk":
            cues.append(("food_whisk", a + 0.4, 0, None))
        elif k == "cook":
            cues.append(("food_simmer" if s.get("bubbles", True) else "food_sizzle", a + 0.2, 0, s["end"] - a))
            if s.get("lid"):
                cues += [("food_lid", a + 0.6, 0, None), ("food_lid", s["end"] - 0.4, -4, None)]
        elif k == "crack":
            n = s.get("count", 2)
            cues += [("food_crack", a + 0.5 + i * min(0.5, 1.8 / n) - 0.05, -(i % 2) * 2, None) for i in range(n)]
        elif k == "muddle":
            cues.append(("bar_muddle", a + 0.35, 0, None))
        elif k == "ice":
            cues.append(("bar_crushed" if s.get("style") == "crushed" else "bar_ice", a + 0.6, 0, None))
        elif k == "stir":
            cues.append(("food_stir" if dish else "bar_stir", a + (0.9 if dish else 0.3), 0, None))
        elif k == "shake":
            cues.append(("bar_shake", a + 0.4, 0, None))
        elif k == "garnish":
            cues += [("bar_leaves", a + 0.4, 0, None), ("bar_leaves", a + 0.8, -2, None)]
        if s.get("spoon"):
            cues.append(("food_stir", a + 0.9, 0, None))
    if not dish:
        cues.append(("bar_cheers", plan["steps"][-1]["end"] + 0.1, 0, None))
    return cues


async def _mix(video: str, voice_wav: str, plan: dict, tmp: str) -> str:
    total = plan["duration"]
    n = int(total * SR) + SR
    cues = _cues(plan)
    bed_kind = "food_bed" if plan.get("vessel") else "bar_bed"
    try:
        lib = await motion_sound.fetch_library({c[0] for c in cues} | {bed_kind}, tmp)
    except Exception as e:
        print(f"[recipe] sound library unavailable: {e!r}")
        lib = {}
    clips = {k: _active_to(_decode(p), EFFECT_DB + motion_sound.SFX_LIBRARY[k][2]) for k, p in lib.items()}
    voice = np.zeros(n)
    v = _decode(voice_wav)[:n]
    voice[:len(v)] = v
    loud = voice[np.abs(voice) > np.abs(voice).max() * 0.02]
    if len(loud):
        voice *= 10 ** ((VOICE_DB - 20 * math.log10(math.sqrt(float(np.mean(loud ** 2))) + 1e-9)) / 20)
    fx = np.zeros(n)
    for k, t, g, dur in cues:
        if k not in clips:
            continue
        a = clips[k].copy()
        if dur and len(a) > dur * SR:
            a = a[: int(dur * SR)]
            f = min(len(a), int(0.25 * SR))
            a[-f:] *= np.linspace(1, 0, f)
        i = int(t * SR)
        a = a[: max(0, n - i)]
        fx[i:i + len(a)] += a * 10 ** (g / 20)
    bed = np.zeros(n)
    if bed_kind in clips and len(clips[bed_kind]):
        b = clips[bed_kind]
        bed = np.tile(b, int(math.ceil(n / len(b))))[:n]
        f = int(1.5 * SR)
        end = int(total * SR)
        bed[max(0, end - f):end] *= np.linspace(1, 0, min(f, end))
        bed[end:] = 0
        # 5 dB down under the voice, smoothed over 0.3 s
        hop = SR // 100
        e = np.array([np.abs(voice[i:i + hop]).mean() for i in range(0, n, hop)])
        on = (e > e.max() * 0.05).astype(float)
        on = np.clip(np.convolve(on, np.ones(30) / 30, "same") * 2, 0, 1)
        bed *= 10 ** (-5 * np.repeat(on, hop)[:n] / 20)
    m = (voice + fx + bed)[: int(total * SR)]
    m /= max(1e-9, float(np.abs(m).max())) / 0.9
    import soundfile as sf
    pre, mixed, out = os.path.join(tmp, "mix.wav"), os.path.join(tmp, "mixn.wav"), os.path.join(tmp, "final.mp4")
    sf.write(pre, m.astype(np.float32), SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", pre, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), mixed], check=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", mixed, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("audio mux failed: " + r.stderr[-300:])
    return out


# ─────────────────────────── the job ───────────────────────────

async def run_recipe_pipeline(job_id: str, p: dict):
    tmp = tempfile.mkdtemp(prefix="recipe-")
    try:
        r = clean_recipe(p["recipe"])
        if len(r["steps"]) < 3:
            raise ValueError("the recipe needs at least 3 steps")
        _job(job_id).update(title=r["name"])

        _stage(job_id, "voice", 1, "Recording the narrator")
        wav, spans, spoken = await _voice(job_id, r, tmp, SPEED)
        if spoken > 46:                                   # long recipes: speak a little faster, never past 1.32
            wav, spans, spoken = await _voice(job_id, r, tmp, min(1.32, SPEED * 1.1))
        mp3 = os.path.join(tmp, "voice.mp3")
        _wav_to_mp3(wav, mp3)
        try:
            words = await get_word_timestamps(open(mp3, "rb").read())
        except Exception as e:
            print(f"[recipe] whisper failed, spreading words: {e!r}")
            words = []

        _stage(job_id, "plan", 2, "Measuring the ingredients")
        plan = _plan(r, spans, words, spoken)
        _job(job_id)["duration"] = plan["duration"]

        _stage(job_id, "render", 3, "Rendering")
        res = await _render_call("/render", {"files": {"index.html": compose(plan)}, "quality": "standard", "fps": FPS,
                                             "timeout_ms": 30 * 60 * 1000}, timeout=3600)
        if res.status_code != 200 or not res.content:
            raise RuntimeError(f"render failed: {res.text[-400:]}")
        video = os.path.join(tmp, "video.mp4")
        open(video, "wb").write(res.content)

        _stage(job_id, "sound", 4, "Mixing the sound")
        final = await _mix(video, wav, plan, tmp)

        _stage(job_id, "upload", 5, "Uploading")
        url = await asyncio.to_thread(upload_bytes_to_r2, open(final, "rb").read(), "recipe", "mp4", "video/mp4")
        thumb, thumb_url = os.path.join(tmp, "thumb.jpg"), None
        at = max(0.5, plan["duration"] - 1.5)              # the finished drink or dish with its ingredient card
        if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", final, "-frames:v", "1", "-q:v", "3", thumb]).returncode == 0:
            thumb_url = await asyncio.to_thread(upload_bytes_to_r2, open(thumb, "rb").read(), "recipe", "jpg", "image/jpeg")
        _job(job_id).update(status="completed", stage="done", step=STEPS, message="Done", final_video_url=url, thumbnail_url=thumb_url)
    except Exception as e:
        traceback.print_exc()
        _job(job_id).update(status="failed", stage="failed",
                            error=("Anthropic API credit is too low" if isinstance(e, BillingError) else str(e))[:500],
                            traceback=traceback.format_exc()[-3000:])
    finally:
        subprocess.run(["rm", "-rf", tmp])
