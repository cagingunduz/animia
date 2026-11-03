"""Long videos (16:9, YouTube): resumable projects made from a template (the first: Flat Explainer).

A project lives in R2 as long/<id>/state.json (plus its assets), so nothing is lost when the server restarts and a
project can always be resumed from the last finished step:

  plan       Claude writes the title, the parts (sections) with their lines, and a shot plan (places, cast, props, shots);
             the user reads / edits it and approves (the site charges the credits on approval)
  art        the style master (the first place), then every place, character pose and prop with it as the reference;
             plates get their blank boards measured; cut-outs are keyed from chroma green
  parts      for each part, in order: voice (Pocket TTS / Kokoro) -> film code (Claude, on the template's kit) -> check
             -> render (chunked) -> sound (voice + foley + bed) -> an mp4 in R2
  final      the parts joined into one mp4 (+ a thumbnail)

Every finished unit (each picture, each part's voice / code / video) is saved before the next starts.
"""

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import tempfile
import time
import traceback
import uuid

import httpx

import long_art
import studio_styles
from jobs import job_store
from motion_pipeline import BillingError
from storybook_pipeline import R2_BUCKET, R2_PUBLIC_BASE, get_r2_client

TEMPLATES = ("flat-explainer", "collage-doc-long", "doc-analysis")
_running: set[str] = set()
_locks: dict[str, asyncio.Lock] = {}


# ─────────────────────────── storage ───────────────────────────

def _key(pid: str, name: str) -> str:
    return f"long/{pid}/{name}"


def _put(pid: str, name: str, data: bytes, ctype: str) -> str:
    get_r2_client().put_object(Bucket=R2_BUCKET, Key=_key(pid, name), Body=data, ContentType=ctype, CacheControl="no-cache")
    return f"{R2_PUBLIC_BASE}/{_key(pid, name)}"


def load(pid: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f-]{36}", pid or ""):
        return None
    try:
        obj = get_r2_client().get_object(Bucket=R2_BUCKET, Key=_key(pid, "state.json"))
        return json.loads(obj["Body"].read())
    except Exception:
        return None


def save(st: dict):
    st["updated"] = time.time()
    _put(st["id"], "state.json", json.dumps(st).encode(), "application/json")


def public(st: dict) -> dict:
    """What the site sees (no internal paths, no film code)."""
    out = {k: v for k, v in st.items() if k not in ("film",)}
    out["running"] = st["id"] in _running
    if st.get("status") in ("planning", "producing") and not out["running"]:
        out["status_note"] = "paused"          # the server restarted mid-way: resume continues from the last finished step
    parts = []
    for p in st.get("parts", []):
        q = {k: v for k, v in p.items() if k not in ("code", "spec", "foley", "timing")}
        if p.get("timing"):
            q["lines"] = [{"text": l["text"], "start": l["start"], "end": l["end"]} for l in p["timing"].get("lines", [])]
        parts.append(q)
    out["parts"] = parts
    return out


def _step(st: dict, stage: str, message: str, progress: float | None = None):
    st.update(stage=stage, message=message)
    if progress is not None:
        st["progress"] = round(max(0.0, min(1.0, progress)), 3)
    job_store[st["id"]] = {**job_store.get(st["id"], {}), "status": "processing", "stage": stage, "message": message}
    print(f"[long {st['id'][:8]}] {stage}: {message}")


# ─────────────────────────── 1. plan ───────────────────────────

PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the video plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "the YouTube title (under 70 characters)"},
            "description": {"type": "string", "description": "a 2-3 sentence YouTube description"},
            "places": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "desc": {"type": "string", "description": "the empty place: what is in it, where its blank board / sign / screen is"}},
                "required": ["id", "desc"]}},
            "cast": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "desc": {"type": "string", "description": "who they are and how they look (clothes, hair, colours)"},
                "poses": {"type": "array", "items": {"type": "string"}, "description": "1-3 poses, e.g. 'standing, pointing up', 'walking, side view', 'seen from behind'"}},
                "required": ["id", "desc", "poses"]}},
            "props": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "desc": {"type": "string"}}, "required": ["id", "desc"]}},
            "sections": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string", "description": "the part's chapter title"},
                "lines": {"type": "array", "items": {"type": "object", "properties": {
                    "text": {"type": "string"}, "say": {"type": "string"}, "pause": {"type": "number"},
                    "mood": {"type": "string", "enum": ["neutral", "deadpan", "excited", "panic", "whisper", "confused", "sad", "angry", "warm"]}},
                    "required": ["text"]}},
                "shots": {"type": "array", "items": {"type": "object", "properties": {
                    "line": {"type": "integer", "description": "0-based line index inside this part"},
                    "at": {"type": "string", "description": "the word the shot starts on"},
                    "place": {"type": "string", "description": "a place id, or 'headline'"},
                    "cast": {"type": "array", "items": {"type": "string"}, "description": "'castid:pose number' entries, e.g. 'viewer:1'"},
                    "props": {"type": "array", "items": {"type": "string"}},
                    "action": {"type": "string", "description": "what happens: who does what, the camera"},
                    "text": {"type": "string", "description": "the words on a surface (and which surface)"},
                    "marks": {"type": "string", "description": "red X / tick / date card / spotlight / counter / icons / headline / splat, with their words"}},
                    "required": ["line", "place", "action"]}}},
                "required": ["title", "lines", "shots"]}},
        },
        "required": ["title", "places", "cast", "sections"],
    },
}


_LINES = {"type": "array", "items": {"type": "object", "properties": {
    "text": {"type": "string"}, "say": {"type": "string"}, "pause": {"type": "number"},
    "mood": {"type": "string", "enum": ["neutral", "deadpan", "excited", "panic", "whisper", "confused", "sad", "angry", "warm"]}},
    "required": ["text"]}}

ARCHIVE_PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the video plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "the YouTube title (under 70 characters)"},
            "description": {"type": "string", "description": "a 2-3 sentence YouTube description"},
            "pictures": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "kind": {"type": "string", "enum": ["plate", "cutout", "document", "portrait"]},
                "search": {"type": "string"}, "alts": {"type": "array", "items": {"type": "string"}},
                "use": {"type": "string", "description": "what it shows in the story (one short sentence)"}},
                "required": ["id", "kind", "search"]}},
            "sections": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string", "description": "the chapter title"},
                "lines": _LINES,
                "shots": {"type": "array", "description": "the picture track", "items": {"type": "object", "properties": {
                    "line": {"type": "integer"}, "at": {"type": "string"},
                    "show": {"type": "array", "items": {"type": "string"}, "description": "picture ids (1-3)"},
                    "words": {"type": "string"}, "ring": {"type": "string"}, "action": {"type": "string", "description": "how they are placed / move"}},
                    "required": ["line", "show"]}}},
                "required": ["title", "lines", "shots"]}},
        },
        "required": ["title", "pictures", "sections"],
    },
}


def plan_system(st: dict) -> str:
    if st.get("art_source") == "mixed":
        return f"""You plan a long YouTube analysis documentary in the {st['name']} style: the script (in chapters) and, for every
shot, its picture layer (A generated illustration, or B real archive footage / photo) and the typography over it. The
pictures are then made or found; an animator adds the typography and the marks over them, chapter by chapter.

{st['plan_md']}

THE LOOK:
{st['style_md']}

THE LINES: `text` is the caption form; `say` the spoken form only when it differs (numbers, symbols). `mood` sets the
delivery; `pause` 0.2-0.5 s. Only true claims."""
    if st.get("art_source") == "archive":
        return f"""You plan a long YouTube documentary in the {st['name']} style: the script (in chapters), the archive pictures
and the picture track. The pictures are then found in open archives; an animator animates each chapter from your track.

{st['plan_md']}

THE LOOK:
{st['style_md']}

THE LINES: `text` is the caption form; `say` the spoken form only when it differs (numbers, symbols). `mood` sets the
delivery; `pause` 0.2-0.6 s. Only true claims."""
    return f"""You plan a long YouTube video in the {st['name']} style: the script (in parts) and the shot plan. The art is
generated from your place, cast and prop descriptions; an animator then animates each part from your shots.

{st['plan_md']}

THE LOOK (for your places, cast and shots):
{st['style_md']}

THE LINES: `text` is the caption form; `say` the spoken form only when it differs (numbers, symbols). `mood` sets the
delivery; `pause` 0.1-0.5 s. Only true claims.
PLACES: an EMPTY place each (no people), described with its blank board / sign / screen where text will go.
CAST: each character's look and the poses the shots need (a pose number is its index from 1).
SHOTS: what is said is what is shown; each starts on the word that names it."""


async def _claude(pid: str, system: str, content, max_tokens: int, role: str, tool: dict | None = None):
    from studio_pipeline import _claude as claude      # same client, usage tracking and billing errors
    job_store.setdefault(pid, {"usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}})
    job_store[pid].setdefault("usage", {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    return await claude(pid, system, content, max_tokens, role, tool=tool)


async def pitch(template: str, hint: str = "") -> list[dict]:
    st = studio_styles.style(template)
    tool = {"name": "pitches", "description": "Three video ideas.", "input_schema": {"type": "object", "properties": {
        "pitches": {"type": "array", "items": {"type": "object", "properties": {"topic": {"type": "string"}, "angle": {"type": "string", "description": "the one shocking true angle"}},
                                               "required": ["topic", "angle"]}}}, "required": ["pitches"]}}
    pid = f"pitch-{uuid.uuid4()}"
    res = await _claude(pid, f"You pitch YouTube explainer topics for the {st['name']} format.\n\n{st['plan_md']}",
                        f"Pitch 3 topics (a what-if, a 'why does X happen', a true story, or how something works), each with one "
                        f"shocking true angle.{(' The creator wants: ' + hint) if hint else ''}", 1500, "pitch", tool)
    job_store.pop(pid, None)
    return [{"topic": str(p.get("topic"))[:120], "angle": str(p.get("angle"))[:240]} for p in (res.get("pitches") or [])][:3]


def _clean_plan(res: dict, st: dict) -> dict:
    slug = long_art.slug
    places = [{"id": slug(p["id"]), "desc": str(p.get("desc") or "")[:500]} for p in res.get("places") or [] if p.get("id")][:24]
    cast = [{"id": slug(c["id"]), "desc": str(c.get("desc") or "")[:400], "poses": [str(x)[:120] for x in (c.get("poses") or ["standing, facing the viewer"])][:3]}
            for c in res.get("cast") or [] if c.get("id")][:12]
    props = [{"id": slug(p["id"]), "desc": str(p.get("desc") or "")[:300]} for p in res.get("props") or [] if p.get("id")][:16]
    sections = []
    for k, sec in enumerate(res.get("sections") or []):
        lines = [{"text": str(l.get("text") or "").strip()[:300], **({"say": str(l["say"])[:300]} if l.get("say") else {}),
                  "pause": float(l.get("pause") or .25), "mood": l.get("mood") or "neutral"} for l in sec.get("lines") or [] if str(l.get("text") or "").strip()]
        if not lines:
            continue
        sections.append({"id": f"p{k + 1}", "title": str(sec.get("title") or f"Part {k + 1}")[:80], "lines": lines,
                         "shots": [{**{kk: v for kk, v in sh.items() if kk in ("at", "place", "cast", "props", "action", "text", "marks")},
                                    "line": int(sh.get("line") or 0)} for sh in sec.get("shots") or []][:80]})
    if not sections or not places:
        raise ValueError("the plan came back empty")
    return {"title": str(res.get("title") or "Untitled")[:100], "description": str(res.get("description") or "")[:600],
            "places": places, "cast": cast, "props": props, "sections": sections}


def _clean_archive_plan(res: dict) -> dict:
    slug = long_art.slug
    pics, seen = [], set()
    for p in res.get("pictures") or []:
        pid = slug(p.get("id") or "")
        if not pid or pid in seen or not str(p.get("search") or "").strip():
            continue
        seen.add(pid)
        pics.append({"id": pid, "kind": p.get("kind") if p.get("kind") in ("plate", "cutout", "document", "portrait") else "document",
                     "search": str(p["search"]).strip()[:160], "alts": [str(a)[:160] for a in (p.get("alts") or [])][:2], "use": str(p.get("use") or "")[:200]})
    sections = []
    for k, sec in enumerate(res.get("sections") or []):
        lines = [{"text": str(l.get("text") or "").strip()[:300], **({"say": str(l["say"])[:300]} if l.get("say") else {}),
                  "pause": float(l.get("pause") or .3), "mood": l.get("mood") or "neutral"} for l in sec.get("lines") or [] if str(l.get("text") or "").strip()]
        if not lines:
            continue
        shots = [{"line": int(sh.get("line") or 0), "at": str(sh.get("at") or "")[:40], "show": [slug(x) for x in sh.get("show") or []][:3],
                  "words": str(sh.get("words") or "")[:60], "ring": str(sh.get("ring") or "")[:40], "action": str(sh.get("action") or "")[:200],
                  "place": slug((sh.get("show") or ["paper"])[0])} for sh in sec.get("shots") or []][:90]
        sections.append({"id": f"p{k + 1}", "title": str(sec.get("title") or f"Chapter {k + 1}")[:80], "lines": lines, "shots": shots})
    if not sections or not pics:
        raise ValueError("the plan came back empty")
    return {"title": str(res.get("title") or "Untitled")[:100], "description": str(res.get("description") or "")[:600],
            "pictures": pics[:90], "places": [], "cast": [], "props": [], "sections": sections}


async def _plan(st_: dict, s: dict):
    _step(s, "plan", "Writing the script and the shot plan", 0.02)
    words = round(s["minutes"] * 60 * st_.get("wps", 3.1))
    ask = (f"The topic: {s['topic'] or 'pick the best one yourself'}\nThe length: {s['minutes']} minutes (about {words} words), "
           f"in parts of 150-280 words.\n" + (f"Notes from the creator: {s['notes']}\n" if s.get("notes") else "") + "Write the plan.")
    src = st_.get("art_source")
    tool = ARCHIVE_PLAN_TOOL if src == "archive" else MIXED_PLAN_TOOL if src == "mixed" else PLAN_TOOL
    res = await _claude(s["id"], plan_system(st_), ask, 32000, "plan", tool)
    s["plan"] = _clean_archive_plan(res) if src == "archive" else _clean_mixed_plan(res) if src == "mixed" else _clean_plan(res, st_)
    s["title"] = s["plan"]["title"]
    s.update(status="awaiting_approval", stage="review", message="Read the script and the shot plan, then approve", progress=0.08)


# ─────────────────────────── 2. art ───────────────────────────

def _art_list(plan: dict) -> list[dict]:
    out = [{"id": p["id"], "kind": "place", "prompt": long_art.plate_prompt(p["desc"]), "aspect": "16:9"} for p in plan["places"]]
    for c in plan["cast"]:
        for n, pose in enumerate(c["poses"], 1):
            out.append({"id": f"{c['id']}_{n}", "kind": "character", "prompt": long_art.char_prompt(c["desc"], pose), "aspect": "2:3",
                        "use": f"{c['id']} — {pose}"})
    out += [{"id": f"prop_{p['id']}", "kind": "prop", "prompt": long_art.object_prompt(p["desc"]), "aspect": "1:1", "use": p["desc"][:80]} for p in plan["props"]]
    return out


async def _art_archive(s: dict, tmp: str):
    """Every picture from the open archives (studio_collage: search + alternatives, a line-aware pick, cut-outs checked,
    one archival grade, credits), uploaded to R2."""
    import studio_collage
    pics = s["plan"]["pictures"]; assets = s.setdefault("assets", {})
    todo = [p for p in pics if p["id"] not in assets and p["id"] not in (s.get("art_missing") or [])]
    said = {}
    for sec in s["plan"]["sections"]:
        for sh in sec["shots"]:
            for x in sh["show"]:
                said.setdefault(x, []).append(sec["lines"][min(len(sec["lines"]) - 1, sh["line"])]["text"])
    async def pick(content):
        return await _claude(s["id"], "You pick archive pictures for a documentary. Answer exactly in the format asked.", content, 120, "art_pick")
    done = {"n": len(pics) - len(todo)}

    async def one(p):
        got = await studio_collage._one(dict(p), "", tmp, pick, " / ".join(said.get(p["id"], []))[:400])
        if got:
            url = await asyncio.to_thread(_put, s["id"], f"art/{p['id']}.webp", open(got["path"], "rb").read(), "image/webp")
            assets[p["id"]] = {"url": url, "kind": got["kind"], "use": p.get("use", ""), **({"shows": got["shows"]} if got.get("shows") else {}),
                               **({"credit": got["credit"]} if got.get("credit") else {}), **({"page": got["page"]} if got.get("page") else {})}
        else:
            s.setdefault("art_missing", []).append(p["id"])
        done["n"] += 1
        _step(s, "art", f"Finding the pictures ({done['n']}/{len(pics)})", 0.1 + 0.15 * done["n"] / len(pics))
        save(s)
    await asyncio.gather(*[one(p) for p in todo])
    if len(assets) < max(4, len(pics) // 3):
        raise RuntimeError("too few pictures were found in the archives: resume to search again")


async def _art(s: dict):
    items = _art_list(s["plan"])
    assets = s.setdefault("assets", {})
    todo = [a for a in items if a["id"] not in assets]
    if not todo:
        return
    master_url = s.get("style_master")
    master = None
    if master_url:
        async with httpx.AsyncClient(timeout=60) as c:
            master = (await c.get(master_url)).content
    else:
        first = next(a for a in items if a["kind"] == "place")
        _step(s, "art", "Drawing the style master", 0.1)
        raw = await long_art.make(first["prompt"], "16:9")
        master_url = await asyncio.to_thread(_put, s["id"], f"art/{first['id']}.png", raw, "image/png")
        s["style_master"] = master_url
        assets[first["id"]] = {"url": master_url, "kind": "place", "boards": long_art.boards(raw)}
        save(s); master = raw
        todo = [a for a in todo if a["id"] != first["id"]]
    done = {"n": len(items) - len(todo)}

    async def one(a):
        try:
            raw = await long_art.make(a["prompt"], a["aspect"], ref=master, ref_url=master_url)
            if a["kind"] == "place":
                url = await asyncio.to_thread(_put, s["id"], f"art/{a['id']}.png", raw, "image/png")
                assets[a["id"]] = {"url": url, "kind": "place", "boards": long_art.boards(raw)}
            else:
                img = await asyncio.to_thread(long_art.key, raw)
                b = io.BytesIO(); img.save(b, "PNG")
                url = await asyncio.to_thread(_put, s["id"], f"art/{a['id']}.png", b.getvalue(), "image/png")
                assets[a["id"]] = {"url": url, "kind": a["kind"], "use": a.get("use", "")}
        except Exception as e:
            print(f"[long] art {a['id']} failed: {e!r}")
            s.setdefault("art_errors", {})[a["id"]] = str(e)[:200]
        done["n"] += 1
        _step(s, "art", f"Drawing the art ({done['n']}/{len(items)})", 0.1 + 0.15 * done["n"] / len(items))
        save(s)
    await asyncio.gather(*[one(a) for a in todo])
    missing = [a["id"] for a in items if a["id"] not in assets]
    if len(missing) > len(items) // 3:
        raise RuntimeError(f"{len(missing)} pictures failed to draw ({', '.join(missing[:6])}): resume to try them again")


# ─────────────────────────── 3. parts ───────────────────────────

def _part_style(st_: dict, voice: str | None) -> dict:
    st = dict(st_)
    if voice and voice in (st.get("voices") or []):
        st["voice"] = voice
    return st


def _track_notes(sec: dict, timing: dict, assets: dict) -> str:
    norm = lambda w: re.sub(r"[^a-z0-9]", "", str(w).lower())
    rows = []
    for sh in sec["shots"]:
        i = max(0, min(len(timing["lines"]) - 1, int(sh.get("line") or 0)))
        ln = timing["lines"][i]; when = ln["start"]
        if sh.get("at"):
            hit = next((w for w in ln["words"] if norm(w["w"]) == norm(str(sh["at"]).split()[0])), None)
            if hit:
                when = hit["s"]
        show = [f'{x} ({assets[x].get("shows") or assets[x].get("use") or assets[x]["kind"]})' for x in sh["show"] if x in assets]
        rows.append(f'{when:6.2f} s (line {i}, "{sh.get("at") or "start"}"): ' + (", ".join(show) if show else "NO PICTURE FOUND: keep the previous picture dimmed, or paper, with the big words")
                    + (f' | words: {sh["words"]}' if sh.get("words") else "") + f' | ring: {sh.get("ring") or "none"}' + (f' | {sh["action"]}' if sh.get("action") else ""))
    return "THE PICTURE TRACK (binding: each picture comes on screen at its time, the moment its word is spoken):\n" + "\n".join(rows)


def _shot_notes(sec: dict, timing: dict) -> str:
    norm = lambda w: re.sub(r"[^a-z0-9]", "", str(w).lower())
    rows = []
    for sh in sec["shots"]:
        i = max(0, min(len(timing["lines"]) - 1, int(sh.get("line") or 0)))
        ln = timing["lines"][i]; when = ln["start"]
        if sh.get("at"):
            hit = next((w for w in ln["words"] if norm(w["w"]) == norm(str(sh["at"]).split()[0])), None)
            if hit:
                when = hit["s"]
        cast = ", ".join(str(x).replace(":", "_") for x in sh.get("cast") or [])
        rows.append(f'{when:6.2f} s (line {i}, "{sh.get("at") or "start"}"): place {sh.get("place")}' + (f" | cast {cast}" if cast else "")
                    + (f" | props {', '.join('prop_' + str(p) for p in sh.get('props') or [])}" if sh.get("props") else "")
                    + f" | {sh.get('action', '')}" + (f" | text: {sh['text']}" if sh.get("text") else "") + (f" | marks: {sh['marks']}" if sh.get("marks") else ""))
    return "THE SHOT PLAN (binding; times are when each shot starts):\n" + "\n".join(rows)


async def _fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url); r.raise_for_status(); return r.content


def _sheet(images: list[dict], raws: dict) -> list[str]:
    """Contact sheets for the animator: places with their measured boards numbered, cut-outs on a checkerboard."""
    from PIL import Image, ImageDraw, ImageFont
    out, cols, cw, ch = [], 3, 420, 260
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for k in range(0, len(images), 9):
        group = images[k:k + 9]; rows = (len(group) + cols - 1) // cols
        S = Image.new("RGB", (cols * cw, rows * (ch + 26)), (40, 40, 40)); d = ImageDraw.Draw(S)
        for i, im in enumerate(group):
            x, y = (i % cols) * cw, (i // cols) * (ch + 26)
            pic = Image.open(io.BytesIO(raws[im["id"]])).convert("RGBA")
            if im["kind"] == "place":
                pic = pic.resize((1920, 1080)); dd = ImageDraw.Draw(pic)
                for n, b in enumerate(im.get("boards") or []):
                    dd.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], outline=(255, 40, 40), width=8)
                    dd.text((b["x"] + 10, b["y"] + 6), f"board {n}", fill=(255, 40, 40), font=ImageFont.load_default())
            pic.thumbnail((cw - 10, ch - 10))
            bg = Image.new("RGBA", pic.size, (200, 200, 200, 255)); cb = ImageDraw.Draw(bg)
            for yy in range(0, pic.height, 14):
                for xx in range(0, pic.width, 14):
                    if (xx // 14 + yy // 14) % 2:
                        cb.rectangle([xx, yy, xx + 13, yy + 13], fill=(165, 165, 165, 255))
            bg.alpha_composite(pic); S.paste(bg.convert("RGB"), (x + (cw - pic.width) // 2, y + 5))
            d.text((x + 6, y + ch + 4), f"{im['id']} ({im['kind']})"[:44], fill=(240, 240, 240), font=font)
        b = io.BytesIO(); S.save(b, "JPEG", quality=80); out.append(base64.b64encode(b.getvalue()).decode())
    return out


async def _part(s: dict, st_: dict, k: int, tmp: str):
    import studio_pipeline as SP
    import survival_voice
    sec = s["plan"]["sections"][k]
    part = s["parts"][k]
    n = len(s["plan"]["sections"])
    base = 0.25 + 0.7 * k / n
    span = 0.7 / n
    st = _part_style(st_, s.get("voice"))
    d = os.path.join(tmp, f"part{k}"); os.makedirs(d, exist_ok=True)

    # voice
    if not part.get("voice_url"):
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: recording the narrator", base + span * .05)
        lines = SP._clean_lines(sec["lines"], st)
        wav = os.path.join(d, "voice.wav")
        async with SP._voice_sem:
            timing = await survival_voice.narrate(lines, wav, speed=st.get("speed", 1.1))
        timing["end"] = round(timing["voice_end"] + st.get("tail", 0.6), 3)
        part["voice_url"] = await asyncio.to_thread(_put, s["id"], f"part{k + 1}/voice.wav", open(wav, "rb").read(), "audio/wav")
        part["timing"] = timing; part["duration"] = timing["end"]
        save(s)
    timing = dict(part["timing"])
    wav = os.path.join(d, "voice.wav")
    if not os.path.exists(wav):
        open(wav, "wb").write(await _fetch(part["voice_url"]))

    # the pictures this part uses
    if st.get("art_source") == "mixed":
        return await _part_mixed(s, st, k, sec, part, timing, wav, d, base, span, n)

    used = set()
    for sh in sec["shots"]:
        used |= set(sh.get("show") or [])
        if sh.get("place") and sh["place"] != "headline":
            used.add(long_art.slug(sh["place"]))
        used |= {long_art.slug(str(c).replace(":", "_")) for c in sh.get("cast") or []}
        used |= {"prop_" + long_art.slug(p) for p in sh.get("props") or []}
    assets = {k2: v for k2, v in s["assets"].items() if k2 in used} or s["assets"]
    raws = dict(zip(assets, await asyncio.gather(*[_fetch(a["url"]) for a in assets.values()])))
    ext = lambda a: "webp" if a["url"].endswith(".webp") else "png"
    timing["images"] = [{"id": i, "file": f"img/{i}.{ext(a)}", "w": 0, "h": 0, "kind": a["kind"], **({"boards": a["boards"]} if a.get("boards") else {}),
                         **({k2: a[k2] for k2 in ("use", "shows", "credit") if a.get(k2)})} for i, a in assets.items()]
    for im, raw in zip(timing["images"], raws.values()):
        from PIL import Image
        im["w"], im["h"] = Image.open(io.BytesIO(raw)).size
    bins = {im["file"]: base64.b64encode(raws[im["id"]]).decode() for im in timing["images"]}
    notes = _track_notes(sec, timing, assets) if st.get("art_source") == "archive" else _shot_notes(sec, timing)
    script = {"title": f'{s["plan"]["title"]} — part {k + 1}: {sec["title"]}', "visual_notes": notes, "lines": sec["lines"]}

    # film
    if not part.get("code"):
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: animating", base + span * .2)
        sheets = await asyncio.to_thread(_sheet, timing["images"], raws)
        code, spec, foley = await SP._film(s["id"], st, script, timing, None, bins, sheets)
        try:
            _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: checking the frames", base + span * .45)
            code2, extra = await SP._review(s["id"], st, script, timing, code, None, bins)
            if extra is not None:
                code, (spec, foley) = code2, extra
        except BillingError:
            raise
        except Exception as e:
            print(f"[long] review skipped: {e!r}")
        part.update(code=code, spec=spec, foley=foley)
        save(s)

    # render + sound
    if not part.get("video_url"):
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: rendering", base + span * .55)
        video = await SP._render(s["id"], st, part["code"], timing, d, None, bins)
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: mixing the sound", base + span * .9)
        final = await SP._sound(s["id"], st, video, wav, timing, part.get("spec") or {}, part.get("foley") or [], d)
        part["video_url"] = await asyncio.to_thread(_put, s["id"], f"part{k + 1}/part.mp4", open(final, "rb").read(), "video/mp4")
        part["status"] = "done"
        if k == 0 and not s.get("thumbnail_url"):
            th = os.path.join(d, "thumb.jpg")
            if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.0", "-i", final, "-frames:v", "1", "-q:v", "3", th]).returncode == 0:
                s["thumbnail_url"] = await asyncio.to_thread(_put, s["id"], "thumb.jpg", open(th, "rb").read(), "image/jpeg")
        save(s)


async def _final(s: dict, tmp: str):
    _step(s, "final", "Joining the parts", 0.96)
    paths = []
    for k, p in enumerate(s["parts"]):
        path = os.path.join(tmp, f"final{k}.mp4"); open(path, "wb").write(await _fetch(p["video_url"])); paths.append(path)
    lst = os.path.join(tmp, "parts.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in paths))
    out = os.path.join(tmp, "video.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("joining the parts failed: " + r.stderr[-400:])
    s["final_video_url"] = await asyncio.to_thread(_put, s["id"], "video.mp4", open(out, "rb").read(), "video/mp4")
    s["duration"] = round(sum(p.get("duration") or 0 for p in s["parts"]), 1)


# ─────────────────────────── the runner ───────────────────────────

async def run(pid: str):
    """Do whatever is not done yet (plan, or art -> parts -> final). Safe to call again after any failure."""
    lock = _locks.setdefault(pid, asyncio.Lock())
    if lock.locked():
        return
    async with lock:
        _running.add(pid)
        tmp = tempfile.mkdtemp(prefix="long-")
        s = load(pid)
        try:
            if not s:
                return
            st_ = studio_styles.style(s["template"])
            s["error"] = None
            if s["status"] == "planning":
                await _plan(st_, s); save(s); return
            if s["status"] != "producing":
                return
            if st_.get("art_source") == "archive":
                await _art_archive(s, tmp)
            elif st_.get("art_source") == "mixed":
                await _art_mixed(s, tmp)
            else:
                await _art(s)
            save(s)
            if not s.get("parts"):
                s["parts"] = [{"id": sec["id"], "title": sec["title"], "status": "waiting"} for sec in s["plan"]["sections"]]
                save(s)
            for k in range(len(s["parts"])):
                if s["parts"][k].get("video_url"):
                    continue
                s["parts"][k]["status"] = "working"; save(s)
                await _part(s, st_, k, tmp)
            await _final(s, tmp)
            s.update(status="completed", stage="done", message="Your video is ready", progress=1.0)
            save(s)
        except Exception as e:
            traceback.print_exc()
            if s:
                msg = "Anthropic API credit is too low" if isinstance(e, BillingError) else str(e)[:400]
                s.update(error=msg, message=f"Stopped: {msg}", status_before_error=s.get("status"))
                if s.get("status") == "planning":
                    s["status"] = "planning"           # resume re-plans
                save(s)
        finally:
            _running.discard(pid)
            subprocess.run(["rm", "-rf", tmp])


def create(template: str, topic: str, minutes: int, voice: str | None, notes: str | None) -> dict:
    st_ = studio_styles.style(template)
    lo, hi = st_.get("minutes", (2, 12))
    s = {"id": str(uuid.uuid4()), "template": template, "template_name": st_["name"], "created": time.time(),
         "topic": (topic or "").strip()[:300], "notes": (notes or "").strip()[:600], "minutes": max(lo, min(hi, int(minutes or 5))),
         "voice": voice if voice in (st_.get("voices") or []) else st_["voice"], "status": "planning", "stage": "plan",
         "message": "Queued", "progress": 0.0, "title": None, "plan": None, "assets": {}, "parts": [], "error": None}
    save(s)
    return s


def update_plan(s: dict, edits: dict) -> dict:
    """Edits before approval: the title, and the lines' text per part (same number of lines keeps the shot plan)."""
    if s["status"] != "awaiting_approval":
        raise ValueError("the plan can only be edited before you approve it")
    if edits.get("title"):
        s["plan"]["title"] = s["title"] = str(edits["title"])[:100]
    for se in edits.get("sections") or []:
        sec = next((x for x in s["plan"]["sections"] if x["id"] == se.get("id")), None)
        if not sec:
            continue
        for i, txt in enumerate(se.get("lines") or []):
            if i < len(sec["lines"]) and str(txt).strip():
                sec["lines"][i]["text"] = str(txt).strip()[:300]
                sec["lines"][i].pop("say", None)
    save(s)
    return s



# ─────────────────────────── documentary analysis: layer A (generated) + layer B (archive footage) ───────────────────────────

LOCK = ("Cinematic editorial illustration for a documentary analysis video, muted desaturated palette (graphite, slate blue, "
        "warm grey) with one warm accent (signal yellow), soft directional light from the upper left, subtle film grain, clean "
        "composition with negative space on one side for on-screen text, 16:9. ")
NEG = (" No text, no letters, no numbers, no logos, no watermark, no UI, no frames or borders, no collage, no photorealistic "
       "news-photo look, no identifiable real person's face (people as silhouettes or from behind).")

MIXED_PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the video plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "the YouTube title (under 70 characters)"},
            "description": {"type": "string", "description": "a 2-3 sentence YouTube description"},
            "sections": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string", "description": "the chapter title"},
                "lines": _LINES,
                "shots": {"type": "array", "description": "a new picture every 3-6 s, in order", "items": {"type": "object", "properties": {
                    "line": {"type": "integer"}, "at": {"type": "string", "description": "the word the shot starts on"},
                    "layer": {"type": "string", "enum": ["A", "B"]},
                    "prompt": {"type": "string", "description": "layer A: the illustration's subject and composition (the style lock is added)"},
                    "search": {"type": "string", "description": "layer B: 2-5 words an archive would title it with"},
                    "alts": {"type": "array", "items": {"type": "string"}},
                    "kind": {"type": "string", "enum": ["video", "image"], "description": "layer B: video when motion matters"},
                    "lower": {"type": "object", "properties": {"title": {"type": "string"}, "sub": {"type": "string"}}, "description": "layer B: place / date for the lower third"},
                    "overlay": {"type": "string", "description": "the typography and marks over this shot (title card / counter / quote / compare / timeline / ring / map pins), with their words"}},
                    "required": ["line", "layer"]}}},
                "required": ["title", "lines", "shots"]}},
        },
        "required": ["title", "sections"],
    },
}


def _clean_mixed_plan(res: dict) -> dict:
    sections = []
    for k, sec in enumerate(res.get("sections") or []):
        lines = [{"text": str(l.get("text") or "").strip()[:320], **({"say": str(l["say"])[:320]} if l.get("say") else {}),
                  "pause": float(l.get("pause") or .3), "mood": l.get("mood") or "neutral"} for l in sec.get("lines") or [] if str(l.get("text") or "").strip()]
        if not lines:
            continue
        sid = f"p{k + 1}"; shots = []
        for j, sh in enumerate(sec.get("shots") or []):
            layer = "B" if sh.get("layer") == "B" and str(sh.get("search") or "").strip() else "A"
            prompt = str(sh.get("prompt") or sh.get("search") or "").strip()[:600]
            if not prompt:
                continue
            shots.append({"id": f"{sid}_s{j + 1}", "line": max(0, min(len(lines) - 1, int(sh.get("line") or 0))), "at": str(sh.get("at") or "")[:40],
                          "layer": layer, "prompt": prompt, "search": str(sh.get("search") or "")[:160], "alts": [str(a)[:160] for a in (sh.get("alts") or [])][:2],
                          "kind": sh.get("kind") if sh.get("kind") in ("video", "image") else "image",
                          "lower": {kk: str(v)[:80] for kk, v in (sh.get("lower") or {}).items() if kk in ("title", "sub") and v} or None,
                          "overlay": str(sh.get("overlay") or "")[:300], "place": f"{sid}_s{j + 1}", "action": str(sh.get("overlay") or "")[:200]})
        if not shots:
            shots = [{"id": f"{sid}_s1", "line": 0, "at": "", "layer": "A", "prompt": sec.get("title") or "an abstract establishing image",
                      "search": "", "alts": [], "kind": "image", "lower": None, "overlay": "", "place": f"{sid}_s1", "action": ""}]
        sections.append({"id": sid, "title": str(sec.get("title") or f"Chapter {k + 1}")[:80], "lines": lines, "shots": shots[:90]})
    if not sections:
        raise ValueError("the plan came back empty")
    return {"title": str(res.get("title") or "Untitled")[:100], "description": str(res.get("description") or "")[:600],
            "places": [], "cast": [], "props": [], "sections": sections}


async def _pick_footage(s: dict, sh: dict, said: str, cands: list) -> dict | None:
    import studio_media
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        thumbs = await asyncio.gather(*[studio_media.thumb(c, x) for x in cands])
    pairs = [(x, th) for x, th in zip(cands, thumbs) if th]
    if not pairs:
        return None
    from PIL import Image
    content = [{"type": "text", "text": f"A documentary needs real archive {sh['kind']} of: {sh['search']}.\nWhile it is on screen the narrator says: {said}\n"
                                        "Pick the candidate that CLEARLY shows exactly that, so the viewer sees what is said; no watermark, no "
                                        "big text, no collage. If none does, answer -1.\nAnswer on one line: the number | what it actually shows (under 15 words)."}]
    for i, (x, th) in enumerate(pairs):
        im = Image.open(io.BytesIO(th)).convert("RGB"); im.thumbnail((320, 320)); b = io.BytesIO(); im.save(b, "JPEG", quality=78)
        content += [{"type": "text", "text": f"{i}: {x.get('title', '')[:80]}"}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}]
    try:
        ans = await _claude(s["id"], "You pick archive footage for a documentary. Answer exactly in the format asked.", content, 120, "footage_pick")
        m = re.search(r"-?\d+", ans); i = int(m.group()) if m else -1
        if 0 <= i < len(pairs):
            return {**pairs[i][0], "shows": ans.split("|", 1)[1].strip()[:120] if "|" in ans else pairs[i][0].get("title", "")[:120]}
    except BillingError:
        raise
    except Exception as e:
        print(f"[long] footage pick failed: {e!r}")
    return None


async def _footage(s: dict, sh: dict, said: str, tmp: str) -> dict | None:
    """Layer B: the search and its alternatives in open archives; the picked clip trimmed to 10 s (or the photo), graded later in the plate."""
    import studio_media
    for q in [sh["search"], *sh.get("alts", [])]:
        cands = []
        for kind in ([sh["kind"], "image"] if sh["kind"] == "video" else ["image"]):
            try:
                cands = [c for c in await studio_media.search(q, kind=kind, n=6) if (c.get("w") or 1000) >= 480]
            except Exception as e:
                print(f"[long] archive search failed: {e!r}")
            if cands:
                break
        if not cands:
            continue
        got = await _pick_footage(s, sh, said, cands)
        if not got:
            continue
        kind = got.get("kind") or "image"
        try:
            if kind == "video":
                raw = os.path.join(tmp, f"{sh['id']}_src"); await studio_media.fetch(got["url"], raw)
                out = os.path.join(tmp, f"{sh['id']}.mp4")
                dur = studio_media.probe(raw).get("duration") or 10
                start = max(0.0, min(dur * .15, dur - 10))
                r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", raw, "-t", "10", "-an", "-vf", "scale=1280:-2",
                                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", out], capture_output=True, text=True)
                if r.returncode != 0:
                    continue
                url = await asyncio.to_thread(_put, s["id"], f"art/{sh['id']}.mp4", open(out, "rb").read(), "video/mp4")
            else:
                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
                    r = await studio_media._get(c, got.get("thumb", "").replace("/500px-", "/1280px-") if got.get("source") == "commons" and (got.get("w") or 0) > 1280 else got["url"])
                    if r.status_code != 200:
                        r = await studio_media._get(c, got["url"])
                    r.raise_for_status()
                from PIL import Image, ImageOps
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(r.content))).convert("RGB"); im.thumbnail((2200, 2200)); b = io.BytesIO(); im.save(b, "JPEG", quality=88)
                url = await asyncio.to_thread(_put, s["id"], f"art/{sh['id']}.jpg", b.getvalue(), "image/jpeg")
            return {"url": url, "kind": kind, "layer": "B", "shows": got.get("shows", ""), "credit": got.get("credit"), "page": got.get("page")}
        except Exception as e:
            print(f"[long] footage {sh['id']} failed: {e!r}")
    return None


async def _art_mixed(s: dict, tmp: str):
    """Every shot's picture: layer B from the open archives (falls back to a layer-A illustration of the same subject,
    never a wrong real picture), layer A generated with the style lock."""
    assets = s.setdefault("assets", {})
    shots = [(sec, sh) for sec in s["plan"]["sections"] for sh in sec["shots"]]
    todo = [(sec, sh) for sec, sh in shots if sh["id"] not in assets]
    done = {"n": len(shots) - len(todo)}
    sem = asyncio.Semaphore(4)

    async def one(sec, sh):
        async with sem:
            said = sec["lines"][sh["line"]]["text"]
            got = None
            if sh["layer"] == "B":
                got = await _footage(s, sh, said, tmp)
            if not got:
                try:
                    prompt = LOCK + (sh["prompt"] if sh["layer"] == "A" else f"An illustration of {sh['prompt']}") + "." + NEG
                    raw = await long_art.make(prompt, "16:9")
                    url = await asyncio.to_thread(_put, s["id"], f"art/{sh['id']}.png", raw, "image/png")
                    got = {"url": url, "kind": "image", "layer": "A", "shows": sh["prompt"][:120]}
                except Exception as e:
                    print(f"[long] art {sh['id']} failed: {e!r}")
                    s.setdefault("art_errors", {})[sh["id"]] = str(e)[:200]
            if got:
                assets[sh["id"]] = got
            done["n"] += 1
            _step(s, "art", f"Finding the footage and drawing the scenes ({done['n']}/{len(shots)})", 0.1 + 0.15 * done["n"] / len(shots))
            save(s)
    await asyncio.gather(*[one(sec, sh) for sec, sh in todo])
    if len(assets) < len(shots) * .6:
        raise RuntimeError("too many shots have no picture yet: resume to try them again")


def _shot_times(sec: dict, timing: dict) -> list[tuple[float, float]]:
    norm = lambda w: re.sub(r"[^a-z0-9]", "", str(w).lower())
    starts = []
    for sh in sec["shots"]:
        ln = timing["lines"][max(0, min(len(timing["lines"]) - 1, sh["line"]))]; t = ln["start"]
        if sh.get("at"):
            hit = next((w for w in ln["words"] if norm(w["w"]) == norm(str(sh["at"]).split()[0])), None)
            if hit:
                t = hit["s"]
        starts.append(t)
    fixed, last = [], 0.0
    for i, t in enumerate(starts):        # in order, at least 1.2 s each, the first from 0
        t = 0.0 if i == 0 else max(t, last + 1.2)
        fixed.append(t); last = t
    return [(a, fixed[i + 1] if i + 1 < len(fixed) else timing["end"]) for i, a in enumerate(fixed)]


async def _part_mixed(s, st, k, sec, part, timing, wav, d, base, span, n):
    import studio_pipeline as SP
    import studio_plate
    times = _shot_times(sec, timing)
    shots, plate_shots = [], []
    for sh, (t0, t1) in zip(sec["shots"], times):
        a = s["assets"].get(sh["id"])
        if t1 - t0 < .05:
            continue
        if a:
            ext = a["url"].rsplit(".", 1)[-1]
            path = os.path.join(d, f"{sh['id']}.{ext}")
            if not os.path.exists(path):
                open(path, "wb").write(await _fetch(a["url"]))
            plate_shots.append({"t0": t0, "t1": t1, "kind": a["kind"], "path": path, "src": 0.0, "fit": "full"})
        shots.append({"t0": round(t0, 3), "t1": round(t1, 3), "layer": (a or {}).get("layer", "A"), "kind": (a or {}).get("kind"),
                      "shows": (a or {}).get("shows", ""), "credit": (a or {}).get("credit"), "lower": sh.get("lower"), "overlay": sh.get("overlay", "")})
    timing["shots"] = shots
    plate = os.path.join(d, "plate.mp4")
    if not os.path.exists(plate):
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: cutting the footage", base + span * .12)
        await asyncio.to_thread(studio_plate.build, plate_shots, timing["end"], plate, d, (1920, 1080))
    rows = "\n".join(f'{x["t0"]:6.2f}-{x["t1"]:6.2f} s · layer {x["layer"]} {x["kind"] or "-"} · {x["shows"]}' + (f' · lower: {x["lower"]}' if x.get("lower") else "")
                     + (f' · credit: {x["credit"]}' if x.get("credit") else "") + (f' · OVERLAY: {x["overlay"]}' if x.get("overlay") else "") for x in shots)
    script = {"title": f'{s["plan"]["title"]} — part {k + 1}: {sec["title"]}', "lines": sec["lines"],
              "visual_notes": "THE SHOTS (already playing in the plate under your canvas; binding): add each shot's overlay over it, on its words.\n" + rows}

    if not part.get("code"):
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: animating", base + span * .2)
        sheet = os.path.join(d, "sheet.jpg")
        mids = [round((x["t0"] + x["t1"]) / 2, 2) for x in shots][:24]
        sel = "+".join(f"between(t\\,{m - .02:.2f}\\,{m + .02:.2f})" for m in mids)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", plate, "-vf", f"select='{sel}',scale=480:270,tile=4x{max(1, (len(mids) + 3) // 4)}",
                        "-frames:v", "1", "-vsync", "vfr", sheet], capture_output=True)
        sheets = [base64.b64encode(open(sheet, "rb").read()).decode()] if os.path.exists(sheet) else None
        code, spec, foley = await SP._film(s["id"], st, script, timing, None, None, sheets)
        try:
            _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: checking the frames", base + span * .45)
            proxy = await asyncio.to_thread(studio_plate.proxy, plate, os.path.join(d, "proxy.mp4"), (960, 540))
            code2, extra = await SP._review(s["id"], st, script, timing, code, proxy, None)
            if extra is not None:
                code, (spec, foley) = code2, extra
        except BillingError:
            raise
        except Exception as e:
            print(f"[long] review skipped: {e!r}")
        part.update(code=code, spec=spec, foley=foley)
        save(s)

    if not part.get("video_url"):
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: rendering", base + span * .55)
        video = await SP._render(s["id"], st, part["code"], timing, d, plate, None)
        _step(s, f"part{k + 1}", f"Part {k + 1}/{n}: mixing the sound", base + span * .9)
        final = await SP._sound(s["id"], st, video, wav, timing, part.get("spec") or {}, part.get("foley") or [], d)
        part["video_url"] = await asyncio.to_thread(_put, s["id"], f"part{k + 1}/part.mp4", open(final, "rb").read(), "video/mp4")
        part["status"] = "done"
        if k == 0 and not s.get("thumbnail_url"):
            th = os.path.join(d, "thumb.jpg")
            if subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.0", "-i", final, "-frames:v", "1", "-q:v", "3", th]).returncode == 0:
                s["thumbnail_url"] = await asyncio.to_thread(_put, s["id"], "thumb.jpg", open(th, "rb").read(), "image/jpeg")
        save(s)
