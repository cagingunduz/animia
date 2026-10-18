"""
Motion Graphics pipeline — Claude writes the animation as code, HyperFrames renders it.

Crew (each role is its own Claude call, see motion_prompts.py):
  Director        references + brand + brief -> design system + beat list (shot list)
  Animator        one HyperFrames composition per SEGMENT (all beats of up to ~15 s),
                  using the Animave motion kit (render_service/kit.js) to keep code short
  Render engineer lint/render failures -> small find/replace edits
  Critic          contact sheet / motion strip / phone test / loop test / determinism
                  -> 0-10 scores; a segment under REVISE_BELOW gets one find/replace revision
  Sound designer  music bed + transition SFX (ElevenLabs sound generation)

Cost control: every job has a hard Claude budget (BUDGET_PER_SECOND × length, floor
BUDGET_MIN). Mandatory calls (director, first animation of each segment) have capped
output so they always fit; optional calls (critic, revisions, gate revisions, loop test)
only run when their worst-case cost still fits next to the mandatory work left.

Approval gates: the shot list and the style frame (a frame of segment 1). The job waits for
POST /motion/{id}/approve, or carries on by itself after `approval_timeout` seconds.
"""

import asyncio
import base64
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import time
import traceback

import anthropic
import httpx

from jobs import job_store
from storybook_pipeline import upload_bytes_to_r2, download_file
from motion_prompts import (DIRECTOR_SYSTEM, ANIMATOR_SYSTEM, RENDER_ENGINEER_NOTE, CRITIC_SYSTEM,
                            EDIT_NOTE)

# Model per crew role — switchable from Railway without a deploy.
_DEFAULT_MODEL = os.environ.get("MOTION_MODEL", "claude-opus-5-5")
ROLE_MODELS = {
    "director": os.environ.get("MOTION_DIRECTOR_MODEL", _DEFAULT_MODEL),
    "animator": os.environ.get("MOTION_ANIMATOR_MODEL", _DEFAULT_MODEL),
    "critic": os.environ.get("MOTION_CRITIC_MODEL", _DEFAULT_MODEL),
}
RENDER_SERVICE_URL = os.environ.get("RENDER_SERVICE_URL", "").rstrip("/")
RENDER_TOKEN = os.environ.get("RENDER_TOKEN", "")
# $ per million tokens (input, output) by model family. Cache writes cost 1.25×, reads 0.1×.
PRICES = {"opus": (5.0, 25.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0)}

# Hard Claude budget per job: $0.025 per output second → $0.25 for a 10 s video.
BUDGET_PER_SECOND = float(os.environ.get("MOTION_BUDGET_PER_SECOND", "0.025"))
BUDGET_MIN = float(os.environ.get("MOTION_BUDGET_MIN", "0.20"))
SEGMENT_MAX_SECONDS = 15.0

PASS_SCORE = 8.0           # "ships" on the critic's scale
REVISE_BELOW = float(os.environ.get("MOTION_REVISE_BELOW", "7.5"))
MAX_RENDER_FIXES = 2
FPS = 30

FONT_FILE = next((p for p in (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
) if os.path.exists(p)), None)

_gates: dict = {}
_client = None
_render_sem = asyncio.Semaphore(int(os.environ.get("MOTION_RENDER_CONCURRENCY", "2")))
_claude_sem = asyncio.Semaphore(int(os.environ.get("MOTION_CLAUDE_CONCURRENCY", "3")))


# ─────────────────────────── job state helpers ───────────────────────────

def _job(job_id: str) -> dict:
    return job_store[job_id]


def _say(job_id: str, role: str, text: str):
    j = _job(job_id)
    j.setdefault("activity", []).append({"role": role, "text": text, "t": round(time.time(), 1)})
    j["activity"] = j["activity"][-80:]
    j["message"] = text
    print(f"[motion {job_id[:8]}] {role}: {text}")


def _stage(job_id: str, stage: str, step: int):
    j = _job(job_id)
    j["stage"] = stage
    j["step"] = step


def _seg_state(job_id: str, seg: dict, **kw):
    """Update every beat (shot row) that belongs to this segment."""
    ns = {s["n"] for s in seg["shots"]}
    for s in _job(job_id).get("shots", []):
        if s["n"] in ns:
            s.update(kw)


def submit_gate(job_id: str, approved: bool, feedback: str | None) -> bool:
    g = _gates.get(job_id)
    if not g:
        return False
    g["response"] = {"approved": bool(approved), "feedback": (feedback or "").strip()}
    g["event"].set()
    return True


async def _gate(job_id: str, stage: str, timeout: int, **data) -> dict:
    """Pause for the user. Returns {"approved": bool, "feedback": str, "auto": bool}."""
    j = _job(job_id)
    if j.get("auto_approve"):
        return {"approved": True, "feedback": "", "auto": True}
    ev = asyncio.Event()
    _gates[job_id] = {"event": ev, "response": None}
    j["gate"] = {"stage": stage, "deadline": time.time() + timeout, "timeout": timeout, **data}
    j["status"] = "awaiting_approval"
    try:
        await asyncio.wait_for(ev.wait(), timeout)
        resp = _gates[job_id]["response"] or {"approved": True, "feedback": ""}
        resp["auto"] = False
    except asyncio.TimeoutError:
        resp = {"approved": True, "feedback": "", "auto": True}
    finally:
        _gates.pop(job_id, None)
        j["gate"] = None
        j["status"] = "processing"
    return resp



# ─────────────────────────── budget ───────────────────────────

def _model(job_id: str, role: str) -> str:
    override = (_job(job_id).get("models") or {}).get(role)
    return override or ROLE_MODELS[role]


def _price(model: str) -> tuple[float, float]:
    return next((v for k, v in PRICES.items() if k in model), PRICES["opus"])


def _image_tokens(b64: str) -> int:
    try:
        import cv2
        import numpy as np
        im = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_UNCHANGED)
        h, w = im.shape[:2]
        scale = min(1.0, 1568 / max(w, h))
        return int(w * scale * h * scale / 750) + 1
    except Exception:
        return 1600


def _input_tokens(system: str, content) -> int:
    n = int(len(system) / 3.2 * 1.25)  # worst case: a cache write
    for c in content if isinstance(content, list) else [{"type": "text", "text": str(content)}]:
        if c.get("type") == "image":
            n += _image_tokens(c["source"]["data"])
        else:
            n += int(len(c.get("text", "")) / 3.2)
    return n + 200  # tools / framing


def _est_cost(job_id: str, role: str, system: str, content, max_out: int) -> float:
    pin, pout = _price(_model(job_id, role))
    return (_input_tokens(system, content) * pin + max_out * pout) / 1e6


def _budget(job_id: str) -> dict:
    return _job(job_id).setdefault("budget", {"limit": BUDGET_MIN, "reserved": 0.0, "future": 0.0})


def _affordable(job_id: str, est: float) -> bool:
    b = _budget(job_id)
    spent = _job(job_id).get("usage", {}).get("cost_usd", 0.0)
    return spent + b["reserved"] + b["future"] + est <= b["limit"] + 1e-9


# ─────────────────────────── Claude ───────────────────────────

class BillingError(RuntimeError):
    """The Anthropic account is out of credit — no point retrying anything."""


class OverBudget(RuntimeError):
    """An optional step was skipped because it would break the job's cost ceiling."""


def _anthropic():
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


async def _claude(job_id: str, system: str, content, max_tokens: int, role: str,
                  tool: dict | None = None, optional: bool = False, mandatory_slot: float = 0.0):
    """One Claude call under the job's budget.

    optional=True  -> raise OverBudget instead of calling when the worst case doesn't fit.
    mandatory_slot -> the part of budget["future"] this call was reserved under (released here).
    Returns the text, or with `tool` the tool's input dict.
    """
    est = _est_cost(job_id, role, system, content, max_tokens)
    b = _budget(job_id)
    if optional and not _affordable(job_id, est):
        raise OverBudget(f"{role}: ${est:.3f} would exceed the ${b['limit']:.2f} ceiling")
    b["future"] = max(0.0, b["future"] - mandatory_slot)
    b["reserved"] += est
    kw = {"tools": [tool], "tool_choice": {"type": "tool", "name": tool["name"]}} if tool else {}
    model = _model(job_id, role)
    try:
        async with _claude_sem:
            async with _anthropic().messages.stream(
                model=model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}], **kw,
            ) as stream:
                msg = await stream.get_final_message()
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e).lower():
            _job(job_id)["billing_exhausted"] = True
            raise BillingError("Anthropic API credit balance is too low") from e
        raise
    finally:
        b["reserved"] = max(0.0, b["reserved"] - est)

    u = msg.usage
    pin, pout = _price(model)
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cost = ((u.input_tokens or 0) * pin + cw * pin * 1.25 + cr * pin * 0.1 + (u.output_tokens or 0) * pout) / 1e6
    usage = _job(job_id).setdefault("usage", {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    usage["calls"] += 1
    usage["input_tokens"] += (u.input_tokens or 0) + cw + cr
    usage["output_tokens"] += u.output_tokens or 0
    usage["cost_usd"] = round(usage["cost_usd"] + cost, 5)
    r = usage.setdefault("by_role", {}).setdefault(role, {"model": model, "calls": 0, "output_tokens": 0, "cost_usd": 0.0})
    r["calls"] += 1
    r["output_tokens"] += u.output_tokens or 0
    r["cost_usd"] = round(r["cost_usd"] + cost, 5)

    if tool:
        for blk in msg.content:
            if getattr(blk, "type", "") == "tool_use":
                return dict(blk.input)
        raise ValueError("model did not return the structured result")
    return "".join(blk.text for blk in msg.content if getattr(blk, "type", "") == "text")


_OBJ = {"type": "object"}
PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the production plan (design system + shot list).",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "concept": {"type": "string"},
            "reference_analysis": {"type": "string"},
            "design": {
                "type": "object",
                "properties": {
                    "palette": _OBJ, "fonts": _OBJ, "texture": {"type": "string"},
                    "motion_language": {"type": "string"}, "rules": {"type": "array", "items": {"type": "string"}},
                },
            },
            "shots": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "duration": {"type": "number"}, "purpose": {"type": "string"},
                        "on_screen_text": {"type": "string"}, "visual": {"type": "string"},
                        "motion": {"type": "string"}, "transition_out": {"type": "string"},
                        "sfx": {"type": "string", "enum": ["none", "whoosh", "impact", "pop", "riser", "click"]},
                    },
                    "required": ["duration", "visual", "motion"],
                },
            },
            "sound": {"type": "object", "properties": {"music_prompt": {"type": "string"}, "mood": {"type": "string"}}},
        },
        "required": ["title", "concept", "design", "shots"],
    },
}
REVIEW_TOOL = {
    "name": "submit_review",
    "description": "Submit the review of this shot.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "properties": {k: {"type": "number"} for k in ("hook", "readability", "composition", "brand", "motion")},
            },
            "overall": {"type": "number"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"t": {"type": ["number", "null"]}, "problem": {"type": "string"}, "fix": {"type": "string"}},
                    "required": ["problem"],
                },
            },
            "verdict": {"type": "string"},
        },
        "required": ["scores", "overall", "issues", "verdict"],
    },
}



EDIT_TOOL = {
    "name": "apply_edits",
    "description": "Exact find/replace edits to apply to the current HTML document, in order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "edits": {
                "type": "array",
                "items": {"type": "object", "properties": {"find": {"type": "string"}, "replace": {"type": "string"}},
                          "required": ["find", "replace"]},
            },
            "note": {"type": "string"},
        },
        "required": ["edits"],
    },
}


def _extract_html(text: str) -> str:
    blocks = re.findall(r"```html\s*(.*?)```", text, flags=re.S | re.I)
    if not blocks:
        blocks = re.findall(r"```\s*(<!doctype.*?|<html.*?)```", text, flags=re.S | re.I)
    if blocks:
        return max(blocks, key=len).strip()
    i = text.lower().find("<!doctype")
    if i < 0:
        i = text.lower().find("<html")
    if i >= 0:
        return text[i:].strip()
    raise ValueError("animator returned no HTML")


def _img(b: bytes, media: str = "image/jpeg") -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(b).decode()}}


def _data_url_bytes(data_url: str) -> tuple[bytes, str]:
    m = re.match(r"data:([\w/+.-]+);base64,(.*)", data_url or "", flags=re.S)
    if not m:
        raise ValueError("bad data url")
    return base64.b64decode(m.group(2)), m.group(1)


def _apply_edits(html: str, edits: list) -> tuple[str, int]:
    applied = 0
    for e in edits or []:
        f, r = e.get("find", ""), e.get("replace", "")
        if f and f in html:
            html = html.replace(f, r, 1)
            applied += 1
    return html, applied


# ─────────────────────────── geometry ───────────────────────────

def _canvas(aspect: str) -> tuple[int, int]:
    # Compositions are always authored at 1080-class size; 720p is a downscale at assembly.
    return {"9:16": (1080, 1920), "1:1": (1080, 1080)}.get(aspect, (1920, 1080))


def _output_size(aspect: str, resolution: str) -> tuple[int, int]:
    w, h = _canvas(aspect)
    if resolution == "720p":
        return (w * 2 // 3) // 2 * 2, (h * 2 // 3) // 2 * 2
    return w, h


def _phone_size(aspect: str) -> tuple[int, int]:
    # How big the video really is on a phone held upright, in CSS pixels.
    return {"9:16": (390, 693), "1:1": (390, 390)}.get(aspect, (390, 219))


# ─────────────────────────── ffmpeg review tools ───────────────────────────

def _ff(args: list) -> bool:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print("[motion ffmpeg]", r.stderr[-800:])
    return r.returncode == 0


def _stamp(expr_time: str = "%{pts\\:hms}") -> str:
    if not FONT_FILE:
        return ""
    return (f",drawtext=fontfile='{FONT_FILE}':text='{expr_time}':x=8:y=8:fontsize=22:"
            "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=4")


def _sheet(video: str, out: str, pre: str, tile: str) -> bool:
    # Timestamps are burned in when ffmpeg has drawtext; otherwise the sheet goes without them.
    for stamp in ((_stamp(), "") if _stamp() else ("",)):
        if _ff(["-i", video, "-vf", f"{pre}{stamp},{tile}", "-frames:v", "1", "-q:v", "3", out]):
            return True
    return False


def _contact_sheet(video: str, out: str, duration: float, aspect: str) -> bool:
    n = max(2, math.ceil(duration * 2))
    cols = 6 if aspect == "9:16" else 4
    rows = math.ceil(n / cols)
    tw = 180 if aspect == "9:16" else 320
    return _sheet(video, out, f"fps=2,scale={tw}:-2", f"tile={cols}x{rows}:padding=4:color=0x222222")


def _motion_strip(video: str, out: str, duration: float, aspect: str) -> bool:
    head = min(1.0, duration / 2)
    tail_start = max(head, duration - 0.5)
    tw = 140 if aspect == "9:16" else 240
    sel = f"select='lt(t\\,{head:.2f})+gte(t\\,{tail_start:.2f})'"
    return _sheet(video, out, f"fps=10,{sel},scale={tw}:-2", "tile=5x3:padding=3:color=0x222222")


def _frame_at(video: str, t: float, out: str, size: tuple[int, int] | None = None) -> bool:
    vf = ["-vf", f"scale={size[0]}:{size[1]}"] if size else []
    return _ff(["-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1", *vf, "-q:v", "2", out])


def _probe_duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _reference_sheets(frames: list, tmp: str) -> list[bytes]:
    """Browser-extracted reference video frames [{t, data_url}] -> timestamped contact sheets."""
    import cv2
    import numpy as np
    tiles = []
    for f in frames[:72]:
        try:
            raw, _ = _data_url_bytes(f.get("data_url", ""))
            im = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if im is None:
                continue
            h, w = im.shape[:2]
            tw = 320
            im = cv2.resize(im, (tw, max(1, int(h * tw / w))))
            label = f"{float(f.get('t', 0)):.1f}s"
            cv2.rectangle(im, (0, 0), (78, 26), (0, 0, 0), -1)
            cv2.putText(im, label, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(im)
        except Exception:
            continue
    if not tiles:
        return []
    th = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, th - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(34, 34, 34)) for t in tiles]
    cols = 5 if tiles[0].shape[0] > tiles[0].shape[1] else 4
    per_sheet = cols * 4
    sheets = []
    for i in range(0, len(tiles), per_sheet):
        chunk = tiles[i:i + per_sheet]
        while len(chunk) % cols:
            chunk.append(np.full_like(chunk[0], 34))
        rows = [np.hstack(chunk[r:r + cols]) for r in range(0, len(chunk), cols)]
        ok, buf = cv2.imencode(".jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
        if ok:
            sheets.append(buf.tobytes())
    return sheets[:3]


# ─────────────────────────── render service ───────────────────────────

async def _render_call(path: str, payload: dict, timeout: float = 900.0) -> httpx.Response:
    if not RENDER_SERVICE_URL:
        raise RuntimeError("RENDER_SERVICE_URL is not set — deploy render_service/ and point the backend at it")
    headers = {"x-render-token": RENDER_TOKEN} if RENDER_TOKEN else {}
    async with _render_sem:
        async with httpx.AsyncClient(timeout=timeout) as c:
            return await c.post(f"{RENDER_SERVICE_URL}{path}", json=payload, headers=headers)


def _project(html: str, assets: dict) -> dict:
    return {"files": {"index.html": html}, "binary_files": assets}


async def _snapshot(html: str, assets: dict, at: list[float]) -> list[bytes]:
    r = await _render_call("/snapshot", {**_project(html, assets), "at": at}, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"snapshot failed: {r.text[:1500]}")
    return [base64.b64decode(f["png"]) for f in r.json().get("frames", [])]


_FORBIDDEN = [
    (r"Math\.random\s*\(", "Math.random() — use anime.createSeededRandom(seed)"),
    (r"Date\.now|new Date\(", "Date — rendering must not read the clock"),
    (r"performance\.now", "performance.now — rendering must not read the clock"),
    (r"requestAnimationFrame", "requestAnimationFrame — the renderer owns the clock"),
    (r"set(Timeout|Interval)\s*\(", "setTimeout/setInterval — build everything synchronously"),
    (r"\bfetch\s*\(|XMLHttpRequest|WebSocket", "network access — no fetching in compositions"),
    (r"<script[^>]+src=[\"'](?!lib/(?:anime\.umd\.min|kit)\.js)", "external script — only lib/anime.umd.min.js and lib/kit.js are allowed"),
    (r"<(video|audio)\b", "video/audio elements — motion graphics are pure HTML/SVG"),
]


def _static_problems(html: str) -> list[str]:
    probs = [msg for pat, msg in _FORBIDDEN if re.search(pat, html)]
    if "__hfAnime" not in html and "K.timeline" not in html:
        probs.append("no timeline registered on window.__hfAnime")
    if 'data-composition-id="shot"' not in html:
        probs.append('root element must have data-composition-id="shot"')
    return probs



# ─────────────────────────── output budgets ───────────────────────────

def _director_max_out(total: float) -> int:
    return int(min(5000, 1000 + 90 * total))


def _animator_max_out(seconds: float) -> int:
    return int(min(9000, max(3000, 450 * seconds)))


CRITIC_MAX_OUT = 700
EDIT_MAX_OUT = 1500


# ─────────────────────────── render with repairs ───────────────────────────

async def _edit(job_id: str, ctx: list, html: str, problem: str, optional: bool = True) -> str | None:
    """Ask the animator for find/replace edits. Returns the edited HTML, or None."""
    res = await _claude(job_id, ANIMATOR_SYSTEM, [
        *ctx, {"type": "text", "text": f"{problem}\n\n{EDIT_NOTE}\n\nCURRENT HTML:\n```html\n{html}\n```"},
    ], max_tokens=EDIT_MAX_OUT, role="animator", tool=EDIT_TOOL, optional=optional)
    new, applied = _apply_edits(html, res.get("edits", []))
    return new if applied else None


async def _render(job_id: str, label: str, html: str, assets: dict, out_path: str, ctx: list) -> tuple[str, bool]:
    """Render; on lint/render errors ask for small fixes (budget permitting)."""
    for attempt in range(MAX_RENDER_FIXES + 1):
        problems = _static_problems(html)
        if not problems:
            r = await _render_call("/render", {**_project(html, assets), "quality": "standard"})
            if r.status_code == 200 and r.content:
                with open(out_path, "wb") as f:
                    f.write(r.content)
                return html, True
            try:
                error = json.dumps(r.json())[:4000]
            except Exception:
                error = r.text[:3000]
        else:
            error = "Static check failed:\n- " + "\n- ".join(problems)
        if attempt == MAX_RENDER_FIXES:
            break
        _say(job_id, "Render engineer", f"{label}: fixing a render error.")
        try:
            fixed = await _edit(job_id, ctx, html, f"{RENDER_ENGINEER_NOTE}\n\nERROR:\n{error}", optional=True)
        except OverBudget:
            _say(job_id, "Render engineer", f"{label}: no budget left for another fix.")
            break
        if not fixed:
            break
        html = fixed
    return html, False


# ─────────────────────────── crew ───────────────────────────

def _brief_text(p: dict) -> str:
    brand = p.get("brand") or {}
    lines = [
        f"BRIEF: {p.get('prompt', '').strip()}",
        f"Title: {p.get('title') or '(none)'}",
        f"Total length: {p.get('duration_seconds', 15)} seconds",
        f"Format: {p.get('aspect_ratio', '16:9')} ({'x'.join(map(str, _canvas(p.get('aspect_ratio', '16:9'))))} px canvas)",
        f"Loop seamlessly: {'yes' if p.get('loop') else 'no'}",
    ]
    if any(brand.get(k) for k in ("name", "colors", "fonts", "tone", "notes", "logo_data_url")):
        lines.append("BRAND KIT (law):")
        if brand.get("name"):
            lines.append(f"- Brand name: {brand['name']}")
        if brand.get("colors"):
            lines.append(f"- Colours: {', '.join(brand['colors'])}")
        if brand.get("fonts"):
            lines.append(f"- Fonts: {', '.join(brand['fonts'])}")
        if brand.get("tone"):
            lines.append(f"- Tone of voice: {brand['tone']}")
        if brand.get("notes"):
            lines.append(f"- Notes: {brand['notes']}")
        if brand.get("logo_data_url"):
            lines.append("- A logo file is available to animators as assets/logo.png (use it in the closing beat).")
    return "\n".join(lines)



async def _direct(job_id: str, p: dict, ref_images: list[bytes], ref_sheets: list[bytes],
                  previous: dict | None = None, feedback: str = "", optional: bool = False,
                  mandatory_slot: float = 0.0) -> dict:
    content = []
    for b in ref_images:
        content.append({"type": "text", "text": "REFERENCE IMAGE (borrow palette/type/texture, not content):"})
        content.append(_img(b))
    if ref_sheets:
        content.append({"type": "text", "text": "REFERENCE VIDEO as timestamped contact sheets (read left→right, top→bottom). "
                                                 "Analyse its shots, cut points, holds and motion vocabulary first:"})
        for s in ref_sheets:
            content.append(_img(s))
    content.append({"type": "text", "text": _brief_text(p)})
    if previous:
        content.append({"type": "text", "text": "YOUR PREVIOUS PLAN:\n" + json.dumps(previous, ensure_ascii=False)
                        + f"\n\nTHE CLIENT'S NOTES — revise the plan accordingly:\n{feedback}"})
    total = float(p.get("duration_seconds", 15))
    plan = await _claude(job_id, DIRECTOR_SYSTEM, content, max_tokens=_director_max_out(total), role="director",
                         tool=PLAN_TOOL, optional=optional, mandatory_slot=mandatory_slot)
    return _normalise_plan(plan, total)


def _normalise_plan(plan: dict, total: float) -> dict:
    shots = [s for s in plan.get("shots", []) if isinstance(s, dict)][:24]
    if not shots:
        raise ValueError("director returned no shots")
    for s in shots:
        try:
            s["duration"] = max(1.0, min(8.0, float(s.get("duration", 3))))
        except (TypeError, ValueError):
            s["duration"] = 3.0
    # Make the shots add up to the requested length exactly.
    scale = total / sum(s["duration"] for s in shots)
    for s in shots:
        s["duration"] = round(max(1.0, s["duration"] * scale), 2)
    drift = round(total - sum(s["duration"] for s in shots), 2)
    shots[-1]["duration"] = round(max(1.0, shots[-1]["duration"] + drift), 2)
    for i, s in enumerate(shots):
        s["n"] = i + 1
        s["id"] = f"s{i + 1}"
    plan["shots"] = shots
    plan.setdefault("design", {})
    plan.setdefault("sound", {})
    return plan


def _segments(plan: dict) -> list[dict]:
    """Group consecutive beats into the fewest evenly sized segments (~≤ SEGMENT_MAX_SECONDS):
    each beat goes to the segment its midpoint falls in."""
    shots = plan["shots"]
    total = sum(s["duration"] for s in shots)
    n = max(1, math.ceil(total / SEGMENT_MAX_SECONDS - 1e-6))
    target = total / n
    groups: dict[int, list] = {}
    t = 0.0
    for s in shots:
        groups.setdefault(min(n - 1, int((t + s["duration"] / 2) // target)), []).append(s)
        t += s["duration"]
    segs = [groups[k] for k in sorted(groups)]
    out, t = [], 0.0
    for i, beats in enumerate(segs):
        d = round(sum(b["duration"] for b in beats), 2)
        out.append({"n": i + 1, "shots": beats, "start": round(t, 2), "duration": d})
        t += d
    return out


def _segment_brief(p: dict, plan: dict, seg: dict, n_segs: int) -> str:
    w, h = _canvas(p.get("aspect_ratio", "16:9"))
    minfont = round(min(w, h) * 0.045)
    beats, t = [], 0.0
    for b in seg["shots"]:
        beats.append({"beat": b["n"], "starts_at_ms": int(t * 1000), "duration_s": b["duration"],
                      **{k: b.get(k) for k in ("purpose", "on_screen_text", "visual", "motion", "transition_out")}})
        t += b["duration"]
    return "\n".join(filter(None, [
        f"CANVAS: W={w} H={h}. DURATION={seg['duration']} seconds. MINFONT={minfont}px.",
        f"VIDEO: \"{plan.get('title', '')}\" — {plan.get('concept', '')}",
        f"BRIEF: {p.get('prompt', '').strip()}",
        "DESIGN SYSTEM: " + json.dumps(plan.get("design", {}), ensure_ascii=False),
        f"SEGMENT {seg['n']} of {n_segs} — its beats, times relative to this composition:",
        json.dumps(beats, ensure_ascii=False),
        "PREVIOUS SEGMENT: " + ("ends with: " + str(plan["shots"][seg["shots"][0]["n"] - 2].get("transition_out", ""))
                                if seg["n"] > 1 else "none — this segment opens the video"),
        "ASSETS: " + ("assets/logo.png (brand logo)" if (p.get("brand") or {}).get("logo_data_url") else "none"),
        _brand_lines(p),
    ]))


def _brand_lines(p: dict) -> str:
    brief = _brief_text(p)
    return "BRAND KIT (law):" + brief.split("BRAND KIT (law):", 1)[1] if "BRAND KIT (law):" in brief else ""


def _animator_ctx(p: dict, plan: dict, seg: dict, n_segs: int, anchor_html: str | None) -> list:
    ctx = [{"type": "text", "text": _segment_brief(p, plan, seg, n_segs)}]
    if anchor_html:
        ctx.append({"type": "text", "text": "STYLE ANCHOR — segment 1 as approved. Match its look, type treatment, "
                                            "texture and motion feel exactly (different content):\n```html\n" + anchor_html + "\n```"})
    return ctx


async def _animate(job_id: str, ctx: list, seconds: float, mandatory_slot: float) -> str:
    text = await _claude(job_id, ANIMATOR_SYSTEM, [*ctx, {"type": "text", "text": "Write this segment now."}],
                         max_tokens=_animator_max_out(seconds), role="animator", mandatory_slot=mandatory_slot)
    return _extract_html(text)


async def _critique(job_id: str, p: dict, plan: dict, seg: dict, video: str, tmp: str,
                    html: str, assets: dict, loop_pair: bytes | None = None) -> dict:
    aspect = p.get("aspect_ratio", "16:9")
    d = seg["duration"]
    base = os.path.join(tmp, f"crit_{seg['n']}_{int(time.time() * 1000)}")
    sheet, strip, phone = base + "_sheet.jpg", base + "_strip.jpg", base + "_phone.jpg"
    _contact_sheet(video, sheet, d, aspect)
    _motion_strip(video, strip, d, aspect)
    _frame_at(video, d * 0.7, phone, _phone_size(aspect))

    notes = []
    try:  # determinism: the same frame rendered twice must be byte-identical (no tokens)
        t = round(d * 0.55, 2)
        a, b = await asyncio.gather(_snapshot(html, assets, [t]), _snapshot(html, assets, [t]))
        if a and b and hashlib.sha256(a[0]).digest() != hashlib.sha256(b[0]).digest():
            notes.append(f"DETERMINISM: frame at {t}s differs between two renders (unseeded randomness or clock use).")
    except Exception as e:
        print(f"[motion] determinism test skipped: {e}")

    content = [{"type": "text", "text": "CONTACT SHEET (2 fps):"}]
    if os.path.exists(sheet):
        content.append(_img(open(sheet, "rb").read()))
    if os.path.exists(strip):
        content += [{"type": "text", "text": "MOTION STRIP (10 fps, entrance then exit):"}, _img(open(strip, "rb").read())]
    if os.path.exists(phone):
        content += [{"type": "text", "text": f"PHONE TEST (real on-phone size, {aspect}):"}, _img(open(phone, "rb").read())]
    if loop_pair:
        content += [{"type": "text", "text": "LOOP TEST — left: last frame of the video, right: first frame. "
                                             "They must join without a visible jump:"}, _img(loop_pair)]
    beats = [{k: b.get(k) for k in ("n", "duration", "on_screen_text", "visual", "motion")} for b in seg["shots"]]
    content.append({"type": "text", "text": "\n".join([
        f"SEGMENT {seg['n']}, {d}s. BRIEF: {p.get('prompt', '').strip()[:1200]}",
        "BEATS: " + json.dumps(beats, ensure_ascii=False),
        "DESIGN SYSTEM: " + json.dumps(plan.get("design", {}), ensure_ascii=False),
        "AUTOMATED FINDINGS: " + ("; ".join(notes) if notes else "none"),
        "Treat this whole segment as the unit under review.",
    ])})
    review = await _claude(job_id, CRITIC_SYSTEM, content, max_tokens=CRITIC_MAX_OUT, role="critic",
                           tool=REVIEW_TOOL, optional=True)
    try:
        review["overall"] = float(review.get("overall", 0))
    except (TypeError, ValueError):
        review["overall"] = 0.0
    if any(n.startswith("DETERMINISM") for n in notes):
        review["overall"] = min(review["overall"], 6.0)
        review.setdefault("issues", []).insert(0, {"t": None, "problem": notes[0], "fix": "Remove clock/randomness use."})
    return review


async def _upload_thumb(video: str, t: float, tmp: str, tag: str) -> str | None:
    p = os.path.join(tmp, f"thumb_{tag}.jpg")
    if _frame_at(video, t, p, None):
        try:
            return upload_bytes_to_r2(open(p, "rb").read(), "motion-thumbs", "jpg", "image/jpeg")
        except Exception:
            return None
    return None



async def _beat_thumbs(job_id: str, seg: dict, video: str, tmp: str):
    t = 0.0
    for b in seg["shots"]:
        url = await _upload_thumb(video, t + b["duration"] * 0.6, tmp, f"{seg['n']}_{b['n']}")
        for s in _job(job_id).get("shots", []):
            if s["n"] == b["n"]:
                s["thumb_url"] = url
        t += b["duration"]


async def _produce_segment(job_id: str, p: dict, plan: dict, seg: dict, n_segs: int, assets: dict, tmp: str,
                           anchor_html: str | None, first: tuple | None = None) -> dict:
    """Animate → render → critique → one find/replace revision if needed (budget permitting)."""
    label = f"Segment {seg['n']}" if n_segs > 1 else "The video"
    ctx = _animator_ctx(p, plan, seg, n_segs, anchor_html)
    slot = _job(job_id)["budget"]["slots"].get(seg["n"], 0.0)
    if first:
        html, video = first
    else:
        _seg_state(job_id, seg, status="animating")
        _say(job_id, "Animator", f"{label}: writing the animation code.")
        html = await _animate(job_id, ctx, seg["duration"], slot)
        _seg_state(job_id, seg, status="rendering")
        video = os.path.join(tmp, f"seg_{seg['n']}_v1.mp4")
        html, ok = await _render(job_id, label, html, assets, video, ctx)
        if not ok:
            _seg_state(job_id, seg, status="failed")
            return {"ok": False}

    best = {"html": html, "video": video, "score": None, "review": None}
    _seg_state(job_id, seg, status="reviewing")
    try:
        _say(job_id, "Critic", f"{label}: reviewing contact sheet, motion strip and phone test.")
        review = await _critique(job_id, p, plan, seg, video, tmp, html, assets)
        best.update(score=review["overall"], review=review)
        _say(job_id, "Critic", f"{label}: {review['overall']:.1f}/10 — {review.get('verdict', '')}")
        _seg_state(job_id, seg, score=round(review["overall"], 1), scores=review.get("scores", {}),
                   issues=review.get("issues", [])[:6], attempts=1)
    except OverBudget as e:
        _say(job_id, "Critic", f"{label}: review skipped to stay within budget.")
        print(f"[motion] {e}")
        review = None
    except BillingError:
        raise
    except Exception as e:
        print(f"[motion] review failed: {e!r}")
        review = None

    if review and review["overall"] < REVISE_BELOW and review.get("issues"):
        _seg_state(job_id, seg, status="revising")
        try:
            _say(job_id, "Animator", f"{label}: fixing the critic's notes (targeted edits).")
            issues = json.dumps(review.get("issues", []), ensure_ascii=False)
            fixed = await _edit(job_id, ctx, html, f"The director rejected this version ({review['overall']:.1f}/10). "
                                                   f"Fix these issues:\n{issues}", optional=True)
            if fixed:
                out2 = os.path.join(tmp, f"seg_{seg['n']}_v2.mp4")
                _seg_state(job_id, seg, status="rendering")
                fixed, ok = await _render(job_id, label, fixed, assets, out2, ctx)
                if ok:
                    best.update(html=fixed, video=out2)
                    _seg_state(job_id, seg, attempts=2)
                    try:  # re-score only if the budget still allows it
                        r2 = await _critique(job_id, p, plan, seg, out2, tmp, fixed, assets)
                        best.update(score=r2["overall"], review=r2)
                        _seg_state(job_id, seg, score=round(r2["overall"], 1), scores=r2.get("scores", {}),
                                   issues=r2.get("issues", [])[:6])
                        _say(job_id, "Critic", f"{label}: revised version {r2['overall']:.1f}/10.")
                    except OverBudget:
                        pass
        except OverBudget:
            _say(job_id, "Animator", f"{label}: revision skipped to stay within budget.")
        except BillingError:
            pass

    await _beat_thumbs(job_id, seg, best["video"], tmp)
    try:
        vurl = upload_bytes_to_r2(open(best["video"], "rb").read(), "motion-shots", "mp4", "video/mp4")
    except Exception:
        vurl = None
    seg["video_url"] = vurl
    _seg_state(job_id, seg, status="completed")
    return {"ok": True, **best}


# ─────────────────────────── sound ───────────────────────────

async def _sound_gen(text: str, seconds: float) -> bytes | None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post("https://api.elevenlabs.io/v1/sound-generation",
                             headers={"xi-api-key": key, "Content-Type": "application/json"},
                             json={"text": text, "duration_seconds": max(0.5, min(22.0, seconds)), "prompt_influence": 0.45})
        if r.status_code == 200 and r.content:
            return r.content
        print(f"[motion sound] {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"[motion sound] {e}")
    return None


SFX_PROMPTS = {
    "whoosh": "short clean whoosh transition, modern motion graphics",
    "impact": "short punchy low impact hit, cinematic, tight",
    "pop": "short soft UI pop, playful",
    "riser": "short tension riser into a hit",
    "click": "crisp UI click",
}


async def _sound_design(job_id: str, plan: dict, total: float, tmp: str) -> tuple[str | None, list]:
    """Returns (music_path, [(time, sfx_path)])."""
    music_prompt = (plan.get("sound") or {}).get("music_prompt") or "minimal modern instrumental motion graphics music bed, steady pulse"
    _say(job_id, "Sound designer", "Scoring a music bed and transition sounds.")
    music_task = _sound_gen(f"Instrumental music, no vocals: {music_prompt}", min(22.0, total))
    kinds = sorted({s.get("sfx") for s in plan["shots"][1:] if s.get("sfx") in SFX_PROMPTS})
    sfx_bytes = await asyncio.gather(music_task, *[_sound_gen(SFX_PROMPTS[k], 1.2) for k in kinds])
    music = sfx_bytes[0]
    music_path = None
    if music:
        music_path = os.path.join(tmp, "music.mp3")
        open(music_path, "wb").write(music)
    files = {}
    for k, b in zip(kinds, sfx_bytes[1:]):
        if b:
            files[k] = os.path.join(tmp, f"sfx_{k}.mp3")
            open(files[k], "wb").write(b)
    cues, t = [], 0.0
    for s in plan["shots"]:
        if s["n"] > 1 and s.get("sfx") in files:
            cues.append((max(0.0, t - 0.15), files[s["sfx"]]))
        t += s["duration"]
    return music_path, cues


# ─────────────────────────── assembly ───────────────────────────

def _assemble(videos: list[str], out: str, size: tuple[int, int], total: float,
              music: str | None, cues: list, tmp: str) -> bool:
    listing = os.path.join(tmp, "concat.txt")
    with open(listing, "w") as f:
        for v in videos:
            f.write(f"file '{v}'\n")
    silent = os.path.join(tmp, "joined.mp4")
    if not _ff(["-f", "concat", "-safe", "0", "-i", listing, "-vf", f"scale={size[0]}:{size[1]}:flags=lanczos,fps={FPS}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an", silent]):
        return False
    dur = _probe_duration(silent) or total
    if not music and not cues:
        os.replace(silent, out)
        return True
    inputs, parts = ["-i", silent], []
    idx = 1
    if music:
        inputs += ["-stream_loop", "-1", "-i", music]
        fade = max(0.0, dur - 1.2)
        parts.append(f"[{idx}:a]atrim=0:{dur:.2f},afade=t=in:d=0.4,afade=t=out:st={fade:.2f}:d=1.2,volume=0.45[m]")
        idx += 1
    labels = ["[m]"] if music else []
    for j, (at, path) in enumerate(cues):
        inputs += ["-i", path]
        ms = int(at * 1000)
        parts.append(f"[{idx}:a]volume=0.9,adelay={ms}|{ms}[s{j}]")
        labels.append(f"[s{j}]")
        idx += 1
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{dur:.2f}[a]")
    return _ff([*inputs, "-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out])



# ─────────────────────────── main ───────────────────────────

async def run_motion_pipeline(job_id: str, p: dict):
    j = _job(job_id)
    timeout = int(p.get("approval_timeout") or 600)
    aspect = p.get("aspect_ratio", "16:9")
    total = float(p.get("duration_seconds") or 15)
    b = _budget(job_id)
    b["limit"] = round(max(BUDGET_MIN, BUDGET_PER_SECOND * total), 3)
    b["slots"] = {}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            j["total_steps"] = 6

            # ── 1. References ──
            _stage(job_id, "analyzing", 1)
            ref_images = []
            for u in (p.get("reference_images") or [])[:2]:
                try:
                    ref_images.append(_data_url_bytes(u)[0] if u.startswith("data:") else await download_file(u))
                except Exception as e:
                    print(f"[motion] reference image skipped: {e}")
            ref_sheets = _reference_sheets(p.get("reference_video_frames") or [], tmp)
            if ref_images or ref_sheets:
                _say(job_id, "Director", f"Studying {len(ref_images)} reference image(s) and "
                                         f"{len(p.get('reference_video_frames') or [])} reference video frame(s).")
            assets = {}
            logo = (p.get("brand") or {}).get("logo_data_url")
            if logo:
                try:
                    assets["assets/logo.png"] = base64.b64encode(_data_url_bytes(logo)[0]).decode()
                except Exception:
                    pass

            # Reserve the animator's worst case before anything else is spent.
            n_guess = max(1, math.ceil(total / SEGMENT_MAX_SECONDS))
            anim_worst = sum(_est_cost(job_id, "animator", ANIMATOR_SYSTEM, [{"type": "text", "text": "x" * 9000}],
                                       _animator_max_out(min(SEGMENT_MAX_SECONDS, total / n_guess))) for _ in range(n_guess))
            b["future"] = anim_worst

            # ── 2. Director: plan + shot-list gate ──
            _stage(job_id, "directing", 2)
            _say(job_id, "Director", "Writing the design system and shot list.")
            plan = await _direct(job_id, p, ref_images, ref_sheets)
            for _ in range(2):
                j["plan"] = plan
                j["shots"] = [{"n": s["n"], "id": s["id"], "duration": s["duration"], "purpose": s.get("purpose"),
                               "on_screen_text": s.get("on_screen_text"), "status": "queued"} for s in plan["shots"]]
                _say(job_id, "Director", f"Shot list ready: {len(plan['shots'])} beats, {total:.0f}s.")
                resp = await _gate(job_id, "shot_list", timeout)
                if resp["approved"] and not resp.get("feedback"):
                    break
                try:
                    _say(job_id, "Director", "Revising the shot list with your notes.")
                    plan = await _direct(job_id, p, ref_images, ref_sheets, previous=plan,
                                         feedback=resp.get("feedback") or "Make it better.", optional=True)
                except OverBudget:
                    _say(job_id, "Director", "The revision budget for this video is used up — continuing with this plan.")
                    break
            j["plan"] = plan

            segs = _segments(plan)
            j["segments"] = [{"n": s["n"], "start": s["start"], "duration": s["duration"],
                              "beats": [x["n"] for x in s["shots"]]} for s in segs]
            # Re-reserve the exact mandatory animator work for the real segments.
            ctx_probe = {s["n"]: _animator_ctx(p, plan, s, len(segs), "x" * 9000 if s["n"] > 1 else None) for s in segs}
            for s in segs:
                b["slots"][s["n"]] = _est_cost(job_id, "animator", ANIMATOR_SYSTEM, ctx_probe[s["n"]],
                                               _animator_max_out(s["duration"]))
            b["future"] = sum(b["slots"].values())

            # ── 3. Style frame (segment 1) + gate ──
            _stage(job_id, "style_frame", 3)
            first = segs[0]
            ctx1 = _animator_ctx(p, plan, first, len(segs), None)
            _seg_state(job_id, first, status="animating")
            _say(job_id, "Animator", "Designing the style frame.")
            anchor = await _animate(job_id, ctx1, first["duration"], b["slots"].pop(first["n"]))
            probe = os.path.join(tmp, "seg_1_v1.mp4")
            anchor, ok = await _render(job_id, "Style frame", anchor, assets, probe, ctx1)
            if not ok:
                raise RuntimeError("the first segment could not be rendered")
            for _ in range(2):
                frame_t = round(min(first["duration"] - 0.2, max(0.6, first["duration"] * 0.35)), 2)
                png = (await _snapshot(anchor, assets, [frame_t]))[0]
                j["style_frame_url"] = upload_bytes_to_r2(png, "motion-style-frames", "png", "image/png")
                _seg_state(job_id, first, thumb_url=j["style_frame_url"], status="awaiting_approval")
                resp = await _gate(job_id, "style_frame", timeout, image_url=j["style_frame_url"])
                if resp["approved"] and not resp.get("feedback"):
                    break
                try:
                    _say(job_id, "Animator", "Applying your notes to the style frame.")
                    fixed = await _edit(job_id, ctx1, anchor, "The client reviewed the style frame. Their notes:\n"
                                        + (resp.get("feedback") or "Make it better."), optional=True)
                    if fixed:
                        fixed, ok = await _render(job_id, "Style frame", fixed, assets, probe, ctx1)
                        if ok:
                            anchor = fixed
                except OverBudget:
                    _say(job_id, "Animator", "The revision budget for this video is used up — continuing with this look.")
                    break

            # ── 4. Every segment: animate, render, critique, targeted fix ──
            _stage(job_id, "animating", 4)
            _say(job_id, "Director", "Style approved. The crew is animating.")
            tasks = [_produce_segment(job_id, p, plan, first, len(segs), assets, tmp, None, first=(anchor, probe))]
            for s in segs[1:]:
                tasks.append(_produce_segment(job_id, p, plan, s, len(segs), assets, tmp, anchor))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            done = []
            for s, r in zip(segs, results):
                if isinstance(r, Exception) or not r.get("ok"):
                    print(f"[motion] segment {s['n']} failed: {r!r}")
                    _seg_state(job_id, s, status="failed")
                    if isinstance(r, BillingError):
                        raise r
                    continue
                done.append((s, r))
            if len(done) < len(segs):
                raise RuntimeError(f"only {len(done)} of {len(segs)} segments could be produced")

            # Optional loop test on the joint between the last and the first frame.
            if p.get("loop"):
                last_s, last_r = done[-1]
                a, bb, pair = (os.path.join(tmp, x) for x in ("loop_a.jpg", "loop_b.jpg", "loop_pair.jpg"))
                size = (270, -2) if aspect == "9:16" else (480, -2)
                _frame_at(last_r["video"], max(0.0, last_s["duration"] - 0.04), a, size)
                _frame_at(done[0][1]["video"], 0.0, bb, size)
                if _ff(["-i", a, "-i", bb, "-filter_complex", "hstack", pair]):
                    try:
                        review = await _critique(job_id, p, plan, last_s, last_r["video"], tmp, last_r["html"], assets,
                                                 loop_pair=open(pair, "rb").read())
                        _say(job_id, "Critic", f"Loop test: {review['overall']:.1f}/10.")
                    except (OverBudget, Exception) as e:
                        print(f"[motion] loop test skipped: {e!r}")

            # ── 5. Sound ──
            _stage(job_id, "sound", 5)
            music, cues = (None, [])
            if p.get("include_music", True):
                music, cues = await _sound_design(job_id, plan, sum(s["duration"] for s, _ in done), tmp)

            # ── 6. Assemble ──
            _stage(job_id, "assembling", 6)
            _say(job_id, "Render engineer", "Assembling the final cut.")
            final = os.path.join(tmp, "final.mp4")
            size = _output_size(aspect, p.get("resolution", "1080p"))
            if not _assemble([r["video"] for _, r in done], final, size, sum(s["duration"] for s, _ in done),
                             music, cues, tmp):
                raise RuntimeError("final assembly failed")
            url = upload_bytes_to_r2(open(final, "rb").read(), "motion-final", "mp4", "video/mp4")

            scores = [r["score"] for _, r in done if r.get("score") is not None]
            j["average_score"] = round(sum(scores) / len(scores), 1) if scores else None
            j["final_video_url"] = url
            j["status"] = "completed"
            j["stage"] = "done"
            j["step"] = j["total_steps"]
            cost = j.get("usage", {}).get("cost_usd", 0.0)
            _say(job_id, "Director", f"Done. Claude cost ${cost:.3f} of a ${b['limit']:.2f} ceiling.")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[motion {job_id[:8]}] FAILED\n{tb}")
        j["status"] = "failed"
        j["error"] = ("Anthropic API credit balance is too low — top up the API account and retry"
                      if isinstance(e, BillingError) or j.get("billing_exhausted") else (str(e) or repr(e)))
        j["traceback"] = tb
        j["gate"] = None
        _gates.pop(job_id, None)
