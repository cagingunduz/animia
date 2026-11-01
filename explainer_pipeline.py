"""
Explainer pipeline: a 30-60 s vertical explainer reel on cream paper with a talking cartoon presenter.

  script     (sync)  Claude writes hook / points / closing; the user edits and approves it in the app
  presenter  (sync)  a description or a photo -> the presenter's parts (Claude), or the app picks them at random
  voices     (sync)  line 1 read by each Kokoro voice so the user can pick one
  job                Kokoro narration (pauses cut to 0.24 s) -> Whisper word timings -> Claude plans the visuals
                     as data -> the explainer kit (render_service/explainer) draws it -> sound -> upload
"""

import asyncio
import json
import os
import re
import subprocess
import tempfile
import traceback

import numpy as np

import motion_sound
import yard_voice
from explainer_prompts import (PLAN_SYSTEM, PLAN_TOOL, PRESENTER_OPTIONS, PRESENTER_SYSTEM, SCRIPT_SYSTEM,
                               SCRIPT_TOOL, presenter_tool)
from jobs import job_store
from motion_pipeline import BillingError, _render_call
from storybook_pipeline import upload_bytes_to_r2
from tts import get_word_timestamps
from yard_pipeline import _assign_words, _claude, _wav_to_mp3

FPS = 30
SPEED = float(os.environ.get("EXPLAINER_VOICE_SPEED", "1.1"))
STEPS = 6
DEMOS = {"bars", "compare", "checklist", "chat", "flow", "search", "number"}


def _job(job_id: str) -> dict:
    return job_store[job_id]


def _stage(job_id: str, stage: str, step: int, message: str):
    _job(job_id).update(status="processing", stage=stage, step=step, total_steps=STEPS, message=message)
    print(f"[explainer {job_id[:8]}] {step}/{STEPS} {message}")


def _scratch_job() -> str:
    """A throwaway job record so the sync calls can reuse the usage-tracking Claude helper."""
    jid = "x-" + os.urandom(6).hex()
    job_store[jid] = {"kind": "scratch", "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}}
    return jid


# ─────────────────────────── sync: script, presenter, voices ───────────────────────────

def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def script_lines(script: dict) -> list[dict]:
    """The approved script -> narration lines with ids and roles (h1 h2 / pN pNe1 pNe2 / close)."""
    out = []
    hook = [_clean(x) for x in (script.get("hook") or []) if _clean(x)][:2]
    for i, t in enumerate(hook):
        out.append({"id": f"h{i + 1}", "role": "hook", "text": t})
    for n, p in enumerate((script.get("points") or [])[:7], 1):
        line = _clean(p.get("line"))
        if not line:
            continue
        out.append({"id": f"p{n}", "role": "point", "point": n, "name": _clean(p.get("name"))[:24] or f"point {n}", "text": line})
        for j, e in enumerate([_clean(x) for x in (p.get("explain") or []) if _clean(x)][:2]):
            out.append({"id": f"p{n}e{j + 1}", "role": "explain", "point": n, "text": e})
    if _clean(script.get("close")):
        out.append({"id": "close", "role": "close", "text": _clean(script.get("close"))})
    return out


async def write_script(topic: str, mention: str | None = None) -> dict:
    jid = _scratch_job()
    try:
        ask = f"Topic: {topic.strip()}"
        if mention and mention.strip():
            ask += f"\nMust mention: {mention.strip()}"
        s = await _claude(jid, SCRIPT_SYSTEM, ask + "\n\nWrite the script and submit it.", 2500, "writer", tool=SCRIPT_TOOL)
        script = {"title": _clean(s.get("title")) or topic.strip()[:80],
                  "hook": [_clean(x) for x in (s.get("hook") or [])][:2],
                  "points": [{"name": _clean(p.get("name")), "line": _clean(p.get("line")),
                              "explain": [_clean(x) for x in (p.get("explain") or [])][:2]} for p in (s.get("points") or [])][:7],
                  "close": _clean(s.get("close"))}
        if len(script["hook"]) < 2 or len(script["points"]) < 2:
            raise ValueError("the script came back incomplete")
        return {"script": script, "cost_usd": job_store[jid]["usage"]["cost_usd"]}
    finally:
        job_store.pop(jid, None)


async def design_presenter(description: str | None = None, image_data_url: str | None = None) -> dict:
    jid = _scratch_job()
    try:
        content = []
        if image_data_url and image_data_url.startswith("data:image/"):
            media, b64 = image_data_url[5:].split(";base64,", 1)
            content.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}})
            content.append({"type": "text", "text": "Design the presenter after this person or character."
                            + (f" Notes: {description.strip()}" if description and description.strip() else "")})
        else:
            content.append({"type": "text", "text": f"Design the presenter from this description: {(description or '').strip()[:500]}"})
        p = await _claude(jid, PRESENTER_SYSTEM, content, 600, "presenter", tool=presenter_tool(PRESENTER_OPTIONS))
        params = {k: (p.get(k) if p.get(k) in v else v[0]) for k, v in PRESENTER_OPTIONS.items()}
        return {"params": params, "cost_usd": job_store[jid]["usage"]["cost_usd"]}
    finally:
        job_store.pop(jid, None)


async def voice_samples(text: str) -> list[dict]:
    """Line 1 in every voice, uploaded so the app can play them."""
    import soundfile as sf
    out = []
    for vid, label in yard_voice.VOICES.items():
        a = await yard_voice.say(text[:200], voice=vid, speed=SPEED)
        with tempfile.TemporaryDirectory() as tmp:
            wav, mp3 = os.path.join(tmp, "v.wav"), os.path.join(tmp, "v.mp3")
            sf.write(wav, a, yard_voice.SR)
            _wav_to_mp3(wav, mp3)
            url = await asyncio.to_thread(upload_bytes_to_r2, open(mp3, "rb").read(), "explainer-voice", "mp3", "audio/mpeg")
        out.append({"voice": vid, "label": label, "url": url})
    return out


# ─────────────────────────── job helpers ───────────────────────────

def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9%']", "", str(w).lower())


def _word_time(line: dict, word: str | None, fallback: float) -> float:
    if word:
        target = _norm(word.split()[0]) if word.split() else ""
        for w in line["words"]:
            if _norm(w["w"]) == target:
                return w["start"]
        if len(target) >= 3:                                  # "recalls" for "recall" and other near misses
            for w in line["words"]:
                if _norm(w["w"]).startswith(target):
                    return w["start"]
    return fallback


def _mouth(audio: np.ndarray, sr: int) -> str:
    """Mouth shape per frame from loudness: -42 dB closed .. -16 dB wide, instant attack, 0.55 release per frame."""
    hop, env, out = sr // FPS, 0.0, []
    for i in range(0, len(audio), hop):
        w = audio[i:i + hop]
        db = 20 * np.log10(np.sqrt(np.mean(w ** 2)) + 1e-9) if len(w) else -90
        lv = min(1.0, max(0.0, (db + 42) / 26))
        env = max(lv, env * 0.55)
        out.append(str(int(round(env * 9))))
    return "".join(out)


def _chunks(lines: list[dict], keywords: dict, end: float) -> list[dict]:
    """Caption chunks: one per line, two for lines over 8 words; the key word shows in red italic."""
    out = []
    for ln in lines:
        ws = ln["words"]
        if not ws:
            continue
        parts = [ws] if len(ws) <= 8 else [ws[:(len(ws) + 1) // 2], ws[(len(ws) + 1) // 2:]]
        keys = [_norm(k) for k in (keywords.get(ln["id"]) or []) if k]
        for part in parts:
            key = next((i for i, w in enumerate(part) if _norm(w["w"]) in keys), -1)
            out.append({"start": part[0]["start"], "words": [{"w": w["w"], "start": w["start"], "end": w["end"]} for w in part], "key": key})
    for i, c in enumerate(out):
        c["end"] = out[i + 1]["start"] if i + 1 < len(out) else end + 1
    return out


def _txt(x, n=40) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


def _demo(d: dict) -> dict:
    d = dict(d or {})
    kind = d.get("kind") if d.get("kind") in DEMOS else "checklist"
    out = {"kind": kind}
    items = d.get("items") or []
    if kind == "bars":
        rows = []
        for it in items[:4]:
            if isinstance(it, (list, tuple)) and len(it) >= 2:
                try:
                    rows.append([_txt(it[0], 18), float(str(it[1]).replace("%", "").replace(",", ""))])
                except ValueError:
                    pass
        out.update(items=rows or [["Before", 1], ["After", 3]], highlight=int(d.get("highlight", len(rows) - 1) or 0),
                   suffix=_txt(d.get("suffix"), 4), prefix=_txt(d.get("prefix"), 3))
    elif kind == "compare":
        pairs = [[_txt(i[0], 16), _txt(i[1] if len(i) > 1 else "", 60)] if isinstance(i, (list, tuple)) else [_txt(i, 16), ""] for i in items[:2]]
        while len(pairs) < 2:
            pairs.append(["Without", ""] if not pairs else ["With", ""])
        out["items"] = pairs
    elif kind == "search":
        out.update(query=_txt(d.get("query"), 40), items=[_txt(i, 34) for i in items[:3]])
    elif kind == "number":
        try:
            out["value"] = float(str(d.get("value", 0)).replace("%", "").replace(",", ""))
        except ValueError:
            out["value"] = 0
        out.update(prefix=_txt(d.get("prefix"), 3), suffix=_txt(d.get("suffix"), 4), caption=_txt(d.get("caption"), 60))
    else:
        out["items"] = [_txt(i, 60 if kind == "chat" else 30) for i in items[:5] if _txt(i)] or ["Step one", "Step two"]
    return out


def build_plan(lines: list[dict], vis: dict, mouth: str, presenter: dict, duration: float) -> tuple[dict, list[dict]]:
    """Claude's visual plan + word timings -> the kit's plan (absolute times) and the sound events (ms)."""
    by = {l["id"]: l for l in lines}
    sfx = []
    hk = vis.get("hook") or {}
    h1, h2 = by.get("h1"), by.get("h2")
    prob = hk.get("problem") or {}
    hook = {"label": _txt(hk.get("label"), 24) or "intro", "stat": {"num": _txt((hk.get("stat") or {}).get("num"), 8), "text": _txt((hk.get("stat") or {}).get("text"), 28)},
            "problem": {"at": 0.0, "label": _txt(prob.get("label"), 34), "title": _txt(prob.get("title"), 22),
                        "lines": [_txt(x, 30) for x in (prob.get("lines") or [])[:2]], "strikeAt": h1["end"] - 0.15 if h1 else 1.0}}
    cards = [_txt(c, 10) for c in (hk.get("payoff_cards") or [])[:3] if _txt(c)]
    if h2 and cards:
        hook["payoff"] = {"at": h2["start"] + 0.1, "cards": cards, "ring": max(0, min(len(cards) - 1, int(hk.get("ring") or 0))),
                          "ringAt": min(h2["end"] - 0.2, h2["start"] + 1.2)}
        sfx += [{"t": (hook["payoff"]["at"] + i * 0.16) * 1000, "kind": "pop"} for i in range(len(cards))]
    sfx.append({"t": 0, "kind": "pop"})
    if h1:
        sfx.append({"t": hook["problem"]["strikeAt"] * 1000, "kind": "swipe"})
    points = []
    pv = vis.get("points") or []
    for n in sorted({l["point"] for l in lines if l.get("role") == "point"}):
        p_line = by[f"p{n}"]
        ex = [l for l in lines if l.get("role") == "explain" and l.get("point") == n]
        v = pv[n - 1] if n - 1 < len(pv) else {}
        at = _word_time(p_line, v.get("title_word"), p_line["start"] + 0.2)
        # the card stays through the point line and the first explanation line; the demo acts out the last one
        explain = ex[-1]["start"] if len(ex) > 1 else (ex[0]["start"] if ex else p_line["end"] + 0.3)
        explain = max(explain, at + 2.4)
        title = [_txt(x, 14) for x in (v.get("title") or [])[:2] if _txt(x)] or [p_line.get("name", "Point").title(), ""]
        cd = v.get("card") or {}
        card = {"caption": _txt(cd.get("caption"), 60)}
        try:
            if cd.get("value") is not None and str(cd.get("value")).strip() != "":
                card.update(value=float(str(cd["value"]).replace("%", "").replace(",", "")), prefix=_txt(cd.get("prefix"), 3), suffix=_txt(cd.get("suffix"), 4))
            else:
                card["big"] = _txt(cd.get("big") or title[-1], 16)
        except ValueError:
            card["big"] = _txt(cd.get("big") or title[-1], 16)
        term = v.get("terminal") or {}
        stamp = v.get("stamp") or {}
        st_at = None
        for l in ex:
            t = _word_time(l, stamp.get("stamp_word"), -1)
            if t >= 0:
                st_at = t
                break
        pt = {"n": n, "name": p_line.get("name", f"point {n}"), "from": p_line["start"], "at": at, "explainAt": explain,
              "title": title, "card": card,
              "stat": {"num": _txt((v.get("stat") or {}).get("num"), 8), "text": _txt((v.get("stat") or {}).get("text"), 28)},
              "terminal": {"kind": "search" if term.get("kind") == "search" else "terminal", "text": _txt(term.get("text"), 40)} if _txt(term.get("text")) else None,
              "demo": _demo(v.get("demo")),
              "stamp": {"text": _txt(stamp.get("text"), 12), "at": st_at if st_at is not None else explain + 0.9} if _txt(stamp.get("text")) else None}
        points.append(pt)
        sfx += [{"t": (pt["from"] - 0.3) * 1000, "kind": "whoosh"}, {"t": at * 1000, "kind": "impact"},
                {"t": (at + 0.3) * 1000, "kind": "pop"}]
        if card.get("value") is not None:
            sfx.append({"t": (at + 0.4) * 1000, "kind": "count", "dur": 1150})
        if pt["terminal"]:
            sfx.append({"t": (at + 1.05) * 1000, "kind": "type", "dur": 900})
        sfx.append({"t": explain * 1000, "kind": "rise"})
        if pt["stamp"]:
            sfx.append({"t": pt["stamp"]["at"] * 1000, "kind": "thud"})
    close = None
    cl, cv = by.get("close"), vis.get("close") or {}
    if cl:
        words = [_txt(w, 12) for w in (cv.get("words") or [])[:4] if _txt(w)] or cl["text"].split()[:4]
        close = {"from": cl["start"], "at": cl["start"] + 0.2, "name": "recap", "label": _txt(cv.get("label"), 28) or "remember",
                 "words": words, "stamp": _txt(cv.get("stamp"), 12) or None, "stampAt": _word_time(cl, cv.get("stamp_word"), cl["start"] + 0.8)}
        sfx += [{"t": (cl["start"] - 0.3) * 1000, "kind": "whoosh"}, {"t": close["at"] * 1000, "kind": "pop"}]
        if close["stamp"]:
            sfx.append({"t": close["stampAt"] * 1000, "kind": "thud"})
    chunks = _chunks(lines, vis.get("keywords") or {}, duration)
    nods = [c["words"][c["key"]]["start"] for c in chunks if c["key"] >= 0]
    plan = {"duration": duration, "chunks": chunks, "hook": hook, "points": points, "close": close, "nods": nods,
            "presenter": {"params": presenter, "mouth": mouth, "seed": 7}}
    return plan, [dict(e, t=int(max(0, e["t"]))) for e in sfx]


def compose(plan: dict) -> str:
    dur = plan["duration"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="lib/kit.css">
<style>#root{{width:1080px;height:1920px;position:relative;overflow:hidden}}</style></head><body>
<div id="root" data-composition-id="explainer" data-no-timeline data-start="0" data-duration="{dur}" data-width="1080" data-height="1920"></div>
<script src="lib/anime.umd.min.js"></script><script src="lib/kit.js"></script>
<script src="explainer/presenter.js"></script><script src="explainer/explainer.js"></script>
<script>
(function () {{
  const PLAN = {json.dumps(plan)};
  const tl = K.timeline();
  window.__kCues = window.__kCues || [];
  let draw = () => {{}};
  try {{ draw = EX.run(document.getElementById('root'), PLAN); }}
  catch (e) {{ window.__kCues.push({{ t: 0, kind: 'error', msg: String((e && e.stack) || e).slice(0, 900) }}); }}
  tl._kHooks.push(ms => draw(ms / 1000));
  tl.add({{ k: 0 }}, {{ k: 1, duration: {int(dur * 1000)}, ease: 'linear' }}, 0);
  draw(0);
}})();
</script></body></html>"""


# ─────────────────────────── the job ───────────────────────────

async def run_explainer_pipeline(job_id: str, p: dict):
    import soundfile as sf
    tmp = tempfile.mkdtemp(prefix="explainer-")
    try:
        lines = script_lines(p["script"])
        if len(lines) < 4:
            raise ValueError("the script is too short")
        voice = p.get("voice") if p.get("voice") in yard_voice.VOICES else "am_michael"
        presenter = {k: (p.get("presenter") or {}).get(k) if (p.get("presenter") or {}).get(k) in v else v[0]
                     for k, v in PRESENTER_OPTIONS.items()}

        _stage(job_id, "voice", 1, "Recording the narrator")
        audio, spans = await yard_voice.narrate(lines, speed=SPEED, gap=0.22, voice=voice, max_pause=0.24)
        wav, mp3 = os.path.join(tmp, "voice.wav"), os.path.join(tmp, "voice.mp3")
        sf.write(wav, audio, yard_voice.SR)
        _wav_to_mp3(wav, mp3)
        duration = round(len(audio) / yard_voice.SR + 0.6, 3)
        _job(job_id)["duration"] = duration

        _stage(job_id, "timing", 2, "Timing every word")
        try:
            words = await get_word_timestamps(open(mp3, "rb").read())
        except Exception as e:
            print(f"[explainer] whisper failed, spreading words: {e!r}")
            words = []
        timed = _assign_words(spans, words)
        for l, t in zip(lines, timed):
            l.update(start=t["start"], end=t["end"], words=t["words"])

        _stage(job_id, "plan", 3, "Planning the cards")
        listing = "\n".join(f'{l["id"]:>6} [{l["role"]}{" " + str(l["point"]) if l.get("point") else ""}] {l["text"]}' for l in lines)
        vis = await _claude(job_id, PLAN_SYSTEM, f"TITLE: {p['script'].get('title', '')}\n\nLINES:\n{listing}\n\nPlan the visuals.",
                            3500, "planner", tool=PLAN_TOOL)
        plan, sfx = build_plan(lines, vis, _mouth(audio, yard_voice.SR), presenter, duration)
        html = compose(plan)
        r = await _render_call("/cues", {"files": {"index.html": html}}, timeout=180)
        if r.status_code == 200:
            errs = [c.get("msg") for c in r.json().get("cues", []) if c.get("kind") == "error"] + list(r.json().get("errors") or [])
            if errs:
                raise RuntimeError("the explainer page failed to load: " + "; ".join(map(str, errs))[:400])

        _stage(job_id, "render", 4, "Rendering")
        r = await _render_call("/render", {"files": {"index.html": html}, "quality": "standard", "fps": FPS,
                                            "timeout_ms": 30 * 60 * 1000}, timeout=3600)
        if r.status_code != 200 or not r.content:
            raise RuntimeError(f"render failed: {r.text[-400:]}")
        video = os.path.join(tmp, "video.mp4")
        open(video, "wb").write(r.content)

        _stage(job_id, "sound", 5, "Mixing the sound")
        final = os.path.join(tmp, "final.mp4")
        events = motion_sound.plan_events(sfx)
        try:
            lib = await motion_sound.fetch_library({e["kind"] for e in events} | {"explainer_bed"}, tmp)
        except Exception as e:
            print(f"[explainer] sound library unavailable: {e!r}")
            lib = {}
        music = lib.pop("explainer_bed", None)
        if not motion_sound.mix(video, final, duration, events, lib, [{"path": wav, "start": 0.0, "tempo": 1.0}], music):
            r2 = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a",
                                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", final], capture_output=True, text=True)
            if r2.returncode != 0:
                raise RuntimeError("audio mix failed: " + r2.stderr[-300:])

        _stage(job_id, "upload", 6, "Uploading")
        url = await asyncio.to_thread(upload_bytes_to_r2, open(final, "rb").read(), "explainer", "mp4", "video/mp4")
        thumb, thumb_url = os.path.join(tmp, "thumb.jpg"), None
        if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.6", "-i", final, "-frames:v", "1", "-q:v", "3", thumb]).returncode == 0:
            thumb_url = await asyncio.to_thread(upload_bytes_to_r2, open(thumb, "rb").read(), "explainer", "jpg", "image/jpeg")
        _job(job_id).update(status="completed", stage="done", step=STEPS, message="Done", final_video_url=url, thumbnail_url=thumb_url)
    except Exception as e:
        traceback.print_exc()
        _job(job_id).update(status="failed", stage="failed",
                            error=("Anthropic API credit is too low" if isinstance(e, BillingError) else str(e))[:500],
                            traceback=traceback.format_exc()[-3000:])
    finally:
        subprocess.run(["rm", "-rf", tmp])
