"""
Video Analysis: take a reference reel apart (the analysis stage of ReelMimic, vendored in video_analysis/).

    1. measure   video_analysis/analyze.py in a subprocess (CPU): shots and cut rhythm, camera moves per shot, look and
                 palette per shot, BPM / beats / build-and-hit moments, flash frames, a motion fingerprint, contact sheets
    2. publish   contact sheets, fingerprint picture and report.json → R2
    3. describe  Claude (Sonnet, prompt model) reads the numbers + both contact sheets and writes the style breakdown:
                 hook, structure, pacing, camera, look, text, sound, and how to make one like it with Animave

No video is generated; one Claude call per analysis (~$0.03–0.06).
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

import anthropic

from jobs import job_store
from motion_pipeline import THINK_ROOM, BillingError, _anthropic, _record_usage
from storybook_pipeline import upload_bytes_to_r2

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZE = os.path.join(HERE, "video_analysis", "analyze.py")
MODEL = os.environ.get("ANALYSIS_MODEL", os.environ.get("PROMPT_MODEL", "claude-sonnet-5-5"))
EFFORT = os.environ.get("ANALYSIS_EFFORT", "medium")
MAX_SECONDS = int(os.environ.get("ANALYSIS_MAX_SECONDS", "1200"))     # longer references are refused (CPU time)
TIMEOUT = int(os.environ.get("ANALYSIS_TIMEOUT", "1800"))
STEPS = 3
_slots = asyncio.Semaphore(int(os.environ.get("ANALYSIS_CONCURRENCY", "2")))   # analyze.py uses every core

LANGS = {"tr": "Turkish", "en": "English"}


def new_job(source: str, brief: str, lang: str) -> dict:
    return {
        "kind": "analysis", "status": "queued", "stage": "queued", "step": 0, "total_steps": STEPS, "message": "Queued",
        "source": source, "brief": brief, "lang": lang, "report": None, "breakdown": None, "files": {},
        "error": None, "traceback": None, "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
    }


def _log(job_id: str, step: int, stage: str, message: str):
    job_store[job_id].update(status="processing", step=step, stage=stage, message=message)
    print(f"[analysis {job_id}] {step}/{STEPS} {stage}: {message}")


def _run(cmd: list, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _duration(path: str) -> float:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], 60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ValueError("this file could not be read as a video")


BOT_CHECK = ("confirm you're not a bot", "confirm you\u2019re not a bot", "sign in to confirm", "use --cookies", "login required",
             "rate-limit reached", "http error 429")


def _cookie_file(out: str) -> str | None:
    """YTDLP_COOKIES: a Netscape cookies.txt (raw text or base64) from a logged-in browser. Datacenter IPs get YouTube's
    "confirm you're not a bot" wall without it. Written into the job's temp folder (yt-dlp rewrites the file)."""
    raw = os.environ.get("YTDLP_COOKIES", "").strip()
    if not raw:
        return None
    if not raw.startswith(("#", ".")) and "\t" not in raw:
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            print("[analysis] YTDLP_COOKIES is neither cookies.txt text nor base64; ignored")
            return None
    path = os.path.join(out, "cookies.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw if raw.endswith("\n") else raw + "\n")
    return path


def _download(url: str, out: str) -> str:
    """yt-dlp at ≤720p, refusing anything known to be longer than MAX_SECONDS before it is downloaded (an unreported
    length passes here; run_analysis measures the file).
    Optional: YTDLP_COOKIES (see _cookie_file) and YTDLP_PROXY (e.g. a residential proxy URL)."""
    cmd = [sys.executable, "-m", "yt_dlp", "-f", "bv*[height<=720]+ba/b[height<=720]/b", "--merge-output-format", "mp4",
           "--match-filter", f"duration <=? {MAX_SECONDS}", "--no-playlist", "-o", os.path.join(out, "input.%(ext)s")]
    cookies = _cookie_file(out)
    if cookies:
        cmd += ["--cookies", cookies]
    if os.environ.get("YTDLP_PROXY"):
        cmd += ["--proxy", os.environ["YTDLP_PROXY"]]
    r = _run(cmd + [url], 600)
    if cookies:
        try:
            os.remove(cookies)
        except OSError:
            pass
    files = [f for f in os.listdir(out) if f.startswith("input.")]
    if not files:
        log = (r.stdout + r.stderr).lower()
        if "does not pass filter" in log:
            raise ValueError(f"the video is longer than {MAX_SECONDS // 60} minutes")
        if any(k in log for k in BOT_CHECK):
            print(f"[analysis] link blocked by the site (cookies={'yes' if cookies else 'no'}, "
                  f"proxy={'yes' if os.environ.get('YTDLP_PROXY') else 'no'}): {(r.stderr or r.stdout)[-300:]}")
            raise ValueError("this site blocked our server from downloading the video. Download it on your device "
                             "and upload the file instead.")
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["no file"]
        raise ValueError("download failed: " + tail[0][:240])
    return os.path.join(out, files[0])


def _measure(src: str, out: str) -> dict:
    r = _run([sys.executable, ANALYZE, src, "--out", out], TIMEOUT)
    report = os.path.join(out, "report.json")
    if r.returncode or not os.path.isfile(report):
        raise RuntimeError("analysis failed: " + (r.stderr or r.stdout)[-600:])
    with open(report, encoding="utf-8") as f:
        return json.load(f)


def _publish(job_id: str, out: str) -> dict:
    files = {}
    for name, key, ctype in [("sheet_1fps.jpg", "sheet_1fps", "image/jpeg"), ("sheet_scenes.jpg", "sheet_scenes", "image/jpeg"),
                             ("fingerprint.png", "fingerprint", "image/png"), ("report.json", "report", "application/json")]:
        p = os.path.join(out, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                files[key] = upload_bytes_to_r2(f.read(), f"analysis/{job_id}", name.rsplit(".", 1)[1], ctype)
    return files


def compact(rep: dict) -> dict:
    """The report without the long arrays (every beat, every per-shot vector), for the page and for Claude."""
    au = dict(rep.get("audio") or {})
    beats = au.pop("beats", None) or []
    au["beat_count"] = len(beats)
    shots = []
    for s in rep.get("shot_details") or []:
        shots.append({"shot": s["shot"], "start": s["start"], "end": s["end"], "camera": s["camera"]["kind"],
                      "pace": s["camera"]["pace"], "brightness": s["look"]["brightness"],
                      "colourfulness": s["look"]["colourfulness"], "dominant": s["look"]["dominant"][:3]})
    fp = rep.get("fingerprint") or {}
    return {"video": rep.get("video"), "crop": rep.get("crop"), "pacing": rep.get("pacing"), "look_summary": rep.get("look_summary"),
            "audio": au, "flashes": rep.get("flashes") or [], "shots": shots,
            "motion": {"cadence": fp.get("cadence"), "peaks": fp.get("peaks"), "rhythm": fp.get("rhythm")} if fp else None}


BREAKDOWN_TOOL = {
    "name": "submit_breakdown",
    "description": "Submit the style breakdown of the reference video.",
    "input_schema": {
        "type": "object",
        "required": ["summary", "format", "hook", "structure", "pacing", "camera", "look", "text_and_graphics", "sound",
                     "recreate", "animave_format"],
        "properties": {
            "summary": {"type": "string", "description": "2-3 sentences: what kind of video this is and why it works."},
            "format": {"type": "string", "description": "The genre/format in a few words (e.g. 'kinetic-type explainer')."},
            "hook": {"type": "string", "description": "What happens in the first 1-3 seconds to stop the scroll."},
            "structure": {"type": "array", "description": "The video's beats in order.", "items": {
                "type": "object", "required": ["start", "end", "beat"],
                "properties": {"start": {"type": "number"}, "end": {"type": "number"},
                               "beat": {"type": "string", "description": "What this stretch does (hook, setup, reveal, payoff, CTA…)."}}}},
            "pacing": {"type": "string", "description": "Cut rhythm in plain words, citing the numbers (shot length, cuts vs beat)."},
            "camera": {"type": "string", "description": "Framing and camera movement habits."},
            "look": {"type": "string", "description": "Rendering style, lighting and palette."},
            "palette": {"type": "array", "items": {"type": "string"}, "description": "4-6 hex colours that define the look."},
            "text_and_graphics": {"type": "string", "description": "Captions, on-screen text, typography, overlays ('none' if none)."},
            "sound": {"type": "string", "description": "Music/voice/SFX, tempo and where the hits land ('silent' if silent)."},
            "recreate": {"type": "array", "items": {"type": "string"}, "description": "4-7 concrete rules to make a new video in this style."},
            "animave_format": {"type": "string", "description": "The closest Animave format and why, one sentence."},
        },
    },
}

SYSTEM = """You are a short-form video editor who reverse-engineers reels. You get measurements of a reference video
(made by an analysis script: shot cuts, per-shot camera motion and look, tempo, beats, build-and-hit moments, flash
frames) and two contact sheets: one frame per second (tiled left→right, top→bottom) and the middle frame of every shot
(labelled with its time). Describe how the video is made — its style, not its subject — so someone could make a NEW,
original video in the same style. Trust the numbers for timing and the pictures for content and look; say so when they
disagree. Be concrete and short; no filler. Never suggest copying the original footage, characters, logos or music.

Animave formats to choose from: Explainer (cream-paper talking presenter), Motion Graphics (vector/kinetic type),
3D Build (time-lapse construction), 3D Health (x-ray body), 3D Render (cinematic 3D), Recipe (drink/dish steps),
Block Horror (blocky night-town horror), Survival Story (stickman survival thriller), Style Studio (stylised footage)."""


def _image_block(path: str):
    if not os.path.isfile(path):
        return None
    data = open(path, "rb").read()
    if len(data) > 3_500_000:   # keep under the API's 5 MB image limit
        import cv2
        img = cv2.imread(path)
        img = cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2))
        data = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(data).decode()}}


async def _describe(job_id: str, out: str, summary: dict, brief: str, lang: str) -> dict:
    content = []
    for name, label in [("sheet_1fps.jpg", "Contact sheet, one frame per second:"), ("sheet_scenes.jpg", "Middle frame of each shot:")]:
        img = _image_block(os.path.join(out, name))
        if img:
            content += [{"type": "text", "text": label}, img]
    content.append({"type": "text", "text": "Measurements:\n" + json.dumps(summary, ensure_ascii=False)})
    if brief:
        content.append({"type": "text", "text": f"The user wants to make: {brief}\nAim the 'recreate' rules at that."})
    content.append({"type": "text", "text": f"Write every text field in {LANGS.get(lang, 'English')}. "
                                            f"Answer by calling the `submit_breakdown` tool."})
    try:
        async with _anthropic().messages.stream(
            model=MODEL, max_tokens=3000 + THINK_ROOM.get(EFFORT, 10000), output_config={"effort": EFFORT},
            system=SYSTEM, tools=[BREAKDOWN_TOOL], tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            msg = await stream.get_final_message()
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e).lower():
            raise BillingError("Anthropic API credit balance is too low") from e
        raise
    _record_usage(job_id, "describe", MODEL, msg.usage)
    for b in msg.content:
        if getattr(b, "type", "") == "tool_use":
            return dict(b.input)
    raise ValueError(f"no breakdown returned ({msg.stop_reason})")


async def run_analysis(job_id: str, file_path: str | None, url: str | None, brief: str = "", lang: str = "tr"):
    """file_path: an uploaded file (deleted afterwards); url: a link yt-dlp can fetch."""
    work = tempfile.mkdtemp(prefix=f"analysis-{job_id[:8]}-")
    try:
        async with _slots:
            _log(job_id, 1, "measuring", "Downloading the video" if url else "Reading the video")
            src = await asyncio.to_thread(_download, url, work) if url else file_path
            dur = await asyncio.to_thread(_duration, src)
            if dur > MAX_SECONDS:
                raise ValueError(f"the video is {dur / 60:.1f} minutes; the limit is {MAX_SECONDS // 60} minutes")
            _log(job_id, 1, "measuring", "Measuring shots, camera, colour and rhythm")
            out = os.path.join(work, "analysis")
            report = await asyncio.to_thread(_measure, src, out)
        summary = compact(report)
        job_store[job_id]["report"] = summary
        _log(job_id, 2, "publishing", "Saving contact sheets")
        job_store[job_id]["files"] = await asyncio.to_thread(_publish, job_id, out)
        _log(job_id, 3, "describing", "Writing the style breakdown")
        try:   # the measurements are already useful on their own: a failed write-up doesn't fail the job
            job_store[job_id]["breakdown"] = await _describe(job_id, out, summary, brief, lang)
        except Exception as e:
            job_store[job_id]["breakdown_error"] = str(e)[:300]
            print(f"[analysis {job_id}] breakdown skipped: {e}")
        job_store[job_id].update(status="completed", stage="done", step=STEPS, message="Done")
    except Exception as e:
        job_store[job_id].update(status="failed", stage="failed", error=str(e)[:400], traceback=traceback.format_exc()[-3000:],
                                 message="Failed")
        print(f"[analysis {job_id}] failed: {e}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if file_path:
            try:
                os.remove(file_path)
            except OSError:
                pass
