"""
Motion Graphics sound design: animation-synced SFX + narration, mixed with ducking.

  * SFX library: one ElevenLabs sound-generation per KIND, generated once and cached in R2
    (motion-sfx/v1/<kind>.mp3), then reused by every video — near-zero cost per video.
  * Cues: the motion kit records every animation (pop, rise, count, draw, …) with its time;
    the render service returns them (/cues). Each cue gets its effect at that exact moment.
  * Narration: one ElevenLabs line per beat, placed at the beat start and gently sped up
    (≤ 1.15×) if it would run into the next line.
  * Mix: effects (and optional music) are ducked under the voice, then limited.
"""

import asyncio
import os
import subprocess

import httpx

from storybook_pipeline import get_r2_client, R2_BUCKET, R2_PUBLIC_BASE
from tts import generate_speech, generate_speech_timed

SFX_VERSION = "v1"

# kind -> (ElevenLabs prompt, seconds, gain dB relative to a normalised source,
#          minimum gap to the previous cue of the same kind in ms)
SFX_LIBRARY = {
    "rise":  ("quick soft airy whoosh, clean modern UI motion design, very short", 0.8, -9, 250),
    "soft":  ("very soft subtle swish of air, gentle, delicate UI movement", 0.6, -15, 500),
    "out":   ("fast soft swoosh out, airy clean transition", 0.7, -10, 300),
    "pop":   ("soft rounded bubble pop, clean UI notification, short", 0.5, -7, 90),
    "grow":  ("short smooth rising slide, soft synth swell, UI element growing", 0.8, -12, 200),
    "swipe": ("clean quick paper swipe", 0.6, -11, 250),
    "count": ("fast soft digital ticking, counter numbers rolling up, clean UI", 3.5, -13, 400),
    "draw":  ("smooth marker pen drawing a long line on paper", 3.5, -12, 400),
    "type":  ("light keyboard typing, a few quick soft keystrokes", 1.5, -10, 300),
    "impact": ("soft deep cinematic thump, subtle", 0.9, -7, 400),
    "chime": ("bright warm positive notification chime, short", 1.0, -10, 400),
}
SFX_TARGET_DB = -16.0     # mean level every effect is normalised to before its gain
VOICE_TARGET_LUFS = -18.0  # integrated loudness of every narration line
MASTER_LUFS = -16.0        # final mix (social media), applied as ONE static gain
# Cues that fall this close to a stronger cue are dropped so the mix doesn't get busy.
BUSY_MS = 220
PRIORITY = {"impact": 0, "pop": 1, "count": 2, "draw": 2, "type": 2, "rise": 3, "out": 3,
            "swipe": 3, "grow": 4, "chime": 1, "soft": 9}


def _key(kind: str) -> str:
    return f"motion-sfx/{SFX_VERSION}/{kind}.mp3"


async def _generate_sfx(prompt: str, seconds: float) -> bytes | None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return None
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.elevenlabs.io/v1/sound-generation",
                         headers={"xi-api-key": key, "Content-Type": "application/json"},
                         json={"text": prompt, "duration_seconds": max(0.5, min(22.0, seconds)),
                               "prompt_influence": 0.6})
    if r.status_code == 200 and r.content:
        return r.content
    print(f"[motion sound] sfx {r.status_code} {r.text[:200]}")
    return None


_locks: dict = {}


async def sfx_url(kind: str) -> str | None:
    """Public URL of a library effect; generated and cached on first use."""
    if kind not in SFX_LIBRARY:
        return None
    url = f"{R2_PUBLIC_BASE}/{_key(kind)}"
    lock = _locks.setdefault(kind, asyncio.Lock())
    async with lock:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                if (await c.head(url)).status_code == 200:
                    return url
        except Exception:
            pass
        prompt, seconds, _, _ = SFX_LIBRARY[kind]
        data = await _generate_sfx(prompt, seconds)
        if not data:
            return None
        get_r2_client().put_object(Bucket=R2_BUCKET, Key=_key(kind), Body=data, ContentType="audio/mpeg")
        return url


async def _download(url: str, path: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(url)
        if r.status_code == 200:
            open(path, "wb").write(r.content)
            return True
    except Exception as e:
        print(f"[motion sound] download failed {url}: {e}")
    return False


def plan_events(cues: list[dict]) -> list[dict]:
    """Cues (ms, absolute) -> effect events: per-kind spacing, busy-ness thinning, priorities."""
    events, last_by_kind = [], {}
    for c in sorted(cues, key=lambda c: (c["t"], PRIORITY.get(c["kind"], 5))):
        kind = c["kind"]
        if kind not in SFX_LIBRARY:
            continue
        gap = SFX_LIBRARY[kind][3]
        if c["t"] - last_by_kind.get(kind, -10_000) < gap:
            continue
        # drop a low-priority cue that lands right on top of a more important one
        clash = [e for e in events if abs(e["t"] - c["t"]) < BUSY_MS]
        if clash and min(PRIORITY.get(e["kind"], 5) for e in clash) <= PRIORITY.get(kind, 5) and kind in ("soft", "grow"):
            continue
        events.append({"t": c["t"], "kind": kind, "dur": c.get("dur", 0)})
        last_by_kind[kind] = c["t"]
    return events


async def narrate(lines: list[dict], voice_id: str, tmp: str) -> list[dict]:
    """lines: [{start (s), window (s), text, tone?}] -> [{path, start, tempo}] scheduled without overlaps."""
    async def one(i, ln):
        data = await generate_speech(ln["text"], voice_id, ln.get("tone") or "explainer")
        p = os.path.join(tmp, f"vo_{i}.mp3")
        open(p, "wb").write(data)
        return p
    paths = await asyncio.gather(*[one(i, ln) for i, ln in enumerate(lines) if ln.get("text")],
                                 return_exceptions=True)
    out, cursor, k = [], 0.0, 0
    for ln in lines:
        if not ln.get("text"):
            continue
        p = paths[k]
        k += 1
        if isinstance(p, Exception):
            print(f"[motion sound] narration failed: {p}")
            continue
        p = normalize_voice(p, VOICE_TARGET_LUFS)
        dur = probe(p)
        start = max(ln["start"] + 0.12, cursor + 0.15)
        room = ln["start"] + ln["window"] - start
        tempo = 1.0 if dur <= room or room <= 0 else min(1.15, dur / room)
        out.append({"path": p, "start": start, "tempo": tempo})
        cursor = start + dur / tempo
    return out


# Audio-first timing: a narrated beat lasts exactly lead + speech + tail.
VO_LEAD = 0.25
VO_TAIL = 0.35
MIN_BEAT = 1.6


DEFAULT_SPEED = 1.15  # narration pace for Motion Graphics (ElevenLabs native speed)


async def narrate_first(beats: list[dict], voice_id: str, tmp: str, tone: str = "explainer",
                        speed: float = DEFAULT_SPEED) -> list[dict | None]:
    """Record every beat's line BEFORE animating. Returns per beat
    {path, dur, words:[{word, start, end}]} (seconds, relative to the line) or None."""
    async def one(i, b):
        text = (b.get("voiceover") or "").strip()
        if not text:
            return None
        audio, words = await generate_speech_timed(text, voice_id, tone, speed=speed)
        p = os.path.join(tmp, f"vo_{i}.mp3")
        open(p, "wb").write(audio)
        p = normalize_voice(p, VOICE_TARGET_LUFS)
        return {"path": p, "dur": probe(p), "words": words}
    res = await asyncio.gather(*[one(i, b) for i, b in enumerate(beats)], return_exceptions=True)
    out = []
    for r in res:
        if isinstance(r, Exception):
            print(f"[motion sound] narration failed: {r!r}")
            out.append(None)
        else:
            out.append(r)
    return out


def retime(beats: list[dict], vo: list[dict | None]) -> None:
    """Set each narrated beat's duration from its recording, in place."""
    for b, v in zip(beats, vo):
        if v:
            b["duration"] = round(max(MIN_BEAT, VO_LEAD + v["dur"] + VO_TAIL), 2)
            b["vo"] = v


def normalize(path: str, target_db: float) -> str:
    """Bring a clip to a target mean level (peak-safe), in place. Library clips from ElevenLabs
    vary by 15 dB, so gains only mean something after this."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    import re as _re
    mean = _re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    peak = _re.search(r"max_volume: (-?[\d.]+) dB", r.stderr)
    if not mean or not peak:
        return path
    gain = min(target_db - float(mean.group(1)), -1.0 - float(peak.group(1)))
    if abs(gain) < 0.5:
        return path
    tmp = path + ".norm.wav"
    ok = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-af", f"volume={gain:.2f}dB", tmp]).returncode == 0
    if ok:
        os.replace(tmp, path + ".wav")
        return path + ".wav"
    return path


def loudness(path: str) -> tuple[float | None, float | None]:
    """(integrated LUFS, true peak dBTP) of a file."""
    import re as _re
    r = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    summary = r.stderr[r.stderr.rfind("Summary:"):]
    i = _re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    tp = _re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary)
    return (float(i.group(1)) if i else None, float(tp.group(1)) if tp else None)


def normalize_voice(path: str, target_lufs: float) -> str:
    """Speech is matched on perceived loudness (LUFS) with a single static gain per line —
    never a dynamic compressor, so the voice can't swell or dip inside a sentence."""
    i, tp = loudness(path)
    if i is None or i < -60:
        return path
    gain = target_lufs - i
    if tp is not None:
        gain = min(gain, -1.0 - tp)
    out = path + ".voice.wav"
    ok = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-af", f"volume={gain:.2f}dB", out]).returncode == 0
    return out if ok else path


def probe(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


async def fetch_library(kinds: set, tmp: str) -> dict:
    files = {}
    urls = await asyncio.gather(*[sfx_url(k) for k in sorted(kinds)])
    for kind, url in zip(sorted(kinds), urls):
        p = os.path.join(tmp, f"sfx_{kind}.mp3")
        if url and await _download(url, p):
            files[kind] = normalize(p, SFX_TARGET_DB)
    return files


def mix(video: str, out: str, total: float, events: list[dict], sfx_files: dict,
        voice: list[dict], music: str | None = None) -> bool:
    """Video + effects (+ music) ducked under narration -> out (video stream copied)."""
    inputs, chains, sfx_labels, vo_labels = ["-i", video], [], [], []
    idx = 1
    kind_index = {}
    for kind, path in sfx_files.items():
        uses = [e for e in events if e["kind"] == kind]
        if not uses:
            continue
        inputs += ["-i", path]
        kind_index[kind] = idx
        split = "".join(f"[{kind}{j}]" for j in range(len(uses)))
        chains.append(f"[{idx}:a]asplit={len(uses)}{split}" if len(uses) > 1 else f"[{idx}:a]anull{split}")
        for j, e in enumerate(uses):
            gain = SFX_LIBRARY[kind][2]
            length = SFX_LIBRARY[kind][1] if kind not in ("count", "draw", "type") else max(0.4, min(SFX_LIBRARY[kind][1], e["dur"] / 1000))
            ms = int(e["t"])
            lab = f"s{kind}{j}"
            chains.append(f"[{kind}{j}]atrim=0:{length:.2f},afade=t=out:st={max(0.0, length - 0.15):.2f}:d=0.15,"
                          f"volume={gain}dB,adelay={ms}|{ms}[{lab}]")
            sfx_labels.append(f"[{lab}]")
        idx += 1
    if music:
        inputs += ["-stream_loop", "-1", "-i", music]
        chains.append(f"[{idx}:a]atrim=0:{total:.2f},afade=t=in:d=0.6,afade=t=out:st={max(0.0, total - 1.5):.2f}:d=1.5,volume=-20dB[mus]")
        sfx_labels.append("[mus]")
        idx += 1
    for j, v in enumerate(voice):
        inputs += ["-i", v["path"]]
        ms = int(v["start"] * 1000)
        tempo = f"atempo={v['tempo']:.3f}," if abs(v["tempo"] - 1.0) > 0.005 else ""
        chains.append(f"[{idx}:a]{tempo}aresample=44100,adelay={ms}|{ms}[v{j}]")
        vo_labels.append(f"[v{j}]")
        idx += 1
    if not sfx_labels and not vo_labels:
        return False
    if sfx_labels:
        chains.append(f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:normalize=0:duration=longest[bus]")
    if vo_labels:
        chains.append(f"{''.join(vo_labels)}amix=inputs={len(vo_labels)}:normalize=0:duration=longest,volume=1.0[vo]")
    if sfx_labels and vo_labels:
        chains.append("[vo]asplit=2[vo1][vo2]")
        chains.append("[bus][vo1]sidechaincompress=threshold=0.04:ratio=5:attack=15:release=350[ducked]")
        chains.append("[ducked][vo2]amix=inputs=2:normalize=0:duration=longest[pre]")
    else:
        chains.append(f"{'[bus]' if sfx_labels else '[vo]'}anull[pre]")
    chains.append(f"[pre]apad,atrim=0:{total:.2f},aresample=44100[a]")
    premaster = out + ".premaster.wav"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chains),
                        "-map", "[a]", "-c:a", "pcm_s16le", premaster], capture_output=True, text=True)
    if r.returncode != 0:
        print("[motion sound] mix failed:", r.stderr[-1500:])
        return False
    # Mastering: measure once, then ONE static gain to MASTER_LUFS (true-peak capped). No
    # loudnorm in dynamic mode — that rides the level up and down inside sentences.
    i, tp = loudness(premaster)
    gain = 0.0 if i is None else MASTER_LUFS - i
    if tp is not None:
        gain = min(gain, -1.5 - tp)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", premaster,
                        "-filter:a", f"volume={gain:.2f}dB", "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out],
                       capture_output=True, text=True)
    try:
        os.remove(premaster)
    except OSError:
        pass
    if r.returncode != 0:
        print("[motion sound] master failed:", r.stderr[-1500:])
    return r.returncode == 0
